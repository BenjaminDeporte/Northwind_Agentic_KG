"""Tool node tests: one requested call yields one trace record and tool message."""
import json
from langchain_core.messages import AIMessage, ToolMessage

from src.agents.nodes import execute_tool_step


def _state(name, args):
    request = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call-1"}])
    return {"question": "test", "messages": [request], "trace": [], "loop_count": 2}


def test_curated_tool_executes_once_and_records_result():
    calls = []
    def tool(**kwargs):
        calls.append(kwargs)
        return {
            "status": "ok", "error": None,
            "product": {"label": "Product", "key": "1", "name": "Chai"},
            "recommendations": [{"product": {"label": "Product", "key": "2", "name": "Chang"},
                "co_bought": 2, "evidence": {"nodes": [
                    {"label": "Product", "key": "1", "name": "Chai", "properties": {}},
                    {"label": "Product", "key": "2", "name": "Chang", "properties": {}},
                ], "edges": []}}],
        }
    update = execute_tool_step(_state("co_purchase", {"product_key": "1"}), {"co_purchase": tool})
    assert calls == [{"product_key": "1"}]
    assert len(update["trace"]) == 1
    record = update["trace"][0]
    assert record["step"] == 2
    assert record["tool_name"] == "co_purchase"
    assert record["mode"] == "curated"
    assert record["result_rows"] == 1
    assert record["retry_count"] == 0
    assert isinstance(update["messages"][0], ToolMessage)
    assert json.loads(update["messages"][0].content)["status"] == "ok"


def test_exploratory_retry_count_and_query_are_recorded():
    tool = lambda **kwargs: {
        "status": "retry_ok", "error": None, "query": kwargs["query"],
        "rows": [{"values": {"x": 1}, "evidence": {"nodes": [], "edges": []}}],
        "attempts": [{"cypher": "MATCH (n) RETURN n", "valid": False, "error": "first failed"},
                    {"cypher": "MATCH (n) RETURN n", "valid": True, "error": None}],
    }
    update = execute_tool_step(_state("run_readonly_cypher", {"query": "MATCH (n) RETURN n"}), {"run_readonly_cypher": tool})
    record = update["trace"][0]
    assert record["mode"] == "exploratory"
    assert record["retry_count"] == 1
    assert record["cypher"] == "MATCH (n) RETURN n"
    assert record["result_rows"] == 1


def test_missing_tool_is_visible_as_invalid_call():
    update = execute_tool_step(_state("lookup_entity", {"name": "Chai"}), {})
    assert update["trace"][0]["status"] == "invalid"
    assert len(update["messages"]) == 1


def test_tool_exception_is_visible_as_invalid_call():
    def broken(**kwargs):
        raise RuntimeError("database unavailable")
    update = execute_tool_step(_state("lookup_entity", {"name": "Chai"}), {"lookup_entity": broken})
    assert update["trace"][0]["status"] == "invalid"
    assert "database unavailable" in update["messages"][0].content


def test_malformed_tool_result_is_rejected_before_tool_message():
    update = execute_tool_step(
        _state("co_purchase", {"product_key": "1"}),
        {"co_purchase": lambda **kwargs: {"status": "ok", "recommendations": []}},
    )
    record = update["trace"][0]
    payload = json.loads(update["messages"][0].content)
    assert record["status"] == payload["status"] == "invalid"
    assert record["result_rows"] == 0
    assert "Malformed co_purchase result" in payload["error"]
    assert payload["product"] is None and payload["recommendations"] == []

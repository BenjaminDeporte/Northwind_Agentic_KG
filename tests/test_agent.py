"""Agent node tests: decisions are separate from tool execution."""
from unittest.mock import patch

from langchain_core.messages import AIMessage
from src.agents.nodes import agent_step
from src.agents.state import MAX_STEPS


def _state(count=0):
    return {"question": "Find Chai", "loop_count": count, "messages": [], "trace": []}


def test_agent_emits_one_tool_request_without_executing_it():
    called = []
    tools = {"lookup_entity": lambda **kwargs: called.append(kwargs)}
    with patch("src.agents.llm.generate_agent_response", return_value='TOOL: lookup_entity({"name":"Chai","label":"Product"})'):
        update = agent_step(_state(), tools)
    assert update["loop_count"] == 1
    assert len(update["messages"]) == 1
    message = update["messages"][0]
    assert isinstance(message, AIMessage)
    assert message.tool_calls[0]["name"] == "lookup_entity"
    assert message.tool_calls[0]["args"] == {"name": "Chai", "label": "Product"}
    assert called == []
    assert "trace" not in update


def test_agent_emits_final_message_without_tool_call():
    with patch("src.agents.llm.generate_agent_response", return_value="FINAL: I have enough evidence"):
        update = agent_step(_state(), {})
    assert update["messages"][0].content.startswith("FINAL:")
    assert update["messages"][0].tool_calls == []


def test_agent_does_not_call_model_after_budget():
    with patch("src.agents.llm.generate_agent_response") as model:
        update = agent_step(_state(MAX_STEPS), {})
    model.assert_not_called()
    assert update == {"loop_count": MAX_STEPS}


def test_agent_stops_after_citable_exploratory_result():
    import json
    from langchain_core.messages import ToolMessage
    state = _state(1)
    state["messages"] = [ToolMessage(
        content=json.dumps({"status": "ok", "rows": [{
            "values": {"productID": "1", "productName": "Chai", "revenue": 10.0},
            "evidence": {"nodes": [{"label": "Product", "key": "1", "name": "Chai", "properties": {}}], "edges": []},
        }]}),
        name="run_readonly_cypher", tool_call_id="call-1",
    )]
    with patch("src.agents.llm.generate_agent_response") as model:
        update = agent_step(state, {"run_readonly_cypher": lambda **kwargs: None})
    model.assert_not_called()
    assert update["loop_count"] == 1
    assert update["messages"][0].content.startswith("FINAL:")


def test_agent_stops_after_exploratory_count_with_evidence_nodes():
    import json
    from langchain_core.messages import ToolMessage
    state = _state(2)
    state["messages"] = [ToolMessage(
        content=json.dumps({"status": "ok", "rows": [{
            "values": {
                "order_count": 2,
                "anchor": {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste"},
            },
            "evidence": {"nodes": [
                {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "properties": {}},
                {"label": "Order", "key": "1", "name": "1", "properties": {}},
                {"label": "Order", "key": "2", "name": "2", "properties": {}},
            ], "edges": []},
        }]}),
        name="run_readonly_cypher", tool_call_id="call-count",
    )]
    with patch("src.agents.llm.generate_agent_response") as model:
        update = agent_step(state, {"run_readonly_cypher": lambda **kwargs: None})
    model.assert_not_called()
    assert update["loop_count"] == 2
    assert update["messages"][0].content.startswith("FINAL:")


def test_agent_stops_after_exploratory_query_failure():
    import json
    from langchain_core.messages import ToolMessage
    state = _state(2)
    state["messages"] = [ToolMessage(
        content=json.dumps({"status": "invalid", "error": "semicolon rejected", "rows": [], "attempts": []}),
        name="run_readonly_cypher", tool_call_id="call-invalid",
    )]
    with patch("src.agents.llm.generate_agent_response") as model:
        update = agent_step(state, {"run_readonly_cypher": lambda **kwargs: None})
    model.assert_not_called()
    assert update["messages"][0].content.startswith("FINAL:")

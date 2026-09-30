"""Agent node tests: decisions are separate from tool execution."""
from unittest.mock import patch

import pytest

from langchain_core.messages import AIMessage
from src.agents.nodes import agent_step
from src.agents.state import MAX_STEPS


def _state(count=0):
    return {"question": "Find Chai", "loop_count": count, "messages": [], "trace": []}


def test_agent_emits_one_tool_request_without_executing_it():
    called = []
    tools = {"lookup_entity": lambda **kwargs: called.append(kwargs)}
    with patch("src.agents.llm.generate_agent_response", return_value='TOOL: lookup_entity({"name":"Chai","label":"Product"})'):
        update = agent_step(_state())
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
        update = agent_step(_state())
    assert update["messages"][0].content.startswith("FINAL:")
    assert update["messages"][0].tool_calls == []


def test_agent_does_not_call_model_after_budget():
    with patch("src.agents.llm.generate_agent_response") as model:
        update = agent_step(_state(MAX_STEPS))
    model.assert_not_called()
    assert update == {"loop_count": MAX_STEPS}


@pytest.mark.parametrize("tool_name,payload", [
    ("lookup_entity", {
        "status": "ok", "error": None, "query_name": "Chai", "matches": [{
            "node": {"label": "Product", "key": "1", "name": "Chai", "properties": {}},
            "match": "exact",
            "evidence": {"nodes": [{"label": "Product", "key": "1", "name": "Chai", "properties": {}}], "edges": []},
        }],
    }),
    ("impact_analysis", {
        "status": "ok", "error": None,
        "anchor": {"label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": {}},
        "aggregates": {},
        "evidence": {"nodes": [{"label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": {}}], "edges": []},
        "subgraph": {"nodes": [], "edges": []},
    }),
    ("co_purchase", {
        "status": "ok", "error": None,
        "recommendations": [{
            "product": {"label": "Product", "key": "2", "name": "Chang", "properties": {}},
            "evidence": {"nodes": [
                {"label": "Product", "key": "1", "name": "Chai", "properties": {}},
                {"label": "Product", "key": "2", "name": "Chang", "properties": {}},
            ], "edges": []},
        }],
    }),
    ("customer_history", {
        "status": "ok", "error": None,
        "customer": {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "properties": {}},
        "orders": [{
            "order": {"label": "Order", "key": "1", "name": "1", "properties": {}},
            "evidence": {"nodes": [
                {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "properties": {}},
                {"label": "Order", "key": "1", "name": "1", "properties": {}},
            ], "edges": [{"type": "PURCHASED"}]},
        }],
    }),
    ("aggregate", {
        "status": "ok", "error": None, "n_groups": 1,
        "groups": [{"group_value": "UK", "metric_value": 1, "evidence": {
            "nodes": [{"label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": {}}], "edges": [],
        }}],
    }),
    ("run_readonly_cypher", {
        "status": "ok", "error": None, "query": "MATCH (p:Product) RETURN p", "attempts": [],
        "rows": [{"values": {"product": "Chai"}, "evidence": {
            "nodes": [{"label": "Product", "key": "1", "name": "Chai", "properties": {}}], "edges": [],
        }}],
    }),
    ("run_readonly_cypher", {
        "status": "retry_ok", "error": None, "query": "MATCH (p:Product) RETURN p", "attempts": [{"status": "retry_ok"}],
        "rows": [{"values": {"product": "Chai"}, "evidence": {
            "nodes": [{"label": "Product", "key": "1", "name": "Chai", "properties": {}}], "edges": [],
        }}],
    }),
])
def test_successful_tool_result_returns_control_to_agent(tool_name, payload):
    import json
    from langchain_core.messages import ToolMessage

    state = _state(2)
    state["messages"] = [ToolMessage(
        content=json.dumps(payload), name=tool_name, tool_call_id="successful-call",
    )]
    next_decision = 'TOOL: lookup_entity({"name":"Chai","label":"Product"})'
    with patch("src.agents.llm.generate_agent_response", return_value=next_decision) as model:
        update = agent_step(state)

    model.assert_called_once()
    assert update["loop_count"] == 3
    assert update["messages"][0].tool_calls[0]["name"] == "lookup_entity"


def test_curated_empty_result_returns_control_to_agent():
    import json
    from langchain_core.messages import ToolMessage

    state = _state(1)
    state["messages"] = [ToolMessage(
        content=json.dumps({"status": "empty", "error": None, "groups": [], "n_groups": 0}),
        name="aggregate", tool_call_id="empty-aggregate",
    )]
    with patch("src.agents.llm.generate_agent_response", return_value="FINAL: No groups found.") as model:
        update = agent_step(state)
    model.assert_called_once()
    assert update["loop_count"] == 2
    assert update["messages"][0].content == "FINAL: No groups found."


@pytest.mark.parametrize("status,error", [
    ("empty", None), ("invalid", "semicolon rejected"), ("retry_failed", "query failed"),
])
def test_agent_stops_after_terminal_exploratory_outcome(status, error):
    import json
    from langchain_core.messages import ToolMessage
    state = _state(2)
    state["messages"] = [ToolMessage(
        content=json.dumps({"status": status, "error": error, "rows": [], "attempts": []}),
        name="run_readonly_cypher", tool_call_id=f"call-{status}",
    )]
    with patch("src.agents.llm.generate_agent_response") as model:
        update = agent_step(state)
    model.assert_not_called()
    assert update["messages"][0].content.startswith("FINAL:")


def test_agent_refuses_to_finalize_after_scalar_only_exploratory_result():
    import json
    from langchain_core.messages import ToolMessage

    state = _state(1)
    state["messages"] = [ToolMessage(
        content=json.dumps({
            "status": "ok",
            "rows": [{"values": {"productID": "1", "productName": "Chai", "totalQuantity": 120},
                      "evidence": {"nodes": [], "edges": []}}],
        }),
        name="run_readonly_cypher", tool_call_id="scalar-only",
    )]
    with patch("src.agents.llm.generate_agent_response", return_value="FINAL: Chai was most ordered."):
        update = agent_step(state)
    assert update["loop_count"] == 2
    assert "one recovery tool call" in update["messages"][0].content
    assert not update["messages"][0].content.startswith("FINAL:")


def test_agent_returns_control_after_exactly_one_inadequate_evidence_recovery():
    import json
    from langchain_core.messages import ToolMessage

    node = {"label": "Product", "key": "1", "name": "Chai", "properties": {}}
    inadequate = ToolMessage(
        content=json.dumps({"status": "ok", "rows": [{"values": {"totalQuantity": 120}, "evidence": {"nodes": [], "edges": []}}]}),
        name="run_readonly_cypher", tool_call_id="first",
    )
    recovery = ToolMessage(
        content=json.dumps({"status": "ok", "rows": [{"values": {"totalQuantity": 120}, "evidence": {"nodes": [node], "edges": []}}]}),
        name="run_readonly_cypher", tool_call_id="recovery",
    )
    state = _state(3)
    state["messages"] = [inadequate, recovery]
    with patch("src.agents.llm.generate_agent_response", return_value="FINAL: I can answer the supported parts.") as model:
        update = agent_step(state)
    model.assert_called_once()
    assert "one evidence-recovery call" in model.call_args.kwargs["messages"][-1].content
    assert update["messages"][0].content.startswith("FINAL:")

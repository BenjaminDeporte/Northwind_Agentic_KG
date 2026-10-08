import json

from langchain_core.messages import AIMessage, ToolMessage

from scripts.run_smoke_test import initial_state, summarize_state


def test_initial_state_matches_generic_contract():
    state = initial_state("How many customers?")
    assert state["question"] == "How many customers?"
    assert state["messages"] == []
    assert state["loop_count"] == 0


def test_summarize_state_exposes_cypher_validation_and_neo4j_outputs():
    state = initial_state("How many customers?")
    state["route"] = "agent"
    state["loop_count"] = 1
    state["answer"] = "There are 91 customers."
    state["result"] = {"value": 91}
    state["messages"] = [
        AIMessage(content="MATCH (c:Customer) RETURN count(c)", name="text2cypher"),
        ToolMessage(
            content=json.dumps({"status": "valid", "attempt": 1, "query": "MATCH (c:Customer) RETURN count(c)"}),
            name="validate_cypher",
            tool_call_id="validate-cypher-1",
        ),
        ToolMessage(
            content=json.dumps({"status": "ok", "rows": [{"values": {"count": 91}}]}),
            name="neo4j",
            tool_call_id="neo4j-readonly",
        ),
    ]
    summary = summarize_state(state)
    assert summary["generated_cypher"] == ["MATCH (c:Customer) RETURN count(c)"]
    assert summary["validation_attempts"][0]["status"] == "valid"
    assert summary["neo4j_results"][0]["status"] == "ok"
    json.dumps(summary)

"""Behavioral tests for the contracted graph and read-only boundary."""
from unittest.mock import patch
import json

from langchain_core.messages import AIMessage, ToolMessage
from src.agents.graph import compile_graph
from src.agents.nodes import execute_tool_step, _parse_llm_tool_call
from src.neo4j.client import Neo4jClient
from src.neo4j.tools import aggregate, run_readonly_cypher


def _initial(question):
    return {
        "question": question, "route": "", "messages": [], "trace": [], "answer": "",
        "citations": [], "confidence": 0.0, "confidence_rationale": "",
        "loop_count": 0, "error": None,
    }


def test_compiled_graph_executes_one_tool_and_cites_returned_node():
    graph = compile_graph({"lookup_entity": lambda **kwargs: {
        "status": "ok", "query_name": kwargs["name"],
        "matches": [{"label": "Product", "key": "1", "name": "Chai", "match": "exact", "properties": {}}],
    }})
    assert {"classify", "agent", "tools", "synthesize", "degrade"} <= set(graph.nodes)
    assert type(graph.channels["messages"]).__name__ == "BinaryOperatorAggregate"
    responses = iter(['TOOL: lookup_entity({"name":"Chai","label":"Product"})', "FINAL: enough evidence"])
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response", lambda **kwargs: next(responses)
    ), patch("src.agents.llm.synthesize_from_evidence", lambda draft: draft):
        # Graph captures classify on construction, so rebuild under the patch.
        graph = compile_graph({"lookup_entity": lambda **kwargs: {
            "status": "ok", "query_name": kwargs["name"],
            "matches": [{"label": "Product", "key": "1", "name": "Chai", "match": "exact", "properties": {}}],
        }})
        state = graph.invoke(_initial("Find Chai"))
    assert [r["tool_name"] for r in state["trace"]] == ["lookup_entity"]
    assert state["citations"] == [{"label": "Product", "key": "1", "name": "Chai"}]
    assert "[Product:1]" in state["answer"]
    assert sum(isinstance(m, ToolMessage) for m in state["messages"]) == 1


def test_budget_executes_eight_calls_then_degrades():
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response",
        lambda **kwargs: 'TOOL: lookup_entity({"name":"missing","label":"Product"})',
    ):
        graph = compile_graph({"lookup_entity": lambda **kwargs: {
            "status": "empty", "query_name": kwargs["name"], "matches": [],
        }})
        state = graph.invoke(_initial("Hard question"))
    assert state["route"] == "degrade"
    assert len(state["trace"]) == 8
    assert state["confidence"] == 0.4
    assert "Truncated" in state["answer"]


def test_retry_details_reach_trace_and_tool_message():
    call = AIMessage(content="", tool_calls=[{
        "name": "run_readonly_cypher", "args": {"query": "MATCH (n RETURN n"}, "id": "c1",
    }])
    state = _initial("query")
    state["messages"] = [call]
    state["loop_count"] = 1
    result = execute_tool_step(state, {"run_readonly_cypher": lambda **kwargs: {
        "status": "retry_ok", "query": kwargs["query"], "rows": [{"productID": "1"}],
        "attempts": [
            {"cypher": kwargs["query"], "valid": False, "error": "bad syntax"},
            {"cypher": "MATCH (p:Product) RETURN p.productID", "valid": True, "error": None},
        ],
    }})
    assert result["trace"][0]["retry_count"] == 1
    assert result["trace"][0]["cypher"] == "MATCH (n RETURN n"
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], ToolMessage)


def test_parser_handles_markdown_and_braces_in_quoted_query():
    parsed = _parse_llm_tool_call('**TOOL**: `run_readonly_cypher({"query":"MATCH (p:Product {productID: $id}) RETURN p"})`')
    assert parsed == {"tool": "run_readonly_cypher", "args": {"query": "MATCH (p:Product {productID: $id}) RETURN p"}}


def test_read_only_guard_rejects_writes_and_multiple_statements():
    client = object.__new__(Neo4jClient)
    assert client._validate_read_only("MATCH (n) WHERE n.title = 'CREATE' RETURN n")
    for query in ["CREATE (n)", "MATCH (n) RETURN n; DELETE n", "MATCH (n) CALL db.labels() RETURN n", "MATCH (n) SET n.x=1 RETURN n"]:
        assert not client._validate_read_only(query)


def test_aggregate_filter_is_parameterized():
    with patch("src.neo4j.tools.client") as client:
        client.run_read_query.return_value = ([], None)
        result = aggregate("Supplier", "country", "sum_revenue", "country='UK'")
    assert result["status"] == "empty"
    query, params = client.run_read_query.call_args.args
    assert "$where_value" in query and "'UK'" not in query
    assert params == {"where_value": "UK"}
    assert "LIMIT 20" in query


def test_exploratory_schema_rejects_unknown_identifiers():
    from src.neo4j.tools import _validate_schema_cypher
    assert _validate_schema_cypher("MATCH (p:Product) RETURN p.productID") is None
    assert "node label" in _validate_schema_cypher("MATCH (x:Unknown) RETURN x")
    assert "relationship type" in _validate_schema_cypher("MATCH (p:Product)-[:UNKNOWN]->(x) RETURN p")
    assert "property" in _validate_schema_cypher("MATCH (p:Product) RETURN p.name")


def test_aggregate_claims_cite_contributing_nodes():
    payload = {"status": "ok", "n_groups": 1, "groups": [{
        "group_value": "UK", "metric_value": 35916.8,
        "evidence": [{"label": "Supplier", "key": "1", "name": "Exotic Liquids"}],
    }]}
    decisions = iter([
        'TOOL: aggregate({"label":"Supplier","group_by":"country","metric":"sum_revenue"})',
        'FINAL: enough evidence',
    ])
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response", lambda **kwargs: next(decisions)
    ), patch("src.agents.llm.synthesize_from_evidence", lambda draft: draft):
        state = compile_graph({"aggregate": lambda **kwargs: payload}).invoke(_initial("Revenue by supplier country"))
    assert state["citations"] == [{"label": "Supplier", "key": "1", "name": "Exotic Liquids"}]
    assert "35916.8 [Supplier:1]" in state["answer"]


def test_show_customer_by_key_has_details_citation_and_consistent_trace():
    from src.neo4j.tools import lookup_entity

    customer = {
        "customerID": "ALFKI", "companyName": "Alfreds Futterkiste",
        "city": "Berlin", "country": "Germany",
    }

    def mocked_read(cypher, parameters=None):
        if "toString(n.customerID) = $name" in cypher:
            return ([{"n": customer}], None)
        return ([], None)

    decisions = iter([
        'TOOL: lookup_entity({"name":"ALFKI","label":"Customer"})',
        "FINAL: I have the customer details.",
    ])
    with patch("src.neo4j.tools.client.run_read_query", side_effect=mocked_read), patch(
        "src.agents.graph.classify", lambda state: {**state, "route": "agent"}
    ), patch("src.agents.llm.generate_agent_response", lambda **kwargs: next(decisions)), patch(
        "src.agents.llm.synthesize_from_evidence", lambda draft: draft
    ):
        state = compile_graph({"lookup_entity": lookup_entity}).invoke(
            _initial("Show info of customer ALFKI")
        )

    assert state["answer"].startswith("Matching graph nodes:")
    assert "Alfreds Futterkiste [Customer:ALFKI]" in state["answer"]
    assert "city: Berlin" in state["answer"] and "country: Germany" in state["answer"]
    assert state["citations"] == [{
        "label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste",
    }]
    assert [(item["tool_name"], item["status"], item["result_rows"]) for item in state["trace"]] == [
        ("lookup_entity", "ok", 1),
    ]


def test_multiple_statement_query_is_invalid_and_recorded_without_execution():
    query = "MATCH (c:Customer) RETURN c; MATCH (o:Order) RETURN o"
    state = _initial("run this query")
    state["loop_count"] = 1
    state["messages"] = [AIMessage(content="", tool_calls=[{
        "name": "run_readonly_cypher", "args": {"query": query}, "id": "multi",
    }])]
    with patch("src.neo4j.tools.client.explain") as explain, patch(
        "src.neo4j.tools.client.run_read_query"
    ) as execute:
        update = execute_tool_step(state, {"run_readonly_cypher": run_readonly_cypher})
    explain.assert_not_called()
    execute.assert_not_called()
    assert update["trace"][0]["status"] == "invalid"
    assert update["trace"][0]["result_rows"] == 0
    message = update["messages"][0]
    assert json.loads(message.content)["status"] == "invalid"


def test_trailing_semicolon_read_query_is_accepted_by_tool():
    query = "MATCH (c:Customer) RETURN c;"
    with patch("src.neo4j.tools.client.explain", return_value=True), patch(
        "src.neo4j.tools.client.run_read_query", return_value=([], None)
    ) as execute:
        result = run_readonly_cypher(query)
    assert result["status"] == "empty"
    assert result["query"] == query
    assert result["error"] is None
    execute.assert_called_once_with(query)

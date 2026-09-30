"""Behavioral tests for the contracted graph and read-only boundary."""
from unittest.mock import Mock, patch
import json

from langchain_core.messages import AIMessage, ToolMessage
from src.agents.graph import compile_graph
from src.agents.nodes import execute_tool_step, _parse_llm_tool_call
from src.neo4j.client import Neo4jClient
from src.neo4j.tools import aggregate, run_readonly_cypher


def _initial(question):
    return {
        "question": question, "route": "", "messages": [], "trace": [], "answer": "",
        "draft_answer": None, "draft_citations": [], "consistency_status": "pending", "consistency_feedback": None,
        "citations": [], "confidence": 0.0, "confidence_rationale": "",
        "loop_count": 0, "error": None,
    }


def test_compiled_graph_executes_one_tool_and_cites_returned_node():
    graph = compile_graph({"lookup_entity": lambda **kwargs: {
        "status": "ok", "error": None, "query_name": kwargs["name"],
        "matches": [{"node": {"label": "Product", "key": "1", "name": "Chai", "properties": {}}, "match": "exact", "evidence": {"nodes": [{"label": "Product", "key": "1", "name": "Chai", "properties": {}}], "edges": []}}],
    }})
    assert {"classify", "agent", "tools", "synthesize", "consistency_check", "degrade"} <= set(graph.nodes)
    assert type(graph.channels["messages"]).__name__ == "BinaryOperatorAggregate"
    responses = iter(['TOOL: lookup_entity({"name":"Chai","label":"Product"})', "FINAL: enough evidence"])
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response", lambda **kwargs: next(responses)
    ), patch("src.agents.llm.synthesize_from_evidence", lambda draft: draft), patch(
        "src.agents.llm.evaluate_answer_consistency", lambda **kwargs: {"decision": "pass", "feedback": ""}
    ):
        # Graph captures classify on construction, so rebuild under the patch.
        graph = compile_graph({"lookup_entity": lambda **kwargs: {
            "status": "ok", "error": None, "query_name": kwargs["name"],
            "matches": [{"node": {"label": "Product", "key": "1", "name": "Chai", "properties": {}}, "match": "exact", "evidence": {"nodes": [{"label": "Product", "key": "1", "name": "Chai", "properties": {}}], "edges": []}}],
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
        "status": "retry_ok", "error": None, "query": kwargs["query"], "rows": [{"values": {"productID": "1"}, "evidence": {"nodes": [], "edges": []}}],
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
    payload = {"status": "ok", "status": "ok", "error": None, "n_groups": 1, "groups": [{
        "group_value": "UK", "metric_value": 35916.8,
        "evidence": {"nodes": [{"label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": {}}], "edges": []},
    }]}
    decisions = iter([
        'TOOL: aggregate({"label":"Supplier","group_by":"country","metric":"sum_revenue"})',
        'FINAL: enough evidence',
    ])
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response", lambda **kwargs: next(decisions)
    ), patch("src.agents.llm.synthesize_from_evidence", lambda draft: draft), patch(
        "src.agents.llm.evaluate_answer_consistency", lambda **kwargs: {"decision": "pass", "feedback": ""}
    ):
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
    ), patch("src.agents.llm.evaluate_answer_consistency", lambda **kwargs: {"decision": "pass", "feedback": ""}):
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



def test_shared_customer_products_retries_after_single_history_result():
    savea = {"label": "Customer", "key": "SAVEA", "name": "Save-a-lot Markets", "properties": {}}
    alfki = {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "properties": {}}
    order_a = {"label": "Order", "key": "10324", "name": "10324", "properties": {}}
    order_b = {"label": "Order", "key": "10643", "name": "10643", "properties": {}}
    product = {"label": "Product", "key": "1", "name": "Chai", "properties": {}}

    def edge(kind, source, target):
        return {"type": kind, "from": {"label": source["label"], "key": source["key"]},
                "to": {"label": target["label"], "key": target["key"]}, "properties": {}}

    history_payload = {
        "status": "ok", "error": None,
        "customer": {"label": "Customer", "key": "SAVEA", "name": "Save-a-lot Markets"},
        "orders": [{
            "order": {"label": "Order", "key": "10324", "name": "10324"},
            "order_date": "1996-10-08", "total": 100.0, "ship_country": "USA",
            "evidence": {"nodes": [savea, order_a], "edges": [edge("PURCHASED", savea, order_a)]},
        }],
    }
    cypher_payload = {
        "status": "ok", "error": None,
        "query": "MATCH customer order paths to products",
        "attempts": [{"cypher": "MATCH customer order paths to products", "valid": True, "error": None}],
        "rows": [{
            "values": {"product_name": "Chai", "customer_ids": ["SAVEA", "ALFKI"]},
            "evidence": {
                "nodes": [savea, order_a, product, alfki, order_b],
                "edges": [edge("PURCHASED", savea, order_a), edge("ORDERS", order_a, product),
                          edge("PURCHASED", alfki, order_b), edge("ORDERS", order_b, product)],
            },
        }],
    }
    decisions = iter([
        'TOOL: customer_history({"customer_key":"SAVEA"})',
        'TOOL: run_readonly_cypher({"query":"MATCH customer order paths to products"})',
    ])
    evaluator = lambda **kwargs: {"decision": "pass", "feedback": ""}
    tools = {
        "customer_history": lambda **kwargs: history_payload,
        "run_readonly_cypher": lambda **kwargs: cypher_payload,
    }
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response", lambda **kwargs: next(decisions)
    ), patch("src.agents.llm.synthesize_from_evidence", lambda draft: draft), patch(
        "src.agents.llm.evaluate_answer_consistency", evaluator
    ):
        state = compile_graph(tools).invoke(_initial(
            "Which products do customers SAVEA and ALFKI both order?"
        ))

    assert state["consistency_status"] == "pass"
    assert state["loop_count"] == 2
    assert [row["tool_name"] for row in state["trace"]] == ["customer_history", "run_readonly_cypher"]
    assert "Chai" in state["answer"]
    assert "SAVEA" in state["answer"] and "ALFKI" in state["answer"]
    assert {item["key"] for item in state["citations"]} == {"SAVEA", "ALFKI", "1"}
    assert state["confidence"] == 0.6


def test_consistency_retry_keeps_budget_and_degrades_at_max_steps():
    decisions = iter([
        "FINAL: I have an answer.",
        'TOOL: lookup_entity({"name":"Chai","label":"Product"})',
    ])
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response", lambda **kwargs: next(decisions)
    ), patch(
        "src.agents.llm.evaluate_answer_consistency",
        lambda **kwargs: {"decision": "revise", "feedback": "The answer has no graph evidence."},
    ):
        state = _initial("Find a product")
        state["loop_count"] = 6
        graph = compile_graph({"lookup_entity": lambda **kwargs: {
            "status": "empty", "error": None, "query_name": kwargs["name"], "matches": [],
        }})
        result = graph.invoke(state)

    assert result["loop_count"] == 8
    assert result["route"] == "degrade"
    assert result["draft_answer"] is None
    assert result["citations"] == []
    assert "Truncated" in result["answer"]
    assert result["consistency_status"] == "revise"


def test_unmarked_model_completion_after_whole_graph_count_is_checked_and_accepted():
    nodes = [
        {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "properties": {}},
        {"label": "Order", "key": "10248", "name": "10248", "properties": {}},
        {"label": "Product", "key": "1", "name": "Chai", "properties": {}},
    ]
    payload = {
        "status": "ok",
        "error": None,
        "query": "MATCH (n) RETURN count(n) AS node_count, collect(DISTINCT n)[0..3] AS evidence_nodes",
        "attempts": [],
        "rows": [{
            "values": {"node_count": 141, "evidence_nodes": nodes},
            "evidence": {"nodes": nodes, "edges": []},
        }],
    }
    decisions = iter([
        'TOOL: run_readonly_cypher({"query":"MATCH (n) RETURN count(n) AS node_count, collect(DISTINCT n)[0..3] AS evidence_nodes"})',
    ])
    reviewer = Mock(return_value={"decision": "pass", "feedback": ""})
    misleading_rewrite = Mock(return_value=(
        "141 nodes are associated with Alfreds Futterkiste "
        "[Customer:ALFKI] [Order:10248] [Product:1]."
    ))
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response", lambda **kwargs: next(decisions)
    ), patch("src.agents.llm.synthesize_from_evidence", misleading_rewrite), patch(
        "src.agents.llm.evaluate_answer_consistency", reviewer,
    ):
        state = compile_graph({"run_readonly_cypher": lambda **kwargs: payload}).invoke(
            _initial("How many nodes are there in the graph?")
        )

    assert state["consistency_status"] == "pass"
    assert state["loop_count"] == 1
    assert len(state["trace"]) == 1
    assert "The Northwind dataset contains 141 nodes." in state["answer"]
    assert "for Alfreds Futterkiste" not in state["answer"]
    assert len(state["citations"]) == 3
    misleading_rewrite.assert_not_called()
    reviewer.assert_called_once()


def test_scalar_only_whole_graph_node_count_gets_one_bounded_evidence_recovery():
    nodes = [
        {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "properties": {}},
        {"label": "Order", "key": "10248", "name": "10248", "properties": {}},
        {"label": "Product", "key": "1", "name": "Chai", "properties": {}},
    ]
    queries = []
    decisions = iter([
        'TOOL: run_readonly_cypher({"query":"MATCH (n) RETURN count(n) AS total_nodes"})',
        "The count result is sufficient.",
    ])

    def readonly(query):
        queries.append(query)
        evidence = nodes if "evidence_nodes" in query else []
        return {
            "status": "ok",
            "error": None,
            "query": query,
            "attempts": [],
            "rows": [{
                "values": {"total_nodes": 141, "evidence_nodes": evidence} if evidence else {"total_nodes": 141},
                "evidence": {"nodes": evidence, "edges": []},
            }],
        }

    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response", lambda **kwargs: next(decisions)
    ), patch("src.agents.llm.synthesize_from_evidence", lambda draft: draft), patch(
        "src.agents.llm.evaluate_answer_consistency",
        lambda **kwargs: {"decision": "pass", "feedback": ""},
    ):
        state = compile_graph({"run_readonly_cypher": lambda **kwargs: readonly(**kwargs)}).invoke(
            _initial("How many nodes are there in the graph?")
        )

    assert state["consistency_status"] == "pass"
    assert state["loop_count"] == 2
    assert len(state["trace"]) == 2
    assert [record["status"] for record in state["trace"]] == ["ok", "ok"]
    assert "The Northwind dataset contains 141 nodes." in state["answer"]
    assert len(state["citations"]) == 3
    assert "collect(DISTINCT n)[0..3] AS evidence_nodes" in queries[1]

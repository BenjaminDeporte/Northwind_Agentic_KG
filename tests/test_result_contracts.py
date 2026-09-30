"""Runtime result validation tests for every tool contract."""
import pytest

from src.neo4j.result_contracts import ToolResultValidationError, validate_tool_result


NODE = {"label": "Customer", "key": "ALFKI", "name": "Alfreds", "properties": {}}
ORDER = {"label": "Order", "key": "10643", "name": "10643", "properties": {}}
EDGE = {
    "type": "PURCHASED", "from": {"label": "Customer", "key": "ALFKI"},
    "to": {"label": "Order", "key": "10643"}, "properties": {},
}


@pytest.mark.parametrize(("tool", "payload"), [
    ("lookup_entity", {"query_name": "Alfreds", "matches": [{
        "node": NODE, "match": "exact", "evidence": {"nodes": [NODE], "edges": []},
    }]}),
    ("impact_analysis", {
        "anchor": NODE, "subgraph": {"nodes": [NODE], "edges": []},
        "aggregates": {"products_affected": 0, "orders_affected": 0, "revenue_at_risk": 0.0, "unusable_lines": 0},
        "evidence": {"nodes": [NODE], "edges": []},
    }),
    ("co_purchase", {"product": {"label": "Product", "key": "1", "name": "Chai"},
        "recommendations": [{"product": {"label": "Product", "key": "2", "name": "Chang"}, "co_bought": 3,
            "evidence": {"nodes": [
                {"label": "Product", "key": "1", "name": "Chai", "properties": {}},
                {"label": "Product", "key": "2", "name": "Chang", "properties": {}},
            ], "edges": []}}]}),
    ("customer_history", {"customer": {"label": "Customer", "key": "ALFKI", "name": "Alfreds"},
        "orders": [{"order": {"label": "Order", "key": "10643", "name": "10643"}, "order_date": "1997-08-25",
            "total": 12.0, "ship_country": "Germany", "evidence": {"nodes": [NODE, ORDER], "edges": [EDGE]}}]}),
    ("aggregate", {"groups": [{"group_value": "Germany", "metric_value": 12.0, "evidence": {"nodes": [NODE], "edges": []}}], "n_groups": 1}),
    ("run_readonly_cypher", {"query": "MATCH (c:Customer) RETURN c", "attempts": [
        {"cypher": "MATCH (c:Customer) RETURN c", "valid": True, "error": None}],
        "rows": [{"values": {"customer": NODE}, "evidence": {"nodes": [NODE], "edges": []}}]}),
])
def test_each_tool_success_schema_validates(tool, payload):
    result = {"status": "ok", "error": None, **payload}
    assert validate_tool_result(tool, result) is result


@pytest.mark.parametrize(("tool", "payload"), [
    ("lookup_entity", {"query_name": "x", "matches": []}),
    ("impact_analysis", {"anchor": None, "subgraph": {"nodes": [], "edges": []},
        "aggregates": {"products_affected": 0, "orders_affected": 0, "revenue_at_risk": 0.0, "unusable_lines": 0},
        "evidence": {"nodes": [], "edges": []}}),
    ("co_purchase", {"product": None, "recommendations": []}),
    ("customer_history", {"customer": None, "orders": []}),
    ("aggregate", {"groups": [], "n_groups": 0}),
    ("run_readonly_cypher", {"query": "MATCH (n) RETURN n", "attempts": [], "rows": []}),
])
def test_empty_schema_validates_for_each_tool(tool, payload):
    result = {"status": "empty", "error": None, **payload}
    assert validate_tool_result(tool, result) is result


def test_error_status_requires_error_string_and_complete_payload():
    result = {"status": "invalid", "error": "unsupported label", "query_name": "x", "matches": []}
    assert validate_tool_result("lookup_entity", result) is result
    with pytest.raises(ToolResultValidationError, match="useful error"):
        validate_tool_result("lookup_entity", {**result, "error": None})
    with pytest.raises(ToolResultValidationError, match="required"):
        validate_tool_result("lookup_entity", {k: v for k, v in result.items() if k != "error"})


def test_validator_rejects_unassociated_and_over_limit_evidence():
    good = {"status": "ok", "error": None, "query_name": "ALFKI", "matches": [{
        "node": NODE, "match": "exact", "evidence": {"nodes": [], "edges": []},
    }]}
    with pytest.raises(ToolResultValidationError, match="include its matched node"):
        validate_tool_result("lookup_entity", good)

    nodes = [
        {"label": "Supplier", "key": str(i), "name": f"S{i}", "properties": {}}
        for i in range(4)
    ]
    aggregate = {"status": "ok", "error": None, "n_groups": 1, "groups": [{
        "group_value": "UK", "metric_value": 1,
        "evidence": {"nodes": nodes, "edges": []},
    }]}
    with pytest.raises(ToolResultValidationError, match="3-handle limit"):
        validate_tool_result("aggregate", aggregate)


def test_validator_rejects_retry_status_for_curated_tool():
    result = {"status": "retry_ok", "error": None, "product": None, "recommendations": []}
    with pytest.raises(ToolResultValidationError, match="reserved"):
        validate_tool_result("co_purchase", result)

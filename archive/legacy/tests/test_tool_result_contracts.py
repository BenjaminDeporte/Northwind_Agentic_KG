"""Deterministic contract tests for the six graph tools; no live services."""
from unittest.mock import MagicMock

from src.neo4j import tools


class FakeNode(dict):
    def __init__(self, label, **properties):
        super().__init__(properties)
        self.labels = {label}


class FakeRelationship(dict):
    def __init__(self, rel_type, start_node, end_node, **properties):
        super().__init__(properties)
        self.type = rel_type
        self.start_node = start_node
        self.end_node = end_node


def test_lookup_result_has_common_error_and_match_local_canonical_evidence(monkeypatch):
    supplier = {"supplierID": "1", "companyName": "Exotic Liquids", "country": "UK", "phone": "555"}

    def query(cypher, parameters=None):
        if "n.companyName = $name" in cypher:
            return ([{"n": supplier}], None)
        return ([], None)

    monkeypatch.setattr(tools.client, "run_read_query", query)
    result = tools.lookup_entity("Exotic Liquids", "Supplier")

    assert result["status"] == "ok" and result["error"] is None
    match = result["matches"][0]
    assert match["node"] == {
        "label": "Supplier", "key": "1", "name": "Exotic Liquids",
        "properties": {"country": "UK", "phone": "555"},
    }
    assert match["evidence"] == {"nodes": [match["node"]], "edges": []}


def test_lookup_execution_failure_has_error_and_empty_payload(monkeypatch):
    monkeypatch.setattr(tools.client, "run_read_query", MagicMock(side_effect=RuntimeError("offline")))
    result = tools.lookup_entity("ALFKI", "Customer")
    assert result["status"] == "invalid"
    assert "offline" in result["error"]
    assert result["matches"] == []


def test_impact_keeps_full_subgraph_and_limits_claim_evidence(monkeypatch):
    supplier = {"supplierID": "1", "companyName": "Supplier A", "country": "UK"}
    product = {"productID": "2", "productName": "Product B", "unitPrice": 3.0}
    order = {"orderID": 10, "orderDate": "1997-01-01"}
    customer = {"customerID": "ALFKI", "companyName": "Customer C"}

    def query(cypher, parameters=None):
        if "RETURN a" in cypher:
            return ([{"a": supplier}], None)
        return ([{"p": product, "o": order, "c": customer, "line": {"quantity": 2, "unitPrice": 3.0}}], None)

    monkeypatch.setattr(tools.client, "run_read_query", query)
    result = tools.impact_analysis("1", "Supplier", depth=3)

    assert result["status"] == "ok" and result["error"] is None
    assert result["aggregates"]["revenue_at_risk"] == 6.0
    assert len(result["subgraph"]["nodes"]) == 4
    assert len(result["evidence"]["nodes"]) <= 3
    assert len(result["evidence"]["edges"]) <= 2
    selected = {(node["label"], node["key"]) for node in result["evidence"]["nodes"]}
    assert ("Supplier", "1") in selected
    assert all(
        (edge["from"]["label"], edge["from"]["key"]) in selected
        and (edge["to"]["label"], edge["to"]["key"]) in selected
        for edge in result["evidence"]["edges"]
    )


def test_impact_query_failure_has_useful_error(monkeypatch):
    monkeypatch.setattr(tools.client, "run_read_query", MagicMock(side_effect=RuntimeError("offline")))
    result = tools.impact_analysis("1", "Supplier")
    assert result["status"] == "invalid" and "offline" in result["error"]
    assert result["subgraph"] == {"nodes": [], "edges": []}


def test_copurchase_associates_each_count_with_product_pair(monkeypatch):
    anchor = {"productID": "1", "productName": "Chai", "unitPrice": 18.0}
    related = {"productID": "2", "productName": "Chang", "unitPrice": 19.0}

    def query(cypher, parameters=None):
        if cypher.strip().endswith("RETURN p"):
            return ([{"p": anchor}], None)
        return ([{"p2": related, "co_bought": 4}], None)

    monkeypatch.setattr(tools.client, "run_read_query", query)
    result = tools.co_purchase("1")

    assert result["status"] == "ok" and result["error"] is None
    recommendation = result["recommendations"][0]
    assert recommendation["product"] == {"label": "Product", "key": "2", "name": "Chang"}
    assert recommendation["co_bought"] == 4
    assert [(n["key"]) for n in recommendation["evidence"]["nodes"]] == ["1", "2"]
    assert recommendation["evidence"]["edges"] == []


def test_copurchase_query_failure_returns_error(monkeypatch):
    monkeypatch.setattr(tools.client, "run_read_query", MagicMock(side_effect=RuntimeError("offline")))
    result = tools.co_purchase("1")
    assert result["status"] == "invalid" and "offline" in result["error"]
    assert result["recommendations"] == []


def test_customer_history_returns_order_nodes_and_customer_order_edge(monkeypatch):
    customer = FakeNode("Customer", customerID="ALFKI", companyName="Alfreds Futterkiste", country="Germany")
    order = FakeNode("Order", orderID=10643, orderDate="1997-08-25 00:00:00.000", shipCountry="Germany")
    purchase = FakeRelationship("PURCHASED", customer, order)

    def query(cypher, parameters=None):
        return ([{
            "c": customer, "o": order, "purchase": purchase,
            "order_date": order["orderDate"], "total": 1086.0, "ship_country": "Germany",
        }], None)

    monkeypatch.setattr(tools.client, "run_read_query", query)
    result = tools.customer_history("ALFKI")

    assert result["status"] == "ok" and result["error"] is None
    entry = result["orders"][0]
    assert entry["order"] == {"label": "Order", "key": "10643", "name": "10643"}
    assert [node["label"] for node in entry["evidence"]["nodes"]] == ["Customer", "Order"]
    assert entry["evidence"]["edges"][0]["type"] == "PURCHASED"
    assert entry["evidence"]["edges"][0]["from"] == {"label": "Customer", "key": "ALFKI"}
    assert entry["evidence"]["edges"][0]["to"] == {"label": "Order", "key": "10643"}


def test_customer_history_execution_failure_returns_error(monkeypatch):
    monkeypatch.setattr(tools.client, "run_read_query", MagicMock(side_effect=RuntimeError("offline")))
    result = tools.customer_history("ALFKI")
    assert result["status"] == "invalid" and "offline" in result["error"]
    assert result["orders"] == []


def test_aggregate_returns_at_most_three_canonical_handles(monkeypatch):
    nodes = [
        {"supplierID": str(i), "companyName": f"Supplier {i}", "country": "UK"}
        for i in range(1, 8)
    ]
    observed = {}

    def query(cypher, parameters=None):
        observed["query"] = cypher
        return ([{"group_value": "UK", "metric_value": 42.0, "evidence_nodes": nodes}], None)

    monkeypatch.setattr(tools.client, "run_read_query", query)
    result = tools.aggregate("Supplier", "country", "sum_revenue")

    assert result["status"] == "ok" and result["error"] is None
    assert "collect(DISTINCT s)[0..3]" in observed["query"]
    evidence = result["groups"][0]["evidence"]
    assert len(evidence["nodes"]) == 3 and evidence["edges"] == []
    assert all(node["label"] == "Supplier" and "properties" in node for node in evidence["nodes"])


def test_aggregate_execution_failure_returns_useful_error(monkeypatch):
    monkeypatch.setattr(tools.client, "run_read_query", MagicMock(side_effect=RuntimeError("offline")))
    result = tools.aggregate("Supplier", "country", "sum_revenue")
    assert result["status"] == "invalid" and "offline" in result["error"]
    assert result["groups"] == [] and result["n_groups"] == 0

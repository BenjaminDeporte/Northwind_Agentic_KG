"""Contract tests for the exploratory read-only tool."""
import json
from unittest.mock import MagicMock, call, patch

from src.neo4j.client import Neo4jClient

from src.neo4j.tools import _normalize_cypher_row, run_readonly_cypher


@patch("src.neo4j.tools.client")
def test_success_and_empty_are_distinct(mock_client):
    mock_client._validate_read_only.return_value = True
    mock_client.explain.return_value = True
    mock_client.run_read_query.return_value = ([{"productID": "1"}], MagicMock())
    good = run_readonly_cypher("MATCH (p:Product) RETURN p.productID AS productID")
    assert good["status"] == "ok"
    assert len(good["attempts"]) == 1
    assert good["error"] is None
    assert good["rows"] == [{
        "values": {"productID": "1"},
        "evidence": {"nodes": [], "edges": []},
    }]
    mock_client.run_read_query.return_value = ([], MagicMock())
    empty = run_readonly_cypher("MATCH (p:Product) WHERE p.productID = 'missing' RETURN p")
    assert empty["status"] == "empty"
    assert empty["rows"] == []
    assert empty["error"] is None


@patch("src.neo4j.tools.client")
def test_write_request_is_invalid_without_execution(mock_client):
    mock_client._validate_read_only.return_value = False
    result = run_readonly_cypher("CREATE (n)")
    assert result["status"] == "invalid"
    assert result["error"] == result["attempts"][0]["error"]
    assert len(result["attempts"]) == 1
    mock_client.explain.assert_not_called()
    mock_client.run_read_query.assert_not_called()


@patch("src.neo4j.tools._repair_cypher", return_value="MATCH (p:Product) RETURN p.productID AS productID")
@patch("src.neo4j.tools.client")
def test_explain_failure_repairs_once_with_error(mock_client, repair):
    mock_client._validate_read_only.return_value = True
    mock_client.explain.side_effect = [False, True]
    mock_client.run_read_query.return_value = ([{"productID": "1"}], MagicMock())
    result = run_readonly_cypher("MATCH (p:Product RETURN p")
    assert result["status"] == "retry_ok"
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["valid"] is False
    assert result["attempts"][1]["valid"] is True
    assert result["attempts"][0]["cypher"] != result["attempts"][1]["cypher"]
    assert "EXPLAIN" in repair.call_args.args[1]


@patch("src.neo4j.tools._repair_cypher", return_value="MATCH (p:Product) RETURN p")
@patch("src.neo4j.tools.client")
def test_execution_failure_repairs_once(mock_client, repair):
    mock_client._validate_read_only.return_value = True
    mock_client.explain.return_value = True
    mock_client.run_read_query.side_effect = [RuntimeError("bad execution"), ([{"x": 1}], MagicMock())]
    result = run_readonly_cypher("MATCH (n) RETURN n")
    assert result["status"] == "retry_ok"
    assert len(result["attempts"]) == 2
    assert "bad execution" in repair.call_args.args[1]


@patch("src.neo4j.tools._repair_cypher", return_value="MATCH (p:Product RETURN p")
@patch("src.neo4j.tools.client")
def test_retry_stops_after_second_failure(mock_client, repair):
    mock_client._validate_read_only.return_value = True
    mock_client.explain.return_value = False
    result = run_readonly_cypher("MATCH (n RETURN n")
    assert result["status"] == "retry_failed"
    assert len(result["attempts"]) == 2
    assert repair.call_count == 1
    assert result["error"] == result["attempts"][-1]["error"]


@patch("src.neo4j.tools._repair_cypher", return_value="DELETE n")
@patch("src.neo4j.tools.client")
def test_repaired_write_is_never_executed(mock_client, repair):
    mock_client._validate_read_only.side_effect = [True, True, False]
    mock_client.explain.return_value = False
    result = run_readonly_cypher("MATCH (n RETURN n")
    assert result["status"] == "retry_failed"
    mock_client.run_read_query.assert_not_called()


def test_read_only_validator_accepts_only_one_trailing_semicolon():
    client = object.__new__(Neo4jClient)
    query = "MATCH (c:Customer) RETURN c;  "

    assert client._normalize_read_only_query(query) == "MATCH (c:Customer) RETURN c"
    assert client._validate_read_only(query)
    assert not client._validate_read_only("MATCH (c:Customer) RETURN c; MATCH (o:Order) RETURN o")
    assert not client._validate_read_only("MATCH (c:Customer) RETURN c; DELETE c")


def test_semicolons_inside_literals_and_comments_are_not_statement_delimiters():
    client = object.__new__(Neo4jClient)
    assert client._validate_read_only("MATCH (c:Customer) WHERE c.companyName = 'A;B' RETURN c")
    assert client._validate_read_only("MATCH (c:Customer) RETURN c // ; not a statement delimiter")


def test_trailing_semicolon_is_removed_before_explain_and_execution():
    client = object.__new__(Neo4jClient)
    query = "MATCH (c:Customer) RETURN c;  "
    session = MagicMock()
    result = MagicMock()
    result.__iter__.return_value = iter([])
    session.run.return_value = result
    session_context = MagicMock()
    session_context.__enter__.return_value = session

    with patch.object(client, "_session", return_value=session_context):
        assert client.explain(query)
        rows, _ = client.run_read_query(query)

    assert rows == []
    assert session.run.call_args_list == [
        call("EXPLAIN MATCH (c:Customer) RETURN c"),
        call("MATCH (c:Customer) RETURN c", {}),
    ]


class _FakeNode(dict):
    def __init__(self, label, **properties):
        super().__init__(properties)
        self.labels = {label}


class _FakeRelationship(dict):
    def __init__(self, rel_type, start_node, end_node, **properties):
        super().__init__(properties)
        self.type = rel_type
        self.start_node = start_node
        self.end_node = end_node


class _FakePath:
    def __init__(self, nodes, relationships):
        self.nodes = tuple(nodes)
        self.relationships = tuple(relationships)


def test_normalized_row_supports_nodes_relationships_paths_and_mixed_values():
    customer = _FakeNode("Customer", customerID="ALFKI", companyName="Alfreds Futterkiste", city="Berlin")
    order = _FakeNode("Order", orderID=10643, orderDate="2012-08-25")
    purchased = _FakeRelationship("PURCHASED", customer, order)
    row = _normalize_cypher_row({
        "order_count": 1,
        "customer": customer,
        "relationship": purchased,
        "path": _FakePath([customer, order], [purchased]),
        "extra_nodes": [order],
    })

    assert row["values"]["order_count"] == 1
    assert row["values"]["customer"] == {
        "label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste",
        "properties": {"customerID": "ALFKI", "companyName": "Alfreds Futterkiste", "city": "Berlin"},
    }
    assert row["values"]["path"]["nodes"][0]["key"] == "ALFKI"
    assert row["values"]["relationship"]["type"] == "PURCHASED"
    assert { (node["label"], node["key"]) for node in row["evidence"]["nodes"] } == {
        ("Customer", "ALFKI"), ("Order", "10643"),
    }
    assert len(row["evidence"]["edges"]) == 1
    json.dumps(row, allow_nan=False)
    assert row["evidence"]["edges"][0] == {
        "type": "PURCHASED",
        "from": {"label": "Customer", "key": "ALFKI"},
        "to": {"label": "Order", "key": "10643"},
        "properties": {},
    }


def test_normalized_scalar_only_row_has_empty_evidence():
    assert _normalize_cypher_row({"total": 4.5, "name": "Northwind"}) == {
        "values": {"total": 4.5, "name": "Northwind"},
        "evidence": {"nodes": [], "edges": []},
    }

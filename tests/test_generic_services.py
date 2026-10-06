import json

from architectures.generic import run_readonly_cypher, validate_cypher
from common.neo4j.results import result_envelope


SCHEMA = """
## Node labels
| Label | Count | Key | Name property | Properties |
| Customer | 91 | customerID | companyName | customerID, companyName, city |
| Order | 830 | orderID | orderID | orderID |
## Relationships
| Type | From → To | Count | Properties |
| PURCHASED | Customer → Order | 830 | — |
"""


def test_validation_accepts_read_query_and_terminal_semicolon():
    result = validate_cypher(
        "MATCH (c:Customer) RETURN c.customerID AS customerID;", schema=SCHEMA
    )
    assert result == {
        "status": "valid",
        "query": "MATCH (c:Customer) RETURN c.customerID AS customerID",
        "error": None,
    }


def test_validation_rejects_writes_unknown_labels_properties_and_multiple_statements():
    assert validate_cypher("CREATE (c:Customer)", schema=SCHEMA)["status"] == "invalid"
    assert validate_cypher("MATCH (x:Widget) RETURN x", schema=SCHEMA)["status"] == "invalid"
    assert validate_cypher("MATCH (c:Customer) RETURN c.unknown_field", schema=SCHEMA)["status"] == "invalid"
    assert validate_cypher("MATCH (c:Customer) RETURN c; MATCH (o:Order) RETURN o", schema=SCHEMA)["status"] == "invalid"


def test_validation_can_call_explain_without_executing_data_query():
    calls = []
    result = validate_cypher(
        "MATCH (c:Customer) RETURN count(c)",
        schema=SCHEMA,
        explain=calls.append,
    )
    assert result["status"] == "valid"
    assert calls == ["MATCH (c:Customer) RETURN count(c)"]


class FakeNode:
    labels = {"Customer"}
    element_id = "customer-1"
    _properties = {"customerID": "ALFKI", "companyName": "Alfreds"}


class FakeRelationship:
    element_id = "rel-1"
    start_node = FakeNode()
    end_node = object()
    _properties = {}

    @property
    def type(self):
        return "PURCHASED"

    @property
    def end_node(self):
        return type("OrderNode", (), {"element_id": "order-1"})()


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, query):
        return self.rows


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def session(self):
        return FakeSession(self.rows)


def test_result_envelope_preserves_scalars_nodes_relationships_and_nested_values():
    node = FakeNode()
    relationship = FakeRelationship()
    envelope = result_envelope(
        [{"count": 1, "customer": node, "path": {"rel": relationship}, "items": [node]}],
        query="MATCH (c:Customer) RETURN c",
    )
    assert envelope["status"] == "ok"
    assert envelope["rows"][0]["values"]["count"] == 1
    assert envelope["rows"][0]["values"]["customer"]["kind"] == "node"
    assert len(envelope["evidence"]["nodes"]) == 1
    assert len(envelope["evidence"]["edges"]) == 1
    json.dumps(envelope)


def test_executor_returns_empty_and_failed_outcomes_without_raising():
    empty = run_readonly_cypher("MATCH (c:Customer) RETURN c", neo4j_client=FakeClient([]), schema=SCHEMA)
    assert empty["status"] == "empty"
    assert empty["rows"] == []
    failed = run_readonly_cypher("MATCH (c:Customer) RETURN c", neo4j_client=object(), schema=SCHEMA)
    assert failed["status"] == "failed"
    assert failed["error"]

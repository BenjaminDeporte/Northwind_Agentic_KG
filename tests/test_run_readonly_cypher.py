"""Contract tests for the exploratory read-only tool."""
from unittest.mock import MagicMock, patch

from src.neo4j.tools import run_readonly_cypher


@patch("src.neo4j.tools.client")
def test_success_and_empty_are_distinct(mock_client):
    mock_client._validate_read_only.return_value = True
    mock_client.explain.return_value = True
    mock_client.run_read_query.return_value = ([{"productID": "1"}], MagicMock())
    good = run_readonly_cypher("MATCH (p:Product) RETURN p.productID AS productID")
    assert good["status"] == "ok"
    assert len(good["attempts"]) == 1
    mock_client.run_read_query.return_value = ([], MagicMock())
    empty = run_readonly_cypher("MATCH (p:Product) WHERE p.productID = 'missing' RETURN p")
    assert empty["status"] == "empty"
    assert empty["rows"] == []


@patch("src.neo4j.tools.client")
def test_write_request_is_invalid_without_execution(mock_client):
    mock_client._validate_read_only.return_value = False
    result = run_readonly_cypher("CREATE (n)")
    assert result["status"] == "invalid"
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


@patch("src.neo4j.tools._repair_cypher", return_value="DELETE n")
@patch("src.neo4j.tools.client")
def test_repaired_write_is_never_executed(mock_client, repair):
    mock_client._validate_read_only.side_effect = [True, True, False]
    mock_client.explain.return_value = False
    result = run_readonly_cypher("MATCH (n RETURN n")
    assert result["status"] == "retry_failed"
    mock_client.run_read_query.assert_not_called()

"""
Unit tests for run_readonly_cypher tool (Phase 2, Item 2.1).

Contract: PROJECT.md §4.5 — run_readonly_cypher
PLAN.md 2.1 — Agent-written Cypher

Testing strategy: Deterministic, no live DB calls (mocked client).
"""

import pytest
from unittest.mock import MagicMock, patch

from src.neo4j.tools import run_readonly_cypher


class TestRunReadonlyCypherBasic:
    """Test basic run_readonly_cypher functionality."""

    @patch('src.neo4j.tools.client')
    def test_returns_dict(self, mock_client):
        """run_readonly_cypher returns a dictionary."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        assert isinstance(result, dict)

    @patch('src.neo4j.tools.client')
    def test_returns_query_field(self, mock_client):
        """Result contains the original query."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        query = "MATCH (n) RETURN n"
        result = run_readonly_cypher(query)
        assert result['query'] == query

    @patch('src.neo4j.tools.client')
    def test_returns_attempts_field(self, mock_client):
        """Result contains attempts list."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        assert 'attempts' in result
        assert isinstance(result['attempts'], list)

    @patch('src.neo4j.tools.client')
    def test_returns_rows_field(self, mock_client):
        """Result contains rows list."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        assert 'rows' in result
        assert isinstance(result['rows'], list)

    @patch('src.neo4j.tools.client')
    def test_returns_status_field(self, mock_client):
        """Result contains status field."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        assert 'status' in result


class TestRunReadonlyCypherStatuses:
    """Test different status values."""

    @patch('src.neo4j.tools.client')
    def test_ok_status(self, mock_client):
        """Valid query returns 'ok' status."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        assert result['status'] == 'ok'

    @patch('src.neo4j.tools.client')
    def test_empty_status(self, mock_client):
        """Query that returns no rows has 'ok' status (empty is legitimate)."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) WHERE n.name = 'nonexistent' RETURN n")
        assert result['status'] == 'ok'
        assert result['rows'] == []

    @patch('src.neo4j.tools.client')
    def test_invalid_status_on_read_only_violation(self, mock_client):
        """Query with write operations returns invalid status."""
        mock_client._validate_read_only.return_value = False
        
        result = run_readonly_cypher("CREATE (n)")
        assert result['status'] in ['invalid', 'retry_failed']

    @patch('src.neo4j.tools.client')
    def test_invalid_status_on_explain_failure(self, mock_client):
        """Query that fails EXPLAIN returns invalid or retry status."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = False
        
        result = run_readonly_cypher("INVALID CYPHER SYNTAX")
        assert result['status'] in ['invalid', 'retry_failed']


class TestRunReadonlyCypherRetry:
    """Test retry behavior."""

    @patch('src.neo4j.tools.client')
    def test_one_retry_on_failure(self, mock_client):
        """Exactly one retry is attempted on failure."""
        mock_client._validate_read_only.side_effect = [True, True]
        mock_client.explain.side_effect = [False, True]
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        
        # Should have attempted twice (initial + retry)
        assert len(result['attempts']) == 2

    @patch('src.neo4j.tools.client')
    def test_retry_ok_status(self, mock_client):
        """Retry that succeeds returns 'retry_ok' status."""
        mock_client._validate_read_only.side_effect = [True, True]
        mock_client.explain.side_effect = [False, True]
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        assert result['status'] == 'retry_ok'

    @patch('src.neo4j.tools.client')
    def test_retry_failed_status(self, mock_client):
        """Retry that also fails returns 'retry_failed' status."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = False
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        assert result['status'] == 'retry_failed'

    @patch('src.neo4j.tools.client')
    def test_max_one_retry(self, mock_client):
        """At most one retry is attempted."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = False
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        
        # Should have at most 2 attempts (initial + 1 retry)
        assert len(result['attempts']) <= 2


class TestRunReadonlyCypherAttempts:
    """Test attempts field structure."""

    @patch('src.neo4j.tools.client')
    def test_attempt_has_cypher(self, mock_client):
        """Each attempt has cypher field."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        
        for attempt in result['attempts']:
            assert 'cypher' in attempt

    @patch('src.neo4j.tools.client')
    def test_attempt_has_valid(self, mock_client):
        """Each attempt has valid field."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        
        for attempt in result['attempts']:
            assert 'valid' in attempt

    @patch('src.neo4j.tools.client')
    def test_attempt_has_error(self, mock_client):
        """Each attempt has error field."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        
        for attempt in result['attempts']:
            assert 'error' in attempt

    @patch('src.neo4j.tools.client')
    def test_valid_attempt_has_no_error(self, mock_client):
        """Valid attempts have error=None or None."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        
        for attempt in result['attempts']:
            if attempt['valid']:
                assert attempt['error'] is None


class TestRunReadonlyCypherReadOnly:
    """Test read-only enforcement."""

    @patch('src.neo4j.tools.client')
    def test_rejects_create(self, mock_client):
        """Rejects CREATE statements."""
        mock_client._validate_read_only.return_value = False
        
        result = run_readonly_cypher("CREATE (n)")
        assert result['status'] in ['invalid', 'retry_failed']

    @patch('src.neo4j.tools.client')
    def test_rejects_merge(self, mock_client):
        """Rejects MERGE statements."""
        mock_client._validate_read_only.return_value = False
        
        result = run_readonly_cypher("MERGE (n)")
        assert result['status'] in ['invalid', 'retry_failed']

    @patch('src.neo4j.tools.client')
    def test_rejects_delete(self, mock_client):
        """Rejects DELETE statements."""
        mock_client._validate_read_only.return_value = False
        
        result = run_readonly_cypher("DELETE n")
        assert result['status'] in ['invalid', 'retry_failed']

    @patch('src.neo4j.tools.client')
    def test_rejects_set(self, mock_client):
        """Rejects SET statements."""
        mock_client._validate_read_only.return_value = False
        
        result = run_readonly_cypher("SET n.prop = 1")
        assert result['status'] in ['invalid', 'retry_failed']

    @patch('src.neo4j.tools.client')
    def test_rejects_apoc(self, mock_client):
        """Rejects APOC calls."""
        mock_client._validate_read_only.return_value = False
        
        result = run_readonly_cypher("CALL apoc.meta.data()")
        assert result['status'] in ['invalid', 'retry_failed']

    @patch('src.neo4j.tools.client')
    def test_accepts_read_only_query(self, mock_client):
        """Accepts read-only queries."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("MATCH (n) RETURN n")
        assert result['status'] == 'ok'


class TestRunReadonlyCypherEdgeCases:
    """Test edge cases."""

    @patch('src.neo4j.tools.client')
    def test_empty_query(self, mock_client):
        """Handles empty query string."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("")
        assert 'status' in result

    @patch('src.neo4j.tools.client')
    def test_whitespace_query(self, mock_client):
        """Handles whitespace-only query."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        result = run_readonly_cypher("   ")
        assert 'status' in result

    @patch('src.neo4j.tools.client')
    def test_complex_query(self, mock_client):
        """Handles complex query."""
        mock_client._validate_read_only.return_value = True
        mock_client.explain.return_value = True
        mock_client.run_read_query.return_value = ([], MagicMock())
        
        complex_query = """
        MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[:ORDERS]-(o:Order)
        WHERE s.supplierID = '1'
        RETURN p.productName, sum(o.quantity) as total
        ORDER BY total DESC
        LIMIT 10
        """
        result = run_readonly_cypher(complex_query)
        assert result['status'] == 'ok'
        assert result['query'] == complex_query

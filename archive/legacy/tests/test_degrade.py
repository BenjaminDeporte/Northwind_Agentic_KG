"""
Unit tests for degrade node (Phase 2, Item 2.7).

Contract: PROJECT.md §2 — degrade node
PLAN.md 2.7 — reached on MAX_STEPS exhaustion

Testing strategy: Mocked, deterministic, no API calls.
"""

import pytest

from src.agents.nodes import degrade
from src.agents.state import ROUTE_DEGRADE, MAX_STEPS


class TestDegradeBasic:
    """Test basic degrade functionality."""

    def test_routes_to_degrade(self):
        """degrade sets route to ROUTE_DEGRADE."""
        state = {
            'question': "Test",
            'route': '',
            'loop_count': MAX_STEPS,
            'trace': [],
        }
        result = degrade(state)
        assert result['route'] == ROUTE_DEGRADE

    def test_sets_confidence_cap(self):
        """degrade sets confidence to hard cap 0.4."""
        state = {
            'question': "Test",
            'route': '',
            'loop_count': MAX_STEPS,
            'trace': [],
        }
        result = degrade(state)
        assert result['confidence'] == 0.4

    def test_sets_confidence_rationale(self):
        """degrade sets confidence_rationale with truncation disclosure."""
        state = {
            'question': "Test",
            'route': '',
            'loop_count': MAX_STEPS,
            'trace': [],
        }
        result = degrade(state)
        assert 'Hard cap 0.4' in result['confidence_rationale']
        assert 'budget exhausted' in result['confidence_rationale']
        assert 'truncation disclosure mandatory' in result['confidence_rationale']

    def test_sets_answer_with_disclosure(self):
        """degrade sets answer with explicit truncation disclosure."""
        state = {
            'question': "Test",
            'route': '',
            'loop_count': MAX_STEPS,
            'trace': [],
        }
        result = degrade(state)
        assert 'Truncated' in result['answer']
        assert 'maximum steps' in result['answer']
        assert 'MAX_STEPS' in result['answer']

    def test_sets_error(self):
        """degrade sets error field."""
        state = {
            'question': "Test",
            'route': '',
            'loop_count': MAX_STEPS,
            'trace': [],
        }
        result = degrade(state)
        assert result['error'] is not None
        assert 'Budget exhausted' in result['error']


class TestDegradeInvariants:
    """Test degrade invariants."""

    def test_uses_loop_count_in_message(self):
        """Degrade message includes the actual loop_count."""
        state = {
            'question': "Test",
            'route': '',
            'loop_count': MAX_STEPS + 1,
            'trace': [],
        }
        result = degrade(state)
        # The message includes the loop_count in the text "after {loop_count} iterations"
        assert f'{MAX_STEPS + 1} iterations' in result['answer']

    def test_preserves_state_fields(self):
        """Non-route fields are preserved or updated."""
        state = {
            'question': "Test question",
            'route': 'agent',
            'loop_count': MAX_STEPS,
            'trace': [{'step': 1, 'tool_name': 'test', 'args': {}, 'mode': 'curated', 'status': 'ok', 'result_rows': 1, 'cypher': None, 'latency_ms': 100, 'retry_count': 0}],
        }
        result = degrade(state)
        
        assert result['question'] == "Test question"
        assert result['loop_count'] == MAX_STEPS
        assert result['trace'] == state['trace']

    def test_overrides_previous_route(self):
        """degrade overrides any previous route value."""
        state = {
            'question': "Test",
            'route': 'agent',
            'loop_count': MAX_STEPS,
            'trace': [],
        }
        result = degrade(state)
        assert result['route'] == ROUTE_DEGRADE

    def test_overrides_previous_confidence(self):
        """degrade overrides any previous confidence value with 0.4."""
        state = {
            'question': "Test",
            'route': 'agent',
            'loop_count': MAX_STEPS,
            'confidence': 0.9,
            'trace': [],
        }
        result = degrade(state)
        assert result['confidence'] == 0.4


class TestDegradeEdgeCases:
    """Test edge cases for degrade."""

    def test_zero_loop_count(self):
        """degrade works even with loop_count=0 (though shouldn't happen)."""
        state = {
            'question': "Test",
            'route': '',
            'loop_count': 0,
            'trace': [],
        }
        result = degrade(state)
        assert result['route'] == ROUTE_DEGRADE
        assert result['confidence'] == 0.4

    def test_empty_state(self):
        """degrade handles minimal state."""
        state = {'loop_count': MAX_STEPS}
        result = degrade(state)
        assert result['route'] == ROUTE_DEGRADE
        assert result['confidence'] == 0.4

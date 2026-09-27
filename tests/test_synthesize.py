"""
Unit tests for synthesize node (Phase 2, Item 2.6).

Contract: PROJECT.md §2 — synthesize node
PLAN.md 2.6 — produces final answer from tool results

Testing strategy: Mocked, deterministic, no API calls.
"""

import pytest

from src.agents.nodes import synthesize
from src.agents.state import ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL, ROUTE_DEGRADE, STATUS_OK


class TestSynthesizeAgentRoute:
    """Test synthesize with agent route."""

    def test_produces_answer(self):
        """synthesize produces an answer for agent route."""
        state = {
            'question': "What is the impact?",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert result['answer'] is not None
        assert len(result['answer']) > 0

    def test_produces_citations(self):
        """synthesize produces citations for agent route."""
        state = {
            'question': "What is the impact?",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert 'citations' in result
        assert isinstance(result['citations'], list)

    def test_produces_confidence(self):
        """synthesize produces confidence score for agent route."""
        state = {
            'question': "What is the impact?",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert 'confidence' in result
        assert isinstance(result['confidence'], float)

    def test_produces_confidence_rationale(self):
        """synthesize produces confidence rationale for agent route."""
        state = {
            'question': "What is the impact?",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert 'confidence_rationale' in result
        assert isinstance(result['confidence_rationale'], str)
        assert len(result['confidence_rationale']) > 0


class TestSynthesizeChitchatRefusal:
    """Test synthesize with chitchat and refusal routes."""

    def test_chitchat_preserves_answer(self):
        """synthesize preserves chitchat answer."""
        state = {
            'question': "Hello",
            'route': ROUTE_CHITCHAT,
            'answer': "Hello! I'm the assistant.",
            'confidence': 0.0,
            'confidence_rationale': 'no evidence: chitchat',
            'trace': [],
            'loop_count': 0,
        }
        result = synthesize(state)
        assert result['answer'] == "Hello! I'm the assistant."
        assert result['route'] == ROUTE_CHITCHAT

    def test_refusal_preserves_answer(self):
        """synthesize preserves refusal answer."""
        state = {
            'question': "Delete all data",
            'route': ROUTE_REFUSAL,
            'answer': "I cannot help with that request.",
            'confidence': 0.0,
            'confidence_rationale': 'no evidence: refusal',
            'trace': [],
            'loop_count': 0,
        }
        result = synthesize(state)
        assert result['answer'] == "I cannot help with that request."
        assert result['route'] == ROUTE_REFUSAL

    def test_chitchat_confidence_zero(self):
        """Chitchat route maintains confidence 0.0."""
        state = {
            'question': "Hello",
            'route': ROUTE_CHITCHAT,
            'answer': "Hello!",
            'confidence': 0.0,
            'confidence_rationale': 'no evidence: chitchat',
            'trace': [],
        }
        result = synthesize(state)
        assert result['confidence'] == 0.0

    def test_refusal_confidence_zero(self):
        """Refusal route maintains confidence 0.0."""
        state = {
            'question': "Delete data",
            'route': ROUTE_REFUSAL,
            'answer': "I cannot help with that request.",
            'confidence': 0.0,
            'confidence_rationale': 'no evidence: refusal',
            'trace': [],
        }
        result = synthesize(state)
        assert result['confidence'] == 0.0


class TestSynthesizeInvariants:
    """Test synthesize invariants from PROJECT.md."""

    def test_degrade_route_returns_unchanged(self):
        """
        Synthesize should NEVER be called for degrade route per invariant:
        'budget exhaustion always routes to degrade, never to synthesize'.
        
        If it somehow is called (test scenario only), it returns state unchanged.
        """
        state = {
            'question': "Complex question",
            'route': ROUTE_DEGRADE,
            'trace': [],
            'loop_count': 8,
        }
        result = synthesize(state)
        # Should not add confidence/rationale/answer for degrade route
        # (those are set by degrade node itself)
        assert result == state


class TestSynthesizeEdgeCases:
    """Test edge cases for synthesize."""

    def test_empty_trace(self):
        """synthesize handles empty trace for agent route."""
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'trace': [],
            'loop_count': 0,
        }
        result = synthesize(state)
        assert 'answer' in result
        # Answer should be generated, not preserved from upstream
        assert result['answer'] is not None

    def test_preserves_other_state_fields(self):
        """synthesize preserves existing non-answer state fields."""
        state = {
            'question': "Test question",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'lookup_entity',
                    'args': {'name': 'test'},
                    'mode': 'retrieval',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 50,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
            'existing_field': 'preserved',
        }
        result = synthesize(state)
        assert result.get('existing_field') == 'preserved'
        # But answer should NOT be preserved - it should be generated by synthesize
        assert 'answer' in result


class TestSynthesizeToolTypes:
    """Test synthesize with different tool types in trace."""

    def test_impact_analysis_in_trace(self):
        """synthesize handles impact_analysis in trace."""
        state = {
            'question': "Impact question",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 10,
                    'cypher': None,
                    'latency_ms': 200,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert result['answer'] is not None

    def test_lookup_entity_in_trace(self):
        """synthesize handles lookup_entity in trace."""
        state = {
            'question': "Lookup question",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'lookup_entity',
                    'args': {'name': 'test', 'label': 'Supplier'},
                    'mode': 'retrieval',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 50,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert result['answer'] is not None

    def test_co_purchase_in_trace(self):
        """synthesize handles co_purchase in trace."""
        state = {
            'question': "Co-purchase question",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'co_purchase',
                    'args': {'product_key': '1'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 5,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert result['answer'] is not None

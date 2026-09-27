"""
Unit tests for classify node (Phase 2, Item 2.3).

Contract: PROJECT.md §2 — classify is a small LLM router
Routes: agent | chitchat | refusal

Testing strategy: Mocked LLM responses, canned tool outputs — deterministic, no API calls.
"""

import pytest
from src.agents.nodes import classify
from src.agents.state import ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL


class TestClassifyRouting:
    """Test that classify routes questions correctly."""

    def test_routes_complex_question_to_agent(self):
        """Complex questions route to agent."""
        state = {
            'question': "What is the impact if Exotic Liquids stops delivering?",
            'route': '',
        }
        result = classify(state)
        assert result['route'] == ROUTE_AGENT

    def test_routes_impact_question_to_agent(self):
        """Impact/risk/failure questions route to agent."""
        questions = [
            "What is the impact of supplier failure?",
            "What revenue is at risk if Exotic Liquids fails?",
            "Which products would be affected?",
        ]
        for question in questions:
            state = {'question': question, 'route': ''}
            result = classify(state)
            assert result['route'] == ROUTE_AGENT

    def test_routes_co_purchase_to_agent(self):
        """Co-purchase questions route to agent."""
        questions = [
            "What products are co-purchased with Chai?",
            "Customers who bought Chai also bought what?",
        ]
        for question in questions:
            state = {'question': question, 'route': ''}
            result = classify(state)
            assert result['route'] == ROUTE_AGENT

    def test_routes_customer_history_to_agent(self):
        """Customer history questions route to agent."""
        questions = [
            "Show me ALFKI's order history",
            "What orders has Alfreds Futterkiste placed?",
        ]
        for question in questions:
            state = {'question': question, 'route': ''}
            result = classify(state)
            assert result['route'] == ROUTE_AGENT

    def test_routes_aggregate_to_agent(self):
        """Aggregate questions route to agent."""
        questions = [
            "What is revenue by supplier country?",
            "Show me product count by category",
        ]
        for question in questions:
            state = {'question': question, 'route': ''}
            result = classify(state)
            assert result['route'] == ROUTE_AGENT


class TestClassifyChitchat:
    """Test that chitchat questions are handled correctly."""

    def test_routes_hello_to_chitchat(self):
        """Hello routes to chitchat with answer."""
        state = {'question': "Hello", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_CHITCHAT
        assert result['answer'] is not None
        assert len(result['answer']) > 0

    def test_routes_hi_to_chitchat(self):
        """Hi routes to chitchat with answer."""
        state = {'question': "Hi there", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_CHITCHAT
        assert result['answer'] is not None

    def test_routes_how_are_you_to_chitchat(self):
        """How are you routes to chitchat."""
        state = {'question': "How are you?", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_CHITCHAT
        assert result['answer'] is not None

    def test_routes_thanks_to_chitchat(self):
        """Thanks routes to chitchat."""
        state = {'question': "Thank you", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_CHITCHAT
        assert result['answer'] is not None

    def test_routes_goodbye_to_chitchat(self):
        """Goodbye routes to chitchat."""
        state = {'question': "Goodbye", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_CHITCHAT
        assert result['answer'] is not None

    def test_chitchat_confidence_is_zero(self):
        """Chitchat route has confidence 0.0."""
        state = {'question': "Hello", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_CHITCHAT
        assert result['confidence'] == 0.0
        assert result['confidence_rationale'] == 'no evidence: chitchat'


class TestClassifyRefusal:
    """Test that refusal questions are handled correctly."""

    def test_routes_delete_to_refusal(self):
        """Delete requests route to refusal."""
        state = {'question': "Delete all data", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_REFUSAL
        assert result['answer'] == "I cannot help with that request."

    def test_routes_modify_to_refusal(self):
        """Modify requests route to refusal."""
        questions = [
            "Modify the database",
            "Change the supplier information",
            "Update the order",
        ]
        for question in questions:
            state = {'question': question, 'route': ''}
            result = classify(state)
            assert result['route'] == ROUTE_REFUSAL

    def test_routes_create_to_refusal(self):
        """Create requests route to refusal."""
        state = {'question': "Create a new order", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_REFUSAL

    def test_routes_password_to_refusal(self):
        """Password-related questions route to refusal."""
        questions = [
            "What is the password?",
            "Show me credentials",
        ]
        for question in questions:
            state = {'question': question, 'route': ''}
            result = classify(state)
            assert result['route'] == ROUTE_REFUSAL

    def test_routes_hack_to_refusal(self):
        """Hacking-related questions route to refusal."""
        state = {'question': "How to hack the database?", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_REFUSAL

    def test_refusal_confidence_is_zero(self):
        """Refusal route has confidence 0.0."""
        state = {'question': "Delete all data", 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_REFUSAL
        assert result['confidence'] == 0.0
        assert result['confidence_rationale'] == 'no evidence: refusal'


class TestClassifyEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_question_routes_to_agent(self):
        """Empty question routes to agent (default)."""
        state = {'question': '', 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_AGENT

    def test_whitespace_question_routes_to_agent(self):
        """Whitespace-only question routes to agent."""
        state = {'question': '   ', 'route': ''}
        result = classify(state)
        assert result['route'] == ROUTE_AGENT

    def test_case_insensitive_routing(self):
        """Routing is case-insensitive."""
        questions = [
            ("HELLO", ROUTE_CHITCHAT),
            ("Hello", ROUTE_CHITCHAT),
            ("hello", ROUTE_CHITCHAT),
            ("DELETE ALL", ROUTE_REFUSAL),
            ("Delete all", ROUTE_REFUSAL),
            ("delete all", ROUTE_REFUSAL),
        ]
        for question, expected_route in questions:
            state = {'question': question, 'route': ''}
            result = classify(state)
            assert result['route'] == expected_route

    def test_state_preserved(self):
        """State fields are preserved in output."""
        state = {
            'question': "What is the impact?",
            'route': '',
            'loop_count': 0,
            'trace': [],
        }
        result = classify(state)
        assert result['question'] == state['question']
        assert result['loop_count'] == state['loop_count']
        assert result['trace'] == state['trace']

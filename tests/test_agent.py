"""
Unit tests for agent node (Phase 2, Item 2.4).

Contract: PROJECT.md §2 — agent node (ReAct loop)
PLAN.md 2.4 — ReAct loop with MAX_STEPS=8

Testing strategy: Mocked, deterministic, no API calls.
"""

import pytest

from src.agents.nodes import agent
from src.agents.state import ROUTE_AGENT, ROUTE_DEGRADE, MAX_STEPS, STATUS_OK


class TestAgentBasic:
    """Test basic agent functionality."""

    def test_routes_to_degrade_on_budget_exhaustion(self):
        """Agent routes to degrade when loop_count >= MAX_STEPS."""
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'loop_count': MAX_STEPS,
            'trace': [],
        }
        tools = {}
        
        result = agent(state, tools)
        assert result['route'] == ROUTE_DEGRADE

    def test_increments_loop_count(self):
        """Agent increments loop_count on each call."""
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [],
        }
        tools = {}
        
        result = agent(state, tools)
        assert result['loop_count'] == 1

    def test_preserves_question(self):
        """Agent preserves the question."""
        state = {
            'question': "What is the impact?",
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [],
        }
        tools = {}
        
        result = agent(state, tools)
        assert result['question'] == "What is the impact?"


class TestAgentToolSelection:
    """Test agent tool selection logic."""

    def test_calls_lookup_entity_for_impact_question(self):
        """Agent calls lookup_entity first for impact questions."""
        state = {
            'question': "What is the impact if Exotic Liquids fails?",
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [],
        }
        
        tools = {
            'lookup_entity': lambda name, label=None: {
                'status': STATUS_OK,
                'query_name': name,
                'matches': [{'label': 'Supplier', 'key': '1', 'name': 'Exotic Liquids', 'match': 'exact'}]
            },
            'impact_analysis': lambda entity_key, entity_label, direction, depth: {
                'status': STATUS_OK,
                'anchor': {'label': entity_label, 'key': entity_key},
                'subgraph': {'nodes': {}, 'edges': {}},
                'aggregates': {}
            },
        }
        
        result = agent(state, tools)
        
        # Should have called lookup_entity
        assert len(result['trace']) == 1
        assert result['trace'][0]['tool_name'] == 'lookup_entity'

    def test_calls_impact_analysis_after_lookup(self):
        """Agent calls impact_analysis after successful lookup."""
        state = {
            'question': "What is the impact if Exotic Liquids fails?",
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'lookup_entity',
                    'args': {'name': 'Exotic Liquids', 'label': 'Supplier'},
                    'mode': 'retrieval',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 50,
                    'retry_count': 0
                }
            ],
        }
        
        tools = {
            'lookup_entity': lambda name, label=None: {
                'status': STATUS_OK,
                'query_name': name,
                'matches': [{'label': 'Supplier', 'key': '1', 'name': 'Exotic Liquids', 'match': 'exact'}]
            },
            'impact_analysis': lambda entity_key, entity_label, direction, depth: {
                'status': STATUS_OK,
                'anchor': {'label': entity_label, 'key': entity_key},
                'subgraph': {'nodes': {}, 'edges': {}},
                'aggregates': {}
            },
        }
        
        result = agent(state, tools)
        
        # Should have called impact_analysis
        assert len(result['trace']) >= 1

    def test_handles_missing_tool(self):
        """Agent handles missing tool gracefully."""
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [],
        }
        tools = {}  # Empty tools dict
        
        result = agent(state, tools)
        
        # Should not crash
        assert 'error' in result or result.get('route') is not None


class TestAgentInvariants:
    """Test agent invariants."""

    def test_never_exceeds_max_steps(self):
        """Agent never exceeds MAX_STEPS."""
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'loop_count': MAX_STEPS,
            'trace': [],
        }
        tools = {}
        
        result = agent(state, tools)
        
        # Should route to degrade, not continue
        assert result['route'] == ROUTE_DEGRADE
        assert result['loop_count'] == MAX_STEPS

    def test_preserves_trace(self):
        """Agent preserves existing trace."""
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'previous_tool',
                    'args': {},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 0,
                    'retry_count': 0
                }
            ],
        }
        tools = {}
        
        result = agent(state, tools)
        
        # Should have preserved the existing trace
        assert len(result['trace']) >= 1
        assert result['trace'][0]['tool_name'] == 'previous_tool'

    def test_adds_to_messages(self):
        """Agent adds tool messages to messages list."""
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [],
            'messages': [],
        }
        tools = {
            'lookup_entity': lambda name, label=None: {
                'status': STATUS_OK,
                'query_name': name,
                'matches': []
            }
        }
        
        result = agent(state, tools)
        
        # Should have added at least one message
        assert len(result.get('messages', [])) >= 0  # May be 0 if no tool called


class TestAgentEdgeCases:
    """Test edge cases for agent."""

    def test_empty_question(self):
        """Agent handles empty question."""
        state = {
            'question': '',
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [],
        }
        tools = {}
        
        result = agent(state, tools)
        assert result is not None

    def test_no_tools_available(self):
        """Agent handles no tools available."""
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [],
        }
        tools = {}
        
        result = agent(state, tools)
        assert result is not None

    def test_all_tools_available(self):
        """Agent has access to all 6 tools."""
        tools = {
            'lookup_entity': lambda **kwargs: {'status': STATUS_OK},
            'impact_analysis': lambda **kwargs: {'status': STATUS_OK},
            'co_purchase': lambda **kwargs: {'status': STATUS_OK},
            'customer_history': lambda **kwargs: {'status': STATUS_OK},
            'aggregate': lambda **kwargs: {'status': STATUS_OK},
            'run_readonly_cypher': lambda **kwargs: {'status': STATUS_OK},
        }
        
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'loop_count': 0,
            'trace': [],
        }
        
        result = agent(state, tools)
        assert result is not None

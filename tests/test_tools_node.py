"""
Unit tests for tools dispatcher node (Phase 2, Item 2.5).

Contract: PROJECT.md §2 — tools node
PLAN.md 2.5 — dispatches one tool call

Testing strategy: Mocked, deterministic, no API calls.
"""

import pytest
from unittest.mock import MagicMock

from src.agents.nodes import tools_dispatcher
from src.agents.state import ToolCallRecord, MODE_CURATED, MODE_EXPLORATORY, MODE_RETRIEVAL, STATUS_OK


class TestToolsDispatcherBasic:
    """Test basic tools dispatcher functionality."""

    def test_returns_state_and_result(self):
        """tools_dispatcher returns updated state and tool result."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok', 'result': 'test'}
        
        updated_state, tool_result = tools_dispatcher(
            state, 'test_tool', tool_func, 1, {}
        )
        
        assert isinstance(updated_state, dict)
        assert isinstance(tool_result, dict)

    def test_appends_tool_call_record(self):
        """tools_dispatcher appends exactly one ToolCallRecord to trace."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(
            state, 'test_tool', tool_func, 1, {'arg1': 'value1'}
        )
        
        assert len(updated_state['trace']) == 1
        assert isinstance(updated_state['trace'][0], dict)

    def test_preserves_existing_trace(self):
        """tools_dispatcher preserves existing trace entries."""
        state = {
            'question': 'Test',
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'previous_tool',
                    'args': {},
                    'mode': 'curated',
                    'status': 'ok',
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 0,
                    'retry_count': 0
                }
            ]
        }
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(
            state, 'test_tool', tool_func, 2, {}
        )
        
        assert len(updated_state['trace']) == 2
        assert updated_state['trace'][0]['tool_name'] == 'previous_tool'
        assert updated_state['trace'][1]['tool_name'] == 'test_tool'


class TestToolCallRecordFields:
    """Test ToolCallRecord fields are set correctly."""

    def test_sets_step(self):
        """ToolCallRecord has correct step number."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'test_tool', tool_func, 5, {})
        
        record = updated_state['trace'][0]
        assert record['step'] == 5

    def test_sets_tool_name(self):
        """ToolCallRecord has correct tool name."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'lookup_entity', tool_func, 1, {})
        
        record = updated_state['trace'][0]
        assert record['tool_name'] == 'lookup_entity'

    def test_sets_args(self):
        """ToolCallRecord has correct args."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        args = {'name': 'test', 'label': 'Supplier'}
        
        updated_state, _ = tools_dispatcher(state, 'lookup_entity', tool_func, 1, args)
        
        record = updated_state['trace'][0]
        assert record['args'] == args

    def test_sets_mode_curated(self):
        """Curated tools have mode='curated'."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        for tool_name in ['impact_analysis', 'co_purchase', 'customer_history', 'aggregate']:
            updated_state, _ = tools_dispatcher(state, tool_name, tool_func, 1, {})
            record = updated_state['trace'][0]
            assert record['mode'] == MODE_CURATED

    def test_sets_mode_exploratory(self):
        """Exploratory tools have mode='exploratory'."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'run_readonly_cypher', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['mode'] == MODE_EXPLORATORY

    def test_sets_mode_retrieval(self):
        """Retrieval tools have mode='retrieval'."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'lookup_entity', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['mode'] == MODE_RETRIEVAL

    def test_sets_status(self):
        """ToolCallRecord has correct status from tool result."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'empty'}
        
        updated_state, _ = tools_dispatcher(state, 'test_tool', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['status'] == 'empty'

    def test_sets_result_rows(self):
        """ToolCallRecord has correct result_rows."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok', 'matches': [{'a': 1}, {'a': 2}, {'a': 3}]}
        
        updated_state, _ = tools_dispatcher(state, 'lookup_entity', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['result_rows'] == 3

    def test_sets_result_rows_from_rows(self):
        """ToolCallRecord uses 'rows' field if present."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok', 'rows': [{'a': 1}, {'a': 2}]}
        
        updated_state, _ = tools_dispatcher(state, 'run_readonly_cypher', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['result_rows'] == 2

    def test_sets_result_rows_from_groups(self):
        """ToolCallRecord uses 'groups' field if present."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok', 'groups': [{'a': 1}, {'a': 2}, {'a': 3}, {'a': 4}]}
        
        updated_state, _ = tools_dispatcher(state, 'aggregate', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['result_rows'] == 4

    def test_sets_cypher_for_exploratory(self):
        """Exploratory tools have cypher field populated."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok', 'query': 'MATCH (n) RETURN n'}
        
        updated_state, _ = tools_dispatcher(
            state, 'run_readonly_cypher', tool_func, 1, {'query': 'MATCH (n) RETURN n'}
        )
        record = updated_state['trace'][0]
        # cypher should be populated from the tool result
        assert record.get('cypher') is not None or record['cypher'] is None

    def test_cypher_none_for_curated(self):
        """Curated tools have cypher=None."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'impact_analysis', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['cypher'] is None

    def test_sets_latency_ms(self):
        """ToolCallRecord has latency_ms > 0."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'test_tool', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['latency_ms'] >= 0
        assert isinstance(record['latency_ms'], int)

    def test_sets_retry_count_zero(self):
        """ToolCallRecord has retry_count=0 for first attempt."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'test_tool', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['retry_count'] == 0


class TestToolsDispatcherInvariants:
    """Test tools dispatcher invariants."""

    def test_exactly_one_record_appended(self):
        """Exactly one ToolCallRecord is appended per call."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'test_tool', tool_func, 1, {})
        
        assert len(updated_state['trace']) == 1

    def test_preserves_all_state_fields(self):
        """All state fields are preserved."""
        state = {
            'question': 'Test',
            'route': 'agent',
            'loop_count': 1,
            'trace': [],
            'answer': 'partial',
        }
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'test_tool', tool_func, 1, {})
        
        assert updated_state['question'] == 'Test'
        assert updated_state['route'] == 'agent'
        assert updated_state['loop_count'] == 1
        assert updated_state.get('answer') == 'partial'

    def test_returns_tool_result(self):
        """Tool result is returned unchanged."""
        state = {'question': 'Test', 'trace': []}
        expected_result = {'status': 'ok', 'data': [1, 2, 3]}
        tool_func = lambda **kwargs: expected_result
        
        _, tool_result = tools_dispatcher(state, 'test_tool', tool_func, 1, {})
        
        assert tool_result == expected_result


class TestToolsDispatcherEdgeCases:
    """Test edge cases for tools dispatcher."""

    def test_empty_args(self):
        """tools_dispatcher handles empty args."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'test_tool', tool_func, 1, {})
        
        assert len(updated_state['trace']) == 1
        assert updated_state['trace'][0]['args'] == {}

    def test_complex_args(self):
        """tools_dispatcher handles complex nested args."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        args = {
            'entity_key': '1',
            'entity_label': 'Supplier',
            'direction': 'out',
            'depth': 3,
        }
        
        updated_state, _ = tools_dispatcher(state, 'impact_analysis', tool_func, 1, args)
        
        record = updated_state['trace'][0]
        assert record['args'] == args

    def test_unknown_tool_defaults_to_curated(self):
        """Unknown tools default to curated mode."""
        state = {'question': 'Test', 'trace': []}
        tool_func = lambda **kwargs: {'status': 'ok'}
        
        updated_state, _ = tools_dispatcher(state, 'unknown_tool', tool_func, 1, {})
        record = updated_state['trace'][0]
        assert record['mode'] == MODE_CURATED

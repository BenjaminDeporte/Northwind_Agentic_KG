"""
Unit tests for run-log (Phase 2, Item 2.10).

Contract: PROJECT.md §6 — Run-log (JSONL)
PLAN.md 2.10 — JSONL appender

Testing strategy: Mocked, deterministic, no API calls.
"""

import os
import json
import tempfile
import pytest
from datetime import datetime

from src.utils.runlog import write_run, read_runlog, clear_runlog, RUNLOG_PATH


@pytest.fixture(autouse=True)
def setup_teardown_runlog():
    """Setup and teardown for runlog tests."""
    # Save original path
    original_path = os.environ.get("RUNLOG_PATH")
    
    # Use a temp file for testing
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        temp_path = f.name
    
    os.environ["RUNLOG_PATH"] = temp_path
    
    yield
    
    # Cleanup
    if original_path:
        os.environ["RUNLOG_PATH"] = original_path
    else:
        os.environ.pop("RUNLOG_PATH", None)
    
    if os.path.exists(temp_path):
        os.remove(temp_path)


class TestWriteRun:
    """Test write_run functionality."""

    def test_writes_valid_jsonl(self):
        """write_run produces valid JSONL."""
        clear_runlog()
        
        state = {
            'question': "Test question",
            'route': "agent",
            'trace': [],
            'answer': "Test answer",
            'citations': [],
            'confidence': 0.9,
            'confidence_rationale': "All curated tools succeeded",
            'loop_count': 2,
            'error': None,
        }
        
        write_run(state)
        
        runs = read_runlog()
        assert len(runs) == 1
        
        # Verify it's valid JSON
        entry = runs[0]
        assert isinstance(entry, dict)
        
    def test_writes_all_required_fields(self):
        """write_run writes all required fields."""
        clear_runlog()
        
        state = {
            'question': "Test question",
            'route': "agent",
            'trace': [{'step': 1, 'tool_name': 'test', 'args': {}, 'mode': 'curated', 
                       'status': 'ok', 'result_rows': 1, 'cypher': None, 
                       'latency_ms': 100, 'retry_count': 0}],
            'answer': "Test answer",
            'citations': [{'label': 'Product', 'key': '1', 'name': 'Chai'}],
            'confidence': 0.9,
            'confidence_rationale': "All curated tools succeeded",
            'loop_count': 2,
            'error': None,
        }
        
        write_run(state)
        
        runs = read_runlog()
        entry = runs[0]
        
        required_fields = [
            'ts', 'question', 'route', 'trace', 'hops', 'answer',
            'citations', 'confidence', 'confidence_rationale', 'latency_ms_total'
        ]
        
        for field in required_fields:
            assert field in entry, f"Missing required field: {field}"

    def test_calculates_latency_ms_total(self):
        """latency_ms_total is sum of all trace latencies."""
        clear_runlog()
        
        state = {
            'question': "Test",
            'route': "agent",
            'trace': [
                {'latency_ms': 100, 'step': 1, 'tool_name': 'test1', 'args': {}, 
                 'mode': 'curated', 'status': 'ok', 'result_rows': 1, 
                 'cypher': None, 'retry_count': 0},
                {'latency_ms': 200, 'step': 2, 'tool_name': 'test2', 'args': {}, 
                 'mode': 'curated', 'status': 'ok', 'result_rows': 1, 
                 'cypher': None, 'retry_count': 0},
            ],
            'answer': "Test",
            'citations': [],
            'confidence': 0.9,
            'confidence_rationale': "test",
            'loop_count': 2,
            'error': None,
        }
        
        write_run(state)
        
        runs = read_runlog()
        entry = runs[0]
        
        assert entry['latency_ms_total'] == 300

    def test_calculates_hops_correctly(self):
        """hops is length of trace."""
        clear_runlog()
        
        state = {
            'question': "Test",
            'route': "agent",
            'trace': [
                {'step': 1, 'tool_name': 't1', 'args': {}, 'mode': 'curated',
                 'status': 'ok', 'result_rows': 1, 'cypher': None, 'retry_count': 0, 'latency_ms': 0},
                {'step': 2, 'tool_name': 't2', 'args': {}, 'mode': 'curated',
                 'status': 'ok', 'result_rows': 1, 'cypher': None, 'retry_count': 0, 'latency_ms': 0},
                {'step': 3, 'tool_name': 't3', 'args': {}, 'mode': 'curated',
                 'status': 'ok', 'result_rows': 1, 'cypher': None, 'retry_count': 0, 'latency_ms': 0},
            ],
            'answer': "Test",
            'citations': [],
            'confidence': 0.9,
            'confidence_rationale': "test",
            'loop_count': 3,
            'error': None,
        }
        
        write_run(state)
        
        runs = read_runlog()
        entry = runs[0]
        
        assert entry['hops'] == 3

    def test_append_only(self):
        """Multiple writes append to the same file."""
        clear_runlog()
        
        for i in range(3):
            state = {
                'question': f"Question {i}",
                'route': "agent",
                'trace': [],
                'answer': f"Answer {i}",
                'citations': [],
                'confidence': 0.9,
                'confidence_rationale': "test",
                'loop_count': 1,
                'error': None,
            }
            write_run(state)
        
        runs = read_runlog()
        assert len(runs) == 3

    def test_ts_is_iso_format(self):
        """ts field is ISO 8601 format."""
        clear_runlog()
        
        state = {
            'question': "Test",
            'route': "agent",
            'trace': [],
            'answer': "Test",
            'citations': [],
            'confidence': 0.9,
            'confidence_rationale': "test",
            'loop_count': 1,
            'error': None,
        }
        
        write_run(state)
        
        runs = read_runlog()
        entry = runs[0]
        
        # Should be ISO format with timezone
        ts = entry['ts']
        assert 'T' in ts
        assert ':' in ts


class TestReadRunlog:
    """Test read_runlog functionality."""

    def test_reads_empty_file(self):
        """read_runlog returns empty list for non-existent file."""
        clear_runlog()
        runs = read_runlog()
        assert runs == []

    def test_reads_multiple_entries(self):
        """read_runlog reads all entries from file."""
        clear_runlog()
        
        for i in range(5):
            state = {
                'question': f"Q{i}",
                'route': "agent",
                'trace': [],
                'answer': f"A{i}",
                'citations': [],
                'confidence': 0.9,
                'confidence_rationale': "test",
                'loop_count': 1,
                'error': None,
            }
            write_run(state)
        
        runs = read_runlog()
        assert len(runs) == 5


class TestClearRunlog:
    """Test clear_runlog functionality."""

    def test_clears_file(self):
        """clear_runlog removes the file."""
        clear_runlog()
        
        state = {
            'question': "Test",
            'route': "agent",
            'trace': [],
            'answer': "Test",
            'citations': [],
            'confidence': 0.9,
            'confidence_rationale': "test",
            'loop_count': 1,
            'error': None,
        }
        write_run(state)
        
        assert len(read_runlog()) == 1
        
        clear_runlog()
        
        assert len(read_runlog()) == 0


class TestRunlogInvariants:
    """Test run-log invariants."""

    def test_all_routes_written(self):
        """All route types are written correctly."""
        clear_runlog()
        
        routes = ['agent', 'chitchat', 'refusal', 'degrade']
        
        for route in routes:
            state = {
                'question': f"Test {route}",
                'route': route,
                'trace': [],
                'answer': f"Answer for {route}",
                'citations': [],
                'confidence': 0.0 if route in ['chitchat', 'refusal'] else 0.9,
                'confidence_rationale': 'no evidence' if route in ['chitchat', 'refusal'] else 'test',
                'loop_count': 0,
                'error': None,
            }
            write_run(state)
        
        runs = read_runlog()
        assert len(runs) == 4
        
        for run in runs:
            assert run['route'] in routes

    def test_empty_trace_handled(self):
        """Empty trace is handled correctly."""
        clear_runlog()
        
        state = {
            'question': "Test",
            'route': "chitchat",
            'trace': [],
            'answer': "Hello!",
            'citations': [],
            'confidence': 0.0,
            'confidence_rationale': 'no evidence: chitchat',
            'loop_count': 0,
            'error': None,
        }
        
        write_run(state)
        
        runs = read_runlog()
        entry = runs[0]
        
        assert entry['hops'] == 0
        assert entry['latency_ms_total'] == 0

    def test_preserves_state_fields(self):
        """All state fields are preserved in the run log."""
        clear_runlog()
        
        state = {
            'question': "What is the impact?",
            'route': "agent",
            'trace': [{'step': 1, 'tool_name': 'impact_analysis', 'args': {'entity_key': '1', 'entity_label': 'Supplier'}, 'mode': 'curated', 'status': 'ok', 'result_rows': 10, 'cypher': None, 'latency_ms': 500, 'retry_count': 0}],
            'answer': "Revenue at risk: $35,916.80",
            'citations': [{'label': 'Supplier', 'key': '1', 'name': 'Exotic Liquids'}],
            'confidence': 0.9,
            'confidence_rationale': "Curated tool succeeded",
            'loop_count': 2,
            'error': None,
        }
        
        write_run(state)
        
        runs = read_runlog()
        entry = runs[0]
        
        assert entry['question'] == "What is the impact?"
        assert entry['route'] == "agent"
        assert entry['answer'] == "Revenue at risk: $35,916.80"
        assert len(entry['trace']) == 1
        assert len(entry['citations']) == 1
        assert entry['confidence'] == 0.9

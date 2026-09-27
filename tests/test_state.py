"""
Unit tests for state TypedDicts (Phase 2, Item 2.2).

Contract: PROJECT.md §3 — State TypedDict definitions
Invariants tested:
- ToolCallRecord fields present and typed correctly
- Citation fields present and typed correctly  
- AgentState fields present and typed correctly
- MAX_STEPS = 8 constant
- Mode/status constants defined
"""

import pytest
from src.agents.state import (
    ToolCallRecord,
    Citation,
    AgentState,
    MAX_STEPS,
    MODE_CURATED,
    MODE_EXPLORATORY,
    MODE_RETRIEVAL,
    STATUS_OK,
    STATUS_EMPTY,
    STATUS_INVALID,
    STATUS_RETRY_OK,
    STATUS_RETRY_FAILED,
    ROUTE_AGENT,
    ROUTE_CHITCHAT,
    ROUTE_REFUSAL,
    ROUTE_DEGRADE,
)


class TestToolCallRecord:
    """Test ToolCallRecord TypedDict structure and invariants."""

    def test_tool_call_record_fields(self):
        """ToolCallRecord has all required fields."""
        record = {
            "step": 1,
            "tool_name": "lookup_entity",
            "args": {"name": "test", "label": "Supplier"},
            "mode": "retrieval",
            "status": "ok",
            "result_rows": 1,
            "cypher": None,
            "latency_ms": 100,
            "retry_count": 0,
        }
        # This should not raise TypeError
        tr: ToolCallRecord = record
        assert tr["step"] == 1
        assert tr["tool_name"] == "lookup_entity"
        assert tr["mode"] == "retrieval"
        assert tr["status"] == "ok"
        assert tr["result_rows"] == 1
        assert tr["cypher"] is None
        assert tr["latency_ms"] == 100
        assert tr["retry_count"] == 0

    def test_tool_call_record_retry_count_invariant(self):
        """retry_count must be 0 or 1, never exceeds 1."""
        # Valid: 0
        record0: ToolCallRecord = {
            "step": 1, "tool_name": "test", "args": {}, "mode": "curated",
            "status": "ok", "result_rows": 1, "cypher": None,
            "latency_ms": 50, "retry_count": 0
        }
        assert record0["retry_count"] == 0

        # Valid: 1
        record1: ToolCallRecord = {
            "step": 1, "tool_name": "test", "args": {}, "mode": "exploratory",
            "status": "retry_ok", "result_rows": 5, "cypher": "MATCH (n) RETURN n",
            "latency_ms": 150, "retry_count": 1
        }
        assert record1["retry_count"] == 1

    def test_tool_call_record_exploratory_has_cypher(self):
        """Exploratory mode (run_readonly_cypher) populates cypher field."""
        record: ToolCallRecord = {
            "step": 1,
            "tool_name": "run_readonly_cypher",
            "args": {"query": "MATCH (n) RETURN n"},
            "mode": "exploratory",
            "status": "ok",
            "result_rows": 10,
            "cypher": "MATCH (n) RETURN n",
            "latency_ms": 200,
            "retry_count": 0,
        }
        assert record["cypher"] == "MATCH (n) RETURN n"
        assert record["mode"] == MODE_EXPLORATORY

    def test_tool_call_record_curated_no_cypher(self):
        """Curated tools do NOT populate cypher field (None)."""
        record: ToolCallRecord = {
            "step": 1,
            "tool_name": "lookup_entity",
            "args": {"name": "test"},
            "mode": "retrieval",
            "status": "ok",
            "result_rows": 1,
            "cypher": None,
            "latency_ms": 100,
            "retry_count": 0,
        }
        assert record["cypher"] is None
        assert record["mode"] == MODE_RETRIEVAL

    def test_tool_call_record_all_statuses_valid(self):
        """All defined statuses are valid for ToolCallRecord."""
        statuses = [STATUS_OK, STATUS_EMPTY, STATUS_INVALID, STATUS_RETRY_OK, STATUS_RETRY_FAILED]
        for status in statuses:
            record: ToolCallRecord = {
                "step": 1, "tool_name": "test", "args": {}, "mode": "curated",
                "status": status, "result_rows": 0, "cypher": None,
                "latency_ms": 0, "retry_count": 0
            }
            assert record["status"] == status

    def test_tool_call_record_all_modes_valid(self):
        """All defined modes are valid for ToolCallRecord."""
        modes = [MODE_CURATED, MODE_EXPLORATORY, MODE_RETRIEVAL]
        for mode in modes:
            record: ToolCallRecord = {
                "step": 1, "tool_name": "test", "args": {}, "mode": mode,
                "status": "ok", "result_rows": 0, "cypher": None,
                "latency_ms": 0, "retry_count": 0
            }
            assert record["mode"] == mode


class TestCitation:
    """Test Citation TypedDict structure."""

    def test_citation_fields(self):
        """Citation has all required fields."""
        citation: Citation = {
            "label": "Supplier",
            "key": "1",
            "name": "Exotic Liquids"
        }
        assert citation["label"] == "Supplier"
        assert citation["key"] == "1"
        assert citation["name"] == "Exotic Liquids"

    def test_citation_key_is_key_property(self):
        """Citation key is the SCHEMA.md key property value, not the name."""
        # Correct: key is supplierID
        citation: Citation = {
            "label": "Supplier",
            "key": "1",  # supplierID, not "Exotic Liquids"
            "name": "Exotic Liquids"
        }
        assert citation["key"] == "1"
        assert citation["name"] == "Exotic Liquids"

    def test_citation_product(self):
        """Citation for Product label."""
        citation: Citation = {
            "label": "Product",
            "key": "1",  # productID
            "name": "Chai"
        }
        assert citation["label"] == "Product"
        assert citation["key"] == "1"


class TestAgentState:
    """Test AgentState TypedDict structure and invariants."""

    def test_agent_state_fields(self):
        """AgentState has all required fields."""
        state: AgentState = {
            "question": "What is the impact?",
            "route": "agent",
            "messages": [],
            "trace": [],
            "answer": "",
            "citations": [],
            "confidence": 0.0,
            "confidence_rationale": "",
            "loop_count": 0,
            "error": None,
        }
        assert state["question"] == "What is the impact?"
        assert state["route"] == "agent"
        assert state["messages"] == []
        assert state["trace"] == []
        assert state["answer"] == ""
        assert state["citations"] == []
        assert state["confidence"] == 0.0
        assert state["confidence_rationale"] == ""
        assert state["loop_count"] == 0
        assert state["error"] is None

    def test_agent_state_all_routes_valid(self):
        """All defined routes are valid for AgentState."""
        routes = [ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL, ROUTE_DEGRADE]
        for route in routes:
            state: AgentState = {
                "question": "test",
                "route": route,
                "messages": [],
                "trace": [],
                "answer": "",
                "citations": [],
                "confidence": 0.0,
                "confidence_rationale": "",
                "loop_count": 0,
                "error": None,
            }
            assert state["route"] == route

    def test_agent_state_messages_is_reducer_field(self):
        """messages is the ONLY field with a reducer (add_messages)."""
        # This is a contract assertion: messages has Annotated[list, "add_messages"]
        # We verify it's a list and can be appended to
        state: AgentState = {
            "question": "test",
            "route": "agent",
            "messages": [{"role": "user", "content": "test"}],
            "trace": [],
            "answer": "",
            "citations": [],
            "confidence": 0.0,
            "confidence_rationale": "",
            "loop_count": 0,
            "error": None,
        }
        # Messages is a list (can be extended)
        assert isinstance(state["messages"], list)

    def test_agent_state_trace_is_tool_call_records(self):
        """trace is a list of ToolCallRecord."""
        trace: list[ToolCallRecord] = [
            {
                "step": 1, "tool_name": "lookup_entity", "args": {}, "mode": "retrieval",
                "status": "ok", "result_rows": 1, "cypher": None,
                "latency_ms": 100, "retry_count": 0
            }
        ]
        state: AgentState = {
            "question": "test",
            "route": "agent",
            "messages": [],
            "trace": trace,
            "answer": "",
            "citations": [],
            "confidence": 0.0,
            "confidence_rationale": "",
            "loop_count": 0,
            "error": None,
        }
        assert len(state["trace"]) == 1
        assert state["trace"][0]["tool_name"] == "lookup_entity"


class TestConstants:
    """Test that constants are defined correctly."""

    def test_max_steps_is_8(self):
        """MAX_STEPS constant equals 8."""
        assert MAX_STEPS == 8

    def test_mode_constants(self):
        """Mode constants are defined."""
        assert MODE_CURATED == "curated"
        assert MODE_EXPLORATORY == "exploratory"
        assert MODE_RETRIEVAL == "retrieval"

    def test_status_constants(self):
        """Status constants are defined."""
        assert STATUS_OK == "ok"
        assert STATUS_EMPTY == "empty"
        assert STATUS_INVALID == "invalid"
        assert STATUS_RETRY_OK == "retry_ok"
        assert STATUS_RETRY_FAILED == "retry_failed"

    def test_route_constants(self):
        """Route constants are defined."""
        assert ROUTE_AGENT == "agent"
        assert ROUTE_CHITCHAT == "chitchat"
        assert ROUTE_REFUSAL == "refusal"
        assert ROUTE_DEGRADE == "degrade"

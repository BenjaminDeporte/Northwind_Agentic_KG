"""
Unit tests for confidence rubric (Phase 2, Item 2.9).

Contract: PROJECT.md §5, PLAN.md 2.9
Signature: compute_confidence(trace: list[ToolCallRecord], route: str) -> tuple[float, str]

Invariants tested:
- Route-dependent rules (degrade=0.4, chitchat/refusal=0.0)
- Min-of-caps for agent route
- Retrieval tools never set the floor
- Correct caps for each tool mode/status combination
- Rationale format matches contract
"""

import pytest
from src.agents.rubric import compute_confidence, format_confidence
from src.agents.state import ToolCallRecord, ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL, ROUTE_DEGRADE, MODE_CURATED, MODE_EXPLORATORY, MODE_RETRIEVAL, STATUS_OK, STATUS_EMPTY, STATUS_INVALID, STATUS_RETRY_OK, STATUS_RETRY_FAILED


class TestRouteDependentRules:
    """Test route-dependent confidence rules."""

    def test_degrade_hard_cap_04(self):
        """Route=degrade → hard cap 0.4, overrides min-of-caps."""
        trace = []
        confidence, rationale = compute_confidence(trace, ROUTE_DEGRADE)
        assert confidence == 0.4
        assert "Hard cap 0.4" in rationale
        assert "budget exhausted" in rationale
        assert "MAX_STEPS=8" in rationale

    def test_degrade_with_calls_still_04(self):
        """Degrade cap overrides even if trace has high-confidence calls."""
        trace = [
            {"step": 1, "tool_name": "lookup_entity", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 100, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_DEGRADE)
        assert confidence == 0.4
        assert "Hard cap 0.4" in rationale

    def test_chitchat_confidence_0(self):
        """Route=chitchat → confidence=0.0, rationale='no evidence: chitchat'."""
        trace = []
        confidence, rationale = compute_confidence(trace, ROUTE_CHITCHAT)
        assert confidence == 0.0
        assert rationale == "no evidence: chitchat"

    def test_refusal_confidence_0(self):
        """Route=refusal → confidence=0.0, rationale='no evidence: refusal'."""
        trace = []
        confidence, rationale = compute_confidence(trace, ROUTE_REFUSAL)
        assert confidence == 0.0
        assert rationale == "no evidence: refusal"

    def test_invalid_route_raises(self):
        """Invalid route raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            compute_confidence([], "invalid_route")
        assert "Invalid route" in str(exc_info.value)


class TestAgentRouteMinOfCaps:
    """Test min-of-caps computation for agent route."""

    def test_single_curated_ok_cap_09(self):
        """Single curated ok call → cap 0.9."""
        trace = [
            {"step": 1, "tool_name": "impact_analysis", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 200, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.9
        assert "floor 0.9" in rationale
        assert "curated ok" in rationale

    def test_single_exploratory_ok_cap_06(self):
        """Single exploratory ok call → cap 0.6."""
        trace = [
            {"step": 1, "tool_name": "run_readonly_cypher", "args": {"query": "MATCH (n) RETURN n"}, "mode": MODE_EXPLORATORY, "status": STATUS_OK, "result_rows": 10, "cypher": "MATCH (n) RETURN n", "latency_ms": 150, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.6
        assert "floor 0.6" in rationale
        assert "exploratory ok" in rationale

    def test_single_exploratory_retry_ok_cap_05(self):
        """Single exploratory retry_ok call → cap 0.5."""
        trace = [
            {"step": 1, "tool_name": "run_readonly_cypher", "args": {}, "mode": MODE_EXPLORATORY, "status": STATUS_RETRY_OK, "result_rows": 10, "cypher": "MATCH (n) RETURN n", "latency_ms": 200, "retry_count": 1}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.5
        assert "floor 0.5" in rationale
        assert "retry_ok" in rationale

    def test_single_exploratory_retry_failed_cap_03(self):
        """Single exploratory retry_failed call → cap 0.3."""
        trace = [
            {"step": 1, "tool_name": "run_readonly_cypher", "args": {}, "mode": MODE_EXPLORATORY, "status": STATUS_RETRY_FAILED, "result_rows": 0, "cypher": "MATCH (n) RETURN n", "latency_ms": 100, "retry_count": 1}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.3
        assert "floor 0.3" in rationale

    def test_single_exploratory_empty_cap_03(self):
        """Single exploratory empty call → cap 0.3."""
        trace = [
            {"step": 1, "tool_name": "run_readonly_cypher", "args": {}, "mode": MODE_EXPLORATORY, "status": STATUS_EMPTY, "result_rows": 0, "cypher": "MATCH (n) RETURN n", "latency_ms": 50, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.3

    def test_mixed_caps_min_wins(self):
        """Min of caps wins: curated ok (0.9) + exploratory ok (0.6) → 0.6."""
        trace = [
            {"step": 1, "tool_name": "lookup_entity", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 100, "retry_count": 0},
            {"step": 2, "tool_name": "run_readonly_cypher", "args": {}, "mode": MODE_EXPLORATORY, "status": STATUS_OK, "result_rows": 10, "cypher": "MATCH (n) RETURN n", "latency_ms": 200, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.6
        assert "floor 0.6" in rationale

    def test_mixed_caps_with_exploratory_retry_ok(self):
        """curated ok (0.9) + exploratory retry_ok (0.5) → 0.5."""
        trace = [
            {"step": 1, "tool_name": "impact_analysis", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 200, "retry_count": 0},
            {"step": 2, "tool_name": "run_readonly_cypher", "args": {}, "mode": MODE_EXPLORATORY, "status": STATUS_RETRY_OK, "result_rows": 5, "cypher": "MATCH (n) RETURN n", "latency_ms": 300, "retry_count": 1}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.5
        assert "floor 0.5" in rationale

    def test_mixed_caps_with_retry_failed(self):
        """curated ok (0.9) + exploratory retry_failed (0.3) → 0.3."""
        trace = [
            {"step": 1, "tool_name": "impact_analysis", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 200, "retry_count": 0},
            {"step": 2, "tool_name": "run_readonly_cypher", "args": {}, "mode": MODE_EXPLORATORY, "status": STATUS_RETRY_FAILED, "result_rows": 0, "cypher": "MATCH (n) RETURN n", "latency_ms": 100, "retry_count": 1}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.3
        assert "floor 0.3" in rationale

    def test_all_curated_ok_stays_09(self):
        """Multiple curated ok calls → cap stays 0.9."""
        trace = [
            {"step": 1, "tool_name": "impact_analysis", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 200, "retry_count": 0},
            {"step": 2, "tool_name": "aggregate", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 5, "cypher": None, "latency_ms": 150, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.9


class TestRetrievalNeutral:
    """Test that retrieval (lookup_entity) tools never set the floor."""

    def test_only_retrieval_no_floor(self):
        """Only retrieval calls with no other evidence → confidence=0.0 (no evidence)."""
        trace = [
            {"step": 1, "tool_name": "lookup_entity", "args": {}, "mode": MODE_RETRIEVAL, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 100, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        # Only retrieval calls don't count as evidence
        assert confidence == 0.0
        assert "no evidence" in rationale

    def test_retrieval_plus_curated(self):
        """Retrieval + curated: retrieval ignored, curated sets floor at 0.9."""
        trace = [
            {"step": 1, "tool_name": "lookup_entity", "args": {}, "mode": MODE_RETRIEVAL, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 100, "retry_count": 0},
            {"step": 2, "tool_name": "impact_analysis", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 200, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.9
        assert "floor 0.9" in rationale

    def test_retrieval_plus_exploratory(self):
        """Retrieval + exploratory: retrieval ignored, exploratory sets floor at 0.6."""
        trace = [
            {"step": 1, "tool_name": "lookup_entity", "args": {}, "mode": MODE_RETRIEVAL, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 100, "retry_count": 0},
            {"step": 2, "tool_name": "run_readonly_cypher", "args": {}, "mode": MODE_EXPLORATORY, "status": STATUS_OK, "result_rows": 10, "cypher": "MATCH (n) RETURN n", "latency_ms": 200, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.6
        assert "floor 0.6" in rationale


class TestRationaleFormat:
    """Test that rationale strings match contract format."""

    def test_rationale_includes_step_and_tool(self):
        """Rationale includes step number and tool name."""
        trace = [
            {"step": 3, "tool_name": "impact_analysis", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 1, "cypher": None, "latency_ms": 200, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert "step 3" in rationale
        assert "impact_analysis" in rationale

    def test_rationale_includes_cap_value(self):
        """Rationale includes the cap value."""
        trace = [
            {"step": 1, "tool_name": "run_readonly_cypher", "args": {}, "mode": MODE_EXPLORATORY, "status": STATUS_OK, "result_rows": 10, "cypher": "MATCH (n) RETURN n", "latency_ms": 200, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert f"{confidence}" in rationale or f"floor {confidence}" in rationale


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_trace_agent_route(self):
        """Empty trace with agent route → confidence=0.0 (no evidence)."""
        trace = []
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        assert confidence == 0.0
        assert "no evidence" in rationale

    def test_empty_trace_chitchat_route(self):
        """Empty trace with chitchat route → confidence=0.0."""
        trace = []
        confidence, rationale = compute_confidence(trace, ROUTE_CHITCHAT)
        assert confidence == 0.0
        assert rationale == "no evidence: chitchat"

    def test_curated_invalid_status(self):
        """Curated tool with invalid status → no cap (excluded from min)."""
        trace = [
            {"step": 1, "tool_name": "impact_analysis", "args": {}, "mode": MODE_CURATED, "status": STATUS_INVALID, "result_rows": 0, "cypher": None, "latency_ms": 50, "retry_count": 0},
            {"step": 2, "tool_name": "aggregate", "args": {}, "mode": MODE_CURATED, "status": STATUS_OK, "result_rows": 5, "cypher": None, "latency_ms": 150, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        # Only the second call (ok) contributes, cap = 0.9
        assert confidence == 0.9

    def test_exploratory_invalid_status(self):
        """Exploratory tool with invalid status → treated as non-evidence."""
        trace = [
            {"step": 1, "tool_name": "run_readonly_cypher", "args": {}, "mode": MODE_EXPLORATORY, "status": STATUS_INVALID, "result_rows": 0, "cypher": "MATCH (n) RETURN n", "latency_ms": 50, "retry_count": 0}
        ]
        confidence, rationale = compute_confidence(trace, ROUTE_AGENT)
        # No evidence-contributing calls (invalid doesn't count)
        assert confidence == 0.0


class TestFormatConfidence:
    """Test confidence formatting utility."""

    def test_format_09(self):
        """Format 0.9 as percentage."""
        assert format_confidence(0.9) == "90%"

    def test_format_06(self):
        """Format 0.6 as percentage."""
        assert format_confidence(0.6) == "60%"

    def test_format_05(self):
        """Format 0.5 as percentage."""
        assert format_confidence(0.5) == "50%"

    def test_format_04(self):
        """Format 0.4 as percentage."""
        assert format_confidence(0.4) == "40%"

    def test_format_03(self):
        """Format 0.3 as percentage."""
        assert format_confidence(0.3) == "30%"

    def test_format_00(self):
        """Format 0.0 as percentage."""
        assert format_confidence(0.0) == "0%"

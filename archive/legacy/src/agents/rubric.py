"""
Confidence rubric for the Northwind Agentic KG.

Authoritative contract: PROJECT.md §5

Contract statement: Confidence is a deterministic function of the trace, 
computed in code — never an LLM self-assessment.

Rule: min of caps over evidence-contributing tool calls.
Route-dependent rules:
- route="degrade" → hard cap 0.4, overrides min-of-caps
- route="chitchat" or "refusal" → confidence=0.0, rationale="no evidence: <route>"
- route="agent" → min-of-caps per PROJECT.md §5

Caps table:
- curated, status ok: 0.9
- exploratory, status ok (first try): 0.6
- exploratory, status retry_ok: 0.5
- exploratory, retry_failed OR empty-then-synthesized: 0.3
- retrieval (lookup_entity): neutral — never sets the floor
"""

from typing import Optional, Tuple

from .state import ToolCallRecord, AgentState, ROUTE_DEGRADE, ROUTE_CHITCHAT, ROUTE_REFUSAL, ROUTE_AGENT, MODE_CURATED, MODE_EXPLORATORY, MODE_RETRIEVAL, STATUS_OK, STATUS_RETRY_OK, STATUS_RETRY_FAILED, STATUS_EMPTY


# =============================================================================
# CONFIDENCE CAPS
# =============================================================================

# Caps per PROJECT.md §5
CAP_CURATED_OK = 0.9
CAP_EXPLORATORY_OK = 0.6
CAP_EXPLORATORY_RETRY_OK = 0.5
CAP_EXPLORATORY_RETRY_FAILED_OR_EMPTY = 0.3
CAP_DEGRADE = 0.4
CAP_CHITCHAT_REFUSAL = 0.0


# =============================================================================
# HELPER: Get cap for a single ToolCallRecord
# =============================================================================

def _get_tool_call_cap(record: ToolCallRecord) -> Optional[float]:
    """
    Get the confidence cap for a single ToolCallRecord.
    
    Returns None if the tool call is retrieval (never sets the floor).
    Returns the cap value for evidence-contributing calls.
    """
    mode = record.get('mode', '')
    status = record.get('status', '')
    
    # Retrieval tools (lookup_entity) are neutral — never set the floor
    if mode == MODE_RETRIEVAL:
        return None
    
    # Curated tools
    if mode == MODE_CURATED:
        if status == STATUS_OK:
            return CAP_CURATED_OK
        # Other statuses for curated: fall through to None (or handle specially)
    
    # Exploratory tools (run_readonly_cypher)
    if mode == MODE_EXPLORATORY:
        if status == STATUS_OK:
            return CAP_EXPLORATORY_OK
        elif status == STATUS_RETRY_OK:
            return CAP_EXPLORATORY_RETRY_OK
        elif status in (STATUS_RETRY_FAILED, STATUS_EMPTY):
            return CAP_EXPLORATORY_RETRY_FAILED_OR_EMPTY
    
    # Unknown mode or status
    return None


# =============================================================================
# MAIN FUNCTION: compute_confidence
# =============================================================================

def compute_confidence(trace: list[ToolCallRecord], route: str) -> Tuple[float, str]:
    """
    Compute confidence and rationale from trace and route.
    
    Contract: PROJECT.md §5, PLAN.md 2.9
    
    Args:
        trace: List of ToolCallRecord from the agent execution
        route: One of {"agent", "chitchat", "refusal", "degrade"}
    
    Returns:
        Tuple of (confidence: float, confidence_rationale: str)
    
    Rules:
    - route="degrade" → hard cap 0.4 overrides min-of-caps; rationale includes truncation disclosure
    - route="chitchat" or "refusal" → confidence=0.0, rationale="no evidence: <route>"
    - route="agent" → min-of-caps over evidence-contributing calls (excluding retrieval)
    
    Evidence-contributing calls: curated and exploratory tools (not retrieval).
    Caps:
    - curated ok: 0.9
    - exploratory ok: 0.6
    - exploratory retry_ok: 0.5
    - exploratory retry_failed/empty: 0.3
    - retrieval: neutral (excluded from min-of-caps)
    """
    # Validate route
    if route not in (ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL, ROUTE_DEGRADE):
        raise ValueError(f"Invalid route: {route}. Must be one of: {ROUTE_AGENT}, {ROUTE_CHITCHAT}, {ROUTE_REFUSAL}, {ROUTE_DEGRADE}")
    
    # Route-specific rules
    
    # Degrade: hard cap 0.4, overrides min-of-caps
    if route == ROUTE_DEGRADE:
        return (CAP_DEGRADE, "Hard cap 0.4: budget exhausted (MAX_STEPS=8 reached), truncation disclosure mandatory")
    
    # Chitchat or refusal: no evidence, confidence 0.0
    if route in (ROUTE_CHITCHAT, ROUTE_REFUSAL):
        return (CAP_CHITCHAT_REFUSAL, f"no evidence: {route}")
    
    # Agent route: min-of-caps over evidence-contributing calls
    if route == ROUTE_AGENT:
        # Get caps for all evidence-contributing tool calls
        caps = []
        for record in trace:
            cap = _get_tool_call_cap(record)
            # Retrieval returns None, which we skip
            if cap is not None:
                caps.append(cap)
        
        if not caps:
            # No evidence-contributing calls (only retrieval or empty trace)
            return (CAP_CHITCHAT_REFUSAL, "no evidence: agent route with no evidence-contributing calls")
        
        # Compute min of caps
        confidence = min(caps)
        
        # Build rationale
        # Find which call set the floor
        floor_setting_record = None
        for record in trace:
            cap = _get_tool_call_cap(record)
            if cap is not None and cap == confidence:
                floor_setting_record = record
                break
        
        if floor_setting_record:
            mode = floor_setting_record.get('mode', '')
            status = floor_setting_record.get('status', '')
            step = floor_setting_record.get('step', 0)
            tool_name = floor_setting_record.get('tool_name', '')
            
            if mode == MODE_CURATED and status == STATUS_OK:
                rationale = f"floor {confidence} set by step {step} ({tool_name}, curated ok); all curated tools succeeded"
            elif mode == MODE_EXPLORATORY and status == STATUS_OK:
                rationale = f"floor {confidence} set by step {step} ({tool_name}, exploratory ok, first try)"
            elif mode == MODE_EXPLORATORY and status == STATUS_RETRY_OK:
                rationale = f"floor {confidence} set by step {step} ({tool_name}, exploratory retry_ok)"
            elif mode == MODE_EXPLORATORY and status in (STATUS_RETRY_FAILED, STATUS_EMPTY):
                rationale = f"floor {confidence} set by step {step} ({tool_name}, exploratory {status})"
            else:
                rationale = f"floor {confidence} set by step {step} ({tool_name}, mode={mode}, status={status})"
        else:
            rationale = f"min-of-caps={confidence} over {len(caps)} evidence-contributing calls"
        
        return (confidence, rationale)
    
    # Should not reach here
    raise ValueError(f"Unhandled route: {route}")


# =============================================================================
# UTILITY: Format confidence for display
# =============================================================================

def format_confidence(confidence: float) -> str:
    """Format confidence as percentage for display."""
    return f"{confidence * 100:.0f}%"


# =============================================================================
# CONTRACTS (for reference)
# =============================================================================

# From PROJECT.md §5:
# | Call profile | Cap |
# |---|---|
# | curated, status ok | 0.9 |
# | exploratory, status ok (first try) | 0.6 |
# | exploratory, status retry_ok | 0.5 |
# | exploratory, retry_failed OR empty-then-synthesized | 0.3 |
# | retrieval (lookup_entity) | neutral — never sets the floor |
# | degrade path (budget exhausted) | hard cap 0.4, overrides min, truncation disclosure mandatory |

# From PLAN.md 2.9:
# Route-dependent rules:
# - route="degrade" → hard cap 0.4 overrides min-of-caps
# - route="chitchat" or "refusal" → confidence=0.0, rationale="no evidence: <route>"
# - route="agent" → min-of-caps per PROJECT.md §5

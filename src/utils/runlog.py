"""
Run-log for the Northwind Agentic KG.

Authoritative contracts:
- PROJECT.md §6: Run-log (JSONL)
- PLAN.md 2.10: JSONL appender

Invariants:
- Append-only JSONL
- No run is ever edited or deleted
- Fields: ts, question, route, trace, hops, answer, citations, confidence, 
          confidence_rationale, latency_ms_total
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from src.agents.state import AgentState


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default run-log file path
RUNLOG_PATH = os.getenv("RUNLOG_PATH", "runlog.jsonl")


# =============================================================================
# WRITE RUN
# =============================================================================

def write_run(state: AgentState) -> None:
    """
    Append a run to the JSONL run-log.
    
    Contract: PROJECT.md §6, PLAN.md 2.10
    
    Fields written:
    - ts: ISO 8601 timestamp with timezone
    - question: The user's question
    - route: "agent" | "chitchat" | "refusal" | "degrade"
    - trace: List of ToolCallRecord objects
    - hops: Number of tool calls (length of trace)
    - answer: The final answer string
    - citations: List of Citation objects
    - confidence: Float confidence score
    - confidence_rationale: String explaining the confidence
    - latency_ms_total: Total latency in milliseconds
    
    Invariant: Append-only. No run is ever edited or deleted.
    
    Args:
        state: AgentState from a completed run
    """
    # Calculate total latency from trace
    trace = state.get('trace', [])
    latency_ms_total = sum(record.get('latency_ms', 0) for record in trace)
    
    # Count hops
    hops = len(trace)
    
    # Build run log entry
    run_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "question": state.get('question', ''),
        "route": state.get('route', ''),
        "trace": trace,
        "hops": hops,
        "answer": state.get('answer', ''),
        "citations": state.get('citations', []),
        "confidence": state.get('confidence', 0.0),
        "confidence_rationale": state.get('confidence_rationale', ''),
        "latency_ms_total": latency_ms_total,
    }
    
    # Write to JSONL file
    with open(RUNLOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(run_entry, ensure_ascii=False) + '\n')


# =============================================================================
# READ RUN-LOG
# =============================================================================

def read_runlog() -> list[dict]:
    """
    Read all entries from the run-log.
    
    Returns:
        List of run log entries as dictionaries
    """
    if not os.path.exists(RUNLOG_PATH):
        return []
    
    runs = []
    with open(RUNLOG_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    
    return runs


# =============================================================================
# CLEAR RUN-LOG (for testing only)
# =============================================================================

def clear_runlog() -> None:
    """
    Clear the run-log file. For testing purposes only.
    
    WARNING: This violates the append-only invariant. Use only in tests.
    """
    target = Path(RUNLOG_PATH).resolve()
    if not target.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError("clear_runlog is restricted to temporary test logs")
    if target.exists():
        target.unlink()


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    'RUNLOG_PATH',
    'write_run',
    'read_runlog',
    'clear_runlog',
]

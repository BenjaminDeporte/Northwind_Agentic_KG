"""
Agent state definitions for the Northwind Agentic KG.

Authoritative contracts:
- PROJECT.md §3: State TypedDict definitions
- PROJECT.md §5: Confidence rubric
- SCHEMA.md: labels, keys, relationship types

Invariants:
- messages: ONLY field with reducer (add_messages)
- All other fields: last-write-wins with one owning node
- retry_count ≤ 1 for all tool calls
- MAX_STEPS = 8
"""

from typing import Annotated, TypedDict, Optional
from langgraph.graph.message import add_messages


# =============================================================================
# ToolCallRecord
# =============================================================================

class ToolCallRecord(TypedDict):
    """
    Record of a single tool call execution.
    
    Contract: PROJECT.md §3
    Invariant: retry_count ∈ {0, 1}, never exceeds 1
    """
    step: int                      # 1-based loop iteration
    tool_name: str                 # e.g., "lookup_entity", "run_readonly_cypher"
    args: dict                     # Arguments passed to the tool
    mode: str                      # "curated" | "exploratory" | "retrieval"
    status: str                    # "ok" | "empty" | "invalid" | "retry_ok" | "retry_failed"
    result_rows: int               # Number of rows/records returned
    cypher: Optional[str]          # Populated ONLY for run_readonly_cypher (exploratory mode)
    latency_ms: int                # Execution time in milliseconds
    retry_count: int               # 0 or 1 — invariant: never exceeds 1


# =============================================================================
# Citation
# =============================================================================

class Citation(TypedDict):
    """
    Citation for a node referenced in the final answer.
    
    Contract: PROJECT.md §3
    Rule: No claim without a citation; no citation without a node.
    Key format: SCHEMA.md key property value (e.g., supplierID "1", not name "Exotic Liquids")
    """
    label: str                     # Node label per SCHEMA.md (e.g., "Supplier", "Product")
    key: str                       # The label's key property value (label + key uniquely identifies the node)
    name: str                      # Display name for inline answer text


# =============================================================================
# AgentState
# =============================================================================

class AgentState(TypedDict):
    """
    Complete state of the agent during execution.
    
    Contract: PROJECT.md §3
    
    Reducer rule:
    - messages: ONLY field with reducer (add_messages) — all other fields are last-write-wins
    - Each field has one owning node that sets it
    
    Control-flow invariants:
    - MAX_STEPS = 8
    - Budget exhaustion (loop_count >= MAX_STEPS) always routes to degrade, never to synthesize
    - Every executed tool call appends exactly one ToolCallRecord to trace
    """
    question: str
    route: str                      # "agent" | "chitchat" | "refusal" | "degrade"
    messages: Annotated[list, add_messages]  # ONLY field with a reducer
    trace: list[ToolCallRecord]
    answer: str
    citations: list[Citation]
    confidence: float
    confidence_rationale: str
    loop_count: int
    error: Optional[str]  # None if no error


# =============================================================================
# Constants
# =============================================================================

MAX_STEPS = 8

# Tool modes
MODE_CURATED = "curated"
MODE_EXPLORATORY = "exploratory"
MODE_RETRIEVAL = "retrieval"

# Tool statuses
STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_INVALID = "invalid"
STATUS_RETRY_OK = "retry_ok"
STATUS_RETRY_FAILED = "retry_failed"

# Routes
ROUTE_AGENT = "agent"
ROUTE_CHITCHAT = "chitchat"
ROUTE_REFUSAL = "refusal"
ROUTE_DEGRADE = "degrade"

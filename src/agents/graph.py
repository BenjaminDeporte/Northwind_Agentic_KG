"""
LangGraph graph definition for the Northwind Agentic KG.

Authoritative contracts:
- PROJECT.md §2: Architecture (classify → agent ↔ tools → synthesize, degrade)
- PLAN.md 2.8: LangGraph graph definition

Control-flow invariants:
- MAX_STEPS=8
- Budget exhaustion routes to degrade, never to synthesize
- Every executed tool call appends exactly one ToolCallRecord to trace
- No silent calls

Graph structure:
    classify → agent ↔ agent → synthesize
    classify → END (for chitchat/refusal)
    agent → degrade (on budget exhaustion)
"""

from typing import Callable, Any, Literal
from langgraph.graph import StateGraph, END

from .state import AgentState, ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL, ROUTE_DEGRADE, MAX_STEPS
from .nodes import classify, agent, synthesize, degrade


# =============================================================================
# CONDITION FUNCTIONS
# =============================================================================

def route_from_classify(state: AgentState) -> Literal["agent", END]:
    """Route from classify to agent or END."""
    route = state.get('route', '')
    if route == ROUTE_AGENT:
        return "agent"
    elif route in (ROUTE_CHITCHAT, ROUTE_REFUSAL):
        return END
    else:
        # Default to agent if route not set yet
        return "agent"


def route_from_agent(state: AgentState) -> Literal["agent", "synthesize", "degrade"]:
    """
    Route from agent to next node.
    
    Priority:
    1. degrade - if budget exhausted (loop_count >= MAX_STEPS)
    2. synthesize - if we have an answer
    3. agent - continue looping
    """
    loop_count = state.get('loop_count', 0)
    route = state.get('route', '')
    has_answer = state.get('answer') is not None and bool(state.get('answer', '').strip())
    
    if loop_count >= MAX_STEPS:
        return "degrade"
    elif has_answer:
        return "synthesize"
    else:
        return "agent"


# =============================================================================
# BUILD GRAPH
# =============================================================================

def build_graph(tools: dict[str, Callable]) -> StateGraph[AgentState]:
    """
    Build the LangGraph agent graph.
    
    Contract: PROJECT.md §2, PLAN.md 2.8
    
    Graph structure:
        classify → agent → agent → ... → synthesize
                   → degrade (on budget exhaustion)
        classify → END (for chitchat/refusal)
    
    Nodes:
    - classify: Small LLM router (agent | chitchat | refusal)
    - agent: ReAct loop with MAX_STEPS=8 (one tool call per iteration)
    - synthesize: Produces final answer with citations and confidence
    - degrade: Budget exhaustion handler with 0.4 confidence cap
    
    Control-flow invariants enforced:
    - MAX_STEPS=8
    - Every tool call appends exactly one ToolCallRecord
    - Budget exhaustion always routes to degrade, never to synthesize
    - No silent tool calls
    
    The agent node handles ONE iteration of the ReAct loop per invocation.
    The graph's edges control the looping behavior.
    
    Args:
        tools: Dictionary mapping tool names to tool functions
    
    Returns:
        LangGraph StateGraph
    """
    # Initialize the graph with AgentState as the state schema
    workflow = StateGraph(AgentState)
    
    # =========================================================================
    # NODE 1: classify
    # =========================================================================
    workflow.add_node("classify", classify)
    
    # =========================================================================
    # NODE 2: agent (ReAct loop - one iteration per call)
    # =========================================================================
    def agent_node(state: AgentState) -> AgentState:
        """Wrapper for agent node with tool binding."""
        return agent(state, tools)
    
    workflow.add_node("agent", agent_node)
    
    # =========================================================================
    # NODE 3: synthesize
    # =========================================================================
    workflow.add_node("synthesize", synthesize)
    
    # =========================================================================
    # NODE 4: degrade
    # =========================================================================
    workflow.add_node("degrade", degrade)
    
    # =========================================================================
    # EDGES FROM classify
    # =========================================================================
    workflow.add_conditional_edges(
        "classify",
        route_from_classify,
    )
    
    # =========================================================================
    # EDGES FROM agent
    # =========================================================================
    workflow.add_conditional_edges(
        "agent",
        route_from_agent,
    )
    
    # =========================================================================
    # TERMINAL EDGES
    # =========================================================================
    
    # synthesize → END
    workflow.add_edge("synthesize", END)
    
    # degrade → END
    workflow.add_edge("degrade", END)
    
    # =========================================================================
    # ENTRY POINT
    # =========================================================================
    workflow.set_entry_point("classify")
    
    return workflow


# =============================================================================
# COMPILE GRAPH
# =============================================================================

def compile_graph(tools: dict[str, Callable]):
    """
    Compile the agent graph.
    
    Args:
        tools: Dictionary mapping tool names to tool functions
    
    Returns:
        Compiled LangGraph StateGraph ready for execution
    """
    graph = build_graph(tools)
    return graph.compile()


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    'build_graph',
    'compile_graph',
    'END',
]

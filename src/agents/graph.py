"""
LangGraph graph definition for the Northwind Agentic KG.

Authoritative contracts:
- PROJECT.md §2: Architecture (classify → agent ↔ tools → synthesize; agent → degrade)
- PLAN.md 2.8: LangGraph graph definition

Control-flow invariants:
- MAX_STEPS=8
- Budget exhaustion routes to degrade, never to synthesize
- Every executed tool call appends exactly one ToolCallRecord to trace
- No silent calls

Graph structure:
    classify → agent ↔ tools → synthesize
                   agent → degrade (on budget exhaustion)
"""

from typing import Callable, Any
from langgraph.graph import StateGraph, END

from .state import AgentState, ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL, ROUTE_DEGRADE, MAX_STEPS
from .nodes import classify, agent, synthesize, degrade


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def should_route_to_agent(state: AgentState) -> bool:
    """Check if classify should route to agent."""
    return state.get('route') == ROUTE_AGENT


def should_route_to_end_for_chitchat_refusal(state: AgentState) -> bool:
    """Check if classify should route to END for chitchat/refusal."""
    return state.get('route') in (ROUTE_CHITCHAT, ROUTE_REFUSAL)


def should_synthesize(state: AgentState) -> bool:
    """Check if we should synthesize the answer."""
    route = state.get('route', '')
    return (
        route == ROUTE_AGENT and 
        state.get('answer') is not None and
        len(state.get('trace', [])) > 0
    )


def should_degrade(state: AgentState) -> bool:
    """Check if we should route to degrade."""
    loop_count = state.get('loop_count', 0)
    return loop_count >= MAX_STEPS


# =============================================================================
# BUILD GRAPH
# =============================================================================

def build_graph(tools: dict[str, Callable]) -> StateGraph[AgentState]:
    """
    Build the LangGraph agent graph.
    
    Contract: PROJECT.md §2, PLAN.md 2.8
    
    Graph structure:
        classify → agent ↔ tools → synthesize
                       agent → degrade (on budget exhaustion)
    
    Nodes:
    - classify: Small LLM router (agent | chitchat | refusal)
    - agent: ReAct loop with MAX_STEPS=8
    - synthesize: Produces final answer with citations and confidence
    - degrade: Budget exhaustion handler with 0.4 confidence cap
    
    Control-flow invariants enforced:
    - MAX_STEPS=8
    - Every tool call appends exactly one ToolCallRecord
    - Budget exhaustion always routes to degrade, never to synthesize
    - No silent tool calls
    
    Note: In this implementation, the agent node handles tool calling internally
    via tools_dispatcher, so we don't need a separate tools node in the graph.
    The tools are passed to the agent node.
    
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
    # Routes the question to agent, chitchat, or refusal
    workflow.add_node("classify", classify)
    
    # =========================================================================
    # NODE 2: agent (ReAct loop)
    # =========================================================================
    # The agent performs the ReAct loop with MAX_STEPS=8
    # It handles tool calling internally via tools_dispatcher
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
    
    # classify → agent (for agent route)
    workflow.add_conditional_edges(
        "classify",
        should_route_to_agent,
        "agent",
    )
    
    # classify → END (for chitchat and refusal routes - they already have answer set)
    workflow.add_conditional_edges(
        "classify",
        should_route_to_end_for_chitchat_refusal,
        END,
    )
    
    # =========================================================================
    # EDGES FROM agent
    # =========================================================================
    
    # agent → synthesize (when answer is ready)
    workflow.add_conditional_edges(
        "agent",
        should_synthesize,
        "synthesize",
    )
    
    # agent → degrade (on budget exhaustion)
    workflow.add_conditional_edges(
        "agent",
        should_degrade,
        "degrade",
    )
    
    # agent → agent (continue loop - default when no other condition matches)
    workflow.add_edge("agent", "agent")
    
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

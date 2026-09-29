"""Compiled LangGraph workflow for the contracted Northwind agent."""
from typing import Callable
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage

from .state import AgentState, MAX_STEPS, ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL
from .nodes import classify, agent_step, execute_tool_step, synthesize, degrade


def route_from_classify(state: AgentState):
    return "agent" if state.get("route") == ROUTE_AGENT else END


def route_from_agent(state: AgentState):
    messages = state.get("messages", [])
    latest = messages[-1] if messages else None
    if isinstance(latest, AIMessage) and latest.tool_calls:
        return "tools"
    if state.get("loop_count", 0) >= MAX_STEPS:
        return "degrade"
    if isinstance(latest, AIMessage) and str(latest.content).lstrip().upper().startswith("FINAL:"):
        return "synthesize"
    return "agent"


def build_graph(tools: dict[str, Callable]) -> StateGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node("classify", classify)
    workflow.add_node("agent", lambda state: agent_step(state, tools))
    workflow.add_node("tools", lambda state: execute_tool_step(state, tools))
    workflow.add_node("synthesize", synthesize)
    workflow.add_node("degrade", degrade)
    workflow.set_entry_point("classify")
    workflow.add_conditional_edges("classify", route_from_classify)
    workflow.add_conditional_edges("agent", route_from_agent)
    workflow.add_edge("tools", "agent")
    workflow.add_edge("synthesize", END)
    workflow.add_edge("degrade", END)
    return workflow


def compile_graph(tools: dict[str, Callable]):
    return build_graph(tools).compile()


__all__ = ["build_graph", "compile_graph", "END", "route_from_agent", "route_from_classify"]

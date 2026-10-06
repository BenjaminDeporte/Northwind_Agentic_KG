"""Compiled LangGraph workflow for the contracted Northwind agent."""
from typing import Callable
from langgraph.graph import StateGraph, END
import json

from langchain_core.messages import AIMessage, ToolMessage

from .state import AgentState, MAX_STEPS, ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL
from .nodes import (
    classify, agent_step, execute_tool_step, synthesize, consistency_check, degrade,
    _safe_tool_payload, _tool_result_has_evidence,
)


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
    if isinstance(latest, AIMessage):
        latest_tool = next(
            (message for message in reversed(messages) if isinstance(message, ToolMessage)),
            None,
        )
        if latest_tool is not None:
            try:
                result = json.loads(latest_tool.content)
            except (TypeError, json.JSONDecodeError):
                result = {}
            if result.get("status") in {"ok", "retry_ok"}:
                # A no-tool response after successful evidence is a completion
                # decision even if the model omitted the required FINAL marker.
                # Synthesis and consistency checking still gate user-visible output.
                return "synthesize"
    return "agent"


def route_after_tools(state: AgentState):
    """Send adequate successful evidence straight to synthesis and review."""
    if state.get("loop_count", 0) >= MAX_STEPS:
        return "degrade"
    messages = state.get("messages", [])
    latest = messages[-1] if messages else None
    if isinstance(latest, ToolMessage):
        result = _safe_tool_payload(latest)
        if result.get("status") in {"ok", "retry_ok"} and _tool_result_has_evidence(latest.name or "", result):
            return "synthesize"
    return "agent"


def route_from_consistency(state: AgentState):
    if state.get("loop_count", 0) >= MAX_STEPS:
        return "degrade"
    if state.get("consistency_status") == "pass":
        return "end"
    return "agent"


def build_graph(tools: dict[str, Callable]) -> StateGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node("classify", classify)
    workflow.add_node("agent", agent_step)
    workflow.add_node("tools", lambda state: execute_tool_step(state, tools))
    workflow.add_node("synthesize", synthesize)
    workflow.add_node("consistency_check", consistency_check)
    workflow.add_node("degrade", degrade)
    workflow.set_entry_point("classify")
    workflow.add_conditional_edges("classify", route_from_classify)
    workflow.add_conditional_edges("agent", route_from_agent)
    workflow.add_conditional_edges(
        "tools", route_after_tools,
        {"synthesize": "synthesize", "agent": "agent", "degrade": "degrade"},
    )
    workflow.add_edge("synthesize", "consistency_check")
    workflow.add_conditional_edges(
        "consistency_check", route_from_consistency,
        {"end": END, "agent": "agent", "degrade": "degrade"},
    )
    workflow.add_edge("degrade", END)
    return workflow


def compile_graph(tools: dict[str, Callable]):
    return build_graph(tools).compile()


__all__ = ["build_graph", "compile_graph", "END", "route_from_agent", "route_from_classify", "route_after_tools", "route_from_consistency"]

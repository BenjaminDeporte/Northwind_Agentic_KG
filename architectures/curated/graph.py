"""Compiled LangGraph topology for curated queries with Text2Cypher fallback."""

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, StateGraph

from architectures.generic.graph import route_after_router
from architectures.generic.nodes import (
    answer_generation_node, neo4j_node, route_after_validation, router_node,
    terminal_node, text2cypher_node, validate_cypher_node,
)
from architectures.generic.state import AgentState, MAX_AGENT_TURNS


def curated_agent_node(state: AgentState, *, handlers: Any, conversational_model: str, prompt_version: str) -> dict[str, Any]:
    selected = handlers.select_curated_tool(state["question"], conversational_model=conversational_model, prompt_version=prompt_version)
    return {
        "loop_count": state.get("loop_count", 0) + 1,
        "messages": [ToolMessage(content=json.dumps({"tool_name": selected}), name="curated_selection", tool_call_id=f"curated-selection-{state.get('loop_count', 0) + 1}")],
    }


def route_after_curated_agent(state: AgentState) -> str:
    if state.get("loop_count", 0) >= MAX_AGENT_TURNS:
        return "terminal"
    for message in reversed(state.get("messages", [])):
        if isinstance(message, ToolMessage) and message.name == "curated_selection":
            try:
                selected = json.loads(str(message.content)).get("tool_name")
            except json.JSONDecodeError:
                selected = None
            return "curated_query" if selected else "text2cypher"
    return "text2cypher"


def curated_query_node(state: AgentState, *, handlers: Any) -> dict[str, Any]:
    selection = next((m for m in reversed(state.get("messages", [])) if isinstance(m, ToolMessage) and m.name == "curated_selection"), None)
    selected = json.loads(str(selection.content)).get("tool_name") if selection else None
    if not selected:
        raise ValueError("Curated query node requires a selected tool")
    return {"messages": [AIMessage(content=handlers.curated_query(selected), name="curated_query")]}


def compile_graph(handlers: Any, *, schema: str, schema_prompt: str, conversational_model: str, cypher_model: str, prompt_version: str, neo4j_client: Any = None):
    workflow = StateGraph(AgentState)
    workflow.add_node("router", lambda s: router_node(s, handlers=handlers, conversational_model=conversational_model))
    workflow.add_node("agent", lambda s: curated_agent_node(s, handlers=handlers, conversational_model=conversational_model, prompt_version=prompt_version))
    workflow.add_node("curated_query", lambda s: curated_query_node(s, handlers=handlers))
    workflow.add_node("text2cypher", lambda s: text2cypher_node(s, handlers=handlers, schema_prompt=schema_prompt, cypher_model=cypher_model, prompt_version=prompt_version))
    workflow.add_node("validate_cypher", lambda s: validate_cypher_node(s, handlers=handlers, schema=schema))
    workflow.add_node("neo4j", lambda s: neo4j_node(s, handlers=handlers, neo4j_client=neo4j_client))
    workflow.add_node("answer_generation", lambda s: answer_generation_node(s, handlers=handlers, conversational_model=conversational_model, prompt_version=prompt_version))
    workflow.add_node("terminal", terminal_node)
    workflow.set_entry_point("router")
    workflow.add_conditional_edges("router", route_after_router, {"agent": "agent", "answer_generation": "answer_generation"})
    workflow.add_conditional_edges("agent", route_after_curated_agent, {"curated_query": "curated_query", "text2cypher": "text2cypher", "terminal": "terminal"})
    workflow.add_edge("curated_query", "validate_cypher")
    workflow.add_edge("text2cypher", "validate_cypher")
    workflow.add_conditional_edges("validate_cypher", route_after_validation, {"neo4j": "neo4j", "text2cypher": "text2cypher", "terminal": "terminal"})
    workflow.add_edge("neo4j", "answer_generation")
    workflow.add_edge("answer_generation", "terminal")
    workflow.add_edge("terminal", END)
    return workflow.compile()


__all__ = ["compile_graph", "curated_agent_node", "curated_query_node", "route_after_curated_agent"]

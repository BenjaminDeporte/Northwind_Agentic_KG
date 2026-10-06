"""Compiled LangGraph topology for Architecture 1."""

from typing import Any

from langgraph.graph import END, StateGraph

from .interfaces import GenericHandlers
from .nodes import (
    agent_node,
    answer_generation_node,
    neo4j_node,
    route_after_agent,
    route_after_validation,
    router_node,
    terminal_node,
    text2cypher_node,
    validate_cypher_node,
)
from .state import AgentState


def route_after_router(state: AgentState) -> str:
    route = state.get("route")
    if route == "agent":
        return "agent"
    if route in {"chitchat", "refusal"}:
        return "answer_generation"
    raise ValueError(f"Router did not set a supported route: {route!r}")


def build_graph(
    handlers: GenericHandlers,
    *,
    schema: str,
    schema_prompt: str,
    conversational_model: str,
    cypher_model: str,
    prompt_version: str,
    neo4j_client: Any = None,
) -> StateGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node(
        "router",
        lambda state: router_node(
            state, handlers=handlers, conversational_model=conversational_model
        ),
    )
    workflow.add_node("agent", agent_node)
    workflow.add_node(
        "text2cypher",
        lambda state: text2cypher_node(
            state,
            handlers=handlers,
            schema_prompt=schema_prompt,
            cypher_model=cypher_model,
            prompt_version=prompt_version,
        ),
    )
    workflow.add_node(
        "validate_cypher",
        lambda state: validate_cypher_node(state, handlers=handlers, schema=schema),
    )
    workflow.add_node(
        "neo4j",
        lambda state: neo4j_node(state, handlers=handlers, neo4j_client=neo4j_client),
    )
    workflow.add_node(
        "answer_generation",
        lambda state: answer_generation_node(
            state,
            handlers=handlers,
            conversational_model=conversational_model,
            prompt_version=prompt_version,
        ),
    )
    workflow.add_node("terminal", terminal_node)

    workflow.set_entry_point("router")
    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {"agent": "agent", "answer_generation": "answer_generation"},
    )
    workflow.add_conditional_edges(
        "agent",
        route_after_agent,
        {"text2cypher": "text2cypher", "terminal": "terminal"},
    )
    workflow.add_edge("text2cypher", "validate_cypher")
    workflow.add_conditional_edges(
        "validate_cypher",
        route_after_validation,
        {"neo4j": "neo4j", "text2cypher": "text2cypher", "terminal": "terminal"},
    )
    workflow.add_edge("neo4j", "answer_generation")
    workflow.add_edge("answer_generation", "terminal")
    workflow.add_edge("terminal", END)
    return workflow


def compile_graph(
    handlers: GenericHandlers,
    *,
    schema: str,
    schema_prompt: str,
    conversational_model: str,
    cypher_model: str,
    prompt_version: str,
    neo4j_client: Any = None,
):
    return build_graph(
        handlers,
        schema=schema,
        schema_prompt=schema_prompt,
        conversational_model=conversational_model,
        cypher_model=cypher_model,
        prompt_version=prompt_version,
        neo4j_client=neo4j_client,
    ).compile()


__all__ = ["build_graph", "compile_graph", "route_after_router"]

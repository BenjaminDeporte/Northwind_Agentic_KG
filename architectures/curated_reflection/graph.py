"""Compiled LangGraph topology for curated fallback with reflection."""

from typing import Any

from langgraph.graph import END, StateGraph

from architectures.curated.graph import curated_agent_node, curated_query_node, route_after_curated_agent
from architectures.generic.graph import route_after_router
from architectures.generic.nodes import (
    answer_generation_node, neo4j_node, route_after_validation, router_node,
    terminal_node, text2cypher_node, validate_cypher_node,
)
from architectures.generic.state import AgentState
from architectures.generic_reflection.graph import reflection_node, route_after_reflection


def compile_graph(handlers: Any, *, schema: str, schema_prompt: str, conversational_model: str, cypher_model: str, prompt_version: str, neo4j_client: Any = None):
    workflow = StateGraph(AgentState)
    workflow.add_node("router", lambda s: router_node(s, handlers=handlers, conversational_model=conversational_model))
    workflow.add_node("agent", lambda s: curated_agent_node(s, handlers=handlers, conversational_model=conversational_model, prompt_version=prompt_version))
    workflow.add_node("curated_query", lambda s: curated_query_node(s, handlers=handlers))
    workflow.add_node("text2cypher", lambda s: text2cypher_node(s, handlers=handlers, schema_prompt=schema_prompt, cypher_model=cypher_model, prompt_version=prompt_version))
    workflow.add_node("validate_cypher", lambda s: validate_cypher_node(s, handlers=handlers, schema=schema))
    workflow.add_node("neo4j", lambda s: neo4j_node(s, handlers=handlers, neo4j_client=neo4j_client))
    workflow.add_node("answer_generation", lambda s: answer_generation_node(s, handlers=handlers, conversational_model=conversational_model, prompt_version=prompt_version))
    workflow.add_node("reflection", lambda s: reflection_node(s, handlers=handlers, conversational_model=conversational_model, prompt_version=prompt_version))
    workflow.add_node("terminal", terminal_node)
    workflow.set_entry_point("router")
    workflow.add_conditional_edges("router", route_after_router, {"agent": "agent", "answer_generation": "answer_generation"})
    workflow.add_conditional_edges("agent", route_after_curated_agent, {"curated_query": "curated_query", "text2cypher": "text2cypher", "terminal": "terminal"})
    workflow.add_edge("curated_query", "validate_cypher")
    workflow.add_edge("text2cypher", "validate_cypher")
    workflow.add_conditional_edges("validate_cypher", route_after_validation, {"neo4j": "neo4j", "text2cypher": "text2cypher", "terminal": "terminal"})
    workflow.add_edge("neo4j", "answer_generation")
    workflow.add_edge("answer_generation", "reflection")
    workflow.add_conditional_edges("reflection", route_after_reflection, {"agent": "agent", "terminal": "terminal"})
    workflow.add_edge("terminal", END)
    return workflow.compile()


__all__ = ["compile_graph"]

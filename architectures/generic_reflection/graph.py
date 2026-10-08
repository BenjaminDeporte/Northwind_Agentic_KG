"""Compiled LangGraph topology for generic Text2Cypher with reflection."""

import json
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.graph import END, StateGraph

from architectures.generic.graph import route_after_router
from architectures.generic.nodes import (
    agent_node, answer_generation_node, neo4j_node, route_after_agent,
    route_after_validation, router_node, terminal_node, text2cypher_node,
    validate_cypher_node,
)
from architectures.generic.state import AgentState, MAX_AGENT_TURNS


def reflection_node(state: AgentState, *, handlers: Any, conversational_model: str, prompt_version: str) -> dict[str, Any]:
    draft = state.get("draft_answer") or state.get("answer") or ""
    result = state.get("draft_result") or state.get("result")
    satisfactory, feedback = handlers.reflect_answer(
        state["question"], draft, result,
        conversational_model=conversational_model, prompt_version=prompt_version,
    )
    payload = {"status": "ok" if satisfactory else "retry", "feedback": feedback}
    if satisfactory:
        return {"messages": [ToolMessage(content=json.dumps(payload), name="reflection", tool_call_id="reflection")]} 
    return {
        "answer": None,
        "result": None,
        "messages": [ToolMessage(content=json.dumps(payload), name="reflection", tool_call_id=f"reflection-{state.get('loop_count', 0)}")],
    }


def route_after_reflection(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, ToolMessage) and message.name == "reflection":
            try:
                payload = json.loads(str(message.content))
            except json.JSONDecodeError:
                payload = {}
            if payload.get("status") == "ok":
                return "terminal"
            break
    if state.get("loop_count", 0) >= MAX_AGENT_TURNS:
        return "terminal"
    return "agent"


def compile_graph(handlers: Any, *, schema: str, schema_prompt: str, conversational_model: str, cypher_model: str, prompt_version: str, neo4j_client: Any = None):
    workflow = StateGraph(AgentState)
    workflow.add_node("router", lambda s: router_node(s, handlers=handlers, conversational_model=conversational_model))
    workflow.add_node("agent", agent_node)
    workflow.add_node("text2cypher", lambda s: text2cypher_node(s, handlers=handlers, schema_prompt=schema_prompt, cypher_model=cypher_model, prompt_version=prompt_version))
    workflow.add_node("validate_cypher", lambda s: validate_cypher_node(s, handlers=handlers, schema=schema))
    workflow.add_node("neo4j", lambda s: neo4j_node(s, handlers=handlers, neo4j_client=neo4j_client))
    workflow.add_node("answer_generation", lambda s: answer_generation_node(s, handlers=handlers, conversational_model=conversational_model, prompt_version=prompt_version))
    workflow.add_node("reflection", lambda s: reflection_node(s, handlers=handlers, conversational_model=conversational_model, prompt_version=prompt_version))
    workflow.add_node("terminal", terminal_node)
    workflow.set_entry_point("router")
    workflow.add_conditional_edges("router", route_after_router, {"agent": "agent", "answer_generation": "answer_generation"})
    workflow.add_conditional_edges("agent", route_after_agent, {"text2cypher": "text2cypher", "terminal": "terminal"})
    workflow.add_edge("text2cypher", "validate_cypher")
    workflow.add_conditional_edges("validate_cypher", route_after_validation, {"neo4j": "neo4j", "text2cypher": "text2cypher", "terminal": "terminal"})
    workflow.add_edge("neo4j", "answer_generation")
    workflow.add_edge("answer_generation", "reflection")
    workflow.add_conditional_edges("reflection", route_after_reflection, {"agent": "agent", "terminal": "terminal"})
    workflow.add_edge("terminal", END)
    return workflow.compile()


__all__ = ["compile_graph", "reflection_node", "route_after_reflection"]

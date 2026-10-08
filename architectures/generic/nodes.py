"""Foundation nodes for Architecture 1.

These nodes only orchestrate injected handlers. Model and Neo4j behavior is
implemented in the later Text2Cypher phase.
"""

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from .interfaces import GenericHandlers
from .state import AgentState, MAX_AGENT_TURNS, MAX_CYPHER_ATTEMPTS


def _message_payload(message: BaseMessage | None) -> dict[str, Any]:
    if not isinstance(message, ToolMessage):
        return {}
    try:
        payload = json.loads(str(message.content))
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_message(state: AgentState, message_type: type[BaseMessage], name: str | None = None):
    for message in reversed(state.get("messages", [])):
        if isinstance(message, message_type) and (name is None or message.name == name):
            return message
    return None


def router_node(
    state: AgentState,
    *,
    handlers: GenericHandlers,
    conversational_model: str,
) -> dict[str, Any]:
    route = handlers.route_question(
        state["question"], conversational_model=conversational_model
    )
    if route not in {"chitchat", "refusal", "agent"}:
        raise ValueError(f"Unsupported route returned by router: {route!r}")
    return {"route": route}


def agent_node(state: AgentState) -> dict[str, Any]:
    """Enter the generic Cypher path and count one high-level agent turn."""
    return {"loop_count": state.get("loop_count", 0) + 1}


def text2cypher_node(
    state: AgentState,
    *,
    handlers: GenericHandlers,
    schema_prompt: str,
    cypher_model: str,
    prompt_version: str,
) -> dict[str, Any]:
    previous_query = None
    validation_error = None
    validation_message = _latest_message(state, ToolMessage, "validate_cypher")
    if validation_message is not None:
        validation = _message_payload(validation_message)
        if validation.get("status") == "invalid":
            previous_query = validation.get("query")
            validation_error = validation.get("error")

    query = handlers.generate_cypher(
        state["question"],
        schema_prompt=schema_prompt,
        model_name=cypher_model,
        prompt_version=prompt_version,
        previous_query=previous_query,
        validation_error=validation_error,
    )
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Text2Cypher returned an empty query")
    return {"messages": [AIMessage(content=query, name="text2cypher")]}


def validate_cypher_node(
    state: AgentState,
    *,
    handlers: GenericHandlers,
    schema: str,
) -> dict[str, Any]:
    generated = _latest_message(state, AIMessage, "text2cypher") or _latest_message(state, AIMessage, "curated_query")
    if generated is None:
        raise ValueError("No Text2Cypher message is available for validation")
    query = str(generated.content)
    result = dict(handlers.validate_cypher(query, schema=schema))
    prior_invalid = sum(
        1
        for message in state.get("messages", [])
        if isinstance(message, ToolMessage)
        and message.name == "validate_cypher"
        and _message_payload(message).get("status") == "invalid"
    )
    result.setdefault("query", query)
    result.setdefault("attempt", prior_invalid + 1)
    result.setdefault("max_attempts", MAX_CYPHER_ATTEMPTS)
    result.setdefault("status", "invalid")
    return {
        "messages": [
            ToolMessage(
                content=json.dumps(result, default=str),
                name="validate_cypher",
                tool_call_id=f"validate-cypher-{result['attempt']}",
            )
        ]
    }


def route_after_validation(state: AgentState) -> str:
    message = _latest_message(state, ToolMessage, "validate_cypher")
    result = _message_payload(message)
    if result.get("status") in {"valid", "ok"}:
        return "neo4j"
    if result.get("status") == "invalid" and int(result.get("attempt", 1)) < MAX_CYPHER_ATTEMPTS:
        return "text2cypher"
    return "terminal"


def neo4j_node(
    state: AgentState,
    *,
    handlers: GenericHandlers,
    neo4j_client: Any,
) -> dict[str, Any]:
    validation = _message_payload(_latest_message(state, ToolMessage, "validate_cypher"))
    query = validation.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("No validated Cypher query is available for Neo4j")
    result = handlers.run_readonly_cypher(query, neo4j_client=neo4j_client)
    return {
        "messages": [
            ToolMessage(
                content=json.dumps(result, default=str),
                name="neo4j",
                tool_call_id="neo4j-readonly",
            )
        ]
    }


def answer_generation_node(
    state: AgentState,
    *,
    handlers: GenericHandlers,
    conversational_model: str,
    prompt_version: str,
) -> dict[str, Any]:
    neo4j_message = _latest_message(state, ToolMessage, "neo4j")
    query_result = _message_payload(neo4j_message) if neo4j_message else None
    validation = _message_payload(_latest_message(state, ToolMessage, "validate_cypher"))
    query = validation.get("query") if validation else None
    answer, result = handlers.generate_answer(
        state["question"],
        query if isinstance(query, str) else None,
        query_result,
        route=state["route"],
        conversational_model=conversational_model,
        prompt_version=prompt_version,
    )
    return {
        "draft_answer": answer,
        "draft_result": result,
        "answer": answer,
        "result": result,
        "messages": [AIMessage(content=answer, name="answer_generation")],
    }


def terminal_node(state: AgentState) -> dict[str, Any]:
    if state.get("answer"):
        return {}
    validation = _message_payload(_latest_message(state, ToolMessage, "validate_cypher"))
    error = validation.get("error") or "The architecture could not produce a valid Cypher query."
    return {"error": str(error), "answer": None, "result": None}


def route_after_agent(state: AgentState) -> str:
    if state.get("loop_count", 0) >= MAX_AGENT_TURNS:
        return "terminal"
    return "text2cypher"


__all__ = [
    "agent_node",
    "answer_generation_node",
    "neo4j_node",
    "route_after_agent",
    "route_after_validation",
    "router_node",
    "terminal_node",
    "text2cypher_node",
    "validate_cypher_node",
]

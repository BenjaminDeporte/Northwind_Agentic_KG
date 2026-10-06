"""LangGraph state contract for Architecture 1."""

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages


Route = Literal["chitchat", "refusal", "agent"]


class AgentState(TypedDict):
    """Minimal workflow state; observability belongs to MLflow."""

    question: str
    route: Route
    messages: Annotated[list[Any], add_messages]
    draft_answer: str | None
    draft_result: dict[str, Any] | None
    answer: str | None
    result: dict[str, Any] | None
    loop_count: int
    error: str | None


MAX_AGENT_TURNS = 8
MAX_CYPHER_ATTEMPTS = 3

__all__ = ["AgentState", "MAX_AGENT_TURNS", "MAX_CYPHER_ATTEMPTS", "Route"]

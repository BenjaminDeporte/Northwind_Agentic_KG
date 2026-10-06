"""Injected interfaces for Architecture 1.

The implementations arrive in later phases. Keeping these interfaces separate
lets the graph foundation be tested with deterministic fakes.
"""

from typing import Any, Literal, Protocol


Route = Literal["chitchat", "refusal", "agent"]


class GenericHandlers(Protocol):
    def route_question(
        self,
        question: str,
        *,
        conversational_model: str,
    ) -> Route: ...

    def generate_cypher(
        self,
        question: str,
        *,
        schema_prompt: str,
        model_name: str,
        prompt_version: str,
        previous_query: str | None = None,
        validation_error: str | None = None,
    ) -> str: ...

    def validate_cypher(self, query: str, *, schema: str) -> dict[str, Any]: ...

    def run_readonly_cypher(self, query: str, *, neo4j_client: Any) -> dict[str, Any]: ...

    def generate_answer(
        self,
        question: str,
        query: str | None,
        query_result: dict[str, Any] | None,
        *,
        route: Route,
        conversational_model: str,
        prompt_version: str,
    ) -> tuple[str, dict[str, Any] | None]: ...


__all__ = ["GenericHandlers", "Route"]

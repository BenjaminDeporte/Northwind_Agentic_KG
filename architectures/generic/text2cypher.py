"""Parametrable generic Text2Cypher tool for Architecture 1."""

from __future__ import annotations

import re
from typing import Any, Protocol


class ChatModelClient(Protocol):
    """Small provider-neutral interface required by Text2Cypher."""

    def complete(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Any: ...


def _response_text(response: Any) -> str:
    """Extract text from common chat-client response shapes."""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        if isinstance(response.get("content"), str):
            return response["content"]
        choices = response.get("choices") or []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            if isinstance(message.get("content"), str):
                return message["content"]
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    choices = getattr(response, "choices", None) or []
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
    raise TypeError("The Cypher model response did not contain text content")


def _clean_query(text: str) -> str:
    """Remove common Markdown wrappers while leaving validation to Phase 2.3."""
    query = text.strip()
    fenced = re.search(r"```(?:cypher|CYPHER)?\s*\n?(.*?)```", query, re.DOTALL)
    if fenced:
        query = fenced.group(1).strip()
    if query.lower().startswith("cypher:"):
        query = query.split(":", 1)[1].strip()
    if not query:
        raise ValueError("The Cypher model returned an empty query")
    return query


def build_messages(
    question: str,
    *,
    schema_prompt: str,
    prompt_version: str,
    previous_query: str | None = None,
    validation_error: str | None = None,
) -> list[dict[str, str]]:
    """Build the provider-neutral chat messages for initial or repair generation."""
    repair = previous_query is not None or validation_error is not None
    if repair and (not previous_query or not validation_error):
        raise ValueError("Cypher repair requires both previous_query and validation_error")
    if not repair and (previous_query is not None or validation_error is not None):
        raise ValueError("Initial Cypher generation cannot include repair context")

    system = (
        "You generate Cypher for the Northwind Neo4j graph. Return exactly one "
        "read-only Cypher query and no explanation. Use only the schema supplied below. "
        "Do not write data and do not emit multiple statements.\n\n"
        f"Prompt version: {prompt_version}\n\n{schema_prompt}"
    )
    if repair:
        user = (
            f"Question: {question}\n\n"
            "The previous query failed validation. Rewrite it while preserving the "
            "question's intent.\n"
            f"Previous query:\n{previous_query}\n\n"
            f"Validation error:\n{validation_error}\n\n"
            "Return only the replacement Cypher query."
        )
    else:
        user = f"Question: {question}\n\nReturn only the Cypher query."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def generate_cypher(
    question: str,
    *,
    schema_prompt: str,
    model_name: str,
    prompt_version: str,
    model_client: ChatModelClient,
    previous_query: str | None = None,
    validation_error: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 800,
) -> str:
    """Generate an initial or repaired Cypher query with the selected model."""
    messages = build_messages(
        question,
        schema_prompt=schema_prompt,
        prompt_version=prompt_version,
        previous_query=previous_query,
        validation_error=validation_error,
    )
    response = model_client.complete(
        model_name=model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _clean_query(_response_text(response))


class Text2CypherTool:
    """Provider-neutral tool adapter matching the Architecture 1 handler shape."""

    def __init__(self, model_client: ChatModelClient):
        self.model_client = model_client

    def generate_cypher(
        self,
        question: str,
        *,
        schema_prompt: str,
        model_name: str,
        prompt_version: str,
        previous_query: str | None = None,
        validation_error: str | None = None,
    ) -> str:
        return generate_cypher(
            question,
            schema_prompt=schema_prompt,
            model_name=model_name,
            prompt_version=prompt_version,
            model_client=self.model_client,
            previous_query=previous_query,
            validation_error=validation_error,
        )


__all__ = [
    "ChatModelClient",
    "Text2CypherTool",
    "build_messages",
    "generate_cypher",
]

"""Provider-neutral conversational model adapter for Architecture 1."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from .interfaces import Route


class ConversationalModelClient(Protocol):
    def complete(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Any: ...


def _text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        if isinstance(response.get("content"), str):
            return response["content"]
        choices = response.get("choices") or []
        if choices and isinstance(choices[0], dict):
            content = (choices[0].get("message") or {}).get("content")
            if isinstance(content, str):
                return content
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    choices = getattr(response, "choices", None) or []
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
    raise TypeError("The conversational model response did not contain text content")


def _json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        parsed = json.loads(cleaned)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def build_route_messages(question: str, *, prompt_version: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Classify the user request for the Northwind agent. Return JSON only "
                "with route exactly one of chitchat, refusal, or agent. Use chitchat "
                "for ordinary conversation, refusal for unsafe or disallowed requests, "
                f"and agent for questions requiring graph data. Prompt version: {prompt_version}."
            ),
        },
        {"role": "user", "content": question},
    ]


def route_question(
    question: str,
    *,
    conversational_model: str,
    model_client: ConversationalModelClient,
    prompt_version: str = "generic-v1",
    max_tokens: int = 80,
) -> Route:
    response = model_client.complete(
        model_name=conversational_model,
        messages=build_route_messages(question, prompt_version=prompt_version),
        temperature=0.0,
        max_tokens=max_tokens,
    )
    parsed = _json_object(_text(response)) or {}
    route = parsed.get("route")
    if route in {"chitchat", "refusal", "agent"}:
        return route
    # Treating a malformed classifier response as an agent request preserves
    # answerability while keeping the explicit route contract visible downstream.
    return "agent"


def build_answer_messages(
    question: str,
    query: str | None,
    query_result: dict[str, Any] | None,
    *,
    route: Route,
    prompt_version: str,
) -> list[dict[str, str]]:
    if route == "chitchat":
        instruction = "Respond naturally and briefly to the conversational request."
    elif route == "refusal":
        instruction = "Decline the request briefly and clearly. Do not query or invent graph facts."
    else:
        instruction = (
            "Answer the question using only the supplied query result. If the result is "
            "empty, say that no matching records were found. Do not invent values."
        )
    context = {
        "query": query,
        "query_result": query_result,
    }
    return [
        {
            "role": "system",
            "content": (
                f"You are the Northwind conversational answer model. {instruction} "
                "Return JSON only with an answer string and a result object or null. "
                f"Prompt version: {prompt_version}."
            ),
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nEvidence context:\n{json.dumps(context, default=str)}",
        },
    ]


def generate_answer(
    question: str,
    query: str | None,
    query_result: dict[str, Any] | None,
    *,
    route: Route,
    conversational_model: str,
    model_client: ConversationalModelClient,
    prompt_version: str = "generic-v1",
    temperature: float = 0.0,
    max_tokens: int = 800,
) -> tuple[str, dict[str, Any] | None]:
    response = model_client.complete(
        model_name=conversational_model,
        messages=build_answer_messages(
            question,
            query,
            query_result,
            route=route,
            prompt_version=prompt_version,
        ),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    raw = _text(response)
    parsed = _json_object(raw)
    if parsed is None:
        # Preserve useful text while making the structured-output failure visible
        # to the caller and later MLflow logging.
        return raw.strip(), None
    answer = parsed.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return raw.strip(), None
    result = parsed.get("result")
    return answer.strip(), result if isinstance(result, dict) else None


def reflect_answer(
    question: str,
    draft_answer: str,
    query_result: dict[str, Any] | None,
    *,
    conversational_model: str,
    model_client: ConversationalModelClient,
    prompt_version: str = "generic-v1",
) -> tuple[bool, str | None]:
    """Ask the fixed conversational model whether a draft answers the question."""
    response = model_client.complete(
        model_name=conversational_model,
        messages=[
            {"role": "system", "content": (
                "Review the draft answer against the question and supplied result. "
                "Return JSON only: {\"satisfactory\": true|false, \"feedback\": string}. "
                f"Prompt version: {prompt_version}."
            )},
            {"role": "user", "content": json.dumps({
                "question": question, "draft_answer": draft_answer, "query_result": query_result
            }, default=str)},
        ],
        temperature=0.0,
        max_tokens=180,
    )
    parsed = _json_object(_text(response)) or {}
    return bool(parsed.get("satisfactory")), parsed.get("feedback") if isinstance(parsed.get("feedback"), str) else None


def select_curated_tool(
    question: str,
    *,
    tools: list[dict[str, str]],
    conversational_model: str,
    model_client: ConversationalModelClient,
    prompt_version: str = "generic-v1",
) -> str | None:
    """Let the conversational model select a named curated query or fallback."""
    response = model_client.complete(
        model_name=conversational_model,
        messages=[
            {"role": "system", "content": (
                "Choose a curated graph query only when it directly matches the question. "
                "Return JSON only with tool_name set to one listed name or null. "
                f"Available tools: {json.dumps(tools)}. Prompt version: {prompt_version}."
            )},
            {"role": "user", "content": question},
        ],
        temperature=0.0,
        max_tokens=120,
    )
    parsed = _json_object(_text(response)) or {}
    selected = parsed.get("tool_name")
    names = {tool["name"] for tool in tools}
    return selected if selected in names else None


class ConversationalTool:
    """Handler-shaped adapter for router and answer-generation methods."""

    def __init__(self, model_client: ConversationalModelClient):
        self.model_client = model_client

    def route_question(self, question: str, *, conversational_model: str) -> Route:
        return route_question(
            question,
            conversational_model=conversational_model,
            model_client=self.model_client,
        )

    def generate_answer(
        self,
        question: str,
        query: str | None,
        query_result: dict[str, Any] | None,
        *,
        route: Route,
        conversational_model: str,
        prompt_version: str,
    ) -> tuple[str, dict[str, Any] | None]:
        return generate_answer(
            question,
            query,
            query_result,
            route=route,
            conversational_model=conversational_model,
            model_client=self.model_client,
            prompt_version=prompt_version,
        )

    def reflect_answer(self, question: str, draft_answer: str, query_result: dict[str, Any] | None, *, conversational_model: str, prompt_version: str) -> tuple[bool, str | None]:
        return reflect_answer(question, draft_answer, query_result, conversational_model=conversational_model, model_client=self.model_client, prompt_version=prompt_version)

    def select_curated_tool(self, question: str, *, tools: list[dict[str, str]], conversational_model: str, prompt_version: str) -> str | None:
        return select_curated_tool(question, tools=tools, conversational_model=conversational_model, model_client=self.model_client, prompt_version=prompt_version)


__all__ = [
    "ConversationalModelClient",
    "ConversationalTool",
    "build_answer_messages",
    "build_route_messages",
    "generate_answer",
    "reflect_answer",
    "select_curated_tool",
    "route_question",
]

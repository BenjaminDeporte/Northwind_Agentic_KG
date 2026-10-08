"""Mistral adapter for the shared conversational-model protocol."""

from __future__ import annotations

from typing import Any

from common.config import AppSettings


def _mistral_type():
    """Import lazily so deterministic tests do not construct provider clients."""
    try:
        from mistralai import Mistral
    except ImportError:  # pragma: no cover - compatibility with older SDKs
        from mistralai.client import Mistral
    return Mistral


class MistralChatClient:
    """Implement ``ConversationalModelClient`` using the Mistral chat API.

    The raw SDK response is returned unchanged so callers can retain provider
    metadata for MLflow. This adapter does not parse routing or answer JSON.
    """

    def __init__(self, *, api_key: str | None = None, client: Any = None):
        resolved = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
        if client is None:
            if not resolved:
                raise ValueError("A Mistral API key is required to create the conversational client")
            client = _mistral_type()(api_key=resolved)
        self._client = client

    def complete(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Any:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name is required for a Mistral chat request")
        if not messages:
            raise ValueError("At least one chat message is required")
        return self._client.chat.complete(
            model=model_name.strip(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def build_mistral_client(settings: AppSettings) -> MistralChatClient:
    """Build the fixed conversational client from shared settings."""
    if settings.models.conversational_provider.lower() != "mistral":
        raise ValueError(
            "build_mistral_client requires conversational_provider='mistral'; "
            f"got {settings.models.conversational_provider!r}"
        )
    return MistralChatClient(api_key=settings.models.conversational_api_key)


__all__ = ["MistralChatClient", "build_mistral_client"]

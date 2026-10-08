"""Ollama HTTP adapter for local Cypher-generation models."""

from __future__ import annotations

import json
from typing import Any
from urllib import request


class OllamaChatClient:
    """Implement the generic chat-client protocol against Ollama's `/api/chat`."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        num_gpu: int = 0,
        timeout: float = 120.0,
        opener: Any = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.num_gpu = num_gpu
        self.timeout = timeout
        self._opener = opener or request.urlopen

    def complete(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name is required for an Ollama request")
        if not messages:
            raise ValueError("At least one chat message is required")
        payload = {
            "model": model_name.strip(),
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_gpu": self.num_gpu,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(req, timeout=self.timeout) as response:
                raw = response.read()
        except Exception as exc:
            raise RuntimeError(f"Ollama request failed at {self.base_url}: {exc}") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Ollama returned a non-JSON response") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Ollama returned an invalid response object")
        if result.get("error"):
            raise RuntimeError(f"Ollama error: {result['error']}")
        return result


__all__ = ["OllamaChatClient"]

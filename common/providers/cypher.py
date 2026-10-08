"""Registry selecting the configured Cypher-generation provider."""

from __future__ import annotations

from typing import Any, Callable

from common.config import AppSettings
from common.config.models import CypherModelCandidate, DEFAULT_CYPHER_CANDIDATES

from .mistral import MistralChatClient
from .ollama import OllamaChatClient


class CypherProviderRegistry:
    """Map model identifiers to provider clients without importing SDKs in graphs."""

    def __init__(self):
        self._clients: dict[str, Any] = {}
        self._providers: dict[str, str] = {}

    def register(self, *, model_name: str, provider: str, client: Any) -> None:
        if not model_name.strip():
            raise ValueError("A Cypher model name is required")
        if model_name in self._clients:
            raise ValueError(f"Cypher model is already registered: {model_name}")
        self._clients[model_name] = client
        self._providers[model_name] = provider

    def client_for(self, model_name: str) -> Any:
        try:
            return self._clients[model_name]
        except KeyError as exc:
            available = ", ".join(sorted(self._clients)) or "none"
            raise ValueError(f"Unsupported Cypher model {model_name!r}; registered: {available}") from exc

    def provider_for(self, model_name: str) -> str:
        self.client_for(model_name)
        return self._providers[model_name]

    def model_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._clients))


def build_cypher_registry(
    settings: AppSettings,
    *,
    candidates: tuple[CypherModelCandidate, ...] = DEFAULT_CYPHER_CANDIDATES,
    ollama_client: Any = None,
    mistral_client: Any = None,
    client_factories: dict[str, Callable[[CypherModelCandidate], Any]] | None = None,
) -> CypherProviderRegistry:
    """Build supported configured candidates; fail clearly for unsupported providers."""
    registry = CypherProviderRegistry()
    factories = client_factories or {}
    for candidate in candidates:
        if candidate.name in factories:
            client = factories[candidate.name](candidate)
        elif candidate.provider == "ollama":
            client = ollama_client or OllamaChatClient(
                base_url=settings.models.ollama_base_url,
                num_gpu=settings.models.ollama_num_gpu,
            )
        elif candidate.provider == "mistral":
            client = mistral_client or MistralChatClient(api_key=settings.models.cypher_api_key)
        else:
            # Candidates can be listed for future sweeps without pretending an
            # adapter exists. They are skipped until their provider is implemented.
            continue
        registry.register(model_name=candidate.name, provider=candidate.provider, client=client)
    if not registry.model_names():
        raise ValueError("No supported Cypher model candidates were configured")
    return registry


__all__ = ["CypherProviderRegistry", "build_cypher_registry"]

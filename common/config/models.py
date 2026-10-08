"""Model candidates and configuration metadata for the Architecture 1 sweep."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CypherModelCandidate:
    name: str
    provider: str
    api_key_env: str | None = None
    notes: str = ""


DEFAULT_CYPHER_CANDIDATES: tuple[CypherModelCandidate, ...] = (
    CypherModelCandidate("mistral-large-latest", "mistral", "MISTRAL_API_KEY"),
    CypherModelCandidate("gpt-5", "openai", "OPENAI_API_KEY"),
    CypherModelCandidate("claude-sonnet", "anthropic", "ANTHROPIC_API_KEY"),
    CypherModelCandidate(
        "hf.co/mradermacher/text-to-cypher-Gemma-3-4B-Instruct-2025.04.0-GGUF:Q4_K_M",
        "ollama",
        None,
        "Neo4j Gemma 3 4B quantized Text2Cypher candidate",
    ),
)


__all__ = ["CypherModelCandidate", "DEFAULT_CYPHER_CANDIDATES"]

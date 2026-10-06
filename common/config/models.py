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
    CypherModelCandidate("neo4j/text2cypher", "huggingface", "HF_TOKEN", "Neo4j fine-tuned candidate"),
)


__all__ = ["CypherModelCandidate", "DEFAULT_CYPHER_CANDIDATES"]

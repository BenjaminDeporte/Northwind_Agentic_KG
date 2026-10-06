"""Read-only Neo4j execution using the generic result envelope."""

from __future__ import annotations

from typing import Any

from .results import result_envelope
from .validation import normalize_query, validate_cypher


def _records(client: Any, query: str) -> list[Any]:
    if hasattr(client, "execute_query"):
        result = client.execute_query(query)
        records = result[0] if isinstance(result, tuple) else result
        return list(records)
    session_factory = getattr(client, "session", None)
    if not callable(session_factory):
        raise TypeError("Neo4j client must provide execute_query or session")
    with session_factory() as session:
        result = session.run(query)
        return list(result)


def run_readonly_cypher(query: str, *, neo4j_client: Any, schema: str | None = None) -> dict[str, Any]:
    """Validate and execute one read-only query, returning a stable envelope."""
    normalized = query
    try:
        normalized = normalize_query(query)
        if schema is not None:
            validation = validate_cypher(normalized, schema=schema)
            if validation["status"] != "valid":
                return {**validation, "rows": [], "evidence": {"nodes": [], "edges": []}}
        records = _records(neo4j_client, normalized)
        return result_envelope(records, query=normalized)
    except Exception as exc:
        return result_envelope([], query=normalized, status="failed", error=str(exc))


class Neo4jTool:
    """Handler-shaped adapter used by the generic graph."""

    def __init__(self, client: Any, *, schema: str | None = None):
        self.client = client
        self.schema = schema

    def run_readonly_cypher(self, query: str, *, neo4j_client: Any = None) -> dict[str, Any]:
        return run_readonly_cypher(
            query,
            neo4j_client=neo4j_client or self.client,
            schema=self.schema,
        )


__all__ = ["Neo4jTool", "run_readonly_cypher"]

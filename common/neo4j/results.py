"""JSON-safe generic envelope for Neo4j result rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _node(value: Any) -> dict[str, Any] | None:
    labels = getattr(value, "labels", None)
    props = getattr(value, "_properties", None)
    if labels is None or props is None:
        return None
    identity = getattr(value, "element_id", getattr(value, "id", None))
    return {
        "element_id": str(identity) if identity is not None else None,
        "labels": sorted(str(label) for label in labels),
        "properties": {str(k): _json(v) for k, v in dict(props).items()},
    }


def _relationship(value: Any) -> dict[str, Any] | None:
    rel_type = getattr(value, "type", None)
    if rel_type is None or not hasattr(value, "start_node"):
        return None
    identity = getattr(value, "element_id", getattr(value, "id", None))
    start = getattr(value.start_node, "element_id", getattr(value.start_node, "id", None))
    end = getattr(value.end_node, "element_id", getattr(value.end_node, "id", None))
    props = getattr(value, "_properties", {})
    return {
        "element_id": str(identity) if identity is not None else None,
        "type": str(rel_type),
        "start_element_id": str(start) if start is not None else None,
        "end_element_id": str(end) if end is not None else None,
        "properties": {str(k): _json(v) for k, v in dict(props).items()},
    }


def _json(value: Any) -> Any:
    node = _node(value)
    if node is not None:
        return {"kind": "node", **node}
    relationship = _relationship(value)
    if relationship is not None:
        return {"kind": "relationship", **relationship}
    if hasattr(value, "nodes") and hasattr(value, "relationships"):
        return {
            "kind": "path",
            "nodes": [_json(item) for item in value.nodes],
            "relationships": [_json(item) for item in value.relationships],
        }
    if isinstance(value, Mapping):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def _collect(value: Any, nodes: dict[str, dict], edges: dict[str, dict]) -> None:
    normalized = _json(value)
    if isinstance(normalized, dict):
        if normalized.get("kind") == "node":
            key = normalized.get("element_id") or repr(normalized)
            nodes[key] = normalized
        elif normalized.get("kind") == "relationship":
            key = normalized.get("element_id") or repr(normalized)
            edges[key] = normalized
        for item in normalized.values():
            _collect(item, nodes, edges)
    elif isinstance(normalized, list):
        for item in normalized:
            _collect(item, nodes, edges)


def result_envelope(rows: list[Mapping[str, Any]], *, query: str, status: str = "ok", error: str | None = None) -> dict[str, Any]:
    normalized_rows = []
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    for row in rows:
        values = {str(k): _json(v) for k, v in dict(row).items()}
        for value in row.values():
            _collect(value, nodes, edges)
        normalized_rows.append({"values": values})
    return {
        "status": status if rows or status != "ok" else "empty",
        "query": query,
        "rows": normalized_rows,
        "evidence": {"nodes": list(nodes.values()), "edges": list(edges.values())},
        "error": error,
    }


__all__ = ["result_envelope"]

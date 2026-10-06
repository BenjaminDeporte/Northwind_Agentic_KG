"""Small, deterministic validation boundary for generated Cypher.

Validation is deliberately performed before the driver is called.  The optional
``explain`` callback lets a runtime add Neo4j's EXPLAIN preflight without making
the pure validator depend on a live database.
"""

from __future__ import annotations

import re
from typing import Any, Callable


_WRITE = re.compile(
    r"\b(?:CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b",
    re.IGNORECASE,
)
_CLAUSE = re.compile(
    r"\b(?:MATCH|OPTIONAL\s+MATCH|CALL|WITH|UNWIND|RETURN|WHERE|ORDER\s+BY|"
    r"SKIP|LIMIT|UNION|USE|YIELD|DISTINCT|EXPLAIN)\b",
    re.IGNORECASE,
)
_LABEL = re.compile(r"\(\s*\w*\s*((?::\s*(`[^`]+`|[A-Za-z_][\w]*))+)")
_REL = re.compile(r"\[\s*\w*\s*(?::\s*(`[^`]+`|[A-Za-z_][\w]*))?")
_PROPERTY = re.compile(r"\b\w+\s*\.\s*(`[^`]+`|[A-Za-z_][\w]*)")


def _ident(value: str) -> str:
    value = value.strip()
    return value[1:-1] if value.startswith("`") and value.endswith("`") else value


def _masked(text: str) -> str:
    """Mask strings and comments so delimiters inside them are ignored."""
    out: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("//", i):
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            out.append(" " * (end - i))
            i = end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = len(text) if end < 0 else end + 2
            out.append(" " * (end - i))
            i = end
            continue
        if text[i] in {"'", '"'}:
            quote = text[i]
            j = i + 1
            while j < len(text):
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                j += 1
            out.append(" " * (j - i))
            i = j
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def normalize_query(query: str) -> str:
    """Trim whitespace and one terminal semicolon."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Cypher query is empty")
    query = query.strip()
    masked = _masked(query).rstrip()
    if masked.endswith(";"):
        query = query[: len(masked) - 1].rstrip()
        masked = _masked(query).rstrip()
    if ";" in masked:
        raise ValueError("Multiple Cypher statements are not allowed")
    return query


def validate_cypher(
    query: str,
    *,
    schema: str,
    explain: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Return a structured validation result; never execute a data query."""
    try:
        normalized = normalize_query(query)
        masked = _masked(normalized)
        if _WRITE.search(masked):
            raise ValueError("Write clauses are not allowed")
        if not _CLAUSE.search(masked):
            raise ValueError("Query does not contain a supported Cypher clause")
        if not re.search(r"\bRETURN\b", masked, re.IGNORECASE) and not re.search(
            r"\bYIELD\b", masked, re.IGNORECASE
        ):
            raise ValueError("Read-only query must return or yield a result")

        labels: set[str] = set()
        node_section = schema.split("## Relationships", 1)[0]
        labels.update(
            _ident(x)
            for x in re.findall(r"^\|\s*([A-Za-z_][\w]*)\s*\|", node_section, re.MULTILINE)
            if x.lower() not in {"label", "node label"}
        )
        relationships = set()
        relationship_section = schema.split("## Relationships", 1)[-1]
        relationships.update(
            _ident(x)
            for x in re.findall(r"^\|\s*([A-Za-z_][\w]*)\s*\|", relationship_section, re.MULTILINE)
            if x.lower() not in {"type", "relationship"}
        )
        mentioned_labels = {
            _ident(label)
            for match in _LABEL.finditer(masked)
            for label in re.findall(r":\s*(`[^`]+`|[A-Za-z_][\w]*)", match.group(1))
        }
        unknown_labels = sorted(mentioned_labels - labels) if labels else []
        if unknown_labels:
            raise ValueError(f"Unknown schema label(s): {', '.join(unknown_labels)}")
        mentioned_relationships = {
            _ident(x) for x in _REL.findall(masked) if x
        }
        unknown_relationships = sorted(mentioned_relationships - relationships)
        if unknown_relationships:
            raise ValueError(
                f"Unknown schema relationship type(s): {', '.join(unknown_relationships)}"
            )

        # Property names are checked only when the schema exposes a property list.
        schema_props = {
            _ident(p)
            for p in re.findall(r"\b([A-Za-z_][\w]*)\s*(?:,|\||$)", schema, re.MULTILINE)
        }
        # Avoid rejecting aliases/functions; explicit unknown property checks are
        # handled when the schema has a clear ``Properties`` column.
        if "Properties" in schema:
            properties_section = schema.split("Properties", 1)[1]
            schema_props |= {
                _ident(p)
                for p in re.findall(r"\b([A-Za-z_][\w]*)\b", properties_section)
            }
            unknown_props = sorted(
                {_ident(x) for x in _PROPERTY.findall(masked)} - schema_props
            )
            if unknown_props:
                raise ValueError(f"Unknown schema property reference(s): {', '.join(unknown_props)}")

        if explain is not None:
            explain(normalized)
        return {"status": "valid", "query": normalized, "error": None}
    except Exception as exc:  # validator returns data, it does not raise for bad input
        return {"status": "invalid", "query": query, "error": str(exc)}


__all__ = ["normalize_query", "validate_cypher"]

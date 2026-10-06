"""Mechanical projection of the authoritative SCHEMA.md into prompt context."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any


def default_schema_path() -> Path:
    """Return the repository's authoritative schema path."""
    return Path(__file__).resolve().parents[2] / "SCHEMA.md"


def _read_schema(schema_path: Path | None = None) -> str:
    path = schema_path or default_schema_path()
    if not path.exists():
        raise FileNotFoundError(f"SCHEMA.md not found at {path}")
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}.*?$([\s\S]*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def _table_rows(section: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return []
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        if set(line.replace("|", "").replace(":", "").replace("-", "").strip()) == set():
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def _property_names(value: str) -> list[str]:
    names: list[str] = []
    if not value or value.strip() == "—":
        return names
    # Types may contain commas, for example ``quantity (Long, 100/2155)``.
    # Match the property token and consume its complete parenthesized type.
    for match in re.finditer(
        r"(?<![\w/])([A-Za-z_]\w*)\s*(?:\([^)]*\))?(?=\s*(?:,|$))",
        value,
    ):
        names.append(match.group(1))
    return names


def _direction(value: str) -> tuple[str, str]:
    separator = "→" if "→" in value else "->"
    if separator not in value:
        return "", ""
    left, right = value.split(separator, 1)
    return left.strip(), right.strip()


def extract_labels(schema_text: str) -> list[dict[str, Any]]:
    rows = _table_rows(_section(schema_text, "Node labels"))
    labels = []
    for row in rows:
        label = row.get("Label", "")
        if label:
            labels.append(
                {
                    "label": label,
                    "count": row.get("Count", ""),
                    "key": row.get("Key", ""),
                    "name_property": row.get("Name property", ""),
                    "properties": _property_names(row.get("Properties (verified, types)", "")),
                }
            )
    return labels


def extract_relationships(schema_text: str) -> list[dict[str, Any]]:
    rows = _table_rows(_section(schema_text, "Relationships"))
    relationships = []
    for row in rows:
        rel_type = row.get("Type", "")
        if not rel_type:
            continue
        from_label, to_label = _direction(row.get("From → To", ""))
        relationships.append(
            {
                "type": rel_type,
                "from_label": from_label,
                "to_label": to_label,
                "count": row.get("Count", ""),
                "properties": _property_names(row.get("Properties (verify)", "")),
                "meaning": row.get("Meaning", ""),
            }
        )
    return relationships


def extract_traversal_patterns(schema_text: str) -> list[dict[str, str]]:
    section = _section(schema_text, "Core traversal patterns (the demo beats as Cypher shapes)")
    patterns: list[dict[str, str]] = []
    headings = list(
        re.finditer(r"^\*\*(?P<name>.*?)\:\*\*\s*$", section, flags=re.MULTILINE)
    )
    blocks = list(re.finditer(r"```cypher\s*\n(?P<cypher>.*?)```", section, flags=re.DOTALL))
    for block in blocks:
        heading = next((item for item in reversed(headings) if item.start() < block.start()), None)
        if heading is None:
            continue
        description = section[heading.end() : block.start()].strip()
        patterns.append(
            {
                "name": heading.group("name").strip(),
                "description": description,
                "cypher": block.group("cypher").strip(),
            }
        )
    return patterns


def extract_rules(schema_text: str) -> list[str]:
    section = _section(schema_text, "Rules for the exploratory tool (run_readonly_cypher)")
    return [match.group(1).strip() for match in re.finditer(r"^-\s+(.*)$", section, re.MULTILINE)]


def extract_revenue_rule(schema_text: str) -> str | None:
    match = re.search(r"Revenue must be computed as `([^`]+)`", schema_text)
    return match.group(1) if match else None


def _prompt_from_schema(schema_text: str, *, include_impact_analysis: bool) -> str:
    labels = extract_labels(schema_text)
    relationships = extract_relationships(schema_text)
    patterns = extract_traversal_patterns(schema_text)
    rules = extract_rules(schema_text)
    revenue_rule = extract_revenue_rule(schema_text)

    parts = [
        "# Northwind Neo4j schema",
        "",
        "You are a Cypher query generator. SCHEMA.md is the complete and authoritative graph universe.",
        "Use only the labels, keys, properties, and relationship types listed below.",
        "Generate one read-only Cypher query; do not write data or use multiple statements.",
        "",
        "## Instance summary",
        _section(schema_text, "Instance summary"),
        "",
        "## Node labels",
    ]
    for label in labels:
        parts.append(f"- {label['label']}: key `{label['key']}`")
        if label["name_property"] and label["name_property"] != "—":
            parts.append(f"  name property `{label['name_property']}`")
        if label["properties"]:
            parts.append(f"  properties: {', '.join(label['properties'])}")

    parts.extend(["", "## Relationships"])
    for relationship in relationships:
        direction = f"{relationship['from_label']} → {relationship['to_label']}"
        parts.append(f"- {relationship['type']}: {direction}")
        if relationship["properties"]:
            parts.append(f"  properties: {', '.join(relationship['properties'])}")
        if relationship["meaning"]:
            parts.append(f"  meaning: {relationship['meaning']}")

    parts.extend(["", "## Structural facts", _section(schema_text, "Structural facts"), ""])
    if revenue_rule:
        parts.extend(
            [
                "## Revenue rule",
                f"Revenue must be computed as `{revenue_rule}`.",
                "Treat null quantity as an unusable line rather than silently dropping it.",
                "",
            ]
        )

    parts.extend(["## Core traversal patterns"])
    for pattern in patterns:
        if not include_impact_analysis and pattern["name"].lower().startswith("impact analysis"):
            continue
        parts.extend(
            [
                f"### {pattern['name']}",
                pattern["description"],
                "```cypher",
                pattern["cypher"],
                "```",
                "",
            ]
        )

    parts.extend(["## Read-only generation rules"])
    parts.extend(f"{index}. {rule}" for index, rule in enumerate(rules, start=1))
    parts.append("Never invent graph labels, properties, or relationships.")
    return "\n".join(parts).strip() + "\n"


@lru_cache(maxsize=16)
def _cached_prompt(schema_path: str, include_impact_analysis: bool) -> str:
    return _prompt_from_schema(
        _read_schema(Path(schema_path)),
        include_impact_analysis=include_impact_analysis,
    )


def generate_schema_prompt(
    schema_path: Path | None = None,
    *,
    include_impact_analysis: bool = False,
) -> str:
    """Build a deterministic prompt from SCHEMA.md; never use a hardcoded schema."""
    path = schema_path or default_schema_path()
    return _cached_prompt(str(path.resolve()), include_impact_analysis)


def get_labels(schema_path: Path | None = None) -> list[dict[str, Any]]:
    return extract_labels(_read_schema(schema_path))


def get_relationships(schema_path: Path | None = None) -> list[dict[str, Any]]:
    return extract_relationships(_read_schema(schema_path))


def get_traversal_patterns(schema_path: Path | None = None) -> list[dict[str, str]]:
    return extract_traversal_patterns(_read_schema(schema_path))


def get_revenue_rule(schema_path: Path | None = None) -> str | None:
    return extract_revenue_rule(_read_schema(schema_path))


def clear_schema_prompt_cache() -> None:
    _cached_prompt.cache_clear()


__all__ = [
    "clear_schema_prompt_cache",
    "default_schema_path",
    "extract_labels",
    "extract_relationships",
    "extract_revenue_rule",
    "extract_rules",
    "extract_traversal_patterns",
    "generate_schema_prompt",
    "get_labels",
    "get_relationships",
    "get_revenue_rule",
    "get_traversal_patterns",
]

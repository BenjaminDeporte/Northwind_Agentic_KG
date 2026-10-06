from pathlib import Path

from common.prompts.schema_prompt import (
    clear_schema_prompt_cache,
    generate_schema_prompt,
    get_labels,
    get_relationships,
    get_revenue_rule,
    get_traversal_patterns,
)


ROOT = Path(__file__).parents[1]


def test_extracts_all_northwind_labels_and_relationships():
    labels = get_labels(ROOT / "SCHEMA.md")
    relationships = get_relationships(ROOT / "SCHEMA.md")
    assert len(labels) == 9
    assert len(relationships) == 9
    assert next(item for item in labels if item["label"] == "Customer")["key"] == "customerID"
    purchased = next(item for item in relationships if item["type"] == "PURCHASED")
    assert purchased["from_label"] == "Customer"
    assert purchased["to_label"] == "Order"


def test_extracts_patterns_and_revenue_rule():
    patterns = get_traversal_patterns(ROOT / "SCHEMA.md")
    assert len(patterns) == 3
    assert any("Impact analysis" in pattern["name"] for pattern in patterns)
    assert get_revenue_rule(ROOT / "SCHEMA.md") == "coalesce(line.unitPrice, p.unitPrice) * line.quantity"


def test_prompt_contains_authoritative_schema_context():
    clear_schema_prompt_cache()
    prompt = generate_schema_prompt(ROOT / "SCHEMA.md")
    assert "Customer" in prompt
    assert "PURCHASED: Customer → Order" in prompt
    assert "coalesce(line.unitPrice, p.unitPrice) * line.quantity" in prompt
    assert "Never invent graph labels" in prompt
    assert "Impact analysis" not in prompt
    assert "three total attempts" in prompt.lower()


def test_impact_analysis_can_be_enabled_for_a_later_architecture():
    prompt = generate_schema_prompt(ROOT / "SCHEMA.md", include_impact_analysis=True)
    assert "Impact analysis" in prompt


def test_prompt_generation_is_cached_for_same_schema_path():
    clear_schema_prompt_cache()
    first = generate_schema_prompt(ROOT / "SCHEMA.md")
    second = generate_schema_prompt(ROOT / "SCHEMA.md")
    assert first == second


def test_projection_is_not_hardcoded(tmp_path):
    schema = tmp_path / "SCHEMA.md"
    schema.write_text(
        """# Test\n\n## Node labels\n\n| Label | Count | Key | Name property | Properties (verified, types) |\n|---|---|---|---|---|\n| Widget | 1 | widgetID | widgetName | widgetName |\n\n## Relationships\n\n| Type | From → To | Count | Properties (verify) | Meaning |\n|---|---|---|---|---|\n| LINKS | Widget → Widget | 1 | — | links widgets |\n\n## Core traversal patterns (the demo beats as Cypher shapes)\n\n**Widget lookup:** simple lookup\n\n```cypher\nMATCH (w:Widget) RETURN w\n```\n\n## Rules for the exploratory tool (run_readonly_cypher)\n\n- Use only Widget.\n\n## Structural facts\n\n- Widget is the test label.\n""",
        encoding="utf-8",
    )
    generated = generate_schema_prompt(schema)
    assert "Widget" in generated
    assert "Customer" not in generated

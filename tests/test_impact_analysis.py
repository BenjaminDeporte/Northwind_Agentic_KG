"""
Unit tests for impact_analysis tool (Phase 1, Item 1.2).

Contract: Ground truth dicts from GROUND_TRUTH_PHASE_1.md are assertions.
All tests hit live AuraDB - no mocking.
"""

import json
from src.neo4j.tools import impact_analysis


# =============================================================================
# Ground Truth Data (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================

GT_1_2_1 = {
    "status": "ok",
    "anchor": {"label": "Supplier", "key": "1", "name": "Exotic Liquids", "country": "UK"},
    "subgraph": {
        "nodes": {"Supplier": 1, "Product": 3, "Order": 90, "Customer": 49},
        "edges": {"SUPPLIES": 3, "ORDERS": 94, "PURCHASED": 90}
    },
    "aggregates": {
        "products_affected": 3,
        "orders_affected": 90,
        "revenue_at_risk": 35916.8,
        "unusable_lines": 0
    }
}


# =============================================================================
# Contract Notes (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================
# 1. Traversal pattern: Supplier -[:SUPPLIES]-> Product <-[:ORDERS]- Order <-[:PURCHASED]- Customer
# 2. Revenue figure 35,916.80 is hand-verified to the cent
# 3. Revenue rule: coalesce(line.unitPrice, p.unitPrice) * line.quantity
# 4. Chai lines carry two prices: 14.4 (line-level) and 18.0 (product fallback)


class TestImpactAnalysis:
    """Test impact_analysis tool against live AuraDB."""

    def test_1_2_1_supplier_exotic_liquids(self):
        """GT 1.2.1: Supplier 'Exotic Liquids' impact analysis (depth 3, out)."""
        result = impact_analysis(
            entity_key="1",
            entity_label="Supplier",
            direction="out",
            depth=3
        )
        assert result == GT_1_2_1, f"Expected:\n{json.dumps(GT_1_2_1, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_aggregates_types(self):
        """Verify aggregate value types: products=int, orders=int, revenue=float, unusable=int."""
        result = impact_analysis(
            entity_key="1",
            entity_label="Supplier",
            direction="out",
            depth=3
        )
        assert result["status"] == "ok"
        aggs = result["aggregates"]
        assert isinstance(aggs["products_affected"], int)
        assert isinstance(aggs["orders_affected"], int)
        assert isinstance(aggs["revenue_at_risk"], float)
        assert isinstance(aggs["unusable_lines"], int)

    def test_anchor_structure(self):
        """Verify anchor contains label, key, name, country."""
        result = impact_analysis(
            entity_key="1",
            entity_label="Supplier",
            direction="out",
            depth=3
        )
        assert result["status"] == "ok"
        anchor = result["anchor"]
        assert anchor["label"] == "Supplier"
        assert anchor["key"] == "1"
        assert anchor["name"] == "Exotic Liquids"
        assert anchor["country"] == "UK"

    def test_empty_result(self):
        """Non-existent entity returns empty aggregates."""
        result = impact_analysis(
            entity_key="NonExistent",
            entity_label="Supplier",
            direction="out",
            depth=3
        )
        assert result["status"] == "empty"
        assert result["aggregates"]["products_affected"] == 0
        assert result["aggregates"]["orders_affected"] == 0
        assert result["aggregates"]["revenue_at_risk"] == 0.0

    def test_invalid_direction(self):
        """Invalid direction returns status 'invalid'."""
        result = impact_analysis(
            entity_key="1",
            entity_label="Supplier",
            direction="invalid",
            depth=3
        )
        assert result["status"] == "invalid"

    def test_revenue_precision(self):
        """Revenue at risk must be 35916.8 (hand-verified to the cent)."""
        result = impact_analysis(
            entity_key="1",
            entity_label="Supplier",
            direction="out",
            depth=3
        )
        assert result["aggregates"]["revenue_at_risk"] == 35916.8

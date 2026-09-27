"""
Unit tests for co_purchase tool (Phase 1, Item 1.3).

Contract: Ground truth dicts from GROUND_TRUTH_PHASE_1.md are assertions.
All tests hit live AuraDB - no mocking.
"""

import json
from src.neo4j.tools import co_purchase


# =============================================================================
# Ground Truth Data (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================

GT_1_3_1 = {
    "status": "ok",
    "product": {"label": "Product", "key": "1", "name": "Chai"},
    "recommendations": [
        {"key": "21", "name": "Sir Rodney's Scones", "co_bought": 4, "label": "Product"},
        {"key": "40", "name": "Boston Crab Meat", "co_bought": 4, "label": "Product"},
        {"key": "60", "name": "Camembert Pierrot", "co_bought": 4, "label": "Product"},
        {"key": "71", "name": "Flotemysost", "co_bought": 4, "label": "Product"},
        {"key": "13", "name": "Konbu", "co_bought": 3, "label": "Product"},
        {"key": "23", "name": "Tunnbröd", "co_bought": 3, "label": "Product"},
        {"key": "29", "name": "Thüringer Rostbratwurst", "co_bought": 3, "label": "Product"},
        {"key": "10", "name": "Ikura", "co_bought": 2, "label": "Product"},
        {"key": "17", "name": "Alice Mutton", "co_bought": 2, "label": "Product"},
        {"key": "18", "name": "Carnarvon Tigers", "co_bought": 2, "label": "Product"}
    ]
}


# =============================================================================
# Contract Notes (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================
# 1. Deterministic tie-break: ties on co_bought broken by ascending productID
# 2. co_purchase LIMIT 10 is load-bearing (>10 candidates exist)
# 3. co_bought values are integers (counts)
# 4. Anchor product is excluded from recommendations


class TestCoPurchase:
    """Test co_purchase tool against live AuraDB."""

    def test_1_3_1_chai(self):
        """GT 1.3.1: Co-purchase for Chai (product_key='1')."""
        result = co_purchase(product_key="1")
        assert result == GT_1_3_1, f"Expected:\n{json.dumps(GT_1_3_1, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_product_anchor_structure(self):
        """Verify anchor product has label, key, name."""
        result = co_purchase(product_key="1")
        assert result["status"] == "ok"
        assert result["product"]["label"] == "Product"
        assert result["product"]["key"] == "1"
        assert result["product"]["name"] == "Chai"

    def test_recommendations_structure(self):
        """Verify each recommendation has label, key, name, co_bought."""
        result = co_purchase(product_key="1")
        assert result["status"] == "ok"
        for rec in result["recommendations"]:
            assert "label" in rec
            assert "key" in rec
            assert "name" in rec
            assert "co_bought" in rec

    def test_co_bought_types(self):
        """co_bought values are integers (counts)."""
        result = co_purchase(product_key="1")
        assert result["status"] == "ok"
        for rec in result["recommendations"]:
            assert isinstance(rec["co_bought"], int)

    def test_limited_to_10(self):
        """Results capped at 10 recommendations."""
        result = co_purchase(product_key="1")
        assert result["status"] == "ok"
        assert len(result["recommendations"]) <= 10

    def test_anchor_excluded(self):
        """Anchor product (Chai) is excluded from recommendations."""
        result = co_purchase(product_key="1")
        assert result["status"] == "ok"
        for rec in result["recommendations"]:
            assert rec["key"] != "1"  # Chai's productID

    def test_deterministic_order(self):
        """Ties broken by ascending productID (21 < 40 < 60 < 71 for co_bought=4)."""
        result = co_purchase(product_key="1")
        assert result["status"] == "ok"
        recs = result["recommendations"]
        # First 4 have co_bought=4, ordered by key ascending
        top4_keys = [r["key"] for r in recs[:4]]
        assert top4_keys == ["21", "40", "60", "71"]

    def test_empty_result(self):
        """Non-existent product returns empty."""
        result = co_purchase(product_key="NonExistent")
        assert result["status"] == "empty"
        assert result["recommendations"] == []

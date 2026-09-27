"""
Unit tests for customer_history tool (Phase 1, Item 1.4).

Contract: Ground truth dicts from GROUND_TRUTH_PHASE_1.md are assertions.
All tests hit live AuraDB - no mocking.
"""

import json
from src.neo4j.tools import customer_history


# =============================================================================
# Ground Truth Data (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================

GT_1_4_1 = {
    "status": "ok",
    "customer": {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "country": "Germany"},
    "orders": [
        {"order_key": "10643", "order_date": "1997-08-25 00:00:00.000", "total": 1086.0, "ship_country": "Germany"},
        {"order_key": "10692", "order_date": "1997-10-03 00:00:00.000", "total": 878.0, "ship_country": "Germany"},
        {"order_key": "10702", "order_date": "1997-10-13 00:00:00.000", "total": 330.0, "ship_country": "Germany"},
        {"order_key": "10835", "order_date": "1998-01-15 00:00:00.000", "total": 851.0, "ship_country": "Germany"},
        {"order_key": "10952", "order_date": "1998-03-16 00:00:00.000", "total": 491.2, "ship_country": "Germany"},
        {"order_key": "11011", "order_date": "1998-04-09 00:00:00.000", "total": 960.0, "ship_country": "Germany"}
    ]
}


# =============================================================================
# Contract Notes (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================
# 1. orderDate format: "1997-08-25 00:00:00.000" (milliseconds included) - raw Aura string
# 2. Sort by order_date ascending (orderID monotone with orderDate for ALFKI)
# 3. Per-order totals use revenue rule: coalesce(line.unitPrice, p.unitPrice) * line.quantity
# 4. All orders ship to Germany


class TestCustomerHistory:
    """Test customer_history tool against live AuraDB."""

    def test_1_4_1_alfki(self):
        """GT 1.4.1: Customer history for ALFKI."""
        result = customer_history(customer_key="ALFKI")
        assert result == GT_1_4_1, f"Expected:\n{json.dumps(GT_1_4_1, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_customer_structure(self):
        """Verify customer has label, key, name, country."""
        result = customer_history(customer_key="ALFKI")
        assert result["status"] == "ok"
        assert result["customer"]["label"] == "Customer"
        assert result["customer"]["key"] == "ALFKI"
        assert result["customer"]["name"] == "Alfreds Futterkiste"
        assert result["customer"]["country"] == "Germany"

    def test_order_structure(self):
        """Verify each order has order_key, order_date, total, ship_country."""
        result = customer_history(customer_key="ALFKI")
        assert result["status"] == "ok"
        for order in result["orders"]:
            assert "order_key" in order
            assert "order_date" in order
            assert "total" in order
            assert "ship_country" in order

    def test_order_date_format(self):
        """order_date format is '1997-08-25 00:00:00.000' (with milliseconds)."""
        result = customer_history(customer_key="ALFKI")
        assert result["status"] == "ok"
        for order in result["orders"]:
            assert order["order_date"].endswith("00:00:00.000")
            assert len(order["order_date"]) == 23  # "1997-08-25 00:00:00.000"

    def test_total_types(self):
        """total values are floats (revenue)."""
        result = customer_history(customer_key="ALFKI")
        assert result["status"] == "ok"
        for order in result["orders"]:
            assert isinstance(order["total"], float)

    def test_sorted_ascending(self):
        """Orders sorted by order_date ascending."""
        result = customer_history(customer_key="ALFKI")
        assert result["status"] == "ok"
        dates = [o["order_date"] for o in result["orders"]]
        assert dates == sorted(dates)

    def test_order_count(self):
        """ALFKI has exactly 6 orders."""
        result = customer_history(customer_key="ALFKI")
        assert result["status"] == "ok"
        assert len(result["orders"]) == 6

    def test_all_germany(self):
        """All ALFKI orders ship to Germany."""
        result = customer_history(customer_key="ALFKI")
        assert result["status"] == "ok"
        for order in result["orders"]:
            assert order["ship_country"] == "Germany"

    def test_empty_result(self):
        """Non-existent customer returns empty."""
        result = customer_history(customer_key="NonExistent")
        assert result["status"] == "empty"
        assert result["orders"] == []

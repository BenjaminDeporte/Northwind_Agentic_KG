"""
Unit tests for aggregate tool (Phase 1, Item 1.5).

Contract: Ground truth dicts from GROUND_TRUTH_PHASE_1.md are assertions.
All tests hit live AuraDB - no mocking.
"""

import json
from src.neo4j.tools import aggregate


# =============================================================================
# Ground Truth Data (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================

GT_1_5_1 = {
    "status": "ok",
    "groups": [
        {"group_value": "Germany", "metric_value": 211540.09},
        {"group_value": "75004", "metric_value": 163135.0},
        {"group_value": "USA", "metric_value": 128844.15},
        {"group_value": "74000", "metric_value": 126582.0},
        {"group_value": "3058", "metric_value": 115386.05},
        {"group_value": "Canada", "metric_value": 90899.7},
        {"group_value": "2042", "metric_value": 69636.6},
        {"group_value": "84100", "metric_value": 52929.0},
        {"group_value": "48100", "metric_value": 51082.5},
        {"group_value": "Japan", "metric_value": 49211.5},
        {"group_value": "M14 GSD", "metric_value": 48793.8},
        {"group_value": "Norway", "metric_value": 46897.2},
        {"group_value": "0512", "metric_value": 44935.8},
        {"group_value": "UK", "metric_value": 35916.8},
        {"group_value": "Sweden", "metric_value": 33862.4},
        {"group_value": "Finland", "metric_value": 29804.0},
        {"group_value": "Spain", "metric_value": 26768.8},
        {"group_value": "Denmark", "metric_value": 10884.5},
        {"group_value": "71300", "metric_value": 6664.75},
        {"group_value": "Netherlands", "metric_value": 5901.35}
    ],
    "n_groups": 20
}

GT_1_5_2 = {
    "status": "ok",
    "groups": [
        {"group_value": "1", "metric_value": 12},
        {"group_value": "2", "metric_value": 12},
        {"group_value": "3", "metric_value": 13},
        {"group_value": "4", "metric_value": 10},
        {"group_value": "5", "metric_value": 7},
        {"group_value": "6", "metric_value": 6},
        {"group_value": "7", "metric_value": 5},
        {"group_value": "8", "metric_value": 12}
    ],
    "n_groups": 8
}

GT_1_5_3 = {
    "status": "invalid",
    "groups": [],
    "n_groups": 0
}

GT_1_5_4 = {
    "status": "ok",
    "groups": [
        {"group_value": "UK", "metric_value": 35916.8}
    ],
    "n_groups": 1
}


# =============================================================================
# Contract Notes (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================
# 1. Type pinning: counts=integers, revenues=floats rounded to 2 decimals
# 2. group_values are always raw strings (e.g., "1", not 1; "75000", not 75000)
# 3. 1.5.2 ordering is by group_value ascending
# 4. Supplier group_by whitelist: {country, city, supplierID, companyName, contactName, 
#    contactTitle, address, region, postalCode, phone, fax, homePage}
# 5. 1.5.1 ordered by metric_value descending
# 6. Mutual consistency: UK total = GT 1.2.1's Exotic Liquids figure (35916.8)


def _facts(result):
    """Compare numeric ground truth while separately checking provenance."""
    return {
        "status": result["status"],
        "groups": [{"group_value": g["group_value"], "metric_value": g["metric_value"]} for g in result["groups"]],
        "n_groups": result["n_groups"],
    }


class TestAggregate:
    """Test aggregate tool against live AuraDB."""

    def test_1_5_1_revenue_by_supplier_country(self):
        """GT 1.5.1: Revenue by supplier country."""
        result = aggregate(
            label="Supplier",
            group_by="country",
            metric="sum_revenue"
        )
        assert _facts(result) == GT_1_5_1, f"Expected:\n{json.dumps(GT_1_5_1, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"
        for group in result["groups"]:
            handles = {(item["label"], item["key"]) for item in group["evidence"]}
            assert handles and len(handles) == len(group["evidence"])
            assert all(item["label"] == "Supplier" and item["name"] for item in group["evidence"])
        assert ("Supplier", "1") in {(item["label"], item["key"]) for group in result["groups"] for item in group["evidence"]}

    def test_1_5_2_product_count_by_category(self):
        """GT 1.5.2: Product count by categoryID."""
        result = aggregate(
            label="Product",
            group_by="categoryID",
            metric="count"
        )
        assert _facts(result) == GT_1_5_2, f"Expected:\n{json.dumps(GT_1_5_2, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_1_5_3_invalid_group_by(self):
        """GT 1.5.3: Invalid group_by property."""
        result = aggregate(
            label="Supplier",
            group_by="invalid_property",
            metric="sum_revenue"
        )
        assert result == GT_1_5_3, f"Expected:\n{json.dumps(GT_1_5_3, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_1_5_4_filtered_uk(self):
        """GT 1.5.4: Revenue by supplier country, filtered to UK."""
        result = aggregate(
            label="Supplier",
            group_by="country",
            metric="sum_revenue",
            where="country='UK'"
        )
        assert _facts(result) == GT_1_5_4, f"Expected:\n{json.dumps(GT_1_5_4, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_group_value_types(self):
        """group_value fields are always strings."""
        result = aggregate(
            label="Supplier",
            group_by="country",
            metric="sum_revenue"
        )
        assert result["status"] == "ok"
        for group in result["groups"]:
            assert isinstance(group["group_value"], str)

    def test_metric_value_types_revenue(self):
        """sum_revenue metric values are floats rounded to 2 decimals."""
        result = aggregate(
            label="Supplier",
            group_by="country",
            metric="sum_revenue"
        )
        assert result["status"] == "ok"
        for group in result["groups"]:
            assert isinstance(group["metric_value"], float)
            # Check rounding to 2 decimals
            assert group["metric_value"] == round(group["metric_value"], 2)

    def test_metric_value_types_count(self):
        """count metric values are integers."""
        result = aggregate(
            label="Product",
            group_by="categoryID",
            metric="count"
        )
        assert result["status"] == "ok"
        for group in result["groups"]:
            assert isinstance(group["metric_value"], int)

    def test_ordering_1_5_1_descending(self):
        """1.5.1: groups ordered by metric_value descending."""
        result = aggregate(
            label="Supplier",
            group_by="country",
            metric="sum_revenue"
        )
        assert result["status"] == "ok"
        metric_values = [g["metric_value"] for g in result["groups"]]
        assert metric_values == sorted(metric_values, reverse=True)

    def test_ordering_1_5_2_ascending(self):
        """1.5.2: groups ordered by group_value ascending."""
        result = aggregate(
            label="Product",
            group_by="categoryID",
            metric="count"
        )
        assert result["status"] == "ok"
        group_values = [g["group_value"] for g in result["groups"]]
        assert group_values == sorted(group_values)

    def test_n_groups_count(self):
        """n_groups reflects actual number of groups."""
        result = aggregate(
            label="Supplier",
            group_by="country",
            metric="sum_revenue"
        )
        assert result["status"] == "ok"
        assert result["n_groups"] == len(result["groups"])

    def test_mutual_consistency_uk_revenue(self):
        """UK revenue (35916.8) matches impact_analysis Exotic Liquids figure."""
        result = aggregate(
            label="Supplier",
            group_by="country",
            metric="sum_revenue",
            where="country='UK'"
        )
        assert result["status"] == "ok"
        uk_revenue = result["groups"][0]["metric_value"]
        assert uk_revenue == 35916.8

    def test_invalid_metric(self):
        """Invalid metric returns status 'invalid'."""
        result = aggregate(
            label="Supplier",
            group_by="country",
            metric="invalid_metric"
        )
        assert result["status"] == "invalid"

    def test_invalid_label(self):
        """Invalid label returns status 'invalid'."""
        result = aggregate(
            label="InvalidLabel",
            group_by="country",
            metric="sum_revenue"
        )
        assert result["status"] == "invalid"


def test_all_schema_labels_have_fixed_count_and_revenue_paths():
    cases = [
        ("Supplier", "country"), ("Product", "categoryID"),
        ("Customer", "country"), ("Employee", "employeeID"),
        ("Category", "categoryName"), ("Shipper", "companyName"),
        ("Order", "shipCountry"), ("Territory", "territoryDescription"),
        ("Region", "regionDescription"),
    ]
    for label, group_by in cases:
        for metric in ("count", "sum_revenue"):
            result = aggregate(label, group_by, metric)
            assert result["status"] == "ok", (label, metric, result)
            assert 0 < result["n_groups"] <= 20
            assert all(group["evidence"] for group in result["groups"])
            assert all(node["label"] == label for group in result["groups"] for node in group["evidence"])

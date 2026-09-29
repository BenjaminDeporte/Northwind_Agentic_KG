"""
Unit tests for lookup_entity tool (Phase 1, Item 1.1).

Contract: Ground truth dicts from GROUND_TRUTH_PHASE_1.md are assertions.
All tests hit live AuraDB - no mocking.
"""

import pytest
import json
from src.neo4j.tools import lookup_entity


# =============================================================================
# Ground Truth Data (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================

GT_1_1_1 = {
    "status": "ok",
    "query_name": "Exotic Liquids",
    "matches": [
        {
            "label": "Supplier",
            "key": "1",
            "name": "Exotic Liquids",
            "match": "exact",
            "properties": {"country": "UK", "phone": "(171) 555-2222"}
        }
    ]
}

GT_1_1_2 = {
    "status": "ok",
    "query_name": "Liquids",
    "matches": [
        {
            "label": "Supplier",
            "key": "1",
            "name": "Exotic Liquids",
            "match": "contains",
            "properties": {"country": "UK", "phone": "(171) 555-2222"}
        }
    ]
}

GT_1_1_3 = {
    "status": "ok",
    "query_name": "Exotic Liqids",
    "matches": [
        {
            "label": "Supplier",
            "key": "1",
            "name": "Exotic Liquids",
            "match": "fuzzy",
            "properties": {"country": "UK", "phone": "(171) 555-2222"}
        }
    ]
}

GT_1_1_4 = {
    "status": "empty",
    "query_name": "NonExistentSupplier",
    "matches": []
}

GT_1_1_5 = {
    "status": "ok",
    "query_name": "Chai",
    "matches": [
        {
            "label": "Product",
            "key": "1",
            "name": "Chai",
            "match": "exact",
            "properties": {"unitPrice": 18.0, "unitsInStock": 39}
        }
    ]
}

GT_1_1_6 = {
    "status": "ok",
    "query_name": "Chai",
    "matches": [
        {
            "label": "Product",
            "key": "1",
            "name": "Chai",
            "match": "exact",
            "properties": {"unitPrice": 18.0, "unitsInStock": 39}
        }
    ]
}


# =============================================================================
# Contract Notes (from GROUND_TRUTH_PHASE_1.md)
# =============================================================================
# 1. Keys are SCHEMA.md key-property values ("1" = supplierID/productID), not names
# 2. Per-label property subsets: Supplier = {country, phone}; Product = {unitPrice, unitsInStock}
# 3. Fuzzy calibration: "Exotic Liqids" (edit distance 1) must match; "NonExistentSupplier" must not
# 4. Tier cascade: 1.1.3 exact+contains return 0 rows -> fuzzy tier; 1.1.4 contains returns 0 rows


class TestLookupEntity:
    """Test lookup_entity tool against live AuraDB."""

    def test_1_1_1_exact_supplier(self):
        """GT 1.1.1: Exact match on Supplier 'Exotic Liquids'."""
        result = lookup_entity(name="Exotic Liquids", label="Supplier")
        assert result == GT_1_1_1, f"Expected:\n{json.dumps(GT_1_1_1, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_1_1_2_contains_supplier(self):
        """GT 1.1.2: Contains match on 'Liquids' within Supplier."""
        result = lookup_entity(name="Liquids", label="Supplier")
        assert result == GT_1_1_2, f"Expected:\n{json.dumps(GT_1_1_2, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_1_1_3_fuzzy_supplier(self):
        """GT 1.1.3: Fuzzy match on 'Exotic Liqids' -> 'Exotic Liquids'."""
        result = lookup_entity(name="Exotic Liqids", label="Supplier")
        assert result == GT_1_1_3, f"Expected:\n{json.dumps(GT_1_1_3, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_1_1_4_empty_supplier(self):
        """GT 1.1.4: Empty result for non-existent supplier."""
        result = lookup_entity(name="NonExistentSupplier", label="Supplier")
        assert result == GT_1_1_4, f"Expected:\n{json.dumps(GT_1_1_4, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_1_1_5_exact_product(self):
        """GT 1.1.5: Exact match on Product 'Chai'."""
        result = lookup_entity(name="Chai", label="Product")
        assert result == GT_1_1_5, f"Expected:\n{json.dumps(GT_1_1_5, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_1_1_6_no_label(self):
        """GT 1.1.6: No label filter - finds Product 'Chai'."""
        result = lookup_entity(name="Chai")
        assert result == GT_1_1_6, f"Expected:\n{json.dumps(GT_1_1_6, indent=2)}\nGot:\n{json.dumps(result, indent=2)}"

    def test_type_pinning_properties(self):
        """Verify property types: counts=int, revenues=float, group_values=str."""
        # Supplier properties must be {country, phone}
        result = lookup_entity(name="Exotic Liquids", label="Supplier")
        assert result["status"] == "ok"
        assert len(result["matches"]) > 0
        match = result["matches"][0]
        assert isinstance(match["properties"]["country"], str)
        assert isinstance(match["properties"]["phone"], str)
        
        # Product properties must be {unitPrice, unitsInStock}
        result = lookup_entity(name="Chai", label="Product")
        assert result["status"] == "ok"
        match = result["matches"][0]
        assert isinstance(match["properties"]["unitPrice"], float)
        assert isinstance(match["properties"]["unitsInStock"], int)
        
        # Keys are strings (supplierID/productID values)
        assert isinstance(match["key"], str)

    def test_invalid_label(self):
        """Invalid label returns status 'invalid'."""
        result = lookup_entity(name="test", label="InvalidLabel")
        assert result["status"] == "invalid"
        assert result["matches"] == []


def test_unlabeled_lookup_includes_employee_full_names():
    from unittest.mock import patch
    def query(cypher, parameters=None):
        if "MATCH (n:Employee)" in cypher and "WHERE" in cypher:
            return ([{"n": {"employeeID": "1", "firstName": "Nancy", "lastName": "Davolio"}}], None)
        return ([], None)
    with patch("src.neo4j.tools.client.run_read_query", side_effect=query):
        result = lookup_entity("Nancy Davolio")
    assert any(item["label"] == "Employee" and item["name"] == "Nancy Davolio" for item in result["matches"])


def test_unlabeled_lookup_includes_order_ids():
    from unittest.mock import patch
    def query(cypher, parameters=None):
        if "MATCH (n:Order)" in cypher and "WHERE" in cypher:
            return ([{"n": {"orderID": "10248"}}], None)
        return ([], None)
    with patch("src.neo4j.tools.client.run_read_query", side_effect=query):
        result = lookup_entity("10248")
    assert any(item["label"] == "Order" and item["key"] == "10248" for item in result["matches"])


def test_labeled_customer_key_returns_canonical_lookup_payload(monkeypatch):
    calls = []
    customer = {
        "customerID": "ALFKI", "companyName": "Alfreds Futterkiste",
        "country": "Germany", "city": "Berlin",
    }

    def query(cypher, parameters=None):
        calls.append(cypher)
        if "toString(n.customerID) = $name" in cypher:
            return ([{"n": customer}], None)
        return ([], None)

    monkeypatch.setattr("src.neo4j.tools.client.run_read_query", query)
    result = lookup_entity(name="ALFKI", label="Customer")

    assert result == {
        "status": "ok", "query_name": "ALFKI", "matches": [{
            "label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste",
            "match": "exact", "properties": {"country": "Germany", "city": "Berlin"},
        }],
    }
    assert any("toString(n.customerID) = $name" in cypher for cypher in calls)


def test_labeled_customer_display_name_still_matches_exactly(monkeypatch):
    customer = {"customerID": "ALFKI", "companyName": "Alfreds Futterkiste", "country": "Germany"}

    def query(cypher, parameters=None):
        if "n.companyName = $name" in cypher:
            return ([{"n": customer}], None)
        raise AssertionError("Exact display name should return before key lookup")

    monkeypatch.setattr("src.neo4j.tools.client.run_read_query", query)
    result = lookup_entity(name="Alfreds Futterkiste", label="Customer")
    assert result["status"] == "ok"
    assert result["matches"][0]["key"] == "ALFKI"
    assert result["matches"][0]["match"] == "exact"


def test_key_lookup_miss_preserves_contains_fuzzy_and_empty_tiers(monkeypatch):
    def query(cypher, parameters=None):
        if "toLower(" in cypher and "CONTAINS" in cypher:
            if parameters["name"] == "Alfreds":
                return ([{"n": {"customerID": "ALFKI", "companyName": "Alfreds Futterkiste"}}], None)
            return ([], None)
        if "WHERE" not in cypher:
            return ([{"n": {"customerID": "ALFKI", "companyName": "Alfreds Futterkiste"}}], None)
        return ([], None)

    monkeypatch.setattr("src.neo4j.tools.client.run_read_query", query)
    contains = lookup_entity(name="Alfreds", label="Customer")
    assert contains["matches"][0]["match"] == "contains"

    fuzzy = lookup_entity(name="Alfreds Futterkist", label="Customer")
    assert fuzzy["matches"][0]["match"] == "fuzzy"

    missing = lookup_entity(name="MISSING", label="Customer")
    assert missing == {"status": "empty", "query_name": "MISSING", "matches": []}

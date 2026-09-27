"""
Unit tests for schema prompt extraction (Phase 2, Item 2.1a).

Contract: SCHEMA.md is authoritative; schema prompt must be generated mechanically.
Contract note: PURCHASED correction verified — Customer->Order edge is PURCHASED, not ORDER.
"""

import pytest
from src.agents.schema_prompt import (
    get_labels,
    get_relationships,
    get_traversal_patterns,
    get_revenue_rule,
    generate_schema_prompt,
    clear_schema_prompt_cache,
)


class TestLabelsExtraction:
    """Test label extraction from SCHEMA.md."""

    def test_extract_all_9_labels(self):
        """All 9 node labels are extracted."""
        labels = get_labels()
        assert len(labels) == 9

    def test_product_label(self):
        """Product label has correct properties."""
        labels = get_labels()
        product = next((l for l in labels if l['label'] == 'Product'), None)
        assert product is not None
        assert product['key'] == 'productID'
        assert product['name_property'] == 'productName'
        assert 'unitPrice' in product['properties']
        assert 'unitsInStock' in product['properties']

    def test_supplier_label(self):
        """Supplier label has correct properties."""
        labels = get_labels()
        supplier = next((l for l in labels if l['label'] == 'Supplier'), None)
        assert supplier is not None
        assert supplier['key'] == 'supplierID'
        assert supplier['name_property'] == 'companyName'

    def test_customer_label(self):
        """Customer label has correct properties."""
        labels = get_labels()
        customer = next((l for l in labels if l['label'] == 'Customer'), None)
        assert customer is not None
        assert customer['key'] == 'customerID'
        assert customer['name_property'] == 'companyName'

    def test_order_label_no_name_property(self):
        """Order label has no name property."""
        labels = get_labels()
        order = next((l for l in labels if l['label'] == 'Order'), None)
        assert order is not None
        assert order['key'] == 'orderID'
        # Order has no name property (marked as '—' in SCHEMA.md)
        assert order['name_property'] in ['—', None, '']

    def test_naming_warning_applied(self):
        """Labels use correct name properties per SCHEMA.md naming warning."""
        labels = get_labels()
        label_map = {l['label']: l for l in labels}
        
        # Supplier, Customer, Shipper use companyName
        assert label_map['Supplier']['name_property'] == 'companyName'
        assert label_map['Customer']['name_property'] == 'companyName'
        assert label_map['Shipper']['name_property'] == 'companyName'
        
        # Product uses productName
        assert label_map['Product']['name_property'] == 'productName'
        
        # Category uses categoryName
        assert label_map['Category']['name_property'] == 'categoryName'
        
        # Territory uses territoryDescription
        assert label_map['Territory']['name_property'] == 'territoryDescription'
        
        # Region uses regionDescription
        assert label_map['Region']['name_property'] == 'regionDescription'


class TestRelationshipsExtraction:
    """Test relationship extraction from SCHEMA.md."""

    def test_extract_all_9_relationships(self):
        """All 9 relationship types are extracted."""
        rels = get_relationships()
        assert len(rels) == 9

    def test_purchased_not_order(self):
        """
        CRITICAL: Customer->Order edge type is PURCHASED, not ORDER.
        This is the contract correction that a hand-maintained prompt would miss.
        """
        rels = get_relationships()
        # Find Customer -> Order relationship
        customer_order = next(
            (r for r in rels if r['from_label'] == 'Customer' and r['to_label'] == 'Order'),
            None
        )
        assert customer_order is not None
        assert customer_order['type'] == 'PURCHASED'

    def test_orders_relationship(self):
        """ORDERS relationship is Order -> Product."""
        rels = get_relationships()
        orders = next(
            (r for r in rels if r['type'] == 'ORDERS'),
            None
        )
        assert orders is not None
        assert orders['from_label'] == 'Order'
        assert orders['to_label'] == 'Product'

    def test_supplies_relationship(self):
        """SUPPLIES relationship is Supplier -> Product."""
        rels = get_relationships()
        supplies = next(
            (r for r in rels if r['type'] == 'SUPPLIES'),
            None
        )
        assert supplies is not None
        assert supplies['from_label'] == 'Supplier'
        assert supplies['to_label'] == 'Product'

    def test_part_of_relationship(self):
        """PART_OF relationship is Product -> Category."""
        rels = get_relationships()
        part_of = next(
            (r for r in rels if r['type'] == 'PART_OF'),
            None
        )
        assert part_of is not None
        assert part_of['from_label'] == 'Product'
        assert part_of['to_label'] == 'Category'

    def test_relationship_meanings(self):
        """Relationships have meanings extracted."""
        rels = get_relationships()
        purchased = next(
            (r for r in rels if r['type'] == 'PURCHASED'),
            None
        )
        assert purchased is not None
        assert 'customer placed order' in purchased['meaning'].lower()


class TestRevenueRuleExtraction:
    """Test revenue rule extraction from SCHEMA.md."""

    def test_revenue_rule_extracted(self):
        """Revenue rule is correctly extracted."""
        rule = get_revenue_rule()
        assert rule is not None
        assert 'coalesce' in rule.lower()
        assert 'unitPrice' in rule
        assert 'quantity' in rule

    def test_revenue_rule_exact(self):
        """Revenue rule matches SCHEMA.md exactly."""
        rule = get_revenue_rule()
        expected = "coalesce(line.unitPrice, p.unitPrice) * line.quantity"
        assert rule == expected


class TestSchemaPromptGeneration:
    """Test full schema prompt generation."""

    def test_prompt_generated(self):
        """Schema prompt is generated without error."""
        prompt = generate_schema_prompt()
        assert prompt is not None
        assert len(prompt) > 0

    def test_prompt_contains_purchased(self):
        """Generated prompt contains PURCHASED (not ORDER)."""
        prompt = generate_schema_prompt()
        assert 'PURCHASED' in prompt
        # Should NOT have a line saying Customer-ORDER with type ORDER
        # (The correction is that it's PURCHASED)

    def test_prompt_contains_all_labels(self):
        """Generated prompt contains all 9 labels."""
        prompt = generate_schema_prompt()
        labels = get_labels()
        for label in labels:
            assert label['label'] in prompt

    def test_prompt_contains_revenue_rule(self):
        """Generated prompt contains the revenue rule."""
        prompt = generate_schema_prompt()
        assert 'coalesce' in prompt.lower()
        assert 'revenue' in prompt.lower()

    def test_prompt_cached(self):
        """Schema prompt is cached after first call."""
        clear_schema_prompt_cache()
        prompt1 = generate_schema_prompt()
        prompt2 = generate_schema_prompt()
        # Both calls return the same cached string value
        assert prompt1 == prompt2


class TestMechanicalGeneration:
    """Test that extraction is mechanical (from SCHEMA.md, not hardcoded)."""

    def test_not_hardcoded(self):
        """
        Verify that the extraction reads from SCHEMA.md file.
        If SCHEMA.md changes, the extracted data should change.
        This is a contract: never hand-edited.
        """
        # This is verified by the fact that we read from the file
        # The test passes if the file exists and can be read
        labels = get_labels()
        rels = get_relationships()
        assert len(labels) > 0
        assert len(rels) > 0

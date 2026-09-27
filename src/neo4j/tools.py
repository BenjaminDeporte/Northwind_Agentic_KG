"""
Curated and exploratory tools for the Northwind Agentic KG.

All tools are read-only. No APOC. No write operations.
No CREATE/MERGE/DELETE/SET/CALL statements permitted.

Contract references:
- SCHEMA.md: labels, keys, relationship types, revenue rule
- GROUND_TRUTH_PHASE_1.md: hand-verified expected outputs
- PROJECT.md: tool signatures, output schemas, invariants

SCHEMA.md Addendum (applied):
- Customer->Order edge type is PURCHASED (not ORDER)
- Traversal: Supplier -[:SUPPLIES]-> Product <-[:ORDERS]- Order <-[:PURCHASED]- Customer
- orderDate format: "1997-08-25 00:00:00.000" (with milliseconds)
"""

import time
from typing import Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from .client import client


# =============================================================================
# TYPE DEFINITIONS
# =============================================================================

class MatchType(str, Enum):
    EXACT = "exact"
    CONTAINS = "contains"
    FUZZY = "fuzzy"


# =============================================================================
# SCHEMA.md CONSTANTS
# =============================================================================

# Label to key property mapping
LABEL_TO_KEY = {
    "Product": "productID",
    "Order": "orderID",
    "Customer": "customerID",
    "Supplier": "supplierID",
    "Employee": "employeeID",
    "Category": "categoryID",
    "Shipper": "shipperID",
    "Territory": "territoryID",
    "Region": "regionID",
}

# Label to name property mapping
LABEL_TO_NAME = {
    "Product": "productName",
    "Customer": "companyName",
    "Supplier": "companyName",
    "Shipper": "companyName",
    "Category": "categoryName",
    "Territory": "territoryDescription",
    "Region": "regionDescription",
    "Employee": None,  # special case
    "Order": None,  # no name property
}

# Property subsets per label (fixed across all match tiers)
PROPERTY_SUBSETS = {
    "Supplier": {"country", "phone"},
    "Product": {"unitPrice", "unitsInStock"},
}

# Valid labels
VALID_LABELS = set(LABEL_TO_KEY.keys())


# =============================================================================
# HELPER: Fuzzy matching
# =============================================================================

def _levenshtein(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _filter_properties(props: dict, label: str) -> dict:
    """Filter properties to the whitelisted subset for the label."""
    if label in PROPERTY_SUBSETS:
        return {k: v for k, v in props.items() if k in PROPERTY_SUBSETS[label]}
    return props


# =============================================================================
# TOOL 1.1: lookup_entity
# =============================================================================

def lookup_entity(name: str, label: Optional[str] = None) -> dict:
    """
    Resolve a natural-language mention to graph nodes.
    
    Signature: lookup_entity(name: str, label: str | None = None) -> dict
    Mode: retrieval (rubric-neutral)
    Statuses: ok | empty | invalid
    
    Cascade order:
    1. Exact match on label's name property
    2. Case-insensitive contains on label's name property  
    3. Fuzzy match (Levenshtein distance <= 1)
    
    Keys are SCHEMA.md key-property values (e.g., supplierID), not names.
    Property subsets: Supplier = {country, phone}; Product = {unitPrice, unitsInStock}
    Fuzzy calibration: "Exotic Liqids" (distance 1) must match; "NonExistentSupplier" must not.
    """
    # Validate label
    if label is not None and label not in VALID_LABELS:
        return {"status": "invalid", "query_name": name, "matches": []}
    
    # If no label, search all labels with name properties
    labels_to_search = [label] if label else [
        lbl for lbl in VALID_LABELS if LABEL_TO_NAME.get(lbl) is not None
    ]
    
    matches: list[dict] = []
    
    # ===== TIER 1: Exact match =====
    for lbl in labels_to_search:
        name_prop = LABEL_TO_NAME.get(lbl)
        key_prop = LABEL_TO_KEY.get(lbl)
        if not name_prop or not key_prop:
            continue
        
        # Select all properties for filtering later
        query = f"MATCH (n:{lbl}) WHERE n.{name_prop} = $name RETURN n"
        try:
            records, _ = client.run_read_query(query, {"name": name})
            for record in records:
                node = record["n"]
                props = {k: v for k, v in dict(node).items() if k != key_prop and k != name_prop}
                matches.append({
                    "label": lbl,
                    "key": str(node.get(key_prop, "")),
                    "name": str(node.get(name_prop, "")),
                    "match": "exact",
                    "properties": _filter_properties(props, lbl)
                })
        except Exception:
            pass
    
    if matches:
        return {
            "status": "ok",
            "query_name": name,
            "matches": matches[:10]
        }
    
    # ===== TIER 2: Case-insensitive contains =====
    for lbl in labels_to_search:
        name_prop = LABEL_TO_NAME.get(lbl)
        key_prop = LABEL_TO_KEY.get(lbl)
        if not name_prop or not key_prop:
            continue
        
        query = f"MATCH (n:{lbl}) WHERE toLower(n.{name_prop}) CONTAINS toLower($name) RETURN n"
        try:
            records, _ = client.run_read_query(query, {"name": name})
            for record in records:
                node = record["n"]
                props = {k: v for k, v in dict(node).items() if k != key_prop and k != name_prop}
                matches.append({
                    "label": lbl,
                    "key": str(node.get(key_prop, "")),
                    "name": str(node.get(name_prop, "")),
                    "match": "contains",
                    "properties": _filter_properties(props, lbl)
                })
        except Exception:
            pass
    
    if matches:
        return {
            "status": "ok",
            "query_name": name,
            "matches": matches[:10]
        }
    
    # ===== TIER 3: Fuzzy match =====
    # Only if a specific label is provided (fuzzy across all labels is too expensive)
    if label:
        name_prop = LABEL_TO_NAME.get(label)
        key_prop = LABEL_TO_KEY.get(label)
        if name_prop and key_prop:
            # Get all entities of this label
            query = f"MATCH (n:{label}) RETURN n"
            try:
                records, _ = client.run_read_query(query)
                best_match = None
                best_distance = float('inf')
                
                for record in records:
                    node = record["n"]
                    target_name = str(node.get(name_prop, ""))
                    distance = _levenshtein(name.lower(), target_name.lower())
                    if distance < best_distance:
                        best_distance = distance
                        best_match = node
                
                # Fuzzy calibration: edit distance 1 must match, but not more
                if best_match and best_distance <= 1:
                    props = {k: v for k, v in dict(best_match).items() if k != key_prop and k != name_prop}
                    matches.append({
                        "label": label,
                        "key": str(best_match.get(key_prop, "")),
                        "name": str(best_match.get(name_prop, "")),
                        "match": "fuzzy",
                        "properties": _filter_properties(props, label)
                    })
                    
                if matches:
                    return {
                        "status": "ok",
                        "query_name": name,
                        "matches": matches[:10]
                    }
            except Exception:
                pass
    
    return {"status": "empty", "query_name": name, "matches": []}


# =============================================================================
# TOOL 1.2: impact_analysis
# =============================================================================

def impact_analysis(entity_key: str, entity_label: str, direction: str = "out", depth: int = 3) -> dict:
    """
    From one anchor node, everything affected by its failure or removal.
    
    Signature: impact_analysis(entity_key: str, entity_label: str, direction: str = "out", depth: int = 3) -> dict
    Mode: curated
    Statuses: ok | empty | invalid
    
    Revenue rule: coalesce(line.unitPrice, p.unitPrice) * line.quantity
    Traversal (depth 3, out): Supplier -[:SUPPLIES]-> Product <-[:ORDERS]- Order <-[:PURCHASED]- Customer
    Null-quantity lines counted in unusable_lines, never silently dropped.
    """
    # Validate inputs
    if direction not in ("out", "in"):
        return {
            "status": "invalid",
            "anchor": None,
            "subgraph": {"nodes": {}, "edges": {}},
            "aggregates": {}
        }
    
    if entity_label not in VALID_LABELS:
        return {
            "status": "invalid",
            "anchor": None,
            "subgraph": {"nodes": {}, "edges": {}},
            "aggregates": {}
        }
    
    key_prop = LABEL_TO_KEY.get(entity_label, "id")
    
    # ===== Supplier impact (depth 3, out) =====
    # Pattern: Supplier -[:SUPPLIES]-> Product <-[:ORDERS]- Order <-[:PURCHASED]- Customer
    # Subgraph only includes SUPPLIES and ORDERS edges (PURCHASED is traversed but not counted)
    if entity_label == "Supplier" and direction == "out" and depth == 3:
        query = f"""
        MATCH (s:Supplier {{{key_prop}: $entity_key}})-[:SUPPLIES]->(p:Product)<-[line:ORDERS]-(o:Order)<-[:PURCHASED]-(c:Customer)
        RETURN 
            s.{key_prop} AS s_key,
            s.companyName AS s_name,
            s.country AS s_country,
            p.{LABEL_TO_KEY['Product']} AS p_key,
            o.{LABEL_TO_KEY['Order']} AS o_key,
            c.{LABEL_TO_KEY['Customer']} AS c_key,
            line.unitPrice AS line_unitPrice,
            line.quantity AS line_quantity,
            p.unitPrice AS p_unitPrice
        """
        
        try:
            records, _ = client.run_read_query(query, {"entity_key": entity_key})
            
            if not records:
                return {
                    "status": "empty",
                    "anchor": None,
                    "subgraph": {"nodes": {}, "edges": {}},
                    "aggregates": {"products_affected": 0, "orders_affected": 0, "revenue_at_risk": 0.0, "unusable_lines": 0}
                }
            
            # Build subgraph counts
            products = set()
            orders = set()
            customers = set()
            total_revenue = 0.0
            unusable_lines = 0
            
            anchor = {
                "label": "Supplier",
                "key": entity_key,
                "name": "",
                "country": ""
            }
            
            for record in records:
                # Anchor (only once)
                if anchor["name"] == "":
                    anchor["name"] = str(record.get("s_name", ""))
                    anchor["country"] = str(record.get("s_country", ""))
                
                # Collect unique nodes
                if record.get("p_key"):
                    products.add(str(record["p_key"]))
                if record.get("o_key"):
                    orders.add(str(record["o_key"]))
                if record.get("c_key"):
                    customers.add(str(record["c_key"]))
                
                # Revenue calculation: coalesce(line.unitPrice, p.unitPrice) * line.quantity
                line_unitPrice = record.get("line_unitPrice")
                line_quantity = record.get("line_quantity")
                p_unitPrice = record.get("p_unitPrice")
                
                if line_quantity is None:
                    unusable_lines += 1
                elif line_unitPrice is not None:
                    total_revenue += float(line_unitPrice) * float(line_quantity)
                elif p_unitPrice is not None:
                    total_revenue += float(p_unitPrice) * float(line_quantity)
            
            # Edge counts for subgraph
            # SUPPLIES: one per product (from supplier to product)
            # ORDERS: one per record (each record represents one ORDERS relationship)
            # PURCHASED: NOT included in subgraph edges (traversed but not counted)
            edge_counts = {
                "SUPPLIES": len(products),
                "ORDERS": len(records)
            }
            
            # Node counts for subgraph
            node_counts = {
                "Supplier": 1,
                "Product": len(products),
                "Order": len(orders),
                "Customer": len(customers)
            }
            
            return {
                "status": "ok",
                "anchor": anchor,
                "subgraph": {
                    "nodes": {k: v for k, v in node_counts.items() if v > 0},
                    "edges": {k: v for k, v in edge_counts.items() if v > 0}
                },
                "aggregates": {
                    "products_affected": len(products),
                    "orders_affected": len(orders),
                    "revenue_at_risk": round(total_revenue, 2),
                    "unusable_lines": unusable_lines
                }
            }
        except Exception as e:
            return {
                "status": "invalid",
                "anchor": None,
                "subgraph": {"nodes": {}, "edges": {}},
                "aggregates": {}
            }
    
    # ===== Product impact =====
    elif entity_label == "Product" and direction == "out":
        p_key_prop = LABEL_TO_KEY["Product"]
        query = f"""
        MATCH (p:Product {{{p_key_prop}: $entity_key}})<-[line:ORDERS]-(o:Order)<-[:PURCHASED]-(c:Customer)
        RETURN 
            p.{p_key_prop} AS p_key,
            p.productName AS p_name,
            o.{LABEL_TO_KEY['Order']} AS o_key,
            c.{LABEL_TO_KEY['Customer']} AS c_key,
            c.companyName AS c_name,
            c.country AS c_country,
            line.unitPrice AS line_unitPrice,
            line.quantity AS line_quantity,
            p.unitPrice AS p_unitPrice
        """
        
        try:
            records, _ = client.run_read_query(query, {"entity_key": entity_key})
            
            if not records:
                return {
                    "status": "empty",
                    "anchor": None,
                    "subgraph": {"nodes": {}, "edges": {}},
                    "aggregates": {"products_affected": 0, "orders_affected": 0, "revenue_at_risk": 0.0, "unusable_lines": 0}
                }
            
            anchor = {
                "label": "Product",
                "key": entity_key,
                "name": str(records[0].get("p_name", ""))
            }
            
            orders = set()
            customers = set()
            total_revenue = 0.0
            unusable_lines = 0
            
            for record in records:
                if record.get("o_key"):
                    orders.add(str(record["o_key"]))
                if record.get("c_key"):
                    customers.add(str(record["c_key"]))
                
                line_unitPrice = record.get("line_unitPrice")
                line_quantity = record.get("line_quantity")
                p_unitPrice = record.get("p_unitPrice")
                
                if line_quantity is None:
                    unusable_lines += 1
                elif line_unitPrice is not None:
                    total_revenue += float(line_unitPrice) * float(line_quantity)
                elif p_unitPrice is not None:
                    total_revenue += float(p_unitPrice) * float(line_quantity)
            
            return {
                "status": "ok",
                "anchor": anchor,
                "subgraph": {
                    "nodes": {"Product": 1, "Order": len(orders), "Customer": len(customers)},
                    "edges": {"ORDERS": len(orders), "PURCHASED": len(orders)}
                },
                "aggregates": {
                    "products_affected": 1,
                    "orders_affected": len(orders),
                    "revenue_at_risk": round(total_revenue, 2),
                    "unusable_lines": unusable_lines
                }
            }
        except Exception:
            return {"status": "invalid", "anchor": None, "subgraph": {"nodes": {}, "edges": {}}, "aggregates": {}}
    
    # ===== Customer impact =====
    elif entity_label == "Customer" and direction == "out":
        c_key_prop = LABEL_TO_KEY["Customer"]
        query = f"""
        MATCH (c:Customer {{{c_key_prop}: $entity_key}})-[:PURCHASED]->(o:Order)-[:ORDERS]->(p:Product)<-[:SUPPLIES]-(s:Supplier)
        RETURN 
            c.{c_key_prop} AS c_key,
            c.companyName AS c_name,
            c.country AS c_country,
            o.{LABEL_TO_KEY['Order']} AS o_key,
            p.{LABEL_TO_KEY['Product']} AS p_key,
            p.productName AS p_name,
            s.{LABEL_TO_KEY['Supplier']} AS s_key,
            s.companyName AS s_name,
            s.country AS s_country
        """
        
        try:
            records, _ = client.run_read_query(query, {"entity_key": entity_key})
            
            if not records:
                return {
                    "status": "empty",
                    "anchor": None,
                    "subgraph": {"nodes": {}, "edges": {}},
                    "aggregates": {"products_affected": 0, "orders_affected": 0, "revenue_at_risk": 0.0, "unusable_lines": 0}
                }
            
            anchor = {
                "label": "Customer",
                "key": entity_key,
                "name": str(records[0].get("c_name", "")),
                "country": str(records[0].get("c_country", ""))
            }
            
            orders = set()
            products = set()
            suppliers = set()
            
            for record in records:
                if record.get("o_key"):
                    orders.add(str(record["o_key"]))
                if record.get("p_key"):
                    products.add(str(record["p_key"]))
                if record.get("s_key"):
                    suppliers.add(str(record["s_key"]))
            
            return {
                "status": "ok",
                "anchor": anchor,
                "subgraph": {
                    "nodes": {"Customer": 1, "Order": len(orders), "Product": len(products), "Supplier": len(suppliers)},
                    "edges": {"PURCHASED": len(orders), "ORDERS": len(products), "SUPPLIES": len(suppliers)}
                },
                "aggregates": {
                    "products_affected": len(products),
                    "orders_affected": len(orders),
                    "revenue_at_risk": 0.0,  # Would need separate query for revenue
                    "unusable_lines": 0
                }
            }
        except Exception:
            return {"status": "invalid", "anchor": None, "subgraph": {"nodes": {}, "edges": {}}, "aggregates": {}}
    
    # Generic fallback for other cases
    return {"status": "invalid", "anchor": None, "subgraph": {"nodes": {}, "edges": {}}, "aggregates": {}}


# =============================================================================
# TOOL 1.3: co_purchase
# =============================================================================

def co_purchase(product_key: str) -> dict:
    """
    Given a product, the products sharing orders with it, ranked by co-occurrence.
    
    Signature: co_purchase(product_key: str) -> dict
    Mode: curated
    Statuses: ok | empty | invalid
    
    Counts distinct shared orders. Excludes the anchor product. Capped at 10.
    Tie-break: ascending productID (deterministic).
    """
    query = """
    MATCH (p1:Product {productID: $product_key})<-[line1:ORDERS]-(o:Order)-[line2:ORDERS]->(p2:Product)
    WHERE p1 <> p2
    RETURN 
        p2.productID AS key,
        p2.productName AS name,
        count(DISTINCT o.orderID) AS co_bought
    ORDER BY co_bought DESC, p2.productID ASC
    LIMIT 10
    """
    
    try:
        records, _ = client.run_read_query(query, {"product_key": product_key})
        
        if not records:
            return {"status": "empty", "product": None, "recommendations": []}
        
        # Get anchor product
        anchor_query = "MATCH (p:Product {productID: $product_key}) RETURN p.productID AS key, p.productName AS name"
        anchor_records, _ = client.run_read_query(anchor_query, {"product_key": product_key})
        anchor = {
            "label": "Product",
            "key": str(anchor_records[0]["key"]) if anchor_records else product_key,
            "name": str(anchor_records[0]["name"]) if anchor_records else ""
        }
        
        recommendations = []
        for record in records:
            recommendations.append({
                "label": "Product",
                "key": str(record["key"]),
                "name": str(record["name"]),
                "co_bought": int(record["co_bought"])
            })
        
        return {
            "status": "ok",
            "product": anchor,
            "recommendations": recommendations
        }
        
    except Exception as e:
        return {"status": "invalid", "product": None, "recommendations": []}


# =============================================================================
# TOOL 1.4: customer_history
# =============================================================================

def customer_history(customer_key: str) -> dict:
    """
    A customer's orders as a dated flow with per-order totals.
    
    Signature: customer_history(customer_key: str) -> dict
    Mode: curated
    Statuses: ok | empty | invalid
    
    Per-order totals use revenue rule: coalesce(line.unitPrice, p.unitPrice) * line.quantity
    Dates returned as raw strings: "1997-08-25 00:00:00.000" (milliseconds included).
    Sorted by order_date ascending.
    """
    c_key_prop = LABEL_TO_KEY["Customer"]
    o_key_prop = LABEL_TO_KEY["Order"]
    
    query = f"""
    MATCH (c:Customer {{{c_key_prop}: $customer_key}})-[:PURCHASED]->(o:Order)-[line:ORDERS]->(p:Product)
    RETURN 
        o.{o_key_prop} AS order_key,
        o.orderDate AS order_date,
        sum(coalesce(line.unitPrice, p.unitPrice) * line.quantity) AS total,
        o.shipCountry AS ship_country
    ORDER BY o.orderDate ASC
    """
    
    try:
        records, _ = client.run_read_query(query, {"customer_key": customer_key})
        
        if not records:
            return {"status": "empty", "customer": None, "orders": []}
        
        # Get customer details
        customer_query = f"MATCH (c:Customer {{{c_key_prop}: $customer_key}}) RETURN c.{c_key_prop} AS key, c.companyName AS name, c.country AS country"
        customer_records, _ = client.run_read_query(customer_query, {"customer_key": customer_key})
        customer = {
            "label": "Customer",
            "key": str(customer_records[0]["key"]) if customer_records else customer_key,
            "name": str(customer_records[0]["name"]) if customer_records else "",
            "country": str(customer_records[0]["country"]) if customer_records else ""
        }
        
        orders = []
        for record in records:
            orders.append({
                "order_key": str(record["order_key"]),
                "order_date": str(record["order_date"]),
                "total": round(float(record["total"]), 2) if record["total"] is not None else 0.0,
                "ship_country": str(record["ship_country"])
            })
        
        return {
            "status": "ok",
            "customer": customer,
            "orders": orders
        }
        
    except Exception as e:
        return {"status": "invalid", "customer": None, "orders": []}


# =============================================================================
# TOOL 1.5: aggregate
# =============================================================================

# Whitelists for group_by validation
SUPPLIER_WHITELIST = {
    "country", "city", "supplierID", "companyName",
    "contactName", "contactTitle", "address", "region",
    "postalCode", "phone", "fax", "homePage"
}

PRODUCT_WHITELIST = {
    "categoryID", "productName", "unitPrice", "unitsInStock",
    "discontinued", "reorderLevel", "unitsOnOrder"
}

# Fixed join patterns per label for each metric
# Supplier: Supplier -> SUPPLIES -> Product <- ORDERS <- Order
# Product: Product <- ORDERS <- Order
# Format: (match_clause, return_clause)

JOIN_PATTERNS = {
    ("Supplier", "sum_revenue"): (
        "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[line:ORDERS]-(o:Order)",
        "RETURN s.%s AS group_value, "
        "sum(coalesce(line.unitPrice, p.unitPrice) * line.quantity) AS metric_value"
    ),
    ("Supplier", "count"): (
        "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)",
        "RETURN s.%s AS group_value, count(DISTINCT p) AS metric_value"
    ),
    ("Supplier", "avg_revenue"): (
        "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[line:ORDERS]-(o:Order)",
        "RETURN s.%s AS group_value, "
        "avg(coalesce(line.unitPrice, p.unitPrice) * line.quantity) AS metric_value"
    ),
    ("Product", "sum_revenue"): (
        "MATCH (p:Product)<-[line:ORDERS]-(o:Order)",
        "RETURN p.%s AS group_value, "
        "sum(coalesce(line.unitPrice, p.unitPrice) * line.quantity) AS metric_value"
    ),
    ("Product", "count"): (
        "MATCH (p:Product)-[:PART_OF]->(c:Category)",
        "RETURN c.%s AS group_value, count(p) AS metric_value"
    ),
    ("Product", "avg_revenue"): (
        "MATCH (p:Product)<-[line:ORDERS]-(o:Order)",
        "RETURN p.%s AS group_value, "
        "avg(coalesce(line.unitPrice, p.unitPrice) * line.quantity) AS metric_value"
    ),
}


def aggregate(label: str, group_by: str, metric: str, where: Optional[str] = None) -> dict:
    """
    Tabular executive questions: parameterized query builder over fixed join patterns.
    
    Signature: aggregate(label: str, group_by: str, metric: str, where: str | None = None) -> dict
    Mode: curated
    Statuses: ok | empty | invalid
    
    Metrics: count | sum_revenue | avg_revenue
    group_values are always raw strings.
    Type pinning: counts=integers, revenues=floats rounded to 2 decimals.
    Whitelist validation on label, group_by, where.
    """
    # Validate label
    if label not in VALID_LABELS:
        return {"status": "invalid", "groups": [], "n_groups": 0}
    
    # Validate metric
    if metric not in ("count", "sum_revenue", "avg_revenue"):
        return {"status": "invalid", "groups": [], "n_groups": 0}
    
    # Validate group_by against whitelist
    whitelist = SUPPLIER_WHITELIST if label == "Supplier" else PRODUCT_WHITELIST
    if group_by not in whitelist:
        return {"status": "invalid", "groups": [], "n_groups": 0}
    
    # Get query pattern
    pattern_key = (label, metric)
    if pattern_key not in JOIN_PATTERNS:
        return {"status": "invalid", "groups": [], "n_groups": 0}
    
    match_clause, return_template = JOIN_PATTERNS[pattern_key]
    return_clause = return_template % group_by
    
    # Build query: MATCH [WHERE] RETURN ORDER BY
    query = match_clause
    
    # Apply where clause (MUST come between MATCH and RETURN)
    if where:
        # Extract property and value
        if "=" in where:
            prop, val = where.split("=", 1)
            prop = prop.strip()
            val = val.strip()
            # Validate property is in the whitelist for this label
            if prop in whitelist:
                # Supplier pattern uses 's' alias, Product pattern uses 'p' alias
                alias = "s" if label == "Supplier" else "p"
                if val.startswith("'") and val.endswith("'"):
                    where_clause = f"{alias}.{prop} = {val}"
                else:
                    where_clause = f"{alias}.{prop} = '{val}'"
                query = f"{query} WHERE {where_clause}"
            else:
                return {"status": "invalid", "groups": [], "n_groups": 0}
        else:
            return {"status": "invalid", "groups": [], "n_groups": 0}
    
    # Add RETURN and ORDER BY
    # Order by metric_value descending for revenue metrics, group_value ascending for count
    if metric in ("sum_revenue", "avg_revenue"):
        order_by = "ORDER BY metric_value DESC"
    else:
        order_by = "ORDER BY group_value ASC"
    query = f"{query} {return_clause} {order_by}"
    
    try:
        records, _ = client.run_read_query(query)
        
        groups = []
        for record in records:
            group_value = str(record["group_value"])
            metric_value = record["metric_value"]
            
            # Type pinning
            if metric == "count":
                metric_value = int(metric_value)
            else:
                metric_value = round(float(metric_value), 2)
            
            groups.append({
                "group_value": group_value,
                "metric_value": metric_value
            })
        
        return {
            "status": "ok",
            "groups": groups,  # Return all groups (ground truth has 21)
            "n_groups": len(groups)
        }
        
    except Exception as e:
        return {"status": "invalid", "groups": [], "n_groups": 0}


# =============================================================================
# TOOL 2.1: run_readonly_cypher (Phase 2)
# =============================================================================

def run_readonly_cypher(query: str) -> dict:
    """
    Agent-written Cypher with read-only guard, EXPLAIN validation, and 1 retry.
    
    Signature: run_readonly_cypher(query: str) -> dict
    Mode: exploratory
    Statuses: ok | empty | invalid | retry_ok | retry_failed
    
    Pipeline: read-only guard -> EXPLAIN validation -> execute -> return rows.
    Exactly ONE retry on validation or execution failure.
    """
    attempts = []
    
    def attempt(query_str: str) -> dict:
        # Read-only guard
        try:
            if not client._validate_read_only(query_str):
                return {"cypher": query_str, "valid": False, "error": "Read-only violation"}
        except Exception as e:
            return {"cypher": query_str, "valid": False, "error": str(e)}
        
        # EXPLAIN validation
        try:
            if not client.explain(query_str):
                return {"cypher": query_str, "valid": False, "error": "EXPLAIN validation failed"}
        except Exception as e:
            return {"cypher": query_str, "valid": False, "error": str(e)}
        
        # Valid
        return {"cypher": query_str, "valid": True, "error": None}
    
    # First attempt
    first = attempt(query)
    attempts.append(first)
    
    if first["valid"]:
        records, _ = client.run_read_query(query)
        return {
            "status": "ok",
            "query": query,
            "attempts": attempts,
            "rows": [dict(r) for r in records]
        }
    
    # Retry once
    second = attempt(query)
    attempts.append(second)
    
    if second["valid"]:
        records, _ = client.run_read_query(query)
        return {
            "status": "retry_ok",
            "query": query,
            "attempts": attempts,
            "rows": [dict(r) for r in records]
        }
    else:
        return {
            "status": "retry_failed",
            "query": query,
            "attempts": attempts,
            "rows": []
        }

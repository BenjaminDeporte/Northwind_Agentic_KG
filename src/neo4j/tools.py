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

import json
from enum import Enum
from typing import Any, Optional

from .client import client, Neo4jClient


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

def _lookup_name_expression(label: str) -> str:
    if label == "Employee":
        return "trim(coalesce(n.firstName, '') + ' ' + coalesce(n.lastName, ''))"
    if label == "Order":
        return "toString(n.orderID)"
    return f"n.{LABEL_TO_NAME[label]}"


def _lookup_match(node, node_label: str, tier: str) -> dict:
    props = {key: _json_safe(value) for key, value in dict(node).items()}
    key_prop = LABEL_TO_KEY[node_label]
    if node_label == "Employee":
        name = " ".join(filter(None, [props.get("firstName"), props.get("lastName")]))
    elif node_label == "Order":
        name = str(props.get("orderID", ""))
    else:
        name = str(props.get(LABEL_TO_NAME[node_label]) or props.get(key_prop, ""))
    remaining = {k: v for k, v in props.items() if k not in {key_prop, LABEL_TO_NAME.get(node_label)}}
    canonical = {
        "label": node_label,
        "key": str(props.get(key_prop, "")),
        "name": name,
        "properties": _filter_properties(remaining, node_label),
    }
    return {
        "node": canonical,
        "match": tier,
        "evidence": {"nodes": [canonical], "edges": []},
    }


def lookup_entity(name: str, label: Optional[str] = None) -> dict:
    """Resolve a label-scoped key or name, or search names across all labels."""
    matches_payload = {"query_name": name, "matches": []}
    if label is not None and (not isinstance(label, str) or label not in VALID_LABELS):
        return {"status": "invalid", "error": f"Unsupported label: {label}", **matches_payload}
    if not isinstance(name, str) or not name.strip():
        return {"status": "invalid", "error": "name must be a non-empty string", **matches_payload}
    labels = [label] if label else list(LABEL_TO_KEY)

    def run(query, parameters):
        return client.run_read_query(query, parameters)[0]

    found = []
    for node_label in labels:
        expression = _lookup_name_expression(node_label)
        try:
            rows = run(f"MATCH (n:{node_label}) WHERE {expression} = $name RETURN n", {"name": name})
        except Exception as exc:
            return {"status": "invalid", "error": f"Entity lookup failed: {exc}", **matches_payload}
        found.extend(_lookup_match(row["n"], node_label, "exact") for row in rows)
    if found:
        return {"status": "ok", "error": None, **{**matches_payload, "matches": found[:10]}}

    # A supplied label makes an exact canonical-key lookup unambiguous.
    if label is not None:
        key_property = LABEL_TO_KEY[label]
        try:
            rows = run(
                f"MATCH (n:{label}) WHERE toString(n.{key_property}) = $name RETURN n",
                {"name": name},
            )
        except Exception as exc:
            return {"status": "invalid", "error": f"Entity key lookup failed: {exc}", **matches_payload}
        if rows:
            matches = [_lookup_match(row["n"], label, "exact") for row in rows[:10]]
            return {"status": "ok", "error": None, **{**matches_payload, "matches": matches}}

    found = []
    for node_label in labels:
        expression = _lookup_name_expression(node_label)
        try:
            rows = run(
                f"MATCH (n:{node_label}) WHERE toLower({expression}) CONTAINS toLower($name) RETURN n",
                {"name": name},
            )
        except Exception as exc:
            return {"status": "invalid", "error": f"Entity name search failed: {exc}", **matches_payload}
        found.extend(_lookup_match(row["n"], node_label, "contains") for row in rows)
    if found:
        return {"status": "ok", "error": None, **{**matches_payload, "matches": found[:10]}}

    fuzzy = []
    for node_label in labels:
        try:
            rows = run(f"MATCH (n:{node_label}) RETURN n", {})
        except Exception as exc:
            return {"status": "invalid", "error": f"Entity fuzzy search failed: {exc}", **matches_payload}
        for row in rows:
            match = _lookup_match(row["n"], node_label, "fuzzy")
            distance = _levenshtein(name.lower(), match["node"]["name"].lower())
            if distance <= 1:
                fuzzy.append((distance, match))
    fuzzy.sort(key=lambda item: (item[0], item[1]["node"]["name"], item[1]["node"]["label"]))
    matches = [match for _, match in fuzzy[:10]]
    return {"status": "ok" if matches else "empty", "error": None, **{**matches_payload, "matches": matches}}


# =============================================================================
# TOOL 1.2: impact_analysis
# =============================================================================

def _node_payload(node, label: str) -> dict:
    props = {key: _json_safe(value) for key, value in dict(node).items()}
    key = str(props[LABEL_TO_KEY[label]])
    if label == "Employee":
        name = " ".join(filter(None, [props.get("firstName"), props.get("lastName")]))
    elif label == "Order":
        name = key
    else:
        name = str(props.get(LABEL_TO_NAME[label], key))
    selected = {
        "Supplier": {"country", "city", "phone"},
        "Product": {"unitPrice", "unitsInStock", "discontinued"},
        "Order": {"orderDate", "shipCountry"},
        "Customer": {"country", "city"},
    }.get(label)
    if selected is not None:
        props = {field: props[field] for field in selected if field in props}
    return {"label": label, "key": key, "name": name, "properties": props}


def _impact_result(status: str, anchor: dict | None, subgraph: dict, aggregates: dict, error: str | None = None) -> dict:
    """Build the common impact envelope with a bounded claim evidence sample."""
    all_nodes = subgraph.get("nodes", [])
    selected_nodes = []
    if anchor is not None:
        selected_nodes.append(anchor)
    for node in all_nodes:
        if node is not None and (anchor is None or (node["label"], node["key"]) != (anchor["label"], anchor["key"])):
            selected_nodes.append(node)
            if len(selected_nodes) == 3:
                break
    selected_ids = {(node["label"], node["key"]) for node in selected_nodes}
    selected_edges = [
        {**edge, "properties": edge.get("properties", {})}
        for edge in subgraph.get("edges", [])
        if (edge["from"]["label"], edge["from"]["key"]) in selected_ids
        and (edge["to"]["label"], edge["to"]["key"]) in selected_ids
    ][:2]
    return {
        "status": status,
        "error": error,
        "anchor": anchor,
        "subgraph": subgraph,
        "aggregates": aggregates,
        "evidence": {"nodes": selected_nodes, "edges": selected_edges},
    }


def impact_analysis(entity_key: str, entity_label: str, direction: str = "out", depth: int = 3) -> dict:
    """Return the actual evidence graph and revenue aggregates for an anchor."""
    blank = {"nodes": [], "edges": []}
    zero = {"products_affected": 0, "orders_affected": 0, "revenue_at_risk": 0.0, "unusable_lines": 0}
    if not isinstance(entity_label, str) or entity_label not in {"Supplier", "Product", "Customer"} or direction not in {"out", "in"} or type(depth) is not int or not 1 <= depth <= 3 or not isinstance(entity_key, str) or not entity_key.strip():
        return _impact_result("invalid", None, blank, zero, "Invalid label, direction, or depth")
    key_property = LABEL_TO_KEY[entity_label]
    anchor_query = f"MATCH (a:{entity_label} {{{key_property}: $key}}) RETURN a"
    try:
        anchors, _ = client.run_read_query(anchor_query, {"key": entity_key})
        if not anchors:
            return _impact_result("empty", None, blank, zero)
        anchor = _node_payload(anchors[0]["a"], entity_label)
        if direction == "in":
            if entity_label != "Product":
                return _impact_result("empty", anchor, {"nodes": [anchor], "edges": []}, zero)
            rows, _ = client.run_read_query("""
                MATCH (p:Product {productID: $key})
                OPTIONAL MATCH (s:Supplier)-[:SUPPLIES]->(p)
                OPTIONAL MATCH (o:Order)-[line:ORDERS]->(p)
                OPTIONAL MATCH (c:Customer)-[:PURCHASED]->(o)
                RETURN s, o, c, line
            """, {"key": entity_key})
            nodes = {("Product", anchor["key"]): anchor}
            edges = {}
            orders = set()
            revenue = 0.0
            unusable = 0
            for row in rows:
                supplier_node, order_node, customer_node, line = (row.get(k) for k in ("s", "o", "c", "line"))
                if supplier_node is not None:
                    supplier = _node_payload(supplier_node, "Supplier")
                    nodes[("Supplier", supplier["key"])] = supplier
                    edges[("SUPPLIES", supplier["key"], anchor["key"])] = {
                        "type": "SUPPLIES", "from": {"label": "Supplier", "key": supplier["key"]},
                        "to": {"label": "Product", "key": anchor["key"]}, "properties": {},
                    }
                if order_node is not None:
                    order = _node_payload(order_node, "Order")
                    orders.add(order["key"])
                    nodes[("Order", order["key"])] = order
                    edges[("ORDERS", order["key"], anchor["key"])] = {
                        "type": "ORDERS", "from": {"label": "Order", "key": order["key"]},
                        "to": {"label": "Product", "key": anchor["key"]}, "properties": {},
                    }
                    if line is not None:
                        quantity = dict(line).get("quantity")
                        price = dict(line).get("unitPrice")
                        if price is None:
                            price = dict(anchors[0]["a"]).get("unitPrice")
                        if quantity is None or price is None:
                            unusable += 1
                        else:
                            revenue += float(price) * float(quantity)
                if customer_node is not None and depth >= 2:
                    customer = _node_payload(customer_node, "Customer")
                    nodes[("Customer", customer["key"])] = customer
                    edges[("PURCHASED", customer["key"], order["key"])] = {
                        "type": "PURCHASED", "from": {"label": "Customer", "key": customer["key"]},
                        "to": {"label": "Order", "key": order["key"]}, "properties": {},
                    }
            aggregates = {"products_affected": 1, "orders_affected": len(orders),
                          "revenue_at_risk": round(revenue, 2), "unusable_lines": unusable}
            subgraph = {"nodes": list(nodes.values()), "edges": list(edges.values())}
            return _impact_result("ok" if edges else "empty", anchor, subgraph, aggregates)
        if entity_label == "Supplier":
            query = """
                MATCH (s:Supplier {supplierID: $key})
                OPTIONAL MATCH (s)-[:SUPPLIES]->(p:Product)
                OPTIONAL MATCH (o:Order)-[line:ORDERS]->(p)
                OPTIONAL MATCH (c:Customer)-[:PURCHASED]->(o)
                RETURN p, o, c, line
            """
        elif entity_label == "Product":
            query = """
                MATCH (p:Product {productID: $key})
                OPTIONAL MATCH (o:Order)-[line:ORDERS]->(p)
                OPTIONAL MATCH (c:Customer)-[:PURCHASED]->(o)
                RETURN p, o, c, line
            """
        else:
            query = """
                MATCH (c:Customer {customerID: $key})
                OPTIONAL MATCH (c)-[:PURCHASED]->(o:Order)
                OPTIONAL MATCH (o)-[line:ORDERS]->(p:Product)
                RETURN p, o, c, line
            """
        rows, _ = client.run_read_query(query, {"key": entity_key})
    except Exception as exc:
        return _impact_result("invalid", None, blank, zero, f"Impact query failed: {exc}")

    nodes = {(anchor["label"], anchor["key"]): anchor}
    edges = {}
    products, orders = set(), set()
    revenue = 0.0
    unusable = 0
    def add_node(node, label):
        payload = _node_payload(node, label)
        nodes[(label, payload["key"])] = payload
        return payload
    def add_edge(kind, start, end):
        signature = (kind, start["label"], start["key"], end["label"], end["key"])
        edges[signature] = {"type": kind, "from": {"label": start["label"], "key": start["key"]}, "to": {"label": end["label"], "key": end["key"]}, "properties": {}}

    for row in rows:
        p_node, o_node, c_node, line = (row.get(k) for k in ("p", "o", "c", "line"))
        p = o = c = None
        if entity_label == "Supplier":
            if p_node is not None and depth >= 1:
                p = add_node(p_node, "Product")
                products.add(p["key"])
                add_edge("SUPPLIES", anchor, p)
            if o_node is not None and depth >= 2:
                o = add_node(o_node, "Order")
                orders.add(o["key"])
                add_edge("ORDERS", o, p)
            if c_node is not None and depth >= 3:
                c = add_node(c_node, "Customer")
                add_edge("PURCHASED", c, o)
        elif entity_label == "Product":
            p = anchor
            products.add(p["key"])
            if o_node is not None and depth >= 1:
                o = add_node(o_node, "Order")
                orders.add(o["key"])
                add_edge("ORDERS", o, p)
            if c_node is not None and depth >= 2:
                c = add_node(c_node, "Customer")
                add_edge("PURCHASED", c, o)
        else:
            c = anchor
            if o_node is not None and depth >= 1:
                o = add_node(o_node, "Order")
                orders.add(o["key"])
                add_edge("PURCHASED", c, o)
            if p_node is not None and depth >= 2:
                p = add_node(p_node, "Product")
                products.add(p["key"])
                add_edge("ORDERS", o, p)
        if line is not None and p is not None and o is not None:
            quantity = dict(line).get("quantity")
            price = dict(line).get("unitPrice")
            if price is None:
                price = dict(p_node).get("unitPrice")
            if quantity is None or price is None:
                unusable += 1
            else:
                revenue += float(price) * float(quantity)
    aggregates = {"products_affected": len(products), "orders_affected": len(orders), "revenue_at_risk": round(revenue, 2), "unusable_lines": unusable}
    subgraph = {"nodes": list(nodes.values()), "edges": list(edges.values())}
    return _impact_result("ok" if edges else "empty", anchor, subgraph, aggregates)


# =============================================================================
# TOOL 1.3: co_purchase
# =============================================================================

def co_purchase(product_key: str) -> dict:
    """Return ranked products co-occurring with the anchor in distinct orders."""
    empty = {"product": None, "recommendations": []}
    if not isinstance(product_key, str) or not product_key.strip():
        return {"status": "invalid", "error": "product_key must be a non-empty string", **empty}
    try:
        anchor_rows, _ = client.run_read_query(
            "MATCH (p:Product {productID: $product_key}) RETURN p",
            {"product_key": product_key},
        )
        if not anchor_rows:
            return {"status": "empty", "error": None, **empty}
        anchor_node = _node_payload(anchor_rows[0]["p"], "Product")
        anchor = {field: anchor_node[field] for field in ("label", "key", "name")}
        query = """
            MATCH (p1:Product {productID: $product_key})<-[line1:ORDERS]-(o:Order)-[line2:ORDERS]->(p2:Product)
            WHERE p1 <> p2
            RETURN p2, count(DISTINCT o.orderID) AS co_bought
            ORDER BY co_bought DESC, p2.productID ASC
            LIMIT 10
        """
        records, _ = client.run_read_query(query, {"product_key": product_key})
        recommendations = []
        for record in records:
            node = _node_payload(record["p2"], "Product")
            item = {field: node[field] for field in ("label", "key", "name")}
            recommendations.append({
                "product": item,
                "co_bought": int(record["co_bought"]),
                "evidence": {"nodes": [anchor_node, node], "edges": []},
            })
        return {
            "status": "ok" if recommendations else "empty",
            "error": None,
            "product": anchor,
            "recommendations": recommendations,
        }
    except Exception as exc:
        return {"status": "invalid", "error": f"Co-purchase query failed: {exc}", **empty}


# =============================================================================
# TOOL 1.4: customer_history
# =============================================================================

def customer_history(customer_key: str) -> dict:
    """Return a customer's dated order history with per-order totals and evidence."""
    empty = {"customer": None, "orders": []}
    if not isinstance(customer_key, str) or not customer_key.strip():
        return {"status": "invalid", "error": "customer_key must be a non-empty string", **empty}

    query = """
        MATCH (c:Customer {customerID: $customer_key})
        OPTIONAL MATCH (c)-[purchase:PURCHASED]->(o:Order)
        OPTIONAL MATCH (o)-[line:ORDERS]->(p:Product)
        WITH c, purchase, o, sum(coalesce(line.unitPrice, p.unitPrice) * line.quantity) AS total
        RETURN c, purchase, o, o.orderDate AS order_date, total, o.shipCountry AS ship_country
        ORDER BY order_date ASC
    """
    try:
        records, _ = client.run_read_query(query, {"customer_key": customer_key})
        if not records:
            return {"status": "empty", "error": None, **empty}

        customer_node = _node_payload(records[0]["c"], "Customer")
        customer = {field: customer_node[field] for field in ("label", "key", "name")}
        orders = []
        for record in records:
            order_value = record.get("o")
            if order_value is None:
                continue
            order_node = _node_payload(order_value, "Order")
            order_ref = {field: order_node[field] for field in ("label", "key", "name")}
            relationship = record.get("purchase")
            relationship_properties = _json_safe(dict(relationship)) if relationship is not None else {}
            edge = {
                "type": "PURCHASED",
                "from": {"label": "Customer", "key": customer_node["key"]},
                "to": {"label": "Order", "key": order_node["key"]},
                "properties": relationship_properties,
            }
            orders.append({
                "order": order_ref,
                "order_date": _json_safe(record.get("order_date")),
                "total": round(float(record["total"]), 2) if record.get("total") is not None else 0.0,
                "ship_country": _json_safe(record.get("ship_country")),
                "evidence": {"nodes": [customer_node, order_node], "edges": [edge]},
            })
        return {
            "status": "ok" if orders else "empty",
            "error": None,
            "customer": customer,
            "orders": orders,
        }
    except Exception as exc:
        return {"status": "invalid", "error": f"Customer history query failed: {exc}", **empty}


# =============================================================================
# TOOL 1.5: aggregate
# =============================================================================

# Fixed, whitelisted aggregate projections. Each path is a curated traversal.
AGGREGATE_PROPERTIES = {
    "Supplier": {"country", "city", "supplierID", "companyName", "contactName", "contactTitle", "address", "region", "postalCode", "phone", "fax", "homePage"},
    "Product": {"categoryID", "productID", "productName", "unitPrice", "unitsInStock", "discontinued", "reorderLevel", "unitsOnOrder"},
    "Customer": {"customerID", "companyName", "country", "city", "region"},
    "Employee": {"employeeID", "firstName", "lastName", "title", "country"},
    "Category": {"categoryID", "categoryName"},
    "Shipper": {"shipperID", "companyName"},
    "Order": {"orderID", "orderDate", "shipCountry"},
    "Territory": {"territoryID", "territoryDescription"},
    "Region": {"regionID", "regionDescription"},
}

AGGREGATE_ALIASES = {
    "Supplier": "s", "Product": "p", "Customer": "c", "Employee": "e",
    "Category": "cat", "Shipper": "sh", "Order": "o", "Territory": "t", "Region": "r",
}

COUNT_PATHS = {
    "Supplier": ("MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)", "count(DISTINCT p)"),
    "Product": ("MATCH (p:Product)-[:PART_OF]->(c:Category)", "count(DISTINCT p)"),
    "Customer": ("MATCH (c:Customer)-[:PURCHASED]->(o:Order)", "count(DISTINCT o)"),
    "Employee": ("MATCH (e:Employee)-[:SOLD]->(o:Order)", "count(DISTINCT o)"),
    "Category": ("MATCH (cat:Category)<-[:PART_OF]-(p:Product)<-[:ORDERS]-(o:Order)", "count(DISTINCT o)"),
    "Shipper": ("MATCH (sh:Shipper)-[:SHIPS]->(o:Order)", "count(DISTINCT o)"),
    "Order": ("MATCH (o:Order)-[:ORDERS]->(p:Product)", "count(DISTINCT p)"),
    "Territory": ("MATCH (t:Territory)<-[:IN_TERRITORY]-(e:Employee)", "count(DISTINCT e)"),
    "Region": ("MATCH (r:Region)<-[:IN_REGION]-(t:Territory)", "count(DISTINCT t)"),
}

REVENUE_PATHS = {
    "Supplier": "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[line:ORDERS]-(o:Order)",
    "Product": "MATCH (p:Product)<-[line:ORDERS]-(o:Order)",
    "Customer": "MATCH (c:Customer)-[:PURCHASED]->(o:Order)-[line:ORDERS]->(p:Product)",
    "Employee": "MATCH (e:Employee)-[:SOLD]->(o:Order)-[line:ORDERS]->(p:Product)",
    "Category": "MATCH (cat:Category)<-[:PART_OF]-(p:Product)<-[line:ORDERS]-(o:Order)",
    "Shipper": "MATCH (sh:Shipper)-[:SHIPS]->(o:Order)-[line:ORDERS]->(p:Product)",
    "Order": "MATCH (o:Order)-[line:ORDERS]->(p:Product)",
    "Territory": "MATCH (t:Territory)<-[:IN_TERRITORY]-(e:Employee)-[:SOLD]->(o:Order)-[line:ORDERS]->(p:Product)",
    "Region": "MATCH (r:Region)<-[:IN_REGION]-(t:Territory)<-[:IN_TERRITORY]-(e:Employee)-[:SOLD]->(o:Order)-[line:ORDERS]->(p:Product)",
}


def _aggregate_filter_value(label: str, prop: str, value: str):
    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1]
    if label == "Product":
        if prop == "unitPrice":
            return float(value)
        if prop in {"unitsInStock", "reorderLevel", "unitsOnOrder"}:
            return int(value)
        if prop == "discontinued":
            if value.lower() not in {"true", "false"}:
                raise ValueError("Invalid boolean filter")
            return value.lower() == "true"
    return value


def aggregate(label: str, group_by: str, metric: str, where: Optional[str] = None) -> dict:
    """Run a fixed, parameterized grouped metric with bounded representative evidence."""
    if not isinstance(label, str) or label not in AGGREGATE_PROPERTIES:
        return {"status": "invalid", "error": f"Unsupported label: {label}", "groups": [], "n_groups": 0}
    if not isinstance(metric, str) or metric not in {"count", "sum_revenue", "avg_revenue"}:
        return {"status": "invalid", "error": f"Unsupported aggregate metric: {metric}", "groups": [], "n_groups": 0}
    whitelist = AGGREGATE_PROPERTIES[label]
    if not isinstance(group_by, str) or group_by not in whitelist:
        return {"status": "invalid", "error": f"Unsupported group_by property for {label}: {group_by}", "groups": [], "n_groups": 0}
    alias = AGGREGATE_ALIASES[label]
    if metric == "count":
        match_clause, value_expr = COUNT_PATHS[label]
    else:
        match_clause = REVENUE_PATHS[label]
        revenue = "coalesce(line.unitPrice, p.unitPrice) * line.quantity"
        value_expr = f"sum({revenue})" if metric == "sum_revenue" else f"avg({revenue})"
    filter_prop = None
    parameters = {}
    if where is not None:
        if not isinstance(where, str) or "=" not in where:
            return {"status": "invalid", "error": "where must be a whitelisted equality filter", "groups": [], "n_groups": 0}
        filter_prop, raw_value = (part.strip() for part in where.split("=", 1))
        if filter_prop not in whitelist:
            return {"status": "invalid", "error": f"Unsupported filter property for {label}: {filter_prop}", "groups": [], "n_groups": 0}
        try:
            parameters["where_value"] = _aggregate_filter_value(label, filter_prop, raw_value)
        except ValueError as exc:
            return {"status": "invalid", "error": str(exc), "groups": [], "n_groups": 0}
    if label == "Product" and metric != "count" and (group_by == "categoryID" or filter_prop == "categoryID"):
        match_clause += " MATCH (p)-[:PART_OF]->(c:Category)"
    group_alias = "c" if label == "Product" and group_by == "categoryID" else alias
    filter_alias = "c" if label == "Product" and filter_prop == "categoryID" else alias
    if filter_prop:
        match_clause += f" WHERE {filter_alias}.{filter_prop} = $where_value"
    if label == "Region" and metric != "count":
        match_clause += " WITH DISTINCT r, line, p"
    order_by = "metric_value DESC" if metric != "count" else "group_value ASC"
    query = (
        f"{match_clause} RETURN {group_alias}.{group_by} AS group_value, "
        f"{value_expr} AS metric_value, collect(DISTINCT {alias})[0..3] AS evidence_nodes "
        f"ORDER BY {order_by} LIMIT 20"
    )
    try:
        records, _ = client.run_read_query(query, parameters)
        groups = []
        for record in records:
            handles = {}
            for node in record.get("evidence_nodes", [])[:3]:
                payload = _node_payload(node, label)
                handles[(payload["label"], payload["key"])] = payload
            raw_metric = record["metric_value"]
            groups.append({
                "group_value": str(record["group_value"]),
                "metric_value": int(raw_metric) if metric == "count" else round(float(raw_metric), 2),
                "evidence": {"nodes": list(handles.values()), "edges": []},
            })
        return {"status": "ok" if groups else "empty", "error": None, "groups": groups, "n_groups": len(groups)}
    except Exception as exc:
        return {"status": "invalid", "error": f"Aggregate query failed: {exc}", "groups": [], "n_groups": 0}


# =============================================================================
# TOOL 2.1: run_readonly_cypher (Phase 2)
# =============================================================================

def _repair_cypher(query: str, error: str) -> str:
    """Ask the large model for one corrected read query using the schema contract."""
    from src.agents.llm import complete_mistral_chat, MODEL_AGENT
    from src.agents.schema_prompt import generate_schema_prompt

    prompt = (
        "Repair this one read-only Cypher query for the Northwind graph. "
        "Return only the corrected Cypher, with no markdown or explanation. "
        "Use only the supplied schema and preserve the question's intent.\n\n"
        f"Schema:\n{generate_schema_prompt()}\n\n"
        f"Failed query:\n{query}\n\nError:\n{error}"
    )
    response = complete_mistral_chat(
        model_name=MODEL_AGENT,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=700,
    )
    candidate = response.choices[0].message.content.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return candidate


def _json_safe(value):
    """Convert non-graph Cypher values into JSON-safe scalars or containers."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "iso_format"):
        return value.iso_format()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _cypher_node_payload(node) -> dict:
    """Return a canonical node with all of its JSON-safe properties."""
    labels = sorted(label for label in node.labels if label in LABEL_TO_KEY)
    if not labels:
        raise ValueError("Returned node has no supported Northwind label")
    label = labels[0]
    properties = {key: _json_safe(value) for key, value in dict(node).items()}
    key_property = LABEL_TO_KEY[label]
    key = properties.get(key_property)
    if key is None:
        raise ValueError(f"Returned {label} node is missing key property {key_property}")
    if label == "Employee":
        name = " ".join(filter(None, [properties.get("firstName"), properties.get("lastName")]))
    elif label == "Order":
        name = str(key)
    else:
        name_property = LABEL_TO_NAME[label]
        name = str(properties.get(name_property) or key)
    return {"label": label, "key": str(key), "name": name, "properties": properties}


def _cypher_edge_payload(relationship, evidence: dict) -> dict:
    """Normalize a returned Neo4j relationship and collect its endpoint nodes."""
    start = _cypher_node_payload(relationship.start_node)
    end = _cypher_node_payload(relationship.end_node)
    edge = {
        "type": str(relationship.type),
        "from": {"label": start["label"], "key": start["key"]},
        "to": {"label": end["label"], "key": end["key"]},
        "properties": {key: _json_safe(value) for key, value in dict(relationship).items()},
    }
    _add_evidence_node(evidence, start)
    _add_evidence_node(evidence, end)
    _add_evidence_edge(evidence, edge)
    return edge


def _add_evidence_node(evidence: dict, node: dict) -> None:
    identity = (node["label"], node["key"])
    if identity not in evidence["_node_ids"]:
        evidence["_node_ids"].add(identity)
        evidence["nodes"].append(node)


def _add_evidence_edge(evidence: dict, edge: dict) -> None:
    identity = json.dumps(edge, sort_keys=True, separators=(",", ":"))
    if identity not in evidence["_edge_ids"]:
        evidence["_edge_ids"].add(identity)
        evidence["edges"].append(edge)


def _normalize_cypher_value(value, evidence: dict):
    """Normalize graph entities recursively while retaining returned column structure."""
    if hasattr(value, "nodes") and hasattr(value, "relationships"):
        nodes = [_cypher_node_payload(node) for node in value.nodes]
        edges = [_cypher_edge_payload(edge, evidence) for edge in value.relationships]
        for node in nodes:
            _add_evidence_node(evidence, node)
        return {"nodes": nodes, "edges": edges}
    if hasattr(value, "labels"):
        node = _cypher_node_payload(value)
        _add_evidence_node(evidence, node)
        return node
    if hasattr(value, "start_node") and hasattr(value, "end_node") and hasattr(value, "type"):
        return _cypher_edge_payload(value, evidence)
    if isinstance(value, dict):
        return {str(key): _normalize_cypher_value(item, evidence) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_cypher_value(item, evidence) for item in value]
    return _json_safe(value)


def _normalize_cypher_row(record: dict) -> dict:
    evidence = {"nodes": [], "edges": [], "_node_ids": set(), "_edge_ids": set()}
    values = _normalize_cypher_value(dict(record), evidence)
    return {
        "values": values,
        "evidence": {"nodes": evidence["nodes"], "edges": evidence["edges"]},
    }


def _validate_schema_cypher(query: str) -> str | None:
    """Return an error for identifiers outside the SCHEMA.md universe."""
    import re
    from src.agents.schema_prompt import get_labels, get_relationships

    if "`" in query:
        return "Backtick identifiers are not part of the Northwind schema"
    code = Neo4jClient._mask_literals_and_comments(query)
    labels = {item["label"]: set(item["properties"]) | {item["key"]} for item in get_labels()}
    relationships = {item["type"]: set(item["properties"]) for item in get_relationships()}
    aliases = {}
    for match in re.finditer(r"\(\s*([A-Za-z_][\w]*)\s*:\s*([A-Za-z_][\w]*)", code):
        alias, label = match.groups()
        if label not in labels:
            return f"Unknown node label: {label}"
        aliases[alias] = labels[label]
    for match in re.finditer(r"\(\s*:\s*([A-Za-z_][\w]*)", code):
        if match.group(1) not in labels:
            return f"Unknown node label: {match.group(1)}"
    for match in re.finditer(r"\[\s*([A-Za-z_][\w]*)\s*:\s*([A-Za-z_][\w]*)", code):
        alias, kind = match.groups()
        if kind not in relationships:
            return f"Unknown relationship type: {kind}"
        aliases[alias] = relationships[kind]
    for match in re.finditer(r"\[\s*:\s*([A-Za-z_][\w]*)", code):
        if match.group(1) not in relationships:
            return f"Unknown relationship type: {match.group(1)}"
    for alias, prop in re.findall(r"\b([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\b", code):
        if alias not in aliases or prop not in aliases[alias]:
            return f"Unknown property: {alias}.{prop}"
    return None


def run_readonly_cypher(query: str) -> dict:
    """Validate, run, and at most once repair a read-only Cypher query."""
    attempts = []
    if not isinstance(query, str) or not query.strip():
        invalid_query = query if isinstance(query, str) else str(query)
        error = "query must be a non-empty string"
        attempts.append({"cypher": invalid_query, "valid": False, "error": error})
        return {"status": "invalid", "query": invalid_query, "attempts": attempts, "rows": [], "error": error}
    if not client._validate_read_only(query):
        error = "Only one read-only query is allowed"
        attempts.append({"cypher": query, "valid": False, "error": error})
        return {"status": "invalid", "query": query, "attempts": attempts, "rows": [], "error": error}
    candidate = query
    for index in range(2):
        if index == 1:
            try:
                candidate = _repair_cypher(query, attempts[0]["error"])
            except Exception as exc:
                attempts.append({"cypher": query, "valid": False, "error": f"Repair unavailable: {exc}"})
                break
        if not client._validate_read_only(candidate):
            attempts.append({"cypher": candidate, "valid": False, "error": "Repair is not a single read-only query"})
            break
        try:
            schema_error = _validate_schema_cypher(candidate)
            if schema_error:
                raise ValueError(schema_error)
            if not client.explain(candidate):
                raise ValueError("EXPLAIN validation failed")
            records, _ = client.run_read_query(candidate)
            rows = [_normalize_cypher_row(dict(record)) for record in records]
            attempts.append({"cypher": candidate, "valid": True, "error": None})
            return {
                "status": ("retry_ok" if index else "ok") if rows else "empty",
                "query": query, "attempts": attempts, "rows": rows, "error": None,
            }
        except Exception as exc:
            attempts.append({"cypher": candidate, "valid": False, "error": str(exc)})
    error = attempts[-1]["error"] if attempts else "Query execution failed"
    return {"status": "retry_failed", "query": query, "attempts": attempts, "rows": [], "error": error}

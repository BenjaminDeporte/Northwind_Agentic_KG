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

from typing import Any, Optional
from enum import Enum

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


def lookup_entity(name: str, label: Optional[str] = None) -> dict:
    """Resolve a mention across all nine labels with exact/contains/fuzzy tiers."""
    if label is not None and label not in VALID_LABELS:
        return {"status": "invalid", "query_name": name, "matches": []}
    if not isinstance(name, str) or not name.strip():
        return {"status": "invalid", "query_name": name, "matches": []}
    labels = [label] if label else list(LABEL_TO_KEY)

    def payload(node, node_label, tier):
        props = dict(node)
        key_prop = LABEL_TO_KEY[node_label]
        if node_label == "Employee":
            display_name = " ".join(filter(None, [props.get("firstName"), props.get("lastName")]))
        elif node_label == "Order":
            display_name = str(props.get("orderID", ""))
        else:
            display_name = str(props.get(LABEL_TO_NAME[node_label], ""))
        remaining = {k: v for k, v in props.items() if k not in {key_prop, LABEL_TO_NAME.get(node_label)}}
        return {"label": node_label, "key": str(props.get(key_prop, "")), "name": display_name,
                "match": tier, "properties": _filter_properties(remaining, node_label)}

    for tier in ("exact", "contains"):
        found = []
        for node_label in labels:
            expression = _lookup_name_expression(node_label)
            predicate = f"{expression} = $name" if tier == "exact" else f"toLower({expression}) CONTAINS toLower($name)"
            query = f"MATCH (n:{node_label}) WHERE {predicate} RETURN n"
            try:
                rows, _ = client.run_read_query(query, {"name": name})
            except Exception:
                return {"status": "invalid", "query_name": name, "matches": []}
            found.extend(payload(row["n"], node_label, tier) for row in rows)
        if found:
            return {"status": "ok", "query_name": name, "matches": found[:10]}

    fuzzy = []
    for node_label in labels:
        try:
            rows, _ = client.run_read_query(f"MATCH (n:{node_label}) RETURN n")
        except Exception:
            return {"status": "invalid", "query_name": name, "matches": []}
        for row in rows:
            match = payload(row["n"], node_label, "fuzzy")
            distance = _levenshtein(name.lower(), match["name"].lower())
            if distance <= 1:
                fuzzy.append((distance, match))
    fuzzy.sort(key=lambda item: (item[0], item[1]["name"], item[1]["label"]))
    matches = [match for _, match in fuzzy[:10]]
    return {"status": "ok" if matches else "empty", "query_name": name, "matches": matches}


# =============================================================================
# TOOL 1.2: impact_analysis
# =============================================================================

def _node_payload(node, label: str) -> dict:
    props = dict(node)
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


def impact_analysis(entity_key: str, entity_label: str, direction: str = "out", depth: int = 3) -> dict:
    """Return the actual evidence graph and revenue aggregates for an anchor."""
    blank = {"nodes": [], "edges": []}
    zero = {"products_affected": 0, "orders_affected": 0, "revenue_at_risk": 0.0, "unusable_lines": 0}
    if entity_label not in {"Supplier", "Product", "Customer"} or direction not in {"out", "in"} or type(depth) is not int or not 1 <= depth <= 3:
        return {"status": "invalid", "anchor": None, "subgraph": blank, "aggregates": zero}
    key_property = LABEL_TO_KEY[entity_label]
    anchor_query = f"MATCH (a:{entity_label} {{{key_property}: $key}}) RETURN a"
    try:
        anchors, _ = client.run_read_query(anchor_query, {"key": entity_key})
        if not anchors:
            return {"status": "empty", "anchor": None, "subgraph": blank, "aggregates": zero}
        anchor = _node_payload(anchors[0]["a"], entity_label)
        if direction == "in":
            if entity_label != "Product":
                return {"status": "empty", "anchor": anchor, "subgraph": {"nodes": [anchor], "edges": []}, "aggregates": zero}
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
                        "to": {"label": "Product", "key": anchor["key"]},
                    }
                if order_node is not None:
                    order = _node_payload(order_node, "Order")
                    orders.add(order["key"])
                    nodes[("Order", order["key"])] = order
                    edges[("ORDERS", order["key"], anchor["key"])] = {
                        "type": "ORDERS", "from": {"label": "Order", "key": order["key"]},
                        "to": {"label": "Product", "key": anchor["key"]},
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
                        "to": {"label": "Order", "key": order["key"]},
                    }
            aggregates = {"products_affected": 1, "orders_affected": len(orders),
                          "revenue_at_risk": round(revenue, 2), "unusable_lines": unusable}
            return {"status": "ok" if edges else "empty", "anchor": anchor,
                    "subgraph": {"nodes": list(nodes.values()), "edges": list(edges.values())},
                    "aggregates": aggregates}
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
    except Exception:
        return {"status": "invalid", "anchor": None, "subgraph": blank, "aggregates": zero}

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
        edges[signature] = {"type": kind, "from": {"label": start["label"], "key": start["key"]}, "to": {"label": end["label"], "key": end["key"]}}

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
    return {"status": "ok" if edges else "empty", "anchor": anchor, "subgraph": {"nodes": list(nodes.values()), "edges": list(edges.values())}, "aggregates": aggregates}


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
    """Run a fixed, parameterized aggregate with contributor node handles."""
    invalid = {"status": "invalid", "groups": [], "n_groups": 0}
    if label not in AGGREGATE_PROPERTIES or metric not in {"count", "sum_revenue", "avg_revenue"}:
        return invalid
    whitelist = AGGREGATE_PROPERTIES[label]
    if group_by not in whitelist:
        return invalid
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
        if "=" not in where:
            return invalid
        filter_prop, raw_value = (part.strip() for part in where.split("=", 1))
        if filter_prop not in whitelist:
            return invalid
        try:
            parameters["where_value"] = _aggregate_filter_value(label, filter_prop, raw_value)
        except ValueError:
            return invalid
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
        f"{value_expr} AS metric_value, collect(DISTINCT {alias}) AS evidence_nodes "
        f"ORDER BY {order_by} LIMIT 20"
    )
    try:
        records, _ = client.run_read_query(query, parameters)
        groups = []
        for record in records:
            handles = {}
            for node in record.get("evidence_nodes", []):
                payload = _node_payload(node, label)
                handles[(payload["label"], payload["key"])] = {
                    field: payload[field] for field in ("label", "key", "name")
                }
            raw_metric = record["metric_value"]
            groups.append({
                "group_value": str(record["group_value"]),
                "metric_value": int(raw_metric) if metric == "count" else round(float(raw_metric), 2),
                "evidence": list(handles.values()),
            })
        return {"status": "ok" if groups else "empty", "groups": groups, "n_groups": len(groups)}
    except Exception:
        return invalid


# =============================================================================
# TOOL 2.1: run_readonly_cypher (Phase 2)
# =============================================================================

def _repair_cypher(query: str, error: str) -> str:
    """Ask the large model for one corrected read query using the schema contract."""
    from src.agents.llm import get_mistral_client, MODEL_AGENT
    from src.agents.schema_prompt import generate_schema_prompt

    prompt = (
        "Repair this one read-only Cypher query for the Northwind graph. "
        "Return only the corrected Cypher, with no markdown or explanation. "
        "Use only the supplied schema and preserve the question's intent.\n\n"
        f"Schema:\n{generate_schema_prompt()}\n\n"
        f"Failed query:\n{query}\n\nError:\n{error}"
    )
    response = get_mistral_client().chat.complete(
        model=MODEL_AGENT,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=700,
    )
    candidate = response.choices[0].message.content.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return candidate


def _cypher_json(value):
    if hasattr(value, "labels"):
        labels = sorted(value.labels)
        label = labels[0] if labels else ""
        if label in LABEL_TO_KEY:
            return _node_payload(value, label)
        return dict(value)
    if isinstance(value, dict):
        return {k: _cypher_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_cypher_json(v) for v in value]
    return value


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
    if not client._validate_read_only(query):
        attempts.append({"cypher": query, "valid": False, "error": "Only one read-only query is allowed"})
        return {"status": "invalid", "query": query, "attempts": attempts, "rows": []}
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
            attempts.append({"cypher": candidate, "valid": True, "error": None})
            rows = [_cypher_json(dict(record)) for record in records]
            return {
                "status": ("retry_ok" if index else "ok") if rows else "empty",
                "query": query, "attempts": attempts, "rows": rows,
            }
        except Exception as exc:
            attempts.append({"cypher": candidate, "valid": False, "error": str(exc)})
    return {"status": "retry_failed", "query": query, "attempts": attempts, "rows": []}

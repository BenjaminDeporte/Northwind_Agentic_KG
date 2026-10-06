# SCHEMA.md — Northwind Knowledge Graph

This document is the data contract for the Northwind agentic KG demo. It describes the schema as it exists in the live AuraDB instance, verified via `apoc.meta.stats()` on 2026-09-25. It is authoritative: the coding agent, the tool implementations, and the exploratory-tool schema prompt derive from this file. If the instance changes, this file changes first.

## Instance summary

| Metric | Value |
|---|---|
| Node labels | 9 |
| Relationship types | 9 |
| Property keys | 61 |
| Nodes | 1,104 |
| Relationships | 4,909 |

## Node labels

Verified via `apoc.meta.nodeTypeProperties()` (2026-09-25). All properties exist on 100% of nodes of their label (observations = count), but `mandatory` is FALSE everywhere — Cypher should still not assume presence. All values are Strings except where noted; all dates are ISO-like strings, not Neo4j date types.

**Naming warning:** there is no `name` property on any label. Supplier, Customer and Shipper use `companyName`, Product uses `productName`, Category uses `categoryName`, Territory uses `territoryDescription`, Region uses `regionDescription`. Tools and the schema prompt must use these exact keys.

| Label | Count | Key | Name property | Properties (verified, types) |
|---|---|---|---|---|
| Product | 77 | productID | productName | unitPrice (Double), unitsInStock (Long), reorderLevel (Long), unitsOnOrder (Long), discontinued (Boolean), productName, productID |
| Order | 830 | orderID | — | orderDate (String), requiredDate, shippedDate, freight (String!), shipName, shipAddress, shipCity, shipRegion, shipPostalCode, shipCountry, orderID |
| Customer | 91 | customerID | companyName | contactName, contactTitle, address, city, region, postalCode, country, phone, fax, companyName, customerID |
| Supplier | 29 | supplierID | companyName | contactName, contactTitle, address, city, region, postalCode, country, phone, fax, homePage, companyName, supplierID |
| Employee | 9 | employeeID | lastName + firstName | title, titleOfCourtesy, birthDate, hireDate, address, city, region, postalCode, country, homePhone, extension, photoPath, notes, lastName, firstName, employeeID |
| Category | 8 | categoryID | categoryName | categoryName, description, categoryID |
| Shipper | 3 | shipperID | companyName | companyName, phone, shipperID |
| Territory | 53 | territoryID | territoryDescription | territoryID, territoryDescription |
| Region | 4 | regionID | regionDescription | regionID, regionDescription |

Notes:
- `freight` on Order is a String (currency formatting preserved from source data) — parse before arithmetic.
- Employee names are split (`firstName`/`lastName`); a full-name lookup tool should match on both.

## Relationships

| Type | From → To | Count | Properties (verify) | Meaning |
|---|---|---|---|---|
| PURCHASED | Customer → Order | 830 | — | customer placed order |
| SOLD | Employee → Order | 830 | — | employee processed order |
| SHIPS | Shipper → Order | 830 | — | shipper delivered order |
| ORDERS | Order → Product | 2,155 | quantity (Long, 100/2155), unitPrice (Double, 100/2155), discount (Double, 100/2155) | order line: no OrderDetail node. CAUTION: edge properties exist on only ~5% of edges — see revenue rule below |
| SUPPLIES | Supplier → Product | 77 | — | every product has exactly one supplier |
| PART_OF | Product → Category | 77 | — | every product has exactly one category |
| REPORTS_TO | Employee → Employee | 8 | — | hierarchy; exactly one employee with no manager |
| IN_TERRITORY | Employee → Territory | 49 | — | employee sales coverage |
| IN_REGION | Territory → Region | 53 | — | territory to region mapping |

## Structural facts (useful for tool design and sanity checks)

- Each Order has exactly one Customer, one Employee, one Shipper (830 each). Every order is purchased, sold, and shipped.
- ORDERS edges (2,155) are the order lines: average ~2.6 products per order. All other relationship types carry NO properties.
- **Revenue rule (verified, important):** ORDERS edge properties (`quantity`, `unitPrice`, `discount`) exist on only 100 of 2,155 edges. Revenue must be computed as `coalesce(line.unitPrice, p.unitPrice) * line.quantity` — falling back to Product.unitPrice, which exists on all 77 products. Never assume line.unitPrice is present. Treat null quantity as an unusable line and count it separately rather than dropping silently.
- Every Product has exactly one Supplier and one Category (77/77). Supplier- and Category-centric traversals are deterministic one-hop.
- REPORTS_TO forms a single tree (8 edges, 9 employees, one root).
- Employee → Territory → Region is the only 2-hop path in the org/geography branch.

## Core traversal patterns (the demo beats as Cypher shapes)

**Impact analysis (supplier failure — the wow demo):**

```cypher
MATCH (s:Supplier {companyName: $name})-[:SUPPLIES]->(p:Product)<-[line:ORDERS]-(o:Order)<-[:PURCHASED]-(c:Customer)
RETURN s, p, o, c,
       coalesce(line.unitPrice, p.unitPrice) * line.quantity AS lineRevenue
```

Also aggregate: count(DISTINCT p) products, count(DISTINCT o) orders, sum(lineRevenue) revenue at risk. The coalesce is mandatory — see the revenue rule above.

**Co-purchase (customers who bought X also bought Y):**

```cypher
MATCH (p1:Product {productName: $name})<-[:ORDERS]-(:Order)-[:ORDERS]->(p2:Product)
WHERE p1 <> p2
RETURN p2.productName, count(*) AS coBought
ORDER BY coBought DESC LIMIT 10
```

**Customer order flow over time (churn pattern):**

```cypher
MATCH (c:Customer)-[:PURCHASED]->(o:Order)
WHERE c.customerID = $id
RETURN o.orderDate ORDER BY o.orderDate
```

(Churn = gap analysis over the returned dates — computed in Python, not Cypher.)

## Rules for the exploratory tool (run_readonly_cypher)

- This schema is the complete universe. Any generated Cypher must use only the labels, relationship types, and property names above.
- Read-only enforcement: reject anything that is not a single READ query (no CREATE/MERGE/DELETE/SET/CALL that writes).
- Validate with EXPLAIN before execution. Exactly one retry on validation failure. Status vocabulary: ok / empty / invalid / retry_ok / retry_failed.
- Empty result is a legitimate answer, not an error: report it as such, never invent rows.

## Schema prompt extract (generated from this file, never hand-edited)

The LLM schema prompt for the exploratory tool is built mechanically from the tables above: labels with keys, relationship types with direction, the traversal patterns as few-shot examples, and the four rules. If this file changes, regenerate the prompt.
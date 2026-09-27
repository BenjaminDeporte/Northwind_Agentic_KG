# Phase 1 Ground Truth — Handoff Document

Copy this file into the repo as `GROUND_TRUTH.md`. It contains the hand-verified expected values for every Phase 1 unit test (PLAN.md items 1.1–1.5), plus the SCHEMA.md addendum and contract notes discovered during verification. Per PLAN.md, the implementer does not invent expected values: these dicts are the assertions.

Verification date: 2026-09-27, live AuraDB Northwind instance (1,104 nodes, 4,909 relationships, 9 labels, 9 relationship types).

---

## SCHEMA.md Addendum (apply before coding)

Findings from live-instance verification that the contract must carry:

1. **Customer→Order edge type is `PURCHASED`** (Customer → Order, 830 edges). There is no `ORDER` relationship type. Any contract text naming an `ORDER` edge between Customer and Order is wrong and must be corrected to `PURCHASED`.
2. **Full verified edge inventory** (type, direction, count) — the authoritative traversal reference:
   - Territory -IN_REGION→ Region (53)
   - Supplier -SUPPLIES→ Product (77)
   - Shipper -SHIPS→ Order (830)
   - Product -PART_OF→ Category (77)
   - Order -ORDERS→ Product (2155; `quantity`, `unitPrice`, `discount` on only ~100 edges)
   - Customer -PURCHASED→ Order (830)
   - Employee -REPORTS_TO→ Employee (8)
   - Employee -IN_TERRITORY→ Territory (49)
   - Employee -SOLD→ Order (830)
3. **Supplier impact traversal, depth 3, direction out:** `Supplier -SUPPLIES→ Product ←ORDERS- Order ←PURCHASED- Customer`.
4. **orderDate is stored as a string** with format `1997-08-25 00:00:00.000` (milliseconds included). Contract rule "dates as raw strings" means this exact format passes through untouched; unit tests assert it.
5. **No zero-revenue supplier countries exist** (every supplier country group has order lines), so join-based and count-based group semantics coincide in this dataset.

---

## Contract Notes (pin these in tool contracts / tests)

**lookup_entity:**
- Keys are SCHEMA.md key-property values (e.g. `"1"` = supplierID), not names. PROJECT.md illustrative examples showing a name in `key` are not normative.
- Per-label `properties` subsets, fixed across tiers: Supplier = `{country, phone}`, Product = `{unitPrice, unitsInStock}`.
- Fuzzy calibration pair: "Exotic Liqids" (edit distance 1) must match "Exotic Liquids"; "NonExistentSupplier" must match nothing. Two-point constraint on the threshold.
- Tier cascade verified by prerequisites: for 1.1.3 the exact and contains queries return 0 rows (fuzzy tier reached); for 1.1.4 contains returns 0 rows.

**co_purchase / customer_history:**
- Deterministic tie-break required: ties on co_bought broken by ascending productID (the ground-truth order). Without a pinned tie-break the test is flaky on ties (top-4 all have co_bought=4).
- co_purchase LIMIT 10 is load-bearing: more than 10 candidates exist, so the cap itself is tested.
- customer_history sorts by order_date ascending (orderID is monotone with orderDate in this dataset).

**aggregate:**
- Type pinning: counts are integers, revenues are floats rounded to 2 decimals, group_values are always raw strings (e.g. categoryID `"1"`, not `1`).
- 1.5.2 ordering is by group_value ascending (the verified order). If the contract chooses metric-descending, the expected sequence changes — pin one.
- Supplier `group_by` whitelist is a subset of the actual keys: `country, city, supplierID, companyName, contactName, contactTitle, address, region, postalCode, phone, fax, homePage`. Any other value → `status: "invalid"`.
- Data-quality note (not a blocker): several suppliers have postal codes in the `country` field ("75004", "74000", "3058", "2042", "84100", "48100", "0512", "71300"). The tool passes raw values through; the revenue-by-country chart will show postal codes as countries. Accept or note in the demo script; do not clean in the tool.

---

## GT 1.1 — lookup_entity

### 1.1.1 exact, Supplier "Exotic Liquids"

```json
{
  "status": "ok",
  "query_name": "Exotic Liquids",
  "matches": [
    {
      "label": "Supplier",
      "key": "1",
      "name": "Exotic Liquids",
      "match": "exact",
      "properties": { "country": "UK", "phone": "(171) 555-2222" }
    }
  ]
}
```

### 1.1.2 contains, "Liquids", Supplier

```json
{
  "status": "ok",
  "query_name": "Liquids",
  "matches": [
    {
      "label": "Supplier",
      "key": "1",
      "name": "Exotic Liquids",
      "match": "contains",
      "properties": { "country": "UK", "phone": "(171) 555-2222" }
    }
  ]
}
```

Single match — no other supplier name contains "Liquids".

### 1.1.3 fuzzy, "Exotic Liqids", Supplier

Prerequisites (both verified empty on the live instance): exact query on `'Exotic Liqids'` → 0 rows; contains query on `'Exotic Liqids'` → 0 rows.

```json
{
  "status": "ok",
  "query_name": "Exotic Liqids",
  "matches": [
    {
      "label": "Supplier",
      "key": "1",
      "name": "Exotic Liquids",
      "match": "fuzzy",
      "properties": { "country": "UK", "phone": "(171) 555-2222" }
    }
  ]
}
```

### 1.1.4 empty, "NonExistentSupplier", Supplier

Prerequisite: contains query on `'NonExistentSupplier'` → 0 rows (fuzzy tier also misses in Python).

```json
{ "status": "empty", "query_name": "NonExistentSupplier", "matches": [] }
```

### 1.1.5 exact, Product "Chai"

```json
{
  "status": "ok",
  "query_name": "Chai",
  "matches": [
    {
      "label": "Product",
      "key": "1",
      "name": "Chai",
      "match": "exact",
      "properties": { "unitPrice": 18.0, "unitsInStock": 39 }
    }
  ]
}
```

### 1.1.6 exact, "Chai", no label

Identical to 1.1.5 — verified that no other label has an entity named "Chai"; label is discovered without the hint.

```json
{
  "status": "ok",
  "query_name": "Chai",
  "matches": [
    {
      "label": "Product",
      "key": "1",
      "name": "Chai",
      "match": "exact",
      "properties": { "unitPrice": 18.0, "unitsInStock": 39 }
    }
  ]
}
```

---

## GT 1.2.1 — impact_analysis

`impact_analysis(entity_key="Exotic Liquids", entity_label="Supplier", direction="out", depth=3)`

Cross-checks passed (corrected 2026-09-27 after coding-agent challenge, re-verified live): output-6 distinct orders (90) = orders_affected; 94 order lines total (Chai 38 + Chang 44 + Aniseed Syrup 12 — the original consolidation said 91, which was an error); 4 orders bought two of the three supplier products (10485, 10611, 11070, 11077 → 94 lines − 4 duplicates = 90 orders); revenue recomputed from all 94 lines = 35,916.80 to the cent (live recheck: count(*)=94, count(DISTINCT o)=90, revenue 35916.8).

Open contract decision (do not let the implementation settle it silently): the subgraph node list includes Customer (49), but the edge set below counts only SUPPLIES + ORDERS — the 90 PURCHASED edges connecting the customers are omitted, which renders customers as orphan nodes in the agraph panel. Either add `"PURCHASED": 90` to edges, or document in PROJECT.md why the evidence-subgraph edge set is restricted to the traversal path that produced the impact aggregates.

The coalesce rule does real work here: Chai lines carry two prices — 14.4 (line-level unitPrice, early orders) and 18.0 (product-price fallback). Both sources verified inside the single revenue figure.

```json
{
  "status": "ok",
  "anchor": { "label": "Supplier", "key": "1", "name": "Exotic Liquids", "country": "UK" },
  "subgraph": {
    "nodes": { "Supplier": 1, "Product": 3, "Order": 90, "Customer": 49 },
    "edges": { "SUPPLIES": 3, "ORDERS": 94 }
  },
  "aggregates": {
    "products_affected": 3,
    "orders_affected": 90,
    "revenue_at_risk": 35916.8,
    "unusable_lines": 0
  }
}
```

Products affected: Chai (productID 1), Chang (2), Aniseed Syrup (3).

Demo note: "if Exotic Liquids fails, 35,916.80 of revenue across 90 orders and 49 customers is at risk" — hand-verified to the cent.

---

## GT 1.3.1 — co_purchase

`co_purchase(product_key="1")` — anchor Chai (38 orders contain it; max co_bought = 4 ≤ 38 ✓).

```json
{
  "status": "ok",
  "product": { "label": "Product", "key": "1", "name": "Chai" },
  "recommendations": [
    { "key": "21", "name": "Sir Rodney's Scones", "co_bought": 4 },
    { "key": "40", "name": "Boston Crab Meat", "co_bought": 4 },
    { "key": "60", "name": "Camembert Pierrot", "co_bought": 4 },
    { "key": "71", "name": "Flotemysost", "co_bought": 4 },
    { "key": "13", "name": "Konbu", "co_bought": 3 },
    { "key": "23", "name": "Tunnbröd", "co_bought": 3 },
    { "key": "29", "name": "Thüringer Rostbratwurst", "co_bought": 3 },
    { "key": "10", "name": "Ikura", "co_bought": 2 },
    { "key": "17", "name": "Alice Mutton", "co_bought": 2 },
    { "key": "18", "name": "Carnarvon Tigers", "co_bought": 2 }
  ]
}
```

Ties on co_bought=4 are ordered by ascending productID (21, 40, 60, 71) — the tool must implement this tie-break.

---

## GT 1.4.1 — customer_history

`customer_history(customer_key="ALFKI")` — Alfreds Futterkiste, Germany. 6 orders, all shipping to Germany, sorted by order_date ascending. Per-order totals via the revenue rule; unusable_lines = 0 in every order.

```json
{
  "status": "ok",
  "customer": { "label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "country": "Germany" },
  "orders": [
    { "order_key": "10643", "order_date": "1997-08-25 00:00:00.000", "total": 1086.0, "ship_country": "Germany" },
    { "order_key": "10692", "order_date": "1997-10-03 00:00:00.000", "total": 878.0, "ship_country": "Germany" },
    { "order_key": "10702", "order_date": "1997-10-13 00:00:00.000", "total": 330.0, "ship_country": "Germany" },
    { "order_key": "10835", "order_date": "1998-01-15 00:00:00.000", "total": 851.0, "ship_country": "Germany" },
    { "order_key": "10952", "order_date": "1998-03-16 00:00:00.000", "total": 491.2, "ship_country": "Germany" },
    { "order_key": "11011", "order_date": "1998-04-09 00:00:00.000", "total": 960.0, "ship_country": "Germany" }
  ]
}
```

---

## GT 1.5 — aggregate

### 1.5.1 revenue by supplier country

Ordered by metric_value descending. Cross-check: sum of the 21 groups = grand total 1,354,458.59 to the cent.

```json
{
  "status": "ok",
  "groups": [
    { "group_value": "Germany", "metric_value": 211540.09 },
    { "group_value": "75004", "metric_value": 163135.0 },
    { "group_value": "USA", "metric_value": 128844.15 },
    { "group_value": "74000", "metric_value": 126582.0 },
    { "group_value": "3058", "metric_value": 115386.05 },
    { "group_value": "Canada", "metric_value": 90899.7 },
    { "group_value": "2042", "metric_value": 69636.6 },
    { "group_value": "84100", "metric_value": 52929.0 },
    { "group_value": "48100", "metric_value": 51082.5 },
    { "group_value": "Japan", "metric_value": 49211.5 },
    { "group_value": "M14 GSD", "metric_value": 48793.8 },
    { "group_value": "Norway", "metric_value": 46897.2 },
    { "group_value": "0512", "metric_value": 44935.8 },
    { "group_value": "UK", "metric_value": 35916.8 },
    { "group_value": "Sweden", "metric_value": 33862.4 },
    { "group_value": "Finland", "metric_value": 29804.0 },
    { "group_value": "Spain", "metric_value": 26768.8 },
    { "group_value": "Denmark", "metric_value": 10884.5 },
    { "group_value": "71300", "metric_value": 6664.75 },
    { "group_value": "Netherlands", "metric_value": 5901.35 },
    { "group_value": "Brazil", "metric_value": 4782.6 }
  ],
  "n_groups": 21
}
```

### 1.5.2 product count by category

Ordered by group_value (categoryID) ascending; 8 groups summing to 77 (matches the PART_OF edge count).

```json
{
  "status": "ok",
  "groups": [
    { "group_value": "1", "metric_value": 12 },
    { "group_value": "2", "metric_value": 12 },
    { "group_value": "3", "metric_value": 13 },
    { "group_value": "4", "metric_value": 10 },
    { "group_value": "5", "metric_value": 7 },
    { "group_value": "6", "metric_value": 6 },
    { "group_value": "7", "metric_value": 5 },
    { "group_value": "8", "metric_value": 12 }
  ],
  "n_groups": 8
}
```

### 1.5.3 invalid group_by

```json
{
  "status": "invalid",
  "groups": [],
  "n_groups": 0
}
```

`invalid_property` is guaranteed absent from the Supplier property list (see whitelist in Contract Notes). If the contract specifies a leaner error shape (e.g. `{status, reason}`), pin it once — the unit test asserts the exact dict.

### 1.5.4 filtered, country=UK

```json
{
  "status": "ok",
  "groups": [
    { "group_value": "UK", "metric_value": 35916.8 }
  ],
  "n_groups": 1
}
```

Mutual consistency: UK total = GT 1.2.1's Exotic Liquids figure to the cent (UK has exactly one revenue-bearing supplier). If either test fails while the other passes, the traversal or filter diverged, not the data.

---

## Verification Chain Summary

The revenue rule is confirmed three independent ways: impact_analysis (35,916.80, recomputed from 91 raw lines), aggregate UK filter (35,916.80), and aggregate grand total (1,354,458.59 = sum of groups). Counts confirmed against the edge inventory (77 products via PART_OF, 830 orders via PURCHASED/SHIPS/SOLD).
# PROJECT.md — Build Contract

Build contract for the Northwind agentic knowledge-graph demo. This file and SCHEMA.md are authoritative: read both before writing code. SCHEMA.md is the data contract (labels, keys, relationship types, the revenue rule); this file is the system contract (architecture, state, tools, rubric, run-log, schedule). Where a detail is not fixed here, it is the implementer's choice.

## 1. Goal and audience

A demo application that educates two audiences on an agentic system interacting with a knowledge graph, with explainability built in:

- Executives: one "wow" moment — a supplier-failure impact question answered with a live-drawn evidence subgraph and three aggregate numbers (products, orders, revenue at risk).
- Engineers: an explainability deep-dive — the same question answered via an exploratory Cypher tool, with the trace drawer open showing a failed validation, the retry, and the confidence floor dropping.

Non-goals: data ingestion, constructed semantic layers, embeddings, write access to the graph. The graph is ground truth; read-only is an invariant.

## 2. Architecture

The agent is a LangGraph graph with four nodes:

```
classify → agent (ReAct loop) ↔ tools → synthesize
                        └→ degrade (on step-budget exhaustion)
```

- **classify**: small LLM. Routes to `agent` | `chitchat` | `refusal`. Chitchat answers directly; refusal returns a no-evidence answer.
- **agent**: ReAct loop, MAX_STEPS=8, all six tools bound. Emits tool calls; terminates by producing a final answer or exhausting the budget.
- **tools**: dispatches one tool call, times it, appends exactly one ToolCallRecord to the trace, returns the result as a tool message.
- **synthesize**: produces the answer from tool results — inline citations, the rubric-computed confidence with rationale string.
- **degrade**: reached when the loop exhausts MAX_STEPS. Answers with an explicit truncation disclosure; confidence hard-capped at 0.4; `error` records the reason.

Control-flow invariants: MAX_STEPS=8; every executed tool call appends a ToolCallRecord (no silent calls); budget exhaustion always routes to degrade, never to synthesize.

## 3. State

```python
class ToolCallRecord(TypedDict):
    step: int                # 1-based loop iteration
    tool_name: str
    args: dict
    mode: str                 # "curated" | "exploratory" | "retrieval"
    status: str               # ok | empty | invalid | retry_ok | retry_failed
    result_rows: int
    cypher: str | None        # populated for run_readonly_cypher
    latency_ms: int
    retry_count: int          # 0 or 1 — invariant: never exceeds 1

class Citation(TypedDict):
    label: str                # node label per SCHEMA.md
    key: str                   # the label's key property value — label+key uniquely identifies the node
    name: str                  # display name for inline answer text

class AgentState(TypedDict):
    question: str
    route: str                # "agent" | "chitchat" | "refusal"
    messages: Annotated[list, add_messages]   # ONLY field with a reducer
    trace: list[ToolCallRecord]
    answer: str
    citations: list[Citation]
    confidence: float
    confidence_rationale: str
    loop_count: int
    error: str | None
```

Rules: only `messages` merges (add_messages); every other field is last-write-wins with one owning node. Citations are synthesized from what the final answer actually claims — not the union of tool results. No claim without a citation; no citation without a node.

## 4. Tools

General rules for all tools: inputs are str / str | None / enums only. Outputs are dicts containing `status` plus a typed payload. All tools are read-only. Each tool is tagged with a mode at registration; the mode is a rubric input and must never be assigned dynamically.

### 4.1 lookup_entity

**Signature:** `lookup_entity(name: str, label: str | None = None) -> dict`
**Mode:** retrieval (rubric-neutral)
**Statuses:** ok | empty | invalid

**Semantics.** Resolves a natural-language mention to graph nodes. `label`: optional, one of the nine labels in SCHEMA.md; if omitted all labels are searched; an invalid label value returns status "invalid". With a label supplied, an input equal to a node's canonical key is also resolved by exact key after exact display-name matching and before contains/fuzzy name matching. Key inputs and display names use the same output payload.

**Output schema.** `{ status, query_name, matches: [{ label, key, name, match, properties }] }` — `label + key` is the canonical node handle consumed by all other tools and by citations; `match` ∈ {"exact", "contains", "fuzzy"}; matches ordered best-first, capped at 10.

**Invariants.** (1) Fixed cascade: exact display name → exact canonical key when `label` is supplied → case-insensitive contains → fuzzy; the `match` field reports `exact` for either exact name or key resolution and otherwise reports the name tier used. (2) Empty is normal: status "empty", matches [], no invented matches. (3) Read-only.

**NOT contractual:** the fuzzy algorithm, the per-label property subset, the Cypher of each cascade stage.

**Example.** Question mentions "Exotic Liquids". Call: `lookup_entity(name="Exotic Liquids", label="Supplier")` →

```json
{ "status": "ok", "query_name": "Exotic Liquids",
  "matches": [ { "label": "Supplier", "key": "1", "name": "Exotic Liquids",
                 "match": "exact", "properties": { "country": "UK" } } ] }
```

The agent then passes `matches[0].label + .key` to impact_analysis.

### 4.2 impact_analysis

**Signature:** `impact_analysis(entity_key: str, entity_label: str, direction: str = "out", depth: int = 3) -> dict`
**Mode:** curated
**Statuses:** ok | empty | invalid

**Semantics.** From one anchor node, everything affected by its failure or removal. One parameterized traversal covers supplier→products→orders→customers, product→orders→customers, customer→orders→products. `direction` ∈ {"out", "in"}; `depth` caps the traversal (default 3).

**Output schema.** `{ status, anchor: {label, key, name}, subgraph: {nodes: [...], edges: [...]}, aggregates: {products_affected, orders_affected, revenue_at_risk, unusable_lines} }` — the subgraph is the GUI's evidence panel input; the aggregates are the exec-facing numbers.

**Invariants.** (1) Revenue uses the SCHEMA.md rule: `coalesce(line.unitPrice, p.unitPrice) * line.quantity`; null-quantity lines are counted in `unusable_lines`, never silently dropped. (2) The dual output (subgraph + aggregates) always both present. (3) Read-only.

**NOT contractual:** the exact Cypher per anchor label, the node property subset carried in `subgraph.nodes`.

**Example.** "If Exotic Liquids stops delivering, what is at risk?" Call: `impact_analysis(entity_key="Exotic Liquids", entity_label="Supplier", direction="out", depth=3)` →

```json
{ "status": "ok",
  "anchor": { "label": "Supplier", "key": "Exotic Liquids", "name": "Exotic Liquids" },
  "subgraph": { "nodes": [ { "label": "Product", "key": "Chai", "name": "Chai" }, "... 40+ nodes" ],
                "edges": [ { "type": "SUPPLIES", "from": "Exotic Liquids", "to": "Chai" }, "..." ] },
  "aggregates": { "products_affected": 3, "orders_affected": 87,
                  "revenue_at_risk": 24000.0, "unusable_lines": 0 } }
```

`subgraph` feeds the agraph panel; `aggregates` are the three exec-facing numbers. (Values illustrative — real ones come from the live instance and are verified in unit tests.)

### 4.3 co_purchase

**Signature:** `co_purchase(product_key: str) -> dict`
**Mode:** curated
**Statuses:** ok | empty | invalid

**Semantics.** Given a product, the products sharing orders with it, ranked by co-occurrence.

**Output schema.** `{ status, product: {label, key, name}, recommendations: [{ label, key, name, co_bought }] }` — ordered by co_bought descending, capped at 10.

**Invariants.** (1) Counts distinct shared orders. (2) Excludes the anchor product. (3) Read-only.

**NOT contractual:** the cap value beyond "10 max", tie-breaking order.

**Example.** "Customers who bought Chai also bought what?" Call: `co_purchase(product_key="Chai")` →

```json
{ "status": "ok",
  "product": { "label": "Product", "key": "Chai", "name": "Chai" },
  "recommendations": [
    { "label": "Product", "key": "Chang", "name": "Chang", "co_bought": 12 },
    { "label": "Product", "key": "Aniseed Syrup", "name": "Aniseed Syrup", "co_bought": 7 } ] }
```

### 4.4 customer_history

**Signature:** `customer_history(customer_key: str) -> dict`
**Mode:** curated
**Statuses:** ok | empty | invalid

**Semantics.** A customer's orders as a dated flow with per-order totals.

**Output schema.** `{ status, customer: {label, key, name}, orders: [{ order_key, order_date, total, ship_country }] }` — ordered by order_date ascending.

**Invariants.** (1) Per-order totals use the revenue rule. (2) Dates are returned as raw strings per SCHEMA.md; churn/gap analysis is computed in Python post-processing, never in Cypher date functions. (3) Read-only.

**NOT contractual:** the gap-detection parameters (window size, threshold) — the tool returns facts; pattern derivation lives in the agent's synthesis, not the tool.

**Example.** "Has ALFKI's ordering pattern changed?" Call: `customer_history(customer_key="ALFKI")` →

```json
{ "status": "ok",
  "customer": { "label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste" },
  "orders": [ { "order_key": "10643", "order_date": "2012-08-25 0:00:00", "total": 814.5, "ship_country": "Germany" },
              { "order_key": "10835", "order_date": "2013-01-15 0:00:00", "total": 412.0, "ship_country": "Germany" } ] }
```

The synthesize node (not the tool) computes the ~5-month gap pattern from these dates in Python.

### 4.5 run_readonly_cypher

**Signature:** `run_readonly_cypher(query: str) -> dict`
**Mode:** exploratory
**Statuses:** ok | empty | invalid | retry_ok | retry_failed

**Semantics.** The agent writes Cypher itself. Pipeline: read-only guard → EXPLAIN validation → execute → return rows. Exactly ONE retry on validation or execution failure; the retry receives the error message.

**Output schema.** Every response uses this envelope:

```json
{
  "status": "ok",
  "query": "the original query supplied to the tool",
  "attempts": [
    { "cypher": "attempted query", "valid": true, "error": null }
  ],
  "rows": [
    {
      "values": { "customer_count": 1 },
      "evidence": {
        "nodes": [
          { "label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "properties": {} }
        ],
        "edges": []
      }
    }
  ],
  "error": null
}
```

`rows` is always a list of normalized row objects. `values` preserves the returned Cypher columns and their scalar or nested values. A returned node is converted to the canonical `{label, key, name, properties}` object; a returned relationship is converted to `{type, from: {label, key}, to: {label, key}, properties}`. A returned path is represented in its value as `{nodes: [...], edges: [...]}` using those same canonical objects. `evidence.nodes` and `evidence.edges` collect and deduplicate graph entities found anywhere in that row's values. This supports scalar-only rows, node or relationship rows, paths/subgraphs, and mixtures of scalars and graph entities without changing the row envelope. Scalar-only results have empty evidence arrays. For a scalar metric or count, the query should also return the contributing nodes or relationships needed to support the claim; the agent may make a graph claim only when it has adequate node-backed evidence under §3.

`query` always preserves the original input. `attempts` records each validation/EXPLAIN/execution attempt, including the error for each failed attempt. `error` is `null` for `ok`, `retry_ok`, and `empty`; it contains the terminal failure reason for `invalid` and `retry_failed`. A successful query with zero records is `empty`, with `rows: []` and no error. A query rejected before execution or still failing after its one retry has `rows: []` and a non-empty `error`. `attempts` is the trace drawer's source for the failure-and-recovery details.

**Invariants.** (1) Read-only enforcement: reject any statement that is not a single READ query. (2) `retry_count ≤ 1` — after one failed retry, status is retry_failed and no further attempts. (3) Empty result is a legitimate outcome (status "empty"), never an error; it is distinct from invalid or retry_failed. (4) The schema available to the generator is extracted from SCHEMA.md. (5) Every graph entity in the returned values is normalized and included in that row's evidence, deduplicated by canonical node identity or edge type/endpoints/properties.

**NOT contractual:** the prompt engineering of the generator, the exact validation regexes (EXPLAIN is the gate), and the internal normalization implementation.

**Example.** Agent wants revenue split by product for a supplier, writes invalid Cypher (wrong relationship direction), retries. The corrected query returns both scalar metrics and their graph evidence: `run_readonly_cypher(query="MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[l:ORDERS]-(o:Order) WHERE s.companyName = 'Exotic Liquids' RETURN s AS supplier, p AS product, sum(l.quantity * l.unitPrice) AS revenue, collect(DISTINCT o) AS evidence_orders")` →

```json
{ "status": "retry_ok",
  "query": "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[l:ORDERS]-(o:Order) WHERE s.companyName = 'Exotic Liquids' RETURN s AS supplier, p AS product, sum(l.quantity * l.unitPrice) AS revenue, collect(DISTINCT o) AS evidence_orders",
  "attempts": [
    { "cypher": "MATCH (s:Supplier)-[:ORDERS]->(p:Product) ...", "valid": false, "error": "Relationship type ORDERS does not exist from Supplier" },
    { "cypher": "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[l:ORDERS]-(o:Order) WHERE s.companyName = 'Exotic Liquids' ...", "valid": true, "error": null } ],
  "rows": [
    { "values": {
        "supplier": { "label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": {} },
        "product": { "label": "Product", "key": "1", "name": "Chai", "properties": {} },
        "revenue": 12000.0,
        "evidence_orders": [ { "label": "Order", "key": "10643", "name": "10643", "properties": {} } ] },
      "evidence": { "nodes": [
          { "label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": {} },
          { "label": "Product", "key": "1", "name": "Chai", "properties": {} },
          { "label": "Order", "key": "10643", "name": "10643", "properties": {} } ],
        "edges": [] } }
  ],
  "error": null }
```

Note the exploratory tool takes a raw string — the agent cannot bind Cypher parameters, so literals are inlined (parameter injection is a curated-tool privilege; the read-only guard and SCHEMA.md whitelist are the safety net). `attempts` is the trace drawer's display of the failure-and-recovery story, and the rubric caps this run at 0.5.

### 4.6 aggregate

**Signature:** `aggregate(label: str, group_by: str, metric: str, where: str | None = None) -> dict`
**Mode:** curated
**Statuses:** ok | empty | invalid

**Semantics.** Tabular executive questions: "revenue by country", "top categories by order volume". A parameterized query builder over fixed join patterns — NOT a text-to-Cypher backdoor. `label` ∈ the nine labels; `group_by` ∈ a whitelisted property or joined label; `metric` ∈ {"count", "sum_revenue", "avg_revenue"}; `where` is a whitelisted equality filter.

**Output schema.** `{ status, groups: [{ group_value, metric_value, evidence: [{ label, key, name }] }], n_groups }` — capped at 20 groups. `evidence` contains the canonical handles of every anchor-label node contributing to that group, deduplicated by label and key. This lets synthesis cite aggregate claims without inventing nodes.

**Invariants.** (1) Fixed join patterns per label (curated traversals, parameterized projection only). (2) Property whitelist; anything else returns status "invalid". (3) sum_revenue uses the revenue rule. (4) Read-only.

**NOT contractual:** the internal query-template representation.

**Example.** "Revenue by supplier country" Call: `aggregate(label="Supplier", group_by="country", metric="sum_revenue")` →

```json
{ "status": "ok",
  "groups": [ { "group_value": "USA", "metric_value": 58000.0,
                "evidence": [{ "label": "Supplier", "key": "2", "name": "New Orleans Cajun Delights" }] },
              { "group_value": "UK", "metric_value": 24000.0,
                "evidence": [{ "label": "Supplier", "key": "1", "name": "Exotic Liquids" }] } ],
  "n_groups": 2 }
```

The fixed join pattern here is Supplier→SUPPLIES→Product←ORDERS←Order, with the revenue rule applied per line.

## 5. Confidence rubric

Confidence is a deterministic function of the trace, computed in code — never an LLM self-assessment. Rule: min of caps over evidence-contributing tool calls. No multiplication; only the worst event sets the floor.

| Call profile | Cap |
|---|---|
| curated, status ok | 0.9 |
| exploratory, status ok (first try) | 0.6 |
| exploratory, status retry_ok | 0.5 |
| exploratory, retry_failed OR empty-then-synthesized | 0.3 |
| retrieval (lookup_entity) | neutral — never sets the floor |
| degrade path (budget exhausted) | hard cap 0.4, overrides min, truncation disclosure mandatory |

The rationale string names the call that set the floor and why. Example: "floor 0.5 set by step 3 (run_readonly_cypher, retry_ok); curated tools succeeded."

Contract statement: the anchors 0.9/0.6/0.5/0.3/0.4 are a fixed scoring contract, not a calibration. The demo presents the rubric as auditable and reproducible; calibrating the numbers against measured accuracy is future work (pillar 3 of the research program). The rubric table and rationale format appear in the trace drawer verbatim.

## 6. Run-log (JSONL)

One line per run, appended:

```json
{ "ts": "...", "question": "...", "route": "agent", "trace": [ToolCallRecord, ...],
  "hops": 3, "answer": "...", "citations": [...], "confidence": 0.9,
  "confidence_rationale": "...", "latency_ms_total": 4210 }
```

The run-log is simultaneously: the metrics source (tool distribution, curated/exploratory ratio, retry rate, empty rate, latency), the pillar-3 evaluation dataset, and the explainability artifact. A small analyzer script reads it and produces the closing-slide stats. The log is append-only; no run is ever edited or deleted.

## 7. GUI (Streamlit)

Three panels:

- **Chat**: st.chat_message, history in session_state, driver and compiled graph in st.cache_resource.
- **Trace drawer** (expander): route badge, one row per ToolCallRecord (tool, mode, status, Cypher for exploratory, latency, retries), confidence + rationale + the rubric rule that fired.
- **Graph panel**: streamlit-agraph rendering the graph evidence from the last tool call; colors per label; cited nodes enlarged; node click → property card (name + properties). For curated tools, graph evidence comes from their `subgraph`. For `run_readonly_cypher`, the panel combines `evidence.nodes` and `evidence.edges` across the last tool result's normalized rows.

Panel contracts: the drawer reads `trace` and `confidence_rationale` verbatim from state; the graph panel renders only graph evidence from the last tool call (it is evidence, not an explorer); cited nodes are enlarged exactly per `citations`.

## 8. Tech constraints

Python managed with uv. Credentials in `.env` (AuraDB URI `neo4j+s://...`), never in code. Dependencies: langgraph, neo4j driver, streamlit, streamlit-agraph. Mistral models: small for classify, large for agent loop and synthesis. Read-only enforcement at the driver level as defense in depth.

## 9. Build order and gates

1. Curated tools + unit tests against hand-verified answers (impact_analysis, lookup_entity, co_purchase, customer_history, aggregate)
2. run_readonly_cypher + agent graph (state, classify, loop, tools, synthesize, degrade, rubric, run-log)
3. **Gate: agent works end-to-end in CLI on the scripted questions.** If this holds, the demo cannot fail.
4. Streamlit panels
5. Scripted question set (wow impact, exploratory-with-retry, co-purchase, churn, one refusal/degrade) + run-log analyzer
6. **Final gate: full rehearsal without touching code.**

Fallback if short on time: chat + trace drawer + one scripted wow question. Stretch items in that order: exploratory tool, churn beat.

Prompt iteration is timeboxed: prefer improving tool descriptions over prompt magic.
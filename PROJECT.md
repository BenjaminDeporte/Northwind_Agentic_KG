# PROJECT.md — Build Contract

Build contract for the Northwind agentic knowledge-graph demo. This file and SCHEMA.md are authoritative: read both before writing code. SCHEMA.md is the data contract (labels, keys, relationship types, the revenue rule); this file is the system contract (architecture, state, tools, rubric, run-log, schedule). Where a detail is not fixed here, it is the implementer's choice.

## 1. Goal and audience

A demo application that educates two audiences on an agentic system interacting with a knowledge graph, with explainability built in:

- Executives: one "wow" moment — a supplier-failure impact question answered with a live-drawn evidence subgraph and three aggregate numbers (products, orders, revenue at risk).
- Engineers: an explainability deep-dive — the same question answered via an exploratory Cypher tool, with the trace drawer open showing a failed validation, the retry, and the confidence floor dropping.

Non-goals: data ingestion, constructed semantic layers, embeddings, write access to the graph. The graph is ground truth; read-only is an invariant.

## 2. Architecture

The agent is a LangGraph graph with a bounded ReAct loop and a draft-validation path:

```
classify → agent (ReAct loop) → tools ── adequate evidence ─→ synthesize draft → consistency_check ─→ END
             ↑       ↖──────────── incomplete candidate ───────────────────────────────────┘
             └──────── inadequate/empty tool result ────────────────────────┘
             └→ degrade (on step-budget exhaustion)
```

- **classify**: small LLM. Routes to `agent` | `chitchat` | `refusal`. Chitchat answers directly; refusal returns a no-evidence answer.
- **agent**: ReAct loop, MAX_STEPS=8, all six tools bound. Emits tool calls or a `FINAL:` signal requesting a draft; it does not itself establish that the answer is complete. If the model omits `FINAL:` after a successful tool result and emits no tool call, the graph treats that no-tool turn as a candidate handoff to synthesis; consistency checking still decides whether it answers the question.
- **tools**: dispatches one tool call, times it, appends exactly one ToolCallRecord to the trace, returns the result as a tool message. A successful result with adequate associated node evidence proceeds directly to synthesis; empty or evidence-inadequate results return to the agent for recovery or another approach.
- **synthesize**: produces a candidate answer and candidate citations from tool results.
- **consistency_check**: checks whether the candidate covers the question's requested entities, operation, and constraints, and whether its claims are supported by the associated tool evidence. A passing candidate is committed as the final answer with its citations and rubric-computed confidence. A failing candidate returns specific feedback to the agent for another bounded turn.
- **degrade**: reached when the loop exhausts MAX_STEPS. Answers with an explicit truncation disclosure; confidence hard-capped at 0.4; `error` records the reason.

Control-flow invariants: MAX_STEPS=8; every executed tool call appends a ToolCallRecord (no silent calls); budget exhaustion always routes to degrade, never to synthesize or consistency checking. An evidence-adequate tool result can reach synthesis without spending another agent turn; consistency checking may still return an incomplete candidate to the agent within the remaining shared budget. A consistency retry preserves `loop_count`; it never starts a fresh budget. A rejected candidate is not committed to `answer` or the user-visible conversation as final. Only a passing candidate is committed with its citations and confidence. The existing one-call evidence-recovery limit remains in force; consistency retries do not permit repeated recovery calls for the same unsupported claim.


### Authority and runtime projections

`SCHEMA.md` is the single source of truth for graph labels, keys, properties, relationships, and graph-specific facts. `src/agents/schema_prompt.py` mechanically projects that file into schema context for the agent and Cypher-repair prompts; it is generated context, not a second schema authority. Prompt generation failure must surface as an error rather than substitute a partial hardcoded graph schema.

`PROJECT.md` is the normative source for application architecture, tool signatures and result contracts, evidence policy, and runtime behavior. `AGENT_SYSTEM_PROMPT_TEMPLATE` in `src/agents/llm.py` is model-facing guidance derived from those requirements; it helps the model choose tools and formulate queries but does not enforce the contract. The model chooses tool calls and query strategy. `src/neo4j/result_contracts.py` is the executable mirror that validates tool payloads; `agent_step` enforces loop and recovery bounds; `synthesize` constructs a candidate answer and citations from tool messages; `consistency_check` validates and promotes an adequate candidate. Keep those implementations aligned with this contract. `ToolCallRecord` records call metadata in `trace`; the full structured tool result is carried separately in a LangGraph `ToolMessage` in `messages`.

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
    draft_answer: str | None
    draft_citations: list[Citation]
    consistency_status: str       # "pending" | "pass" | "revise"
    consistency_feedback: str | None
    answer: str
    citations: list[Citation]
    confidence: float
    confidence_rationale: str
    loop_count: int
    error: str | None
```

Rules: only `messages` merges (add_messages); every other field is last-write-wins with one owning node. `synthesize` owns `draft_answer` and `draft_citations`; the initial state supplies `consistency_status="pending"`; `consistency_check` owns `consistency_status`, `consistency_feedback`, and the accepted `answer`, `citations`, `confidence`, and `confidence_rationale`; only a passing check commits the draft to those final fields. Agent turns increment `loop_count`; consistency retries preserve it, and the shared MAX_STEPS budget applies. Citations are synthesized from the final answer's claims and their associated tool evidence, not from the union of tool results. For computed metrics, the tool result is the numeric source and a small number of relevant graph handles identifies its scope; citations do not imply that every contributing record is displayed. No graph claim without a relevant node citation; no citation without a returned node.

## 4. Tools

General rules for all tools: inputs are str / str | None / enums only. Results are structured dictionaries with top-level `status`, nullable `error`, and the tool-specific payload defined below; do not return prose in place of the payload. All tools are read-only. Each tool is tagged with a mode at registration; the mode is a rubric input and must never be assigned dynamically.

**Common status and error contract (all six tools).** `ok` means the operation succeeded and returned one or more results. `empty` means it succeeded but found no matching result; it is a normal outcome, not a query failure. `invalid` means the request was invalid or the operation failed without a successful result. `retry_ok` and `retry_failed` are reserved for `run_readonly_cypher`: the single repair attempt succeeded or also failed, respectively. Every result includes `error`: it is `null` for `ok`, `empty`, and `retry_ok`; it is a useful non-empty string for `invalid` and `retry_failed`. On every status, retain the tool-specific payload with the documented empty or null representation when no result is available. Do not infer failure from an empty payload or infer success from a non-empty one; use `status`.

**Evidence shape and association.** A node handle is `{label, key, name, properties}`. An edge handle is `{type, from: {label, key}, to: {label, key}, properties}`. Place evidence beside the result item it supports: a lookup match, impact result, recommendation, customer order, aggregate group, or exploratory row. Each item's metric/value and evidence must stay associated. Do not flatten handles from unrelated results into a result-wide evidence list or use one item's evidence to support another item's claim.

**Evidence adequacy and demo scope.** Tool-computed scalar values (counts, totals, rankings) are sourced from the tool result. Associate each computed value with its relevant entity, group, or anchor. For a claim about a specific graph edge, the tool payload includes that edge and its endpoint node handles. For a derived relationship metric such as co-purchase counts, associate the computed value with the relevant entity pair; do not return every underlying order or relationship. Keep full graph data only where a tool's purpose requires it, such as the impact-analysis subgraph; citation evidence for a computed claim remains a small representative sample. Inline citations are node citations under `Citation` in §3: use at most three relevant node citations per computed claim. For a specific-edge claim, cite its relevant endpoint node or nodes; the returned edge remains part of the supporting tool evidence. For derived relationship metrics, cite the associated entity handles. Handles identify the claim's graph scope and do not independently prove the numeric calculation. Representative sample nodes must not be treated as a metric's scope anchor. A count is scoped to an entity only when that entity is explicitly returned as its own value in the associated result row. A scalar-only result with no relevant graph handle cannot support a graph answer.

**Bounded evidence recovery.** If an otherwise successful result lacks adequate relevant evidence, the agent may make at most one additional evidence-recovery tool call, using a suitable lookup or query. For a whole-graph node count returned as a scalar without node evidence, the agent deterministically retries the count with up to three representative node handles. This is one extra tool call for the claim, independent of `run_readonly_cypher`'s single internal repair retry. If the recovery result still lacks adequate evidence, synthesis must state that the result could not be supported; it must not state the unsupported graph claim as fact or keep retrying until `MAX_STEPS` is exhausted. A successful, adequately evidenced result needs no recovery call.

The examples below are abbreviated for readability: they may omit `error: null` and repeatable evidence fields, which are required by the schemas above.

### 4.1 lookup_entity

**Signature:** `lookup_entity(name: str, label: str | None = None) -> dict`
**Mode:** retrieval (rubric-neutral)
**Statuses:** ok | empty | invalid

**Semantics.** Resolves a natural-language mention to graph nodes. `label`: optional, one of the nine labels in SCHEMA.md; if omitted all labels are searched; an invalid label value returns status "invalid". With a label supplied, an input equal to a node's canonical key is also resolved by exact key after exact display-name matching and before contains/fuzzy name matching. Key inputs and display names use the same output payload.

**Output schema.** { status, error, query_name, matches: [{ node: {label, key, name, properties}, match, evidence: {nodes: [node], edges: []} }] } — matches are ordered best-first and capped at 10. Each match carries its canonical node and self-associated evidence.

**Invariants.** (1) Fixed cascade: exact display name → exact canonical key when `label` is supplied → case-insensitive contains → fuzzy; the `match` field reports `exact` for either exact name or key resolution and otherwise reports the name tier used. (2) Empty is normal: status "empty", matches [], no invented matches. (3) Read-only.

**NOT contractual:** the fuzzy algorithm, the per-label property subset, the Cypher of each cascade stage.

**Example.** Question mentions "Exotic Liquids". Call: `lookup_entity(name="Exotic Liquids", label="Supplier")` →

```json
{ "status": "ok", "error": null, "query_name": "Exotic Liquids",
  "matches": [ { "node": { "label": "Supplier", "key": "1", "name": "Exotic Liquids",
                              "properties": { "country": "UK" } },
                 "match": "exact",
                 "evidence": { "nodes": [{ "label": "Supplier", "key": "1", "name": "Exotic Liquids",
                                            "properties": { "country": "UK" } }], "edges": [] } } ] }
```

The agent then passes `matches[0].node.label` and `matches[0].node.key` to `impact_analysis`.

### 4.2 impact_analysis

**Signature:** `impact_analysis(entity_key: str, entity_label: str, direction: str = "out", depth: int = 3) -> dict`
**Mode:** curated
**Statuses:** ok | empty | invalid

**Semantics.** From one anchor node, everything affected by its failure or removal. One parameterized traversal covers supplier→products→orders→customers, product→orders→customers, customer→orders→products. `direction` ∈ {"out", "in"}; `depth` caps the traversal (default 3).

**Output schema.** { status, error, anchor: {label, key, name, properties}, subgraph: {nodes, edges}, aggregates: {products_affected, orders_affected, revenue_at_risk, unusable_lines}, evidence: {nodes, edges} }. The aggregate values are associated with the anchor and the returned impact evidence; evidence is bounded to the anchor and at most two additional relevant nodes/edges.

**Invariants.** (1) Revenue uses the SCHEMA.md rule: `coalesce(line.unitPrice, p.unitPrice) * line.quantity`; null-quantity lines are counted in `unusable_lines`, never silently dropped. (2) The dual output (subgraph + aggregates) always both present. (3) Read-only.

**NOT contractual:** the exact Cypher per anchor label, the node property subset carried in `subgraph.nodes`.

**Example.** "If Exotic Liquids stops delivering, what is at risk?" Call: `impact_analysis(entity_key="1", entity_label="Supplier", direction="out", depth=3)` →

```json
{ "status": "ok", "error": null,
  "anchor": { "label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": { "country": "UK" } },
  "subgraph": { "nodes": [{ "label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": { "country": "UK" } },
                           { "label": "Product", "key": "1", "name": "Chai", "properties": { "unitPrice": 18.0 } }],
                "edges": [{ "type": "SUPPLIES", "from": { "label": "Supplier", "key": "1" }, "to": { "label": "Product", "key": "1" }, "properties": {} }] },
  "aggregates": { "products_affected": 3, "orders_affected": 87,
                  "revenue_at_risk": 24000.0, "unusable_lines": 0 },
  "evidence": { "nodes": [{ "label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": { "country": "UK" } },
                            { "label": "Product", "key": "1", "name": "Chai", "properties": { "unitPrice": 18.0 } }],
                "edges": [{ "type": "SUPPLIES", "from": { "label": "Supplier", "key": "1" }, "to": { "label": "Product", "key": "1" }, "properties": {} }] } }
```

`subgraph` feeds the agraph panel; `aggregates` are the three exec-facing numbers. (Values illustrative — real ones come from the live instance and are verified in unit tests.)

### 4.3 co_purchase

**Signature:** `co_purchase(product_key: str) -> dict`
**Mode:** curated
**Statuses:** ok | empty | invalid

**Semantics.** Given a product, the products sharing orders with it, ranked by co-occurrence.

**Output schema.** { status, error, product: {label, key, name}, recommendations: [{product: {label, key, name}, co_bought, evidence: {nodes: [anchor_product, recommended_product], edges: []}}] } — ordered by co_bought descending, capped at 10. The computed count is associated with the product pair; shared-order records are not required.

**Invariants.** (1) Counts distinct shared orders. (2) Excludes the anchor product. (3) Read-only.

**NOT contractual:** the cap value beyond "10 max", tie-breaking order.

**Example.** "Customers who bought Chai also bought what?" Call: `co_purchase(product_key="1")` →

```json
{ "status": "ok", "error": null,
  "product": { "label": "Product", "key": "1", "name": "Chai" },
  "recommendations": [
    { "product": { "label": "Product", "key": "2", "name": "Chang" }, "co_bought": 12,
      "evidence": { "nodes": [ { "label": "Product", "key": "1", "name": "Chai", "properties": {} },
                                { "label": "Product", "key": "2", "name": "Chang", "properties": {} } ], "edges": [] } },
    { "product": { "label": "Product", "key": "3", "name": "Aniseed Syrup" }, "co_bought": 7,
      "evidence": { "nodes": [ { "label": "Product", "key": "1", "name": "Chai", "properties": {} },
                                { "label": "Product", "key": "3", "name": "Aniseed Syrup", "properties": {} } ], "edges": [] } } ] }
```

### 4.4 customer_history

**Signature:** `customer_history(customer_key: str) -> dict`
**Mode:** curated
**Statuses:** ok | empty | invalid

**Semantics.** A customer's orders as a dated flow with per-order totals. The tool returns the full matching order history; it does not impose a ten-order query limit. For ordinary history questions, synthesis may display the first ten evidenced orders and must disclose when it truncates. An explicit request for all/every order must display every returned evidenced order.

**Output schema.** { status, error, customer: {label, key, name}, orders: [{order: {label, key, name}, order_date, total, ship_country, evidence: {nodes: [customer, order], edges: [customer_order_edge]}}] } — ordered by order_date ascending. Each returned order and its computed values carry their own evidence association.

**Invariants.** (1) Per-order totals use the revenue rule. (2) Dates are returned as raw strings per SCHEMA.md; churn/gap analysis is computed in Python post-processing, never in Cypher date functions. (3) Read-only.

**NOT contractual:** the gap-detection parameters (window size, threshold) — the tool returns facts; pattern derivation lives in the agent's synthesis, not the tool.

**Example.** "Has ALFKI's ordering pattern changed?" Call: `customer_history(customer_key="ALFKI")` →

```json
{ "status": "ok", "error": null,
  "customer": { "label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste" },
  "orders": [ { "order": { "label": "Order", "key": "10643", "name": "10643" },
                "order_date": "1997-08-25 00:00:00.000", "total": 1086.0, "ship_country": "Germany",
                "evidence": { "nodes": [ { "label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "properties": {} },
                                          { "label": "Order", "key": "10643", "name": "10643", "properties": {} } ],
                              "edges": [ { "type": "PURCHASED", "from": { "label": "Customer", "key": "ALFKI" },
                                          "to": { "label": "Order", "key": "10643" }, "properties": {} } ] } } ] }
```

The synthesize node (not the tool) computes the largest gap from the complete returned order history, even when a shorter default display is used.

### 4.5 run_readonly_cypher

**Signature:** `run_readonly_cypher(query: str) -> dict`
**Mode:** exploratory
**Statuses:** ok | empty | invalid | retry_ok | retry_failed

**Semantics.** The agent writes Cypher itself. Pipeline: read-only guard → EXPLAIN validation → execute → return rows. Exactly ONE retry on validation or execution failure; the retry receives the error message.

**Output schema.** { status, error, query, attempts: [{cypher, valid, error}], rows: [{values, evidence: {nodes, edges}}] }. The original query and each attempt are retained; each row has independent values and normalized graph evidence.

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

`rows` is always a list of normalized row objects. `values` preserves the returned Cypher columns and their scalar or nested values. A returned node is converted to the canonical `{label, key, name, properties}` object; a returned relationship is converted to `{type, from: {label, key}, to: {label, key}, properties}`. A returned path is represented in its value as `{nodes: [...], edges: [...]}` using those same canonical objects. `evidence.nodes` and `evidence.edges` collect and deduplicate graph entities found anywhere in that row's values. The agent should return only relevant anchors or a bounded representative sample for computed claims instead of collecting all contributors. This supports scalar-only rows, node or relationship rows, paths/subgraphs, and mixtures of scalars and graph entities without changing the row envelope. Scalar-only results have empty evidence arrays. For a scalar metric or count, return the computed value with its relevant anchor or up to three representative nodes/edges. Do not collect every contributing record solely for citation. The metric is sourced from the query result; the returned handles identify its graph scope under the common evidence policy.

`query` always preserves the original input. `attempts` records each validation/EXPLAIN/execution attempt, including the error for each failed attempt. `error` is `null` for `ok`, `retry_ok`, and `empty`; it contains the terminal failure reason for `invalid` and `retry_failed`. A successful query with zero records is `empty`, with `rows: []` and no error. A query rejected before execution or still failing after its one retry has `rows: []` and a non-empty `error`. `attempts` is the trace drawer's source for the failure-and-recovery details.

**Invariants.** (1) Read-only enforcement: reject any statement that is not a single READ query. (2) `retry_count ≤ 1` — after one failed retry, status is retry_failed and no further attempts. (3) Empty result is a legitimate outcome (status "empty"), never an error; it is distinct from invalid or retry_failed. (4) The schema available to the generator is extracted from SCHEMA.md. (5) Every graph entity present in a returned value is normalized to its canonical form, and row evidence is deduplicated by canonical node identity or edge type/endpoints/properties. For computed claims, the generated query should return only a relevant anchor or bounded representative sample; do not collect every contributing record solely to create citation evidence.

**NOT contractual:** the prompt engineering of the generator, the exact validation regexes (EXPLAIN is the gate), and the internal normalization implementation.

**Example.** Agent wants revenue split by product for a supplier, writes invalid Cypher (wrong relationship direction), retries. The corrected query returns both scalar metrics and their graph evidence: `run_readonly_cypher(query="MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[l:ORDERS]-(o:Order) WHERE s.companyName = 'Exotic Liquids' RETURN s AS supplier, p AS product, sum(l.quantity * l.unitPrice) AS revenue, collect(DISTINCT o)[0..3] AS evidence_orders")` →

```json
{ "status": "retry_ok",
  "query": "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[l:ORDERS]-(o:Order) WHERE s.companyName = 'Exotic Liquids' RETURN s AS supplier, p AS product, sum(l.quantity * l.unitPrice) AS revenue, collect(DISTINCT o)[0..3] AS evidence_orders",
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

**Output schema.** { status, error, groups: [{group_value, metric_value, evidence: {nodes, edges}}], n_groups } — capped at 20 groups. Each group's metric is associated with at most three representative canonical handles from that group; return the computed group metric without collecting every contributing record.

**Invariants.** (1) Fixed join patterns per label (curated traversals, parameterized projection only). (2) Property whitelist; anything else returns status "invalid". (3) sum_revenue uses the revenue rule. (4) Read-only.

**NOT contractual:** the internal query-template representation.

**Example.** "Revenue by supplier country" Call: `aggregate(label="Supplier", group_by="country", metric="sum_revenue")` →

```json
{ "status": "ok", "error": null,
  "groups": [ { "group_value": "USA", "metric_value": 58000.0,
                "evidence": { "nodes": [{ "label": "Supplier", "key": "2", "name": "New Orleans Cajun Delights", "properties": {} }], "edges": [] } },
              { "group_value": "UK", "metric_value": 24000.0,
                "evidence": { "nodes": [{ "label": "Supplier", "key": "1", "name": "Exotic Liquids", "properties": {} }], "edges": [] } } ],
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

Three side-by-side panels use independent fixed-height, internally scrollable regions (450 px):

- **Chat**: `st.chat_message`, history in `session_state`, and the question input below its scrollable history. The history auto-scrolls as new messages arrive.
- **Traceable Explainability**: the parent heading uses the same heading level as Chat and Evidence Graph. Separate expandable Trace and Confidence subwindows show the route, one row per `ToolCallRecord` (tool, mode, status, Cypher for exploratory calls, latency, retries), confidence, rationale, and the rubric rule that fired.
- **Evidence Graph**: `streamlit-agraph` rendering the graph evidence from the last tool call; colors per label; cited nodes enlarged; node click → property card (name + properties). For curated tools, graph evidence comes from their `subgraph`. For `run_readonly_cypher`, the panel combines `evidence.nodes` and `evidence.edges` across the last tool result's normalized rows.

Panel contracts: the drawer reads `trace` and `confidence_rationale` verbatim from state; the graph panel renders only graph evidence from the last tool call (it is evidence, not an explorer); cited nodes are enlarged exactly per `citations`.

## 8. Tech constraints

Python managed with uv. Credentials in `.env` (AuraDB URI `neo4j+s://...` and `MISTRAL_API_KEY`), never in code. The Mistral API key authenticates the client; it does not select a model. Model selection is per chat request, so one key may be used with any model available to that key. Requests default to `mistral-large-latest` when no model name is supplied; classify explicitly selects `mistral-small-latest`, and the answer-consistency reviewer uses Mistral Large by default. Each factual candidate requiring semantic review adds one reviewer request. Callers may pass an API key directly, otherwise the client reads `MISTRAL_API_KEY` from the environment. Dependencies: langgraph, neo4j driver, streamlit (1.35 or newer for fixed-height scroll containers), streamlit-agraph. Read-only enforcement at the driver level as defense in depth.

## 9. Build order and gates

1. Curated tools + unit tests against hand-verified answers (impact_analysis, lookup_entity, co_purchase, customer_history, aggregate)
2. run_readonly_cypher + agent graph (state, classify, loop, tools, synthesize, consistency_check, degrade, rubric, run-log)
3. **Gate: agent works end-to-end in CLI on the scripted questions.** If this holds, the demo cannot fail.
4. Streamlit panels
5. Scripted question set (wow impact, exploratory-with-retry, co-purchase, churn, one refusal/degrade) + run-log analyzer
6. **Final gate: full rehearsal without touching code.**

Fallback if short on time: chat + trace drawer + one scripted wow question. Stretch items in that order: exploratory tool, churn beat.

Prompt iteration is timeboxed: prefer improving tool descriptions over prompt magic.
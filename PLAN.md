# PLAN.md — Implementation Plan

This document decomposes PROJECT.md Section 9 (Build Order and Gates) into concrete, actionable work items. It is the execution roadmap for the Northwind agentic knowledge-graph demo.

**Authoritative Contracts:**
- Data: `SCHEMA.md` (labels, keys, relationship types, revenue rule)
- System: `PROJECT.md` (architecture, state, tools, rubric, run-log, gates)

**Invariant:** No deviation from the above contracts. All tools are read-only. The graph is ground truth.

---

## Overview

The build follows the order in PROJECT.md §9, organized into **4 phases** with **2 gates**:

1. **Phase 1: Curated Tools + Unit Tests** — 5 tools, each with hand-verified ground truth from AuraDB
2. **Phase 2: Exploratory Tool + Agent Graph** — 1 tool + 5 nodes + rubric + run-log
3. **Gate 1: End-to-End CLI** — Agent must answer scripted questions without errors
4. **Phase 3: Streamlit GUI** — 3 panels (chat, trace drawer, graph)
5. **Phase 4: Scripted Questions + Analyzer** — Demo beats + metrics
6. **Gate 2: Full Rehearsal** — All scripted questions pass; no code changes

**Fallback:** Chat + trace drawer + one wow question (supplier impact). Stretch: exploratory tool, churn beat.

---

## File Structure

```
Northwind_Agentic_KG/
├── src/
│   ├── neo4j/
│   │   ├── client.py      # (exists) Neo4j driver
│   │   ├── queries.py     # (exists) Cypher utilities
│   │   ├── schema.py      # (exists) Schema extraction
│   │   └── tools.py       # NEW: 6 tools (lookup_entity, impact_analysis, co_purchase, customer_history, aggregate, run_readonly_cypher)
│   │
│   ├── agents/
│   │   ├── state.py       # NEW: ToolCallRecord, Citation, AgentState TypedDicts
│   │   ├── nodes.py       # NEW: classify, agent, tools, synthesize, degrade
│   │   ├── graph.py       # NEW: LangGraph graph definition
│   │   └── rubric.py      # NEW: compute_confidence function
│   │
│   ├── streamlit/
│   │   ├── app.py         # (exists) UPDATE: integrate panels
│   │   └── components/
│   │       ├── chat.py           # NEW: Chat panel
│   │       ├── trace_drawer.py   # NEW: Trace drawer panel
│   │       └── graph_panel.py    # NEW: Graph panel
│   │
│   └── utils/
│       ├── config.py      # (exists) Configuration
│       ├── logging.py     # (exists) Structured logging
│       └── runlog.py       # NEW: JSONL run-log appender
│
├── tests/
│   ├── test_lookup_entity.py
│   ├── test_impact_analysis.py
│   ├── test_co_purchase.py
│   ├── test_customer_history.py
│   ├── test_aggregate.py
│   ├── test_run_readonly_cypher.py
│   ├── test_state.py
│   ├── test_classify.py
│   ├── test_agent.py
│   ├── test_tools_node.py
│   ├── test_synthesize.py
│   ├── test_degrade.py
│   ├── test_graph.py
│   ├── test_rubric.py
│   └── test_runlog.py
│
├── scripts/
│   ├── seed_data.py       # (exists)
│   ├── wow_question.py    # (exists) UPDATE: add all scripted questions
│   ├── test_cli.py        # NEW: Gate 1 — CLI end-to-end test
│   └── analyze_runlog.py  # NEW: Gate 2 — run-log metrics analyzer
│
├── PLAN.md               # This file
├── PROJECT.md            # Authoritative system contract
└── SCHEMA.md             # Authoritative data contract
```

---

## Phase 1: Curated Tools + Unit Tests

*Corresponds to PROJECT.md §9.1: "Curated tools + unit tests against hand-verified answers"*

| # | Work Item | File | Description | Unit Test | Ground Truth Required |
|---|-----------|------|-------------|-----------|------------------------|
| 1.1 | `lookup_entity` | `src/neo4j/tools.py` | Exact/contains/fuzzy cascade on label name properties. Returns `{status, query_name, matches}` with `match` ∈ {"exact", "contains", "fuzzy"}. Capped at 10 matches. | `tests/test_lookup_entity.py` | Yes: 5+ test cases across labels (Supplier, Product, Customer, etc.). Must include one ground-truth case per lookup tier: exact, contains, fuzzy, and empty. |
| 1.2 | `impact_analysis` | `src/neo4j/tools.py` | Traversal from anchor node (supplier/product/customer) with direction and depth. Returns subgraph + aggregates. **Revenue rule:** `coalesce(line.unitPrice, p.unitPrice) * line.quantity`. Null-quantity lines counted in `unusable_lines`. | `tests/test_impact_analysis.py` | Yes: Supplier "Exotic Liquids" expected subgraph nodes/edges + aggregates (products_affected, orders_affected, revenue_at_risk, unusable_lines) |
| 1.3 | `co_purchase` | `src/neo4j/tools.py` | Products co-bought with anchor, ranked by distinct shared order count. Excludes anchor. Capped at 10. | `tests/test_co_purchase.py` | Yes: Product "Chai" expected recommendations with co_bought counts |
| 1.4 | `customer_history` | `src/neo4j/tools.py` | Customer's orders as dated flow with per-order totals (revenue rule). Dates as raw strings. Ordered by date ascending. | `tests/test_customer_history.py` | Yes: Customer "ALFKI" expected orders with order_key, order_date, total, ship_country |
| 1.5 | `aggregate` | `src/neo4j/tools.py` | Parameterized tabular queries. Fixed join patterns per label. `metric` ∈ {"count", "sum_revenue", "avg_revenue"}. Whitelist validation on `label`, `group_by`, `where`. | `tests/test_aggregate.py` | Yes: Revenue by supplier country expected groups |

**Phase 1 Exit Criteria:** All 5 tools pass unit tests against hand-verified AuraDB ground truth.

---

## Phase 2: Exploratory Tool + Agent Graph

*Corresponds to PROJECT.md §9.2: "run_readonly_cypher + agent graph (state, classify, loop, tools, synthesize, degrade, rubric, run-log)"*

| # | Work Item | File | Description | Unit Test |
|---|-----------|------|-------------|-----------|
| 2.1 | `run_readonly_cypher` | `src/neo4j/tools.py` | Agent-written Cypher. Pipeline: read-only guard → EXPLAIN validation → execute. Exactly 1 retry on failure. Statuses: ok/empty/invalid/retry_ok/retry_failed. Returns `{status, query, attempts, rows}`. | `tests/test_run_readonly_cypher.py` |
| 2.1a | Schema-prompt extraction | `src/agents/schema_prompt.py` | Extract labels, relationship types, and traversal patterns from SCHEMA.md into the LLM schema prompt. Generated mechanically; never hand-edited. | `tests/test_schema_prompt.py` |
| 2.2 | State TypedDicts | `src/agents/state.py` | Define `ToolCallRecord`, `Citation`, `AgentState`. `messages` is the only field with reducer (`add_messages`). All others last-write-wins. | `tests/test_state.py` |
| 2.3 | `classify` node | `src/agents/nodes.py` | Small LLM router. Routes to `agent` \| `chitchat` \| `refusal`. Chitchat answers directly; refusal returns no-evidence. | `tests/test_classify.py` |
| 2.4 | `agent` node | `src/agents/nodes.py` | ReAct loop. MAX_STEPS=8. All 6 tools bound. Emits tool calls. Terminates on answer or budget exhaustion. | `tests/test_agent.py` |
| 2.5 | `tools` dispatcher | `src/agents/nodes.py` | Dispatches one tool call. Times it. Appends exactly one `ToolCallRecord` to trace. Returns result as tool message. | `tests/test_tools_node.py` |
| 2.6 | `synthesize` node | `src/agents/nodes.py` | Produces final answer from tool results. Inline citations. Computes confidence via rubric. Generates rationale string. | `tests/test_synthesize.py` |
| 2.7 | `degrade` node | `src/agents/nodes.py` | Reached on MAX_STEPS exhaustion. Explicit truncation disclosure. Confidence hard-capped at 0.4. Records error. | `tests/test_degrade.py` |
| 2.8 | LangGraph graph | `src/agents/graph.py` | 4 nodes: classify → agent ↔ tools → synthesize; agent → degrade (on budget exhaustion). Control-flow invariants enforced. | `tests/test_graph.py` |
| 2.9 | Confidence rubric | `src/agents/rubric.py` | `compute_confidence(trace: list[ToolCallRecord], route: str) -> tuple[float, str]`. Route ∈ {"agent", "chitchat", "refusal", "degrade"}. Rules: route="degrade" → hard cap 0.4 overrides min-of-caps; route="chitchat" or "refusal" → confidence=0.0, rationale="no evidence: <route>"; route="agent" → min-of-caps per PROJECT.md §5. Caps: curated ok=0.9, exploratory ok=0.6, exploratory retry_ok=0.5, exploratory retry_failed/empty-synth=0.3. | `tests/test_rubric.py` |
| 2.10 | Run-log | `src/utils/runlog.py` | JSONL appender. `write_run(state: AgentState) -> None`. Append-only. Fields: ts, question, route, trace, hops, answer, citations, confidence, confidence_rationale, latency_ms_total. | `tests/test_runlog.py` |

**Gate 1: End-to-End CLI Test** *(PROJECT.md §9.3)*

| # | Work Item | File | Description |
|---|-----------|------|-------------|
| G1 | CLI integration | `scripts/test_cli.py` | Agent works end-to-end in CLI on scripted questions. **If this holds, the demo cannot fail.** |

**Gate 1 Exit Criteria:** Agent answers all scripted questions without errors. Trace, confidence, and citations are correct.

---

## Phase 3: Streamlit GUI

*Corresponds to PROJECT.md §9.4: "Streamlit panels"*

| # | Work Item | File | Description |
|---|-----------|------|-------------|
| 3.1 | Chat panel | `src/streamlit/components/chat.py` | `st.chat_message`. History in `session_state`. Driver and compiled graph in `st.cache_resource`. |
| 3.2 | Trace drawer | `src/streamlit/components/trace_drawer.py` | Expander panel. Route badge. One row per `ToolCallRecord` (tool, mode, status, Cypher for exploratory, latency, retries). Displays confidence + rationale + rubric rule. |
| 3.3 | Graph panel | `src/streamlit/components/graph_panel.py` | streamlit-agraph. Renders evidence subgraph from last tool call. Colors per label. Cited nodes enlarged. Node click → property card (name + properties). |
| 3.4 | Main app | `src/streamlit/app.py` | Integrate all panels. Wire agent graph. |

**Phase 3 Exit Criteria:** GUI renders all 3 panels correctly. Chat interaction works. Trace drawer shows full trace. Graph panel renders subgraphs.

---

## Phase 4: Scripted Questions + Analyzer

*Corresponds to PROJECT.md §9.5: "Scripted question set + run-log analyzer"*

| # | Work Item | File | Description |
|---|-----------|------|-------------|
| 4.1 | Scripted questions | `scripts/wow_question.py` | 5 questions: wow impact (supplier failure), exploratory-with-retry, co-purchase, churn, refusal/degrade. |
| 4.2 | Run-log analyzer | `scripts/analyze_runlog.py` | Metrics: tool distribution, curated/exploratory ratio, retry rate, empty rate, latency. Produces closing-slide stats. |

**Gate 2: Full Rehearsal** *(PROJECT.md §9.6)*

Full rehearsal without touching code. All scripted questions pass.

---

## Fallback Plan

*From PROJECT.md §9: "Fallback if short on time"*

1. **Minimum Viable Demo:** Chat + trace drawer + one scripted wow question (supplier impact)
2. **Stretch 1:** Exploratory tool (`run_readonly_cypher`)
3. **Stretch 2:** Churn beat

---

## Key Invariants

- **Read-only:** All tools are read-only. Driver-level enforcement. No CREATE/MERGE/DELETE/SET/CALL.
- **No APOC:** The read-only rule for the exploratory tool explicitly bans `CALL apoc.meta.*`. No curated tool implementation may rely on APOC; use plain Cypher in `tools.py`.
- **Revenue rule:** `coalesce(line.unitPrice, p.unitPrice) * line.quantity` (from SCHEMA.md).
- **MAX_STEPS:** 8. Budget exhaustion always routes to `degrade`, never to `synthesize`.
- **Trace:** Every executed tool call appends exactly one `ToolCallRecord`. No silent calls.
- **Citations:** Synthesized from final answer claims. No claim without a citation. No citation without a node.
- **Messages:** Only field with reducer (`add_messages`). All others last-write-wins.

---

## Testing Strategy

- **Unit tests:** One test file per work item. Each tests against hand-verified ground truth from AuraDB.
- **Mocking strategy:** Agent-node unit tests (2.3–2.8) run against mocked LLM responses and canned tool outputs — deterministic, no API calls. Only curated-tool tests (Phase 1) hit live AuraDB. Only Gate 1 (`scripts/test_cli.py`) hits the live LLM. `scripts/test_cli.py` is excluded from the pytest suite for this reason.
- **Integration tests:** CLI end-to-end (Gate 1). GUI manual testing.
- **Run-log:** Append-only JSONL. Analyzer script validates metrics.

---

## Notes

- **Ground truth answers:** Required for Phase 1 unit tests. To be provided by the user from the live AuraDB instance. The implementer will not invent answers.
- **Repo layout:** Uses existing structure (`src/neo4j/`, `src/agents/`, `src/streamlit/`, `src/utils/`). No new top-level directories.
- **Tech stack:** Python (uv), LangGraph, Neo4j driver, Streamlit, streamlit-agraph. Credentials in `.env`.

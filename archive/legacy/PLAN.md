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
4. **Phase 3 (3.1–3.5): Streamlit foundation** — Launch, cached runtime, chat, and trace drawer
5. **Post-Gate 1 robustness remediation (R1–R6)** — Normalize exploratory outputs and correct invalid/empty/key lookup handling
6. **Cross-tool result contract and evidence implementation (Steps 1–16)** — Apply one evidence policy across all six tools
7. **Answer completeness remediation (Steps 1–8)** — Route by intent and validate answer coverage before returning a graph answer
8. **Phase 3 (3.6–3.8): Evidence graph and GUI acceptance** — Resume graph-panel work after the tool-result policy passes
9. **Phase 4: Scripted Questions + Analyzer** — Demo beats + metrics
9. **Gate 2: Full Rehearsal** — All scripted questions pass; no code changes

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
| 1.1 | `lookup_entity` | `src/neo4j/tools.py` | Exact/contains/fuzzy cascade on label name properties; the R5 remediation adds exact canonical-key lookup when a label is supplied. Returns `{status, query_name, matches}` with `match` ∈ {"exact", "contains", "fuzzy"}. Capped at 10 matches. | `tests/test_lookup_entity.py` | Yes: 5+ test cases across labels (Supplier, Product, Customer, etc.). Must include one ground-truth case per lookup tier: exact, contains, fuzzy, empty, and exact key. |
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
| 2.6 | `synthesize` node | `src/agents/nodes.py` | Produces a candidate draft and citations from tool results. The consistency checker commits the accepted answer; confidence is computed by the rubric after acceptance. | `tests/test_synthesize.py` |
| 2.7 | `degrade` node | `src/agents/nodes.py` | Reached on MAX_STEPS exhaustion. Explicit truncation disclosure. Confidence hard-capped at 0.4. Records error. | `tests/test_degrade.py` |
| 2.8 | LangGraph graph | `src/agents/graph.py` | classify → agent ↔ tools → synthesize → consistency_check; a revise decision returns to agent with the shared loop budget intact, pass ends, and exhausted budget degrades. | `tests/test_graph.py` |
| 2.9 | Confidence rubric | `src/agents/rubric.py` | `compute_confidence(trace: list[ToolCallRecord], route: str) -> tuple[float, str]`. Route ∈ {"agent", "chitchat", "refusal", "degrade"}. Rules: route="degrade" → hard cap 0.4 overrides min-of-caps; route="chitchat" or "refusal" → confidence=0.0, rationale="no evidence: <route>"; route="agent" → min-of-caps per PROJECT.md §5. Caps: curated ok=0.9, exploratory ok=0.6, exploratory retry_ok=0.5, exploratory retry_failed/empty-synth=0.3. | `tests/test_rubric.py` |
| 2.10 | Run-log | `src/utils/runlog.py` | JSONL appender. `write_run(state: AgentState) -> None`. Append-only. Fields: ts, question, route, trace, hops, answer, citations, confidence, confidence_rationale, latency_ms_total. | `tests/test_runlog.py` |

**Gate 1: End-to-End CLI Test** *(PROJECT.md §9.3)*

| # | Work Item | File | Description |
|---|-----------|------|-------------|
| G1 | CLI integration | `scripts/test_cli.py` | Agent works end-to-end in CLI on scripted questions. **If this holds, the demo cannot fail.** |

**Gate 1 Exit Criteria:** Agent answers all scripted questions without errors. Trace, confidence, and citations are correct.

---

## Phase 3: Streamlit GUI

*Corresponds to PROJECT.md §7 and §9.4. The UI renders the contracted chat, trace, and evidence-graph panels using the R1-amended evidence shape; GUI items do not add further agent or tool contract changes.*

Each numbered item is scoped for one short work session. Finish and record one item before starting another. Dependencies show the recommended order; each item still has a concrete deliverable that can be reviewed on its own.

| # | Work Item | Files | Scope and acceptance check | Depends on |
|---|---|---|---|---|
| 3.1 | Streamlit entry point and launch | `src/streamlit/app.py`, `README.md` | Add a minimal app entry point and a documented `uv run streamlit run src/streamlit/app.py` command. Verify the app starts from the repository root and shows the three panel regions without requiring a graph query. Keep credentials out of source and UI. | Gate 1 |
| 3.2 | Cached runtime resources | `src/streamlit/runtime.py` or `app.py` | Create the Neo4j driver/tools and compiled graph through `st.cache_resource`, reusing the existing client/tool construction. Keep imports lazy so the 3.1 shell does not load Neo4j credentials at module import. Confirm the factory is cached and is not invoked by the placeholder app; exercise first-use and rerun reuse when 3.3 wires it to question submission. | 3.1 |
| 3.3 | Per-question graph runner and run logging | `src/streamlit/runtime.py`, `src/utils/runlog.py` | Add a small callable that creates the complete initial `AgentState`, invokes the compiled graph once for a submitted question, and writes the completed state with `write_run` exactly once. Convert expected runtime failures into a UI-displayable error without fabricating a successful state. Confirm by code review that runtime creation occurs only when this callable is invoked, each question gets a fresh state, and logging is attempted once after completion. Keep each submitted question as its own graph invocation; session history is for display unless a later contract explicitly adds conversational graph persistence. | 3.2 |
| 3.4 | Chat history and input panel | `src/streamlit/components/chat.py` | Render prior user/assistant turns from `st.session_state`, accept a new question with `st.chat_input`, show the submitted question and resulting answer, and preserve history across Streamlit reruns. Confirm first question submission initializes the cached runtime and later reruns reuse it. Verify a chitchat/refusal answer renders even when there are no tool results. | 3.1, 3.3 |
| 3.5 | Trace drawer | `src/streamlit/components/trace_drawer.py` | Add an expander showing the route and one row per `ToolCallRecord`: tool, mode, status, step, result count, latency, retry count, and Cypher for exploratory calls. Display confidence and `confidence_rationale` from state, and surface `state.error` when present so routing fallbacks are visible in the UI. Verify empty traces, an exploratory retry trace, and a fallback disclosure render correctly; leave the run-log schema unchanged. | 3.3 |

### Post-Gate 1: Agent Result Robustness Remediation

**Phase 3.6 and later depend on R1–R6 and the cross-tool result/evidence steps below. R1–R6 were completed on 2026-09-29; the cross-tool result/evidence Steps 1–16 passed on 2026-09-30.** Preserve the read-only boundary, six existing tool signatures, `MAX_STEPS=8`, and the grouped-only purpose of `aggregate`. Each step is a short, reviewable session and requires a dated `SESSION_SUMMARY.md` update before moving to the next item.

| # | Work Item | Files | Scope and acceptance check | Depends on |
|---|---|---|---|---|
| R1 | Exploratory result contract | `PROJECT.md` | Amend §4.5 to define a normalized result envelope. Keep `status`, original `query`, and `attempts`; add an explicit error value for invalid/exhausted failures; normalize each row to `values` plus `evidence.nodes` and `evidence.edges`. Values preserve returned scalar columns and JSON-safe nested values; graph entities are represented canonically and also collected as deduplicated evidence. Define the shape for scalar-only, node, relationship/path/subgraph, and mixed rows, as well as `empty` versus invalid/retry-failed outcomes. Update §7 graph-panel input wording so later UI work can consume normalized exploratory evidence while preserving curated tools' existing `subgraph`. Review the proposed schema before implementation. | None |
| R2 | Safe trailing-semicolon handling | `src/neo4j/client.py`, `tests/test_run_readonly_cypher.py` | Normalize one optional trailing semicolon before EXPLAIN and execution. Continue rejecting internal semicolons or multiple statements, and preserve literal/comment masking so semicolons inside strings or comments do not affect the guard. Verify one terminated read query is accepted and multi-statement/write queries remain rejected. | R1 |
| R3 | Cypher row normalizer | `src/neo4j/tools.py`, `tests/test_run_readonly_cypher.py` | Convert every record to the R1 envelope. Normalize Neo4j nodes and relationships into canonical evidence handles; preserve scalars and nested values; collect node/edge evidence from returned nodes, relationships, paths, and combinations; deduplicate evidence per row. Populate useful errors for preflight, schema, EXPLAIN, execution, and exhausted-retry failures. Test scalar, node, relationship/path or subgraph, mixed, and empty results with deterministic fixtures. | R1, R2 |
| R4 | Graph handling and outcome-aware synthesis | `src/agents/nodes.py`, `tests/test_agent.py`, `tests/test_synthesize.py` | Consume only the normalized Cypher result shape. Build answers and citations from scalar values and their returned evidence. Treat successful zero-row results as “no matches”; treat invalid or retry-failed queries as query failures with a concise reason. Do not let an earlier empty lookup mask a later query failure. Stop the loop after a terminal invalid/retry-failed result or a successful result with sufficient evidence so repeated invalid calls cannot exhaust `MAX_STEPS`. Verify all distinctions and citation invariants deterministically. | R3 |
| R5 | Exact key lookup | `PROJECT.md` §4.1, `src/neo4j/tools.py`, `src/agents/llm.py`, `tests/test_lookup_entity.py` | Preserve exact/contains/fuzzy name lookup and add exact canonical-key lookup when a label is specified. A key match returns the same canonical entity payload and existing match result shape; name inputs such as “Alfreds Futterkiste” continue to work. Update §4.1 with the lookup semantics and update the prompt to distinguish a supplied node key from a display name. Verify `Customer` key `ALFKI`, a customer name, existing match tiers, and missing key. | R1 |
| R6 | Robustness acceptance and handoff | `tests/test_run_readonly_cypher.py`, `tests/test_lookup_entity.py`, `tests/test_agent.py`, `tests/test_synthesize.py`, `SESSION_SUMMARY.md` | Run focused tests and the relevant deterministic project suite with `uv`. Cover “show info of customer ALFKI”, a successful zero-row query, a rejected multiple-statement query, a trailing-semicolon query, and an invalid query following an empty lookup. Confirm the answer, status, evidence citations, and trace agree. Record results and mark remediation complete only when all checks pass; no live AuraDB/Mistral calls are part of pytest. | R2, R3, R4, R5 |


### Cross-tool Result Contracts and Evidence Policy (Steps 1–16)

These steps follow R1–R6 and precede Phase 3.6. They apply the common result/evidence policy in PROJECT.md §3–4 to all six tools while preserving their existing signatures and purpose-specific payloads. Each tool implementation step includes focused deterministic tests. No pytest test may call live AuraDB or Mistral.

| Step | Work item | Files | Scope and acceptance check | Depends on |
|---|---|---|---|---|
| 1 | Inventory current tool result behavior | PROJECT.md, src/neo4j/tools.py, src/agents/nodes.py, tests | Record each tool's status, payload fields, error behavior, evidence association, and synthesis path. Include the live count/ranking cases that exposed scalar-only rows and excessive citation output. Produce a gap matrix against PROJECT.md. | R6 |
| 2 | Freeze common result and evidence policy | PROJECT.md, SESSION_SUMMARY.md | Review status/error semantics, claim-to-evidence association, the three-handle inline citation limit, the one bounded evidence-recovery attempt, and the rule that a computed value comes from the tool result while relevant handles identify graph scope. Confirm that exhaustive contributor records are not required. | 1 |
| 3 | Implement lookup_entity contract | src/neo4j/tools.py, tests/test_lookup_entity.py, tests/test_tool_result_contracts.py | Return each match as a canonical node with its match tier and evidence attached to that match. Include useful errors for invalid input and execution failure. Verify exact key/name, contains, fuzzy, empty, payload shape, and evidence association. | 2 |
| 4 | Implement impact_analysis contract | src/neo4j/tools.py, tests/test_impact_analysis.py, tests/test_tool_result_contracts.py | Associate the anchor and bounded relevant graph evidence with the computed impact aggregates; retain the full contracted subgraph for its graph-display purpose. Verify aggregates, anchor, subgraph, status, and evidence agree. | 2 |
| 5 | Implement co_purchase contract | src/neo4j/tools.py, tests/test_co_purchase.py, tests/test_tool_result_contracts.py | Associate each recommendation and co-occurrence metric with the anchor/recommended Product nodes. Shared Order records are not required. Verify recommendation ordering, counts, anchor exclusion, statuses, and evidence. | 2 |
| 6 | Implement customer_history contract | src/neo4j/tools.py, tests/test_customer_history.py, tests/test_tool_result_contracts.py | Return the canonical Customer and canonical Order handles with each order's date, total, and ship country; associate each order entry with the Customer–Order link. Do not return every line item solely as citation evidence. Verify ordered records and per-order evidence. | 2 |
| 7 | Implement aggregate contract | src/neo4j/tools.py, tests/test_aggregate.py, tests/test_tool_result_contracts.py | Return each group value and computed metric with up to three representative canonical handles from that group. Preserve fixed joins, metric/property whitelists, and the grouped-only purpose. Verify empty/invalid/error outcomes and evidence association. | 2 |
| 8 | Implement run_readonly_cypher contract | src/neo4j/tools.py, src/agents/llm.py, tests/test_run_readonly_cypher.py, tests/test_tool_result_contracts.py | Keep the R1 normalized row structure and associate each row's values with relevant node/edge evidence. Update agent query examples to return the metric plus an anchor or at most three representative records, not every contributor. Preserve normalized rows, attempts, and useful terminal errors. | 2 |
| 9 | **Complete — Add shared runtime result validation** | src/agents/state.py or src/neo4j/result_contracts.py, tests | Define typed per-tool result shapes and a runtime validator for the common status/error fields plus required tool-specific fields. Reject malformed outputs before synthesis; do not treat TypedDict annotations as runtime validation. | 3–8 |
| 10 | **Complete — Integrate structured results with dispatcher and trace** | src/agents/nodes.py, tests/test_tools_node.py, tests/test_contract_flow.py | Pass the validated structured result unchanged in ToolMessage content. Derive ToolCallRecord status and result_rows from the same result; preserve the existing trace schema and one-record-per-call invariant. | 9 |
| 11 | **Complete — Apply the evidence policy in synthesis** | src/agents/nodes.py, tests/test_synthesize.py | Handle each tool's typed payload. Make claims only from data present in that tool's result, cite relevant associated handles, limit computed-claim citations to three, keep large outputs readable, and distinguish empty, invalid, and unsupported results. | 10 |
| 12 | **Complete — Implement bounded evidence recovery and prompt guidance** | src/agents/nodes.py, src/agents/llm.py, tests/test_agent.py | After an otherwise successful but inadequately evidenced result, allow one recovery attempt to retrieve an anchor or relevant evidence. If still inadequate, synthesize an explicit unsupported-result answer. Prompt examples return graph nodes for entity/ranking claims and use only supported aggregate metrics. Keep MAX_STEPS=8. | 11 |
| 13 | **Complete — Add per-tool contract tests** | tests/test_lookup_entity.py, tests/test_impact_analysis.py, tests/test_co_purchase.py, tests/test_customer_history.py, tests/test_aggregate.py, tests/test_run_readonly_cypher.py | Verify every success, empty, and invalid/retry result has the required common fields, purpose-specific payload, and evidence attached at the correct item scope. Keep tests deterministic with mocked Neo4j responses. | 3–10 |
| 14 | **Complete — Add cross-tool claim/evidence policy tests** | tests/test_synthesize.py, tests/test_agent.py, tests/test_contract_flow.py | Cover identity/property, relationship, grouped metric, count, ranking, missing evidence, unrelated evidence, empty results, and query failures. Assert answer, citations, tool status, and trace are consistent; ensure a scalar-only final answer is blocked and recovery is bounded to one attempt. | 11–13 |
| 15 | **Complete — Run deterministic project acceptance suite** | tests, SESSION_SUMMARY.md | Run the full relevant pytest suite with uv and no live Neo4j/Mistral calls. Resolve regressions and record the exact command, pass count, and exclusions. | 14 |
| 16 | **Complete — Retest the app and hand off to Phase 3.6** | Streamlit app, SESSION_SUMMARY.md | Restart Streamlit so cached runtime resources use the new graph. Test customer count, customer with most orders, most ordered product, one curated graph result, and one no-match/failure case. Confirm concise answers, relevant citations, result statuses, and traces; then record completion and unblock 3.6. | 15 |

**Step 16 follow-up (2026-09-30):** A live “list all 31 orders” query exposed a synthesis display cap. The full-list path, truthful default truncation disclosure, full-history gap calculation, and strict numeric rewrite validation are implemented and recorded in `SESSION_SUMMARY.md`; 209 deterministic tests pass.


---

### Answer Completeness Remediation and UI Refinement (Steps 1–10)

These steps follow the completed cross-tool result/evidence Steps 1–16 and precede Phase 3.6. Steps are independent short sessions where practical; update `SESSION_SUMMARY.md` with local date/time, changes, verification, remaining issues, and the next step after each completed item. Keep the existing tool signatures, read-only boundary, evidence policy, and `MAX_STEPS=8`.

| Step | Work item | Files | Scope and acceptance check | Depends on |
|---|---|---|---|---|
| 1 | **Complete — Contract for answer drafts and consistency checking** | `PROJECT.md`, `PLAN.md` | Define `FINAL:` as a request to synthesize a candidate, not proof of completeness. Define the post-synthesis consistency check, pass/revise outcomes, draft state, retry feedback, final answer commit, and preservation of the shared `loop_count` budget. Keep the one-call evidence-recovery bound explicit. Confirm this flow does not alter tool signatures or evidence policy. | Completed cross-tool Steps 1–16 |
| 2 | **Complete — Route tool guidance by intent** | `src/agents/llm.py`, `tests/test_agent_prompt.py`, `SESSION_SUMMARY.md` | Guide tool choice by the requested operation and number of subjects, not keyword presence. Restrict `customer_history` to one-customer history/count/pattern intent; add a shared-products example using `run_readonly_cypher` and representative path evidence. Add a deterministic prompt regression test; do not change stop behavior in this step. | 1 |
| 3 | **Complete — Remove success-based forced `FINAL` across tools** | `src/agents/nodes.py`, `tests/test_agent.py` | Removed automatic `FINAL` insertion for successful results from all six tools, including `customer_history`; after `ok` or `retry_ok`, control returns to the model for its next decision. Curated empty results also return to the model. Preserve terminal handling for exploratory `empty`, `invalid`, and `retry_failed` outcomes, plus the one-call evidence-recovery guidance. Deterministic tests cover all tool success paths and retained terminal statuses. | 1, 2 |
| 4 | **Complete — Add explicit draft state and synthesis behavior** | `src/agents/state.py`, `src/agents/nodes.py`, `src/streamlit/runtime.py`, `scripts/test_cli.py`, `tests/test_state.py`, `tests/test_synthesize.py` | Added draft answer/citation fields separately from accepted fields. Synthesis now produces only a draft; the checker commits answer, citations, and rubric confidence after validation. Rejected drafts remain internal and are cleared on budget degradation. Verified with state, synthesis, runtime/CLI initialization, and graph tests. | 1, 3 |
| 5 | **Complete — Implement consistency-check node** | `src/agents/nodes.py`, `src/agents/llm.py`, `tests/test_agent_prompt.py`, `tests/test_contract_flow.py` | Added deterministic citation/evidence checks and requested-key coverage checks, followed by a Mistral reviewer for question operation/constraint coverage. The reviewer returns structured pass/revise feedback; malformed or failed reviews fail closed. Confidence is not used as a completeness signal. | 4 |
| 6 | **Complete — Add retry routing and shared-budget behavior** | `src/agents/graph.py`, `src/agents/nodes.py`, `tests/test_contract_flow.py` | Passing drafts route to `END`; revise feedback returns control to the agent without resetting `loop_count`. Rejected candidates are not committed. The existing MAX_STEPS budget routes exhaustion to `degrade`. The checker has no self-loop and cannot create an unbounded retry path. | 5 |
| 7 | **Complete — Verify end-to-end completeness cases** | `tests/test_contract_flow.py`, `tests/test_agent.py`, `tests/test_synthesize.py`, `tests/test_agent_prompt.py` | Mocked graph tests prove SAVEA-only history is rejected for a SAVEA/ALFKI shared-products question, the follow-up query cites both customers and the product, complete evidence passes, rejected drafts retry with the existing counter, and exhaustion degrades. Tests make no live Mistral or AuraDB calls. | 6 |
| 8 | **Complete — Make the Chat, Trace, and Evidence Graph panels independently scrollable** | `src/streamlit/app.py`, `src/streamlit/components/chat.py`, `tests/test_streamlit_app.py`, `pyproject.toml`, `uv.lock` | Three side-by-side panels each use a 450 px fixed-height, bordered scroll region; chat input remains outside the history region and history auto-scrolls. Raised the minimum Streamlit version to 1.35, where fixed-height scroll containers are available. AppTest verifies the three distinct regions and their heights. | 3.5 |
| 9 | **Complete — Add Traceable Explainability heading** | `src/streamlit/app.py`, `src/streamlit/components/trace_drawer.py`, `tests/test_streamlit_app.py` | Added “Traceable Explainability” above separate Trace and Confidence expanders. Chat, Traceable Explainability, and Evidence Graph use the same Streamlit subheader level; AppTest verifies their common heading tag. | 3.5 |
| 10 | **Complete — Run integrated acceptance and handoff** | `tests/test_streamlit_app.py`, `tests/test_contract_flow.py`, `SESSION_SUMMARY.md` | Full deterministic suite passes. AppTest verifies a long mocked chat answer, one mocked single-customer UI turn, returned-state persistence, panel dimensions, and headings. Compiled-graph acceptance tests pass for SAVEA/ALFKI shared products and an ALFKI single-customer lookup. A headless Streamlit launch returned HTTP 200 without live-service calls. Browser-level scroll interaction remains for visual confirmation. | 7, 8, 9 |

---

| # | Work Item | Files | Scope and acceptance check | Depends on |
|---|---|---|---|---|
| 3.6 | Evidence graph data extraction | `src/streamlit/components/graph_panel.py` | Extract the last tool result and adapt its evidence to the panel input: preserve curated tools' `subgraph`, and map normalized exploratory `evidence.nodes`/`evidence.edges` into the graph shape. Handle absent, malformed, empty, or non-graph results with an explicit empty-state value. Add focused tests for curated impact, exploratory node/subgraph evidence, and tools with no graph evidence. | R6, Step 16 |
| 3.7 | Graph rendering and node details | `src/streamlit/components/graph_panel.py` | Render the extracted evidence using `streamlit-agraph`; apply the contract's label colors and enlarge exactly the nodes present in `state['citations']`. On node selection, show the selected node's name and properties. Verify selection maps back to the original subgraph node and an empty subgraph renders a useful message. | 3.6 |
| 3.8 | Main app integration and GUI acceptance | `src/streamlit/app.py`, `tests/` or manual checklist | Compose chat, trace, and graph panels for each completed turn. Confirm the graph panel uses only the last tool call's evidence (curated `subgraph` or normalized exploratory evidence), all three panels reflect the same returned state, the app handles no-graph-evidence routes, and one UI turn appends exactly one run-log entry. Perform a manual smoke test with the wow impact question and one chitchat or refusal question. | 3.4, 3.5, 3.7 |

**Phase 3 Exit Criteria:** The app launches with `uv`; users can submit a question and see the answer; history survives reruns; the trace drawer renders the returned trace and confidence fields; the graph panel displays the last tool call's graph evidence, highlights cited nodes, and shows selected-node details; completed turns are logged once. The PROJECT.md UI contract from R1 is preserved.

---

## Phase 4: Scripted Questions + Analyzer

*Corresponds to PROJECT.md §6 and §9.5. Use the existing compiled graph, tools, live read-only Neo4j access, and run log; do not create a second agent execution path.*

| # | Work Item | Files | Scope and acceptance check | Depends on |
|---|---|---|---|---|
| 4.1 | Scripted question catalog | `scripts/wow_question.py` or `scripts/demo_questions.py` | Define the five demo beats already in the plan: supplier impact, exploratory query with retry, co-purchase, churn/customer history, and one refusal or budget-degrade case. For each, record a stable ID, prompt, expected route/tool, and verifiable outcome checks. Keep question data separate from execution logic. | Gate 1 |
| 4.2 | Named question runner | `scripts/wow_question.py` or `scripts/demo_questions.py` | Add CLI selection for one named question or the complete catalog. Run each selected case through `compile_graph` and the established execution path, print a concise PASS/FAIL with reasons, and call `write_run` once for each completed run. Check missing credentials up front and return a nonzero exit code on failure. | 4.1 |
| 4.3 | Supplier impact demo check | `scripts/demo_questions.py`, `tests/` | Verify the wow question reaches `impact_analysis`, returns a non-empty evidence subgraph, includes the contracted aggregates, and produces citations for its graph claims. Use live ground truth for the rehearsal and deterministic fixtures for unit coverage. | 4.2 |
| 4.4 | Exploratory retry demo check | `scripts/demo_questions.py`, `tests/` | Verify the exploratory beat shows both attempts (initial validation failure and one successful retry), records `retry_count == 1`, and satisfies the confidence rule. Fail visibly if recovery is absent. | 4.2 |
| 4.5 | Co-purchase and churn demo checks | `scripts/demo_questions.py`, `tests/` | Verify co-purchase uses the expected tool and returns cited recommendations; verify the churn/customer-history beat uses the contracted customer evidence and cited order history/gap. Keep each scenario independently selectable. | 4.2 |
| 4.6 | Refusal or budget-degrade demo check | `scripts/demo_questions.py`, `tests/` | Verify the selected fifth beat reaches its expected route. For refusal, check refusal behavior and no graph citations; for budget degrade, check eight calls, explicit truncation, and the 0.4 confidence cap. | 4.2 |
| 4.7 | Read-only run-log analyzer | `scripts/analyze_runlog.py`, `tests/` | Read JSONL without modifying it. Report run count, tool distribution, curated/exploratory call counts and ratio, retry count/rate (retrying exploratory calls divided by exploratory calls), empty-result rate (empty tool calls divided by all tool calls), and total/mean/median tool latency. Handle a missing or empty log and malformed lines with clear diagnostics. | Gate 1 |
| 4.8 | Closing stats output and Gate 2 rehearsal | `scripts/analyze_runlog.py`, `scripts/`, `SESSION_SUMMARY.md` | Emit concise Markdown or JSON closing-slide statistics to stdout or a specified output path; never rewrite `runlog.jsonl`. Rehearse all five scripted beats in the GUI without code changes, inspect answers/citations/trace/graph and analyzer output, then record pass/fail evidence and any issue in `SESSION_SUMMARY.md`. | 3.8, 4.3, 4.4, 4.5, 4.6, 4.7 |

**Gate 2 Exit Criteria:** Run all five named demo beats in the GUI without code changes. Each reaches its expected route and tool outcome, the UI panels agree with returned graph state, every graph claim has node-backed citations, and the analyzer reports metrics from the append-only run log. Record the rehearsal result in `SESSION_SUMMARY.md`.

---

## Session Handoff Rule for Phase 3 and Phase 4

After every numbered item (including R1–R6 and cross-tool Steps 1–16) is completed, update `SESSION_SUMMARY.md` in the same work session before stopping. Include the local date/time and timezone, item ID and title, files changed, verification performed and result, any remaining issue, and the next item ID. Mark an item complete only when its acceptance check passes. If work stops partway through an item, record it as in progress and note the exact next action. Do not mark dependent items complete by implication. Phase 3.6 and later require R6 and cross-tool Step 16 to be complete.

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

- **Unit tests:** Add focused deterministic tests for pure logic and contracts (state construction, panel data shaping, citations, analyzer metrics, exploratory result normalization, semicolon validation, and query outcome handling). Do not call live AuraDB or Mistral from pytest. For GUI work, test data preparation and session behavior where practical; use the manual acceptance checks for visual rendering and agraph interaction.
- **Ground truth:** Preserve hand-verified AuraDB expectations for curated-tool behavior and the Phase 4 live demo checks. Do not invent expected business values.
- **Live integration:** Gate 1 (`scripts/test_cli.py`) and the Phase 4 demo/rehearsal runner are the live LLM/Neo4j checks. They are separate from pytest and may append run-log entries; identify probes or rehearsals clearly in their questions.
- **GUI integration:** Manually verify Streamlit layout, chat submission, trace display, cited-node emphasis, and node selection in the browser. Keep `uv` as the environment and command runner.
- **Run-log:** Append-only JSONL. Analyzer tests use temporary logs; the analyzer itself never edits the production log.

---

## Notes

- **Ground truth answers:** Required for Phase 1 unit tests. To be provided by the user from the live AuraDB instance. The implementer will not invent answers.
- **Repo layout:** Uses existing structure (`src/neo4j/`, `src/agents/`, `src/streamlit/`, `src/utils/`). No new top-level directories.
- **Tech stack:** Python (uv), LangGraph, Neo4j driver, Streamlit, streamlit-agraph. Credentials in `.env`.


**Post-Step-10 acceptance follow-up:** A live “how many nodes are there in the graph?” run returned one successful count query but used all eight agent iterations because the model omitted `FINAL:` after the tool result. Retests showed that agent turns could still exhaust the budget after the count query, including when the evidence-bearing query finally ran late in the loop. Evidence-adequate successful tool results now route directly to synthesis and the consistency check; the checker returns incomplete candidates to the agent with the shared budget intact. Scalar-only whole-graph node totals get one deterministic read-only recovery query returning the same count plus at most three representative node handles. The regular consistency check remains the acceptance gate. Generic `node_count` aliases synthesize as “nodes” rather than inheriting a sampled node label. Regression coverage is in `tests/test_contract_flow.py`.


**Post-Step-10 live scope correction:** A live tool inspection of the exact whole-graph query returned `total_nodes=1104` and three Territory evidence nodes. Synthesis had mistaken the first sampled Territory for a count anchor and generated an incorrect “nodes associated with Westboro” draft, which the consistency reviewer rejected. Count synthesis now scopes metrics only to an explicitly returned node value; sampled evidence never creates a scope. Generic whole-graph node totals keep a deterministic sentence without a model rewrite. A live end-to-end graph invocation passed in one agent turn.

**Customer product-ranking follow-up:** “Which customer ordered the most products?” now means the customer with the highest count of distinct Product nodes. Questions asking for units, quantity, or volume use a summed quantity metric. Synthesis recognizes Customer plus quantity results and does not label them as a Product answer. Live validation returned Ernst Handel with 56 distinct products in one agent turn.

**Customer product-ranking follow-up:** “Which customer ordered the most products?” now means the customer with the highest count of distinct Product nodes. Questions asking for units, quantity, or volume use a summed quantity metric. Synthesis recognizes Customer plus quantity results and does not label them as a Product answer. Live validation returned Ernst Handel with 56 distinct products in one agent turn.

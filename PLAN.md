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
6. **Phase 3 (3.6–3.8): Evidence graph and GUI acceptance** — Resume graph-panel work after remediation
7. **Phase 4: Scripted Questions + Analyzer** — Demo beats + metrics
8. **Gate 2: Full Rehearsal** — All scripted questions pass; no code changes

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

**Phase 3.6 and later depend on R1–R6. R1–R6 were completed on 2026-09-29; see `SESSION_SUMMARY.md`.** These fixes preserve the read-only boundary, six existing tool signatures, `MAX_STEPS=8`, and the grouped-only purpose of `aggregate`. Each item is a short, reviewable session and requires a dated `SESSION_SUMMARY.md` update before moving to the next item.

| # | Work Item | Files | Scope and acceptance check | Depends on |
|---|---|---|---|---|
| R1 | Exploratory result contract | `PROJECT.md` | Amend §4.5 to define a normalized result envelope. Keep `status`, original `query`, and `attempts`; add an explicit error value for invalid/exhausted failures; normalize each row to `values` plus `evidence.nodes` and `evidence.edges`. Values preserve returned scalar columns and JSON-safe nested values; graph entities are represented canonically and also collected as deduplicated evidence. Define the shape for scalar-only, node, relationship/path/subgraph, and mixed rows, as well as `empty` versus invalid/retry-failed outcomes. Update §7 graph-panel input wording so later UI work can consume normalized exploratory evidence while preserving curated tools' existing `subgraph`. Review the proposed schema before implementation. | None |
| R2 | Safe trailing-semicolon handling | `src/neo4j/client.py`, `tests/test_run_readonly_cypher.py` | Normalize one optional trailing semicolon before EXPLAIN and execution. Continue rejecting internal semicolons or multiple statements, and preserve literal/comment masking so semicolons inside strings or comments do not affect the guard. Verify one terminated read query is accepted and multi-statement/write queries remain rejected. | R1 |
| R3 | Cypher row normalizer | `src/neo4j/tools.py`, `tests/test_run_readonly_cypher.py` | Convert every record to the R1 envelope. Normalize Neo4j nodes and relationships into canonical evidence handles; preserve scalars and nested values; collect node/edge evidence from returned nodes, relationships, paths, and combinations; deduplicate evidence per row. Populate useful errors for preflight, schema, EXPLAIN, execution, and exhausted-retry failures. Test scalar, node, relationship/path or subgraph, mixed, and empty results with deterministic fixtures. | R1, R2 |
| R4 | Graph handling and outcome-aware synthesis | `src/agents/nodes.py`, `tests/test_agent.py`, `tests/test_synthesize.py` | Consume only the normalized Cypher result shape. Build answers and citations from scalar values and their returned evidence. Treat successful zero-row results as “no matches”; treat invalid or retry-failed queries as query failures with a concise reason. Do not let an earlier empty lookup mask a later query failure. Stop the loop after a terminal invalid/retry-failed result or a successful result with sufficient evidence so repeated invalid calls cannot exhaust `MAX_STEPS`. Verify all distinctions and citation invariants deterministically. | R3 |
| R5 | Exact key lookup | `PROJECT.md` §4.1, `src/neo4j/tools.py`, `src/agents/llm.py`, `tests/test_lookup_entity.py` | Preserve exact/contains/fuzzy name lookup and add exact canonical-key lookup when a label is specified. A key match returns the same canonical entity payload and existing match result shape; name inputs such as “Alfreds Futterkiste” continue to work. Update §4.1 with the lookup semantics and update the prompt to distinguish a supplied node key from a display name. Verify `Customer` key `ALFKI`, a customer name, existing match tiers, and missing key. | R1 |
| R6 | Robustness acceptance and handoff | `tests/test_run_readonly_cypher.py`, `tests/test_lookup_entity.py`, `tests/test_agent.py`, `tests/test_synthesize.py`, `SESSION_SUMMARY.md` | Run focused tests and the relevant deterministic project suite with `uv`. Cover “show info of customer ALFKI”, a successful zero-row query, a rejected multiple-statement query, a trailing-semicolon query, and an invalid query following an empty lookup. Confirm the answer, status, evidence citations, and trace agree. Record results and mark remediation complete only when all checks pass; no live AuraDB/Mistral calls are part of pytest. | R2, R3, R4, R5 |

---

| # | Work Item | Files | Scope and acceptance check | Depends on |
|---|---|---|---|---|
| 3.6 | Evidence graph data extraction | `src/streamlit/components/graph_panel.py` | Extract the last tool result and adapt its evidence to the panel input: preserve curated tools' `subgraph`, and map normalized exploratory `evidence.nodes`/`evidence.edges` into the graph shape. Handle absent, malformed, empty, or non-graph results with an explicit empty-state value. Add focused tests for curated impact, exploratory node/subgraph evidence, and tools with no graph evidence. | 3.3, R6 |
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

After every numbered item (including R1–R6) is completed, update `SESSION_SUMMARY.md` in the same work session before stopping. Include the local date/time and timezone, item ID and title, files changed, verification performed and result, any remaining issue, and the next item ID. Mark an item complete only when its acceptance check passes. If work stops partway through an item, record it as in progress and note the exact next action. Do not mark dependent items complete by implication. Phase 3.6 and later require R6 to be complete.

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

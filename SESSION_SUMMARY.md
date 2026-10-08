# Session Summary — Northwind Agentic KG

**Updated:** 2026-09-30 14:16 CEST (Europe/Paris)
**Current milestone:** Cross-tool result/evidence Steps 1–16 complete. Answer-completeness remediation and UI refinement Steps 1–10 complete. Phase 3.6 is ready to resume after the user confirms the UI appearance in their browser.

## Work completed

- Reviewed the implementation against `README.md`, `SCHEMA.md`, `PROJECT.md`, and `PLAN.md`, then corrected the Gate 1 contract deviations. The compiled LangGraph now has a separate tool node, `messages` uses `add_messages`, and every executed tool call produces one trace record. The eight-step budget routes to `degrade` with a truncation disclosure.
- Reworked the Neo4j client and tools for read-only execution, query validation and schema-aware retry. `impact_analysis` returns the actual evidence subgraph and executive aggregates. Entity lookup covers all nine graph labels; aggregation uses fixed, parameterized join patterns, caps results at 20 groups, and includes contributing node handles. Customer history, co-purchase, and exploratory Cypher were also corrected.
- Built final answers from actual tool outputs. The agent creates canonical `Citation` objects for claims it makes, validates the Mistral synthesis draft against the local evidence, and falls back to a grounded answer when needed. Tool-call parsing handles formatted responses and nested JSON.
- Amended `PROJECT.md` §4.6 **with the user's explicit approval** so aggregate groups include `evidence: [{label, key, name}]`. This supplies node citations for aggregate claims. No other contract change was authorized.
- Rewrote the Gate 1 CLI checks to exercise the compiled graph with live questions and deterministic budget and retry probes. Added focused regression coverage for graph flow, tools, citations, synthesis, and run logging. The production run log remains append-only.

## Verification

- `uv run --no-sync python -m pytest -q -o addopts=''`: **208 passed** on the final implementation.
- `uv run --no-sync python -u scripts/test_cli.py`: **9/9 Gate 1 cases passed** (seven live question cases and two controlled probes). The cases cover supplier impact, exploratory Cypher, co-purchase, customer history, aggregation, chitchat, refusal, budget exhaustion, and retry.
- Live AuraDB checks also exercised aggregation across all nine supported labels and incoming impact traversal.

## Decisions and constraints

- Manage the Python environment with **uv** and run commands through `uv run`.
- `PROJECT.md` and `SCHEMA.md` are authoritative. Preserve the six tool signatures, read-only graph access, `MAX_STEPS=8`, one trace entry per executed tool call, and citations backed by graph nodes.
- The user authorized sending **read-only Northwind tool results to Mistral** for answer generation. This is implemented and noted in `src/agents/llm.py`; **revisit this data-sharing choice later** as requested.

## Handoff

- The Gate 1 code and contract amendment are included in the current source changes. `runlog.jsonl` contains appended entries from the CLI runs. Do not rely on the 2026-09-27 handoff's clean-tree status, test count, or claim that exploratory question 2 is broken; those are superseded by this update.
- Reviewed and expanded PLAN.md Phases 3 and 4 into 16 numbered items (3.1–3.8 and 4.1–4.8), each with files, scope, acceptance checks, and dependencies. Added a requirement to update this summary after every item.
- **R1 — Exploratory result contract: complete.** Amended `PROJECT.md` §4.5 with a stable `run_readonly_cypher` envelope: `status`, original `query`, `attempts`, normalized `rows` containing `values` and deduplicated `evidence.nodes`/`evidence.edges`, and nullable terminal `error`. Defined canonical normalization for nodes, relationships, and paths, including empty versus failed outcomes and evidence requirements for scalar claims. Updated §7 so the graph panel can use normalized exploratory evidence while curated tools retain their `subgraph` input. Reviewed the schema and examples; `git diff --check` passed. No code or tests changed. Next: R2, trailing-semicolon validation.
- **R2 — Safe trailing-semicolon handling: complete.** Added `_normalize_read_only_query` in `src/neo4j/client.py`. It accepts and removes one terminal semicolon before validation, EXPLAIN, and execution; semicolons inside strings/comments are masked, while internal/multiple-statement delimiters and writes remain rejected. Added focused validator and mocked execution-path checks in `tests/test_run_readonly_cypher.py`. `uv run --no-sync python -m pytest -q -o addopts='' tests/test_run_readonly_cypher.py tests/test_contract_flow.py`: **17 passed**; `git diff --check` passed. Next: R3, normalize Cypher rows to the R1 contract.
- **R3 — Cypher row normalizer: complete.** Replaced the exploratory tool’s arbitrary row serializer with the R1 envelope: `values`, per-row canonical `evidence.nodes`/`evidence.edges`, and a top-level nullable `error` on every status. Returned nodes retain JSON-safe properties; returned relationships add canonical endpoint nodes and edges; paths and nested mixtures are recursively normalized and deduplicated. Added fixture coverage for scalar-only, node, relationship, path, mixed, and JSON-serializable rows; `uv run --no-sync python -m pytest -q -o addopts='' tests/test_run_readonly_cypher.py`: **11 passed**; `git diff --check` passed. No synthesis changes yet; R4 must adapt the graph to the new row envelope before end-to-end use. Next: R4, outcome-aware agent handling.
- **R4 — Graph handling and outcome-aware synthesis: complete (2026-09-29 19:03 CEST, Europe/Paris).** `agent_step` now consumes normalized evidence rows and ends the loop after successful cited results or terminal exploratory `empty`, `invalid`, and `retry_failed` outcomes. `synthesize` reads only `values` and normalized `evidence`, cites canonical nodes, avoids surfacing scalar-only values without node evidence, and distinguishes successful zero-row queries from rejected or exhausted queries with their error. A later Cypher failure now takes precedence over a preceding empty entity lookup. Updated agent/synthesis tests for the normalized envelope, terminal failures, empty-versus-invalid behavior, scoped counts, and uncitable scalar rows. Full suite: `uv run --no-sync python -m pytest -q -o addopts=''`: **220 passed**; `git diff --check` passed. No live Neo4j or Mistral call was made. Next: R5, exact key lookup; Phase 3.6+ remains paused until R6 passes.
- **R5 — Exact key lookup (2026-09-29 19:09 CEST, Europe/Paris): complete.** Updated `lookup_entity` to check exact display names first, then exact canonical keys when a label is provided, then retain contains and fuzzy name matching. Key lookup uses the schema-mapped key field and `toString` so string and integer IDs share behavior; it returns the same canonical match payload with `match: "exact"`. Amended `PROJECT.md` §4.1 (including correction of its sample canonical key), and updated the active Mistral prompt to distinguish a supplied key from a display name. Deterministic lookup tests cover Customer key `ALFKI`, the customer display name, contains/fuzzy tiers, and a missing key. Focused lookup/agent/synthesis tests: **31 passed, 7 live AuraDB cases deselected**; prompt template formatting and `git diff --check` passed. No live graph or Mistral request was made. Next: R6, robustness acceptance and handoff; Phase 3.6+ remains paused until R6 passes.
- **R6 — Robustness acceptance and handoff (2026-09-29 19:14 CEST, Europe/Paris): complete.** Added a deterministic compiled-graph check for “Show info of customer ALFKI”: exact key lookup returns the customer, synthesis includes returned city/country details, the answer cites `[Customer:ALFKI]`, and the trace reports one successful lookup with one result. Added acceptance assertions for a multiple-statement query being rejected without EXPLAIN/execution and recorded as `invalid`, for terminal-semicolon query acceptance, and for an invalid Cypher result remaining distinct from an earlier empty lookup (including trace statuses and no citations). `synthesize` now includes returned scalar lookup properties in the cited node summary so “show info” surfaces the requested details. Verification: focused R1–R5 acceptance suite **53 passed, 7 live AuraDB cases deselected**; full deterministic project suite `uv run --no-sync python -m pytest -q -o addopts='' -k 'not TestLookupEntity'`: **218 passed, 8 legacy AuraDB tests deselected**; `git diff --check` passed. No live AuraDB or Mistral request was made. R1–R6 remediation is complete. Phase 3.6+ is no longer blocked by R6; resume the pending 3.5 UI retest and retry/fallback trace checks before continuing the GUI plan.
- **Live app smoke test and result-handling follow-up (2026-09-30 10:50 CEST, Europe/Paris):** In the app, “how many customers are there in Northwind graph?” returned the correct count, 91, but synthesis printed all 91 customer citations. “Which customer placed the most order?” first called `aggregate` with unsupported metric `count_orders`, then returned only scalar customer fields from Cypher; “Which product was the most ordered?” likewise returned only scalar product fields. Synthesis correctly refused to make claims without normalized node evidence, but the agent accepted its own final answer despite that missing evidence. Tightened the active prompt with supported aggregate metrics and node-return requirements for customer/product rankings; `agent_step` now rejects model-authored finals after successful scalar-only exploratory rows and asks for a node-returning query; count synthesis cites at most three representative nodes and reports how many additional evidence nodes were returned; ranked-product synthesis now answers from a returned Product node and quantity metric. Added regressions in `tests/test_agent.py` and `tests/test_synthesize.py`. Verification: `uv run --no-sync python -m pytest -q -o addopts='' -k 'not TestLookupEntity'`: **221 passed, 8 legacy AuraDB tests deselected**; prompt formatting and `git diff --check` passed. The currently running Streamlit process has cached runtime resources, so restart it before retesting these changes. Live app retest remains pending; keep Phase 3.6 paused until the count, customer-ranking, and product-ranking answers and traces are verified.
- **3.1 Streamlit entry point and launch:** implemented `src/streamlit/app.py` with the three contracted panel areas as placeholders; updated README setup and launch commands to use `uv`. No Neo4j driver or agent graph is initialized by the shell.
- **3.1 status: complete.** The user launched Streamlit with `uv run streamlit run src/streamlit/app.py`; VS Code made remote port 8501 available, and the placeholder app opened at `localhost:8501`.
- **3.2 status: complete.** Added `src/streamlit/runtime.py` with a lazy `st.cache_resource` factory returning the existing Neo4j singleton client, all six existing tools, and a compiled graph. Neo4j/agent modules are imported only when the factory is first called; the 3.1 page does not call it. Code review confirms the resource factory is cached and deferred. First-use and rerun reuse will be exercised in 3.4 when chat submission calls the runner.
- **3.3 status: complete.** Added `run_question(question)` in `src/streamlit/runtime.py`. It validates non-empty input, calls the cached runtime, builds all ten initial `AgentState` fields fresh, invokes the graph once, and calls `write_run` once after graph completion. Graph/setup errors return no fabricated state plus a displayable message and server-side traceback; run-log failure preserves the completed state and returns a warning. Code review only; no tests or live services were run.
- **3.4 implementation:** added `src/streamlit/components/chat.py` and connected it from `src/streamlit/app.py`. It renders persisted user/assistant turns, accepts `st.chat_input`, calls `run_question`, displays answers or errors, and keeps the latest returned state in session state for the trace/graph panels. A failed new run clears the previous displayed state.
- **3.4 status: complete.** The user confirmed the chat ordering fix. Chat history is rendered above the input after a completed exchange; user observed chitchat and refusal answers.
- **3.5 implementation:** added `src/streamlit/components/trace_drawer.py` and wired it to `last_run_state` in `app.py`. The drawer displays route, every trace record's tool/mode/status/step/rows/latency/retry count, args, exploratory Cypher, confidence, and rationale. It also surfaces `state.error` as a warning for classifier fallback visibility; the PROJECT.md run-log schema is unchanged.
- **3.5 UI observations and follow-up:** The user confirmed chitchat and refusal display “No tool calls in this run” as expected. The live customer-count question exposed an exploratory scalar-without-citations gap. Updated the agent prompt to use `run_readonly_cypher` for whole-dataset counts and return all contributing nodes. The follow-up customer-order-count trace showed successful scalar-only Cypher did not satisfy the stop condition. The prompt now requires counted-node evidence and a customer anchor for exploratory counts, and directs known customer ID order-count questions to `customer_history`; synthesis renders scoped counts and the loop stops after cited count evidence is returned. `aggregate` and `PROJECT.md` remain unchanged. Added deterministic synthesis and loop-completion regression cases in `tests/test_synthesize.py` and `tests/test_agent.py` (21 focused tests passed). **Status: code fix implemented; UI retest and the planned retry/fallback trace checks remain pending.**
- Preserve the PROJECT.md UI contracts. Each question starts a fresh graph invocation because persistent agent memory is not in the contract.

- **Cross-tool result/evidence Step 1 — inventory and gap matrix (2026-09-30 12:04 CEST, Europe/Paris): complete.** Read all six tool implementations, dispatcher/trace handling, and synthesis paths; compared them with the prospective common contract in `PROJECT.md` §4 and the live count/ranking failures. Current implementation gaps:

  | Tool | Current result shape and status/error behavior | Evidence currently returned | Downstream synthesis and gap against PROJECT.md |
  |---|---|---|---|
  | `lookup_entity` | `status`, `query_name`, flat `matches` with canonical fields and match tier; invalid/empty distinguishable, no `error` field | Each match is itself a canonical node, but no explicit per-match `node`/`evidence` envelope | Synthesis cites matches and scalar properties. Missing common nullable `error` and contract-shaped evidence association. |
  | `impact_analysis` | `status`, `anchor`, `subgraph`, `aggregates`; no `error` field | Full traversal subgraph is returned; no separate bounded claim-evidence field | Synthesis cites anchor for all aggregates. Graph payload is useful for display, but result lacks common error/evidence schema and explicit aggregate-to-anchor association. |
  | `co_purchase` | `status`, `product`, flat `recommendations`; invalid/empty distinguishable, no `error` | Recommendation entries have product identity and count, but no explicit canonical product object or evidence | Synthesis cites anchor and each recommendation. Missing error field and pair-scoped evidence. Shared orders need not be returned under the agreed demo policy. |
  | `customer_history` | `status`, `customer`, `orders` with scalar order key/date/total/country; no `error` | Customer is identified; order entries lack canonical Order handles and Customer–Order edge evidence | Synthesis manufactures an Order citation from `order_key`. This can cite a key but does not establish returned canonical node/edge evidence; output contract and evidence association need implementation. |
  | `aggregate` | `status`, `groups`, `n_groups`; invalid/empty distinguishable, no `error` | Each group currently returns a flat `evidence` list of entity handles, collected from all matches in that group; no edge handles | Aggregate synthesis cites every group evidence handle, so it can produce verbose output. The observed 91 citations came from exploratory Cypher before the recent synthesis cap; that case is now capped inline, but its raw row evidence remains unbounded. The aggregate payload still needs a bounded representative sample (maximum three handles) and common envelope. |
  | `run_readonly_cypher` | `status`, original `query`, `attempts`, normalized `rows`, nullable `error`; success/empty/invalid/retry outcomes distinguished | Per row, `values` plus deduplicated normalized `evidence.nodes`/`edges`; nested returned graph values are recursively collected without a bound | Synthesis understands normalized rows, blocks unsupported scalar-only claims, and recognizes customer counts/product rankings. It can still display every collected entity; it needs claim-scoped bounded evidence and bounded recovery. |

  Cross-cutting findings: `execute_tool_step` serializes the tool dictionary unchanged into `ToolMessage`, while `ToolCallRecord` derives status and row count separately; there is no shared runtime result validator. Synthesis has six separate tool-specific branches rather than one validated per-tool contract. `error` is inconsistent or absent outside exploratory Cypher. Existing code does not yet enforce the PROJECT.md output schemas for lookup, impact, co-purchase, customer history, or aggregate. The recent prompt and synthesis changes address the observed exploratory count/ranking examples only; they do not close the all-tool result-contract gaps. No code or tests changed for this audit. Next: Step 2, freeze the common result and evidence policy.

- **Cross-tool result/evidence Step 2 — freeze common policy (2026-09-30 12:11 CEST, Europe/Paris): complete.** Amended `PROJECT.md` §4 with shared status/error semantics for all six tools (`ok`, `empty`, `invalid`; `retry_ok`/`retry_failed` only for exploratory Cypher), required nullable top-level `error`, and retention of the tool-specific payload for each status. Defined claim-local evidence association; computed scalar values come from the tool result, with a relevant anchor/entity/group and no requirement to return every contributor. Specific-edge claims retain the edge and both endpoint handles; derived relationship metrics such as co-purchase counts are scoped to the relevant entity pair without requiring every shared-order record. Set the demo presentation cap at three relevant node citations per computed claim; full impact subgraphs remain available for their graph-display purpose. Bounded evidence recovery to one additional tool call, separate from Cypher's one internal repair retry; if support remains inadequate, synthesis must abstain from the graph claim. This freezes the first-level evidence choice; all-contributor evidence is not required. `git diff --check` passed. No tool implementation or runtime validation was changed. Next: Step 3, implement the `lookup_entity` result contract.

- **Cross-tool result/evidence Step 3 — `lookup_entity` contract (2026-09-30 12:31 CEST, Europe/Paris): complete.** Matches now carry a canonical node, match tier, and node-local evidence; every result includes the common nullable `error` field, with useful invalid/execution errors. Preserved exact display-name, exact label-scoped key, contains, and fuzzy behavior. Added deterministic contract coverage in `tests/test_tool_result_contracts.py` and updated lookup expectations. Next dependency was Step 4.
- **Cross-tool result/evidence Step 4 — `impact_analysis` contract (2026-09-30 12:31 CEST, Europe/Paris): complete.** Preserved the full graph subgraph and aggregate calculations. Added a separate evidence object containing the anchor, at most two additional nodes, and only edges whose endpoints are in that sample; all statuses now include `error`, and query errors carry a useful message. Added mocked checks for aggregate values, full subgraph retention, bounded evidence, and error shape. Next dependency was Step 5.
- **Cross-tool result/evidence Step 5 — `co_purchase` contract (2026-09-30 12:31 CEST, Europe/Paris): complete.** Each recommendation now contains a canonical Product reference, co-occurrence count, and pair-scoped evidence for anchor and recommended product. It does not return every shared Order. Added common error fields, preserved ranking/cap/tie-break behavior, and added deterministic success/error coverage. Next dependency was Step 6.
- **Cross-tool result/evidence Step 6 — `customer_history` contract (2026-09-30 12:31 CEST, Europe/Paris): complete.** Each order now has a canonical Order handle plus its date, total, and ship country, with Customer and Order node handles and the PURCHASED edge attached to that order. The query does not return line items solely for citations. Added consistent status/error payloads and deterministic evidence/error tests. Next dependency was Step 7.
- **Cross-tool result/evidence Step 7 — `aggregate` contract (2026-09-30 12:31 CEST, Europe/Paris): complete.** Kept fixed grouped metrics and whitelists. Each group now carries `evidence: {nodes, edges}` with at most three canonical representative handles; the query itself limits the returned evidence sample. Added useful validation/execution errors and mocked tests for sample bounds and payload shape. Next dependency was Step 8.
- **Cross-tool result/evidence Step 8 — `run_readonly_cypher` contract (2026-09-30 12:31 CEST, Europe/Paris): complete.** Kept the R1 normalized row envelope, attempts, and terminal errors; added a useful error for an empty/non-string query. Updated the agent's metric/ranking query examples to return at most three representative graph records rather than every contributor. Updated PROJECT.md examples and the Step 3–8 file lists in PLAN.md. No pytest test called AuraDB or Mistral.
- **Steps 3–8 verification and handoff (2026-09-30 12:31 CEST, Europe/Paris):** `uv run --no-sync python -m pytest -q -o addopts='' tests/test_tool_result_contracts.py tests/test_run_readonly_cypher.py tests/test_lookup_entity.py tests/test_agent.py tests/test_tools_node.py tests/test_contract_flow.py tests/test_synthesize.py -k 'not TestLookupEntity and not test_show_customer_by_key_has_details_citation_and_consistent_trace'`: **68 passed, 9 deselected** (8 legacy live AuraDB lookup tests and one end-to-end synthesis test). `python -m py_compile src/neo4j/tools.py src/agents/llm.py` and `git diff --check` passed. The excluded R6 flow test now observes the new nested lookup result but synthesis still expects the old flat match shape; the curated tool Q&A integration therefore needs the planned Step 11 synthesis adaptation before it is considered app-ready. The legacy live test cases were not run. Next: Step 9, shared runtime result validation.


## Cross-tool result/evidence Steps 9–16 (2026-09-30)

- **Step 9 — Shared runtime result validation (12:38 CEST, Europe/Paris): complete.** Added `src/neo4j/result_contracts.py` with TypedDict schemas and runtime checks for common status/error fields, required payloads, canonical node/edge handles, claim-local evidence association, evidence bounds, retry status rules, and JSON safety. Added deterministic valid/invalid contract cases in `tests/test_result_contracts.py`; focused tests passed. Next: Step 10.
- **Step 10 — Dispatcher and trace integration (12:41 CEST): complete.** `execute_tool_step` now validates every tool result before it reaches a `ToolMessage`; execution exceptions and malformed results become valid per-tool failure envelopes. The validated result is serialized unchanged, and trace status/row count/retry count derive from that same result. Dispatcher tests cover schema rejection and trace consistency. Next: Step 11.
- **Step 11 — Evidence-policy synthesis (12:48 CEST): complete.** Rewrote synthesis for all six structured tool payloads. It uses each claim's associated evidence, limits inline computed-claim evidence to three handles, keeps lists bounded, distinguishes empty/invalid/unsupported results, and blocks scalar-only unsupported claims. Added recovery-aware unsupported reporting. Focused synthesis and flow tests passed. Next: Step 12.
- **Step 12 — Bounded recovery and prompt guidance (12:52 CEST): complete.** The agent requests one same-claim recovery call after a successful result without sufficient node evidence and then stops; `MAX_STEPS=8` and tool signatures are unchanged. Prompt guidance requests a metric plus anchor and up to three representative handles. Added a test proving the agent does not call the model again after the recovery result. Next: Step 13.
- **Step 13 — Deterministic per-tool contract tests (12:55 CEST): complete.** Added mocked success, empty, and execution-failure coverage across the six tools in `tests/test_tool_result_contracts.py`. Removed the previous legacy test modules that directly contacted AuraDB from pytest collection; those files now point to the deterministic replacement suite. No pytest test calls AuraDB or Mistral. Next: Step 14.
- **Step 14 — Cross-tool evidence-policy tests (12:57 CEST): complete.** Added/updated checks for structured lookup, aggregates, exploratory count/ranking, scalar-only evidence recovery, invalid-versus-empty results, pair-local co-purchase citations, dispatcher trace consistency, and bounded recovery. All focused tests passed. Next: Step 15.
- **Step 15 — Deterministic project acceptance (12:59 CEST): complete.** `uv run pytest -q`: **206 passed** in 21.04 seconds. The full collected suite is deterministic and makes no live service calls. Next: Step 16.
- **Step 16 — App retest and Phase 3.6 handoff (13:00 CEST): complete.** Restarted Streamlit with `uv run streamlit run src/streamlit/app.py --server.headless true`; `http://127.0.0.1:8501/_stcore/health` returned `200 ok`. Through the compiled app runtime, live read-only checks returned: 91 customers with three representative customer citations; Save-a-lot Markets as top customer with 31 orders and customer/order citations; Camembert Pierrot as most ordered product with 1,577 units and product/order citations; Exotic Liquids impact of 3 products, 90 orders, and $35,916.80 with supplier/product/order citations; and a missing customer as a successful empty lookup with no citations. Initial live ranking checks exposed Mistral rewriting the count and citation syntax. Synthesis now accepts rewrites only if they preserve every grounded number and literal citation syntax; both ranking checks passed after the fix. Graph scenarios were run via the compiled app runtime rather than browser automation; the Streamlit server is running and available on port 8501 for UI inspection. Phase 3.6 is unblocked.

- **Files for Steps 9–16:** `src/neo4j/result_contracts.py`, `src/agents/nodes.py`, `src/agents/llm.py`, `src/neo4j/tools.py`, `tests/test_result_contracts.py`, `tests/test_tool_result_contracts.py`, `tests/test_tools_node.py`, `tests/test_agent.py`, `tests/test_synthesize.py`, `tests/test_contract_flow.py`, and the legacy tool test modules now superseded by the deterministic contract suite.


## Step 16 follow-up — exhaustive customer history (2026-09-30 13:56 CEST, Europe/Paris)

The live prompt “List all 31 orders by Save-a-lot Markets” exposed a synthesis-only `orders[:10]` cap. `customer_history` itself had no Cypher row limit and returned all 31 records; synthesis showed ten while implying that was the full result, and computed the largest gap from only those ten. Updated synthesis so explicit all/every/each order requests list all returned evidenced orders, ordinary history answers disclose when only the first ten are shown, and gap analysis uses the complete result. Updated PROJECT.md §4.4 with these semantics. Tightened LLM rewrite validation to reject added numeric annotations such as `[1]`, as well as dropped numbers, by requiring exact number preservation.

Verification: live read-only `customer_history("SAVEA")` returned status `ok` with 31 orders; synthesized exhaustive answer contained 31 order lines and 31 order citations, with a 78-day maximum gap across the full history. `uv run pytest -q`: **209 passed**. This resolves the observed case; the app server remains stopped at the user's request.


## Prompt and schema authority cleanup (2026-09-30 14:06 CEST, Europe/Paris)

Removed the unused `AGENT_SYSTEM_PROMPT`; `AGENT_SYSTEM_PROMPT_TEMPLATE` is the single active ReAct prompt. Removed the hardcoded partial graph-schema fallback and unused generated tool-description plumbing. The agent now requires `generate_schema_prompt()` to succeed before constructing the Mistral request, so missing/broken SCHEMA.md projection surfaces as an error instead of silently changing the model's schema context. Removed the now-unused tool-list parameter from the internal `agent_step` / `generate_agent_response` path.

Added a PROJECT.md authority section: SCHEMA.md owns graph facts; PROJECT.md owns application/tool/evidence contracts; `schema_prompt.py` is a generated projection; prompt text guides model choices; `result_contracts.py`, agent control flow, and synthesis enforce the executable parts; `ToolCallRecord` is call metadata while the full result is in `ToolMessage`. Added deterministic prompt tests for generated-schema injection, absence of the obsolete constant, and propagation of schema-generation failure before any Mistral request. `uv run pytest -q`: **211 passed**; `git diff --check` passed. No live services used.


## Mistral API-key and model selection (2026-09-30 14:16 CEST, Europe/Paris)

Updated `src/agents/llm.py` so `get_mistral_client(api_key=None)` uses an explicit key when supplied, otherwise loads `.env` and reads `MISTRAL_API_KEY`; absence of both raises a clear configuration error. Added `complete_mistral_chat(..., api_key=None, model_name=None)` because Mistral's SDK selects the model on each chat request, not during client construction. An omitted model name defaults to `mistral-large-latest`; classify explicitly selects `mistral-small-latest`. Agent generation and evidence rewriting accept optional key/model overrides; Cypher repair uses the shared request helper. Updated PROJECT.md §8 to state that the key and model are independent and that one key can be used with available Mistral models. Added deterministic tests for explicit/env key resolution, missing keys, Large default, alternate model selection, and prompt behavior. `uv run pytest -q`: **215 passed**. No live Mistral request was made.

## Answer completeness remediation — Steps 1 and 2 (2026-09-30 14:47 CEST, Europe/Paris)

**Step 1 — Contract for answer drafts and consistency checking: complete.** Amended `PROJECT.md` §2–3 to define `FINAL:` as a request for a synthesized draft, followed by a consistency check that validates requested subjects/operation/constraints and evidence support. A passing draft alone is committed as the final answer; a failed draft returns specific feedback to the agent. The contract preserves `loop_count` and `MAX_STEPS=8` across retries, keeps evidence recovery bounded, and does not change tool signatures or evidence policy. Added the corresponding roadmap items before Phase 3.6 in `PLAN.md`.

**Step 2 — Route tool guidance by intent: complete.** Updated the active agent prompt to distinguish a single customer's order history/count/pattern from comparisons and intersections involving multiple customers. Added a SAVEA/ALFKI shared-products Cypher example that returns a Product node and one representative evidence path per customer, with guidance to select tools by the requested operation rather than keyword presence. Clarified that `FINAL:` requests a candidate synthesis and consistency check, rather than asserting completeness. Added a deterministic prompt regression test. Stop behavior is unchanged and remains Step 3.

Verification: `uv run pytest -q tests/test_agent_prompt.py`: **7 passed**; `git diff --check` passed. No Mistral or Neo4j calls were made. Next: Step 3, remove success-based forced `FINAL` behavior.

## Answer completeness remediation — Step 3 (2026-09-30 15:02 CEST, Europe/Paris)

**Step 3 — Remove success-based forced `FINAL` across tools: complete.** Audited every agent-side `FINAL:` insertion and the graph's agent routing. Removed the forced stop after successful (`ok`/`retry_ok`) results for all six tools: `lookup_entity`, `impact_analysis`, `co_purchase`, `customer_history`, `aggregate`, and `run_readonly_cypher`. Successful results, including an evidence-recovery result, now return to the model for its next decision; after a recovery call the model receives a reminder not to repeat that recovery. Curated `empty` results also return to the model. Retained terminal synthesis for exploratory `empty`, `invalid`, and `retry_failed` outcomes, and budget exhaustion still routes to `degrade`.

Added deterministic checks for all six tool success paths, Cypher `retry_ok`, curated empty continuation, exploratory terminal outcomes, and model control after the bounded recovery result. Verification: `uv run pytest -q tests/test_agent.py tests/test_contract_flow.py tests/test_graph.py`: **41 passed**; `git diff --check` passed. The finalization-path audit found no other automatic success-based stop in `agent_step` or `route_from_agent`; remaining `FINAL:` insertion there is limited to exploratory empty/invalid/retry-failed outcomes. A model-generated `FINAL:` continues to route to synthesis by design. No Mistral or Neo4j calls were made. Next: Step 4, explicit draft state and synthesis behavior.

## Answer completeness remediation — Steps 4–7 (2026-09-30 15:33 CEST, Europe/Paris)

**Step 4 — Explicit draft state and synthesis: complete.** Added `draft_answer`, `draft_citations`, `consistency_status`, and `consistency_feedback` to `AgentState` and initialized them in the Streamlit and CLI runners. Synthesis now produces only draft fields. Accepted `answer`, `citations`, and deterministic rubric confidence are committed only by a passing consistency check; a rejected draft clears accepted fields, and budget degradation clears the draft.

**Step 5 — Consistency-check node: complete.** Added deterministic citation-to-result integrity checks and coverage checks for multiple explicit Northwind IDs. The node also calls a Mistral Large reviewer with the original question, compact structured tool results/evidence, citations, and candidate answer to assess requested operation/constraints. It requires structured JSON and fails closed on malformed output or API errors with actionable feedback. Tool properties are omitted and nested data is bounded before sending the review context.

**Step 6 — Retry routing and shared budget: complete.** Wired `synthesize → consistency_check`; passing candidates reach `END`, revise results return to `agent`, and the existing `loop_count` is preserved. Budget exhaustion routes to `degrade` before candidate acceptance; the checker has no self-loop.

**Step 7 — End-to-end completeness acceptance: complete.** Added a mocked compiled-graph regression reproducing the SAVEA/ALFKI failure: SAVEA-only customer history is rejected with ALFKI-specific feedback, the agent issues an exploratory query returning representative paths for both customers and Chai, and the checker accepts the answer with citations for both customers and the product. Added a budget-boundary flow proving a rejected draft does not reset the counter and exhaustion degrades.

Verification: `uv run pytest -q`: **228 passed** before the final budget-routing precedence adjustment; after that adjustment, `uv run pytest -q tests/test_contract_flow.py tests/test_graph.py`: **27 passed**. `uv run python -m py_compile` passed for the modified modules and tests, and `git diff --check` passed. No live Mistral or Neo4j calls were made. The semantic reviewer adds one Mistral Large request for each factual candidate that requires review. Next: Step 8, independent scroll areas for Chat, Trace, and Evidence Graph.


## Answer completeness and UI refinement — Steps 8–10 (2026-09-30 15:45 CEST, Europe/Paris)

**Step 8 — Independent scroll areas: complete.** Reworked the app into three side-by-side panels. Chat history, Trace/Confidence, and Evidence Graph each have their own 450 px bordered scroll region. The chat input stays below the history container, with auto-scroll enabled for new messages. Updated the Streamlit minimum from 1.29 to 1.35 because fixed-height scroll containers are required, and refreshed `uv.lock`.

**Step 9 — Traceable Explainability heading: complete.** Added the requested title above separate Trace and Confidence expanders. Chat, Traceable Explainability, and Evidence Graph all use the same Streamlit subheader level.

**Step 10 — Integrated acceptance: complete.** Added `tests/test_streamlit_app.py`. AppTest confirms all three fixed-height panels, shared heading level, the Trace and Confidence subwindows, and a mocked single-customer chat exchange with long answer content and returned state. Existing compiled-graph acceptance tests passed for the SAVEA/ALFKI shared-products question and the ALFKI customer lookup. Started the app with `uv run streamlit run src/streamlit/app.py --server.headless true --server.port 8502`; HTTP smoke check returned **200**, then the process was stopped. Full suite: `uv run pytest -q`: **230 passed**. `git diff --check` passed. No live Neo4j or Mistral calls were made.

Browser-level scrolling and visual layout were not manually exercised in the user's forwarded VS Code browser; the automated checks verify the configured independent scroll areas and rendering. Next: resume Phase 3.6 when ready.

## Post-Step-10 whole-graph count follow-up (2026-09-30 15:55 CEST, Europe/Paris)

The live question “how many nodes are there in the graph?” ran one valid exploratory query, `MATCH (n) RETURN count(n) AS node_count, collect(DISTINCT n)[0..3] AS evidence_nodes`, but still exhausted `MAX_STEPS=8`. The query and its evidence were successful; the failure was the agent control flow requiring an explicit `FINAL:` marker. A no-tool completion after a successful tool result now routes to candidate synthesis and the existing consistency check, so it cannot bypass evidence or completeness validation. Generic `node_count` is mapped to “nodes” rather than inferred from one sampled node label. Added a compiled-graph regression that verifies the answer is accepted after one tool call, with representative citations and the shared loop counter intact. Updated PROJECT.md and PLAN.md. Verification: `uv run pytest -q`: **231 passed**; targeted shared-customer and budget-boundary flows passed; `git diff --check` and Python compilation passed. No live Mistral or Neo4j calls were made during the fix. Please restart the Streamlit app before retrying the question.

## Whole-graph count recovery correction (2026-09-30 16:04 CEST, Europe/Paris)

The user's retest still exhausted the loop. Its new trace showed a scalar-only query (`MATCH (n) RETURN count(n) AS total_nodes`), so the previous no-tool handoff change did not run: `agent_step` was instead repeatedly asking the model to recover evidence. Added a bounded deterministic recovery for this specific whole-graph node-count shape when a successful Cypher row has a numeric `node_count`/`total_nodes` and no node evidence. It issues exactly one read-only query returning the same total plus at most three representative nodes. The regular result validator, synthesis, and consistency check remain in the path. Added handling for `total_nodes` as a generic node metric and a compiled-graph regression proving the two tool records, bounded counter (3 turns), final numeric answer, and representative citations. Updated PROJECT.md and PLAN.md to record the specific rule and corrected the prior diagnosis. Verification: `uv run pytest -q`: **232 passed**; targeted whole-graph count and shared-customer flows passed; `git diff --check` and py_compile passed. No live services called. Restart the app before another retest.


## Whole-graph count follow-up — direct evidence handoff (2026-09-30 16:12 CEST, Europe/Paris)

The user retested and still saw budget exhaustion, even though the last successful Cypher query included `collect(DISTINCT n)[0..3] AS evidence_nodes`. Run-log confirmed one tool call at agent step 6; the agent was spending further turns after an evidence-adequate result. Changed the tools-node edge: successful results with adequate associated node evidence now go directly to synthesis and the consistency checker, without requesting another ReAct decision. Empty/evidence-inadequate results still return to the agent; failed candidates still loop back with the shared budget; exhaustion still degrades. This is the later contract amendment that supersedes the earlier “successful result returns to model” behavior in answer-completeness Step 3. Updated PROJECT.md architecture and diagram. Regression tests prove the SAVEA/ALFKI incomplete history still gets rejected and retried, while an evidence-complete whole-node count is synthesized and accepted after one tool call. The scalar-only count still receives one bounded evidence recovery. Verification: targeted graph-flow tests **4 passed**; full `uv run pytest -q`: **232 passed**. `uv run python -m py_compile src/agents/graph.py src/agents/nodes.py tests/test_contract_flow.py` and `git diff --check` passed. No live service calls were made. Restart the app and retest.

## Whole-graph count — live diagnosis and verified fix (2026-09-30 16:24 CEST, Europe/Paris)

A third user retest still degraded after one successful evidence-bearing Cypher query at Step 1. Ran that exact query read-only against Neo4j and inspected synthesis: it returned `total_nodes=1104` with three representative Territory nodes, but synthesis wrongly treated the first sampled Territory as the count's scope anchor. Its draft claimed 1,104 nodes were associated with Westboro, so the consistency reviewer appropriately rejected it and later retries exhausted the budget. The earlier mocked tests asserted only that the count and citations appeared, allowing this false scope to pass.

Fixed count synthesis so a scope anchor must be a node returned as its own value column; nodes in `evidence_nodes` are representative evidence only. Whole-graph node totals retain the deterministic dataset-total sentence and skip the optional wording rewrite, which can otherwise alter scope without changing numbers or citation markers. Strengthened the compiled-graph regression with the live-style row shape, the exact dataset-total wording, and a mock that would introduce a misleading scoped rewrite. The scoped customer-order count regression still passes. Updated PROJECT.md evidence semantics and PLAN.md's follow-up note.

Live end-to-end validation (read-only Neo4j and Mistral; invoked the compiled graph directly without writing a run-log entry): **route `agent`, loop_count 1, one successful Cypher tool call, consistency `pass`**, answer: “The Northwind dataset contains 1,104 nodes. Representative evidence: [Territory:01581] [Territory:01730] [Territory:01833].” Full deterministic suite: `uv run pytest -q`: **232 passed**. Python compilation and `git diff --check` passed. Restart Streamlit to load the corrected graph before the next browser retest.


## Redesign foundation — Phase 0.1 to 0.3 (2026-10-06 14:35 CEST, Europe/Paris)

**0.1 — Archive current implementation: complete.** Created `archive/legacy/` as a recoverable snapshot of commit `93b766c`, including the prior source, tests, contracts, and documentation. Added `archive/legacy/ARCHIVE_MANIFEST.md` identifying the snapshot, date, purpose, and runtime boundary. The archive is reference-only; the redesigned runtime will not import from it.

**0.2 — Create new repository layout: complete.** Added the shared `common/` boundary and four architecture directories: `generic`, `generic_reflection`, `curated`, and `curated_reflection`. Added README placeholders documenting ownership and the future architecture-specific `PROJECT.md` contracts.

**0.3 — Define common runtime boundary: complete.** Added boundary documentation for shared configuration, evaluation, MLflow, Neo4j, and schema/prompt projection. The documentation records the fixed conversational-model role, selectable Cypher-model role, configurable MLflow tracking URI, read-only Neo4j boundary, and separation between common services and architecture-specific graph state.

Verification: archive contents were created from the committed implementation; new directories and boundary documents are present; the existing `PLAN.md` and source tree were not overwritten; no application code was changed. Item 0.4 (copying the canonical benchmark CSV) remains next.

**Archive adjustment — ground-truth documents (2026-10-06 14:35 CEST, Europe/Paris).** Verified that all five root `GROUND_TRUTH*.md` files were byte-identical to the copies in `archive/legacy/`, then removed the active-root duplicates. Updated the archive manifest to list the preserved legacy ground-truth documents. The new benchmark artifact for the redesigned project remains a separate Phase 0.4 item.

## Redesign foundation — Phase 0.4 (2026-10-06 14:42 CEST, Europe/Paris)

**0.4 — Add canonical benchmark: complete.** Added `benchmark/northwind_questions.csv` with the 20 benchmark questions across the four agreed groups. Preserved the ground-truth answer column and the informational Cypher provenance in `Comment`; the Cypher is not treated as the generated answer or a scoring target. Added `benchmark/README.md` documenting the columns and evaluation boundary.

Verification: the CSV contains exactly 20 question records, five per group, with multiline answers and Cypher comments quoted as valid CSV fields. The benchmark remains independent of all architecture directories. No model or Neo4j calls were made.

## Architecture 1 contract — item 1.1 (2026-10-06 14:45 CEST, Europe/Paris)

**1.1 — Architecture contract: complete.** Added `architectures/generic/PROJECT.md` for the first redesigned architecture: fixed conversational Mistral model, configurable Cypher-generation model, router, generic Text2Cypher tool, three-total-attempt Cypher validation loop, Neo4j execution, draft/final answer generation, and flat MLflow logging. The contract defines the minimal AgentState without the archived trace, citation, confidence, or rubric systems; it specifies node responsibilities, graph edges, function signatures, prompt/schema authority, failure behavior, non-goals, and acceptance criteria.

Verification: contract references shared `SCHEMA.md` and `common/` boundaries, defines no curated tools or self-reflection for Architecture 1, and preserves the agreed three-attempt Cypher bound. No application code, model calls, or Neo4j calls were made. Next: user review of `architectures/generic/PROJECT.md` before item 1.2 implementation.

**Architecture 1 contract amendments — item 1.1 clarification (2026-10-06).** Applied the agreed design decisions: Cypher validation failures are structured `ToolMessage` results consumed by the next Text2Cypher call; `generate_cypher` handles both initial generation and repair through optional `previous_query` and `validation_error` arguments; `generate_final_answer` was removed in favor of one `generate_answer` function; and Neo4j `EXPLAIN` is the non-executing preflight check before query execution. No implementation code changed. Item 1.2 remains blocked on user approval of the amended contract.

## Architecture 1 foundation — items 1.2 to 1.5 (2026-10-06 15:19 CEST, Europe/Paris)

**1.2 — LangGraph state: complete.** Added `architectures/generic/state.py` with the minimal `AgentState`, `Route` type, `add_messages` reducer, and explicit bounds for high-level agent turns and three total Cypher attempts. The state contains no archived trace, span, citation, confidence, or rubric fields.

**1.3 — LangGraph topology: complete.** Added `architectures/generic/graph.py` and `nodes.py`. The graph implements router branching, agent entry, Text2Cypher, validation, Neo4j, answer generation, terminal handling, and the bounded invalid-query loop. Chitchat and refusal bypass graph access.

**1.4 — Function and tool signatures: complete.** Added `architectures/generic/interfaces.py` with injected handler protocols for routing, combined initial/repair Cypher generation, validation, read-only execution, and one-step answer generation. Validation failures are carried as structured `ToolMessage` values with deterministic tool-call IDs.

**1.5 — Foundation tests: complete.** Added `tests/test_generic_foundation.py` with deterministic fakes covering reducer metadata, interface signatures, valid execution, validation-error feedback into a rewrite, three-attempt termination, chitchat, and refusal. Verification: `uv run --no-sync pytest -q tests/test_generic_foundation.py -o addopts=` — **7 passed**. Python compilation and `git diff --check` passed. No live model or Neo4j calls were made. Next: user review of the implemented foundation before Phase 2.1.

**Architecture 1 route-aware answer fix (2026-10-06).** Updated the `generate_answer` contract and handler protocol to receive the explicit router route. `answer_generation_node` now passes `state["route"]`, so chitchat, refusal, and agent behavior are selected intentionally rather than inferred from query-result presence. Updated the deterministic fake and contract documentation; no live services were used.

## Architecture 1 — Phase 2.1 (2026-10-06 16:15 CEST, Europe/Paris)

**2.1 — Schema prompt projection: complete.** Added `common/prompts/schema_prompt.py`, a mechanical projector that reads the repository-root `SCHEMA.md` and extracts node labels, keys, name properties, relationship directions, structural facts, traversal patterns, read-only rules, and the verified revenue rule. It exposes cached prompt generation plus component accessors for later tools. The projector accepts an explicit schema path for deterministic tests and has no hand-maintained graph facts.

Added `tests/test_generic_schema_prompt.py` covering all nine labels, all nine relationships, the corrected `PURCHASED` direction, traversal patterns, the revenue rule, prompt content, caching, and a temporary-schema proof that the output is not hardcoded. Verification: `uv run --no-sync pytest -q tests/test_generic_schema_prompt.py -o addopts=` — **5 passed**; Python compilation and `git diff --check` passed. No model or Neo4j calls were made. Next: Phase 2.2, the generic Text2Cypher tool.

**Phase 2.1 prompt corrections (2026-10-06 16:29 CEST, Europe/Paris).** Updated the projector to parse relationship properties whose type annotations contain commas, so `ORDERS` now renders `quantity`, `unitPrice`, and `discount` correctly. Updated `SCHEMA.md` to state the agreed three-total-attempt Cypher bound instead of the stale one-retry rule. Architecture 1 now omits the impact-analysis traversal example by default; a named option can include it for a later architecture. Verification: `uv run --no-sync pytest -q tests/test_generic_schema_prompt.py -o addopts=` — **6 passed**; generated-prompt assertions confirmed the impact example is absent by default, the relationship properties are clean, and the three-attempt rule is present. No model or Neo4j calls were made.

## Architecture 1 — Phase 2.2 (2026-10-06)

**2.2 — Generic Text2Cypher tool: complete.** Added `architectures/generic/text2cypher.py` with an injected provider-neutral chat client and per-call `model_name` selection. Initial generation and validation-error repair share one `generate_cypher` function; repair prompts include the previous query and validator error. The tool accepts the generated query as text, removes common Markdown code fences, and leaves syntax/read-only enforcement to Phase 2.3. Added the `Text2CypherTool` adapter matching the Architecture 1 handler shape.

Added `tests/test_generic_text2cypher.py` covering selected-model propagation, prompt context, rewrite context, repair-argument validation, Markdown cleanup, and empty model output. Verification: the focused Text2Cypher tests pass; no live model or Neo4j calls were made. Next: Phase 2.3, Cypher validation.

## Architecture 1 — Phases 2.3 to 2.6 (2026-10-06)

**2.3 — Cypher validation: complete.** Added `common/neo4j/validation.py`. The validator normalizes one terminal semicolon, rejects internal/multiple statements and write clauses, requires a read/yield result, checks labels and explicit properties against the supplied schema, and supports an injected Neo4j `EXPLAIN` callback. Validation returns structured data and does not raise for an invalid generated query.

**2.4 — Bounded rewrite loop: complete.** Kept the three-total-attempt loop in the compiled graph and made the service boundary explicit: each validation result is wrapped by `validate_cypher_node` in a `ToolMessage`, and the next Text2Cypher call receives the failed query and error. The validator and executor contain no hidden retries, so a third failure terminates predictably.

**2.5 — Neo4j execution: complete.** Added `common/neo4j/executor.py` with a `Neo4jTool` adapter and read-only execution through either the driver's `execute_query` API or a session factory. It executes only the normalized query and returns structured failed outcomes instead of leaking driver exceptions into graph state.

**2.6 — Generic result envelope: complete.** Added `common/neo4j/results.py`. Every execution result contains `status`, `query`, `rows`, `evidence`, and nullable `error`; rows preserve scalars and nested JSON-safe nodes, relationships, paths, lists, and maps, while evidence is deduplicated. Empty successful results are distinguished from execution failures. Added `tests/test_generic_services.py` for validation, EXPLAIN injection, bounded execution outcomes, and representative result shapes.

Verification: `uv run --no-sync pytest -q tests/test_generic_services.py tests/test_generic_foundation.py tests/test_generic_text2cypher.py -o addopts=` — **17 passed**; Python compilation and `git diff --check` passed. No live Neo4j or model calls were made. Next: Phase 3.1, draft answer generation and raw structured-output logging.

## Architecture 1 — Phases 3.1 to 3.5 and A1 completion work (2026-10-06)

**3.1 — Draft answer generation: complete.** Added `architectures/generic/conversation.py` with a provider-neutral conversational client, route prompt, answer prompt, JSON extraction, and plain-text fallback. The answer model receives the question, validated query, and generic result envelope. Its structured result is preserved when valid; malformed JSON remains visible as answer text with a null structured result.

**3.2 — Accepted answer handoff: complete for Architecture 1.** The existing `answer_generation_node` intentionally writes both draft and accepted fields in one call. This is the baseline architecture's direct handoff; no second final-answer model call is introduced. Later architectures may insert review/reflection between those fields.

**3.3 — Self-reflection boundary: complete for Architecture 1 as an explicit no-op.** No reflection node is added to the generic baseline, per its contract. The state and graph leave the shared loop counter available for Architecture 2, where reflection will be a separate architecture-specific node.

**3.4 — No-feedback path: complete.** The compiled generic graph routes a successful validated result directly to answer generation and then terminal. Chitchat and refusal use explicit route-specific answer instructions and never access Neo4j.

**3.5 — Architecture acceptance foundation: complete.** Added conversational adapter tests and retained the compiled-graph tests for valid execution, bounded repair, terminal failure, chitchat, and refusal. The generic architecture now has concrete provider-neutral Text2Cypher, validation, Neo4j, result-envelope, routing, and answer-generation services.

**A1.1/A1.2 — Contract and implementation: complete.** The Architecture 1 contract and Phases 1–3 implementation are now represented in code and tests. Added `common/config/models.py` for selectable Cypher candidates and `common/evaluation/model_selection.py` for deterministic baseline selection from completed run results.

**A1.3/A1.4 — Sweep support: implemented, live execution pending.** Candidate metadata and deterministic selection are ready, but the frontier/Neo4j model sweep and baseline decision require configured provider credentials, live model calls, Neo4j access, and MLflow tracking. No model was selected implicitly and no live calls were made in this session.

Verification: `uv run --no-sync pytest -q -o addopts=''` — **264 passed**; Python compilation and `git diff --check` passed. No live model, Neo4j, or MLflow calls were made.

## Plan amendment — shared Phase 4 (2026-10-06)

Revised `PLAN_REDESIGN.md` Phase 4 from MLflow-only work to **Shared Runtime,
Evaluation, and MLflow Integration**. It now contains eight independently
verifiable items: shared settings, conversational and Cypher provider adapters,
runtime factory, architecture registration, live smoke harness, MLflow run
service, and an end-to-end runtime acceptance gate. Architecture 1 model sweep
and baseline selection now explicitly depend on this shared runtime and the
benchmark runner. The architecture-specific contracts remain responsible for
their own state and graph topology.

**Plan ordering correction (2026-10-06).** Moved the Phase 4 section so it is
immediately after the common Phase 3 table and before Architecture 1–4. This is
the actual dependency order: shared settings, provider adapters, runtime
factory, smoke harness, and MLflow must exist before architecture-specific live
runs or model sweeps.

## Phase 4.1 — Shared settings loader (2026-10-08)

**4.1 — Shared settings loader: complete.** Added
`common/config/settings.py` and exported its typed settings classes through
`common.config`. `load_settings()` reads `.env` with process environment
precedence, supports injected mappings for deterministic tests, and covers
Neo4j, conversational/Cypher model roles and key selectors, prompt/schema
versioning, Streamlit, MLflow, application metadata, and logging. Secret values
are excluded from dataclass representations and `public_metadata()`; the
loader does not print credentials. Added `.env.example` entries for the new
runtime roles and MLflow settings.

Verification: the real `.env` loaded successfully without exposing credentials;
`uv run --no-sync pytest -q -o addopts=''` — **270 passed**. No Neo4j, model, or
MLflow calls were made. Next: Phase 4.2, the conversational provider adapter.

## Phase 4.2 — Conversational provider adapter (2026-10-08)

**4.2 — Conversational provider adapter: complete.** Added
`common/providers/mistral.py` and its package export. `MistralChatClient`
implements the provider-neutral conversational client protocol used by the
Architecture 1 router and answer generator, passes the configured model name,
messages, temperature, and token limit to `client.chat.complete`, and returns
the raw SDK response unchanged. `build_mistral_client()` consumes the Phase
4.1 settings object and rejects a non-Mistral conversational provider. The SDK
import and client construction are lazy, so deterministic tests do not contact
Mistral or require a live client.

Added five provider tests covering request mapping, key requirements, settings
integration, provider mismatch, and invalid request parameters. Verification:
focused provider/configuration/conversation tests **17 passed**; no live model
request was made. Next: Phase 4.3, manual Ollama/Gemma runtime preparation.

## Plan amendment — Phase 4.3 Ollama preparation (2026-10-08)

Added a dedicated Phase 4.3 item to `PLAN_REDESIGN.md` for manual Ollama
preparation before the Cypher provider registry. The approved candidate is the
quantized Neo4j Gemma 3 4B model:
`hf.co/mradermacher/text-to-cypher-Gemma-3-4B-Instruct-2025.04.0-GGUF:Q4_K_M`.
The item covers installing Ollama, downloading the model, starting the local
service, checking `ollama list`, exercising the local API with a Cypher prompt,
and recording hardware, model tag, and endpoint. Downstream Phase 4 items were
renumbered to 4.4–4.9, and the default candidate metadata now identifies this
model as an Ollama provider with no API key.

**Phase 4.3 environment verification update (2026-10-08).** On `deel14`, the
Ollama service responded successfully for the selected model when the request
included `options.num_gpu=0`. The model returned valid Cypher (`MATCH (n)
RETURN COUNT(n)`) in approximately 11.4 ms as reported by Ollama's nanosecond
duration field. NVIDIA GPU initialization is
currently blocked by a driver/library mismatch reported by `nvidia-smi`; CPU
inference is therefore the working path until the host driver is repaired. The
Ollama provider adapter in Phase 4.4 must support this runtime option, either per
request or through service configuration. Phase 4.3 remains open for recording
the Ollama version, installed model listing, hardware details, and final
endpoint configuration.

## Phase 4.4 to 4.6 — Provider registry, runtime factory, and architecture registration (2026-10-08)

**4.4 — Cypher provider registry: complete.** Added
`common/providers/ollama.py` and `common/providers/cypher.py`. The Ollama
adapter calls `/api/chat`, uses non-streaming responses, passes the configured
`num_gpu` option (currently `0` for CPU mode), and preserves the raw response.
The registry selects Mistral or Ollama clients by exact model name and skips
providers without an implemented adapter rather than silently substituting a
different model. The Ollama response shape is now accepted by Text2Cypher.

**4.5 — Runtime factory: complete.** Added `common/runtime/factory.py` with
`AgentRuntime` and `build_runtime()`. It loads the configured schema and prompt,
composes conversational, Cypher, validation, and Neo4j services into the
Architecture 1 handler contract, and returns a compiled graph plus runtime
metadata. Dependencies remain injectable for deterministic tests.

**4.6 — Architecture registration: complete.** Added
`common/runtime/architectures.py`. The registry exposes `generic`,
`generic_reflection`, `curated`, and `curated_reflection`; only `generic` is
currently buildable, while the planned architectures fail explicitly as
unimplemented instead of silently falling back.

Added provider and runtime tests covering Ollama request construction, CPU
configuration, registry selection, duplicate/unknown models, runtime
composition, and architecture errors. Verification: focused tests **18
passed**; no live model or Neo4j call was made by the tests.

## Phase 4.7 — Live smoke-test harness (2026-10-08)

**4.7 — Live smoke-test harness: complete.** Added
`scripts/run_smoke_test.py`. The script loads shared settings, builds the
selected runtime, invokes one question through the compiled graph, and prints
JSON containing the route, loop count, answer, structured result, generated
Cypher, validation attempts, Neo4j result envelopes, and terminal error. It
supports architecture and model overrides and works in the documented direct
script form:

```bash
uv run python scripts/run_smoke_test.py --question "How many customers are there?"
```

The formatter is deterministic and does not create a second trace system or
persist output; MLflow logging remains Phase 4.8. Verification: smoke-harness
tests **2 passed**, CLI help works, Python compilation and `git diff --check`
passed. No live model or Neo4j request was made from this environment.

**4.7 live retest correction (2026-10-08).** The first live run reached the
conversational provider but failed while parsing the Mistral SDK response:
Mistral returns an object with `choices[0].message.content`. Extended the shared
conversation parser to support that object shape and added a regression test.
Focused tests passed, followed by the full deterministic suite: **285 passed**.
The original smoke command can now be retried on `deel14`.

**4.7 live query-validation correction (2026-10-08).** The first successful
Ollama/Mistral smoke run generated three semantically valid queries, but Ollama
returned literal `\\n` sequences. The validator therefore failed to recognize
the `RETURN` clause and rejected all three before Neo4j; no value was returned
because execution never started and `EXPLAIN` was never reached. Updated
Text2Cypher cleanup to decode common escaped whitespace sequences and wired the
runtime handler's validation through Neo4j `EXPLAIN` via `Neo4jTool.explain()`.
Added regressions for escaped local-model output and the Ollama response shape.
Full deterministic suite: **287 passed**. The smoke test should be rerun on
`deel14`; its next result will distinguish validator failure, EXPLAIN failure,
and query execution failure.

**Live smoke-test acceptance update (2026-10-08).** The corrected smoke test
returned the expected answer, structured result, valid Cypher, successful
validation, and Neo4j count of 91. One run emitted a transient Neo4j Aura DNS
resolution retry for the Bolt host; the driver recovered and the next three
attempts completed without the warning. No application or query change was
required.

## Phase 4.8 and 4.9 — MLflow run service and runtime acceptance gate (2026-10-08 12:46 CEST)

**4.8 — MLflow run service: complete.** Added `common/mlflow/service.py` and
the package export. `MlflowRunService` configures the tracking URI and
experiment, creates one flat run, logs safe runtime/model/prompt parameters,
records compact run metrics, and stores the complete JSON-safe runtime result
as `runtime_result.json`. The rendered schema prompt is stored separately as
`prompts.json`, so the actual structured answer, Cypher attempts, validation
envelopes, Neo4j results, and answer/error fields remain inspectable. The
service accepts an injected MLflow module for deterministic tests and imports
the real package lazily for live use. MLflow is now a normal uv dependency and
`uv.lock` was updated.

**4.9 — Runtime acceptance gate: complete.** Added
`scripts/run_runtime_acceptance.py`. It builds the selected architecture with
the shared factory, invokes one question using the smoke-test state and
formatter, logs the completed result through MLflow, prints the run ID and
experiment, and closes the Neo4j client. It supports architecture,
conversational-model, Cypher-model, and run-name overrides. The local MLflow
UI can be started with `uv run mlflow server --host 0.0.0.0 --port 5000`.

Verification: focused MLflow/smoke tests **3 passed**; acceptance CLI help
works; full deterministic suite remains **288 passed**. No live acceptance run
was started here because it requires the configured Neo4j, model provider, and
MLflow server.

## Architecture 1 — A1.1 to A1.4 completion (2026-10-08)

**A1.1 and A1.2 — contract and implementation: complete.** The Architecture 1
contract and generic LangGraph implementation are present under
`architectures/generic/`. The graph implements router, generic Text2Cypher,
three-attempt validation/repair, read-only Neo4j execution, answer generation,
and terminal handling. The shared runtime factory selects this architecture
without importing archived code.

**A1.3 — candidate sweep tooling: complete.** Added
`common/evaluation/benchmark.py`, which loads all 20 canonical questions and
provides a transparent first-pass score of `1` (expected answer appears), `0`
(no answer), or `-1` (attempted but not matched). Added
`scripts/run_architecture1_sweep.py`, which runs the generic architecture for
each selected supported Cypher candidate and creates one flat MLflow run per
candidate. Each run stores the question outputs, raw answers, structured
results, and aggregate counts in `benchmark_result.json`; rendered prompts are
stored in `prompts.json`.

**A1.4 — baseline selection tooling: complete; model decision pending review.**
Added `scripts/select_architecture1_baseline.py`, which applies the agreed
score/accuracy/false-positive ordering to a reviewed sweep report. The script
marks its output `review_required` because multi-row answers, refusals, and
structured-output false negatives need human inspection. No model was selected
automatically without completed candidate runs and review.

Verification: new benchmark/model-selection tests **5 passed**; both CLI help
commands work. Example commands:

```bash
uv run python scripts/run_architecture1_sweep.py \
  --cypher-model "mistral-large-latest" \
  --cypher-model "hf.co/mradermacher/text-to-cypher-Gemma-3-4B-Instruct-2025.04.0-GGUF:Q4_K_M"
uv run python scripts/select_architecture1_baseline.py benchmark/architecture1_sweep.json
```

## Phase 5 — Deterministic evaluation (2026-10-08 13:28 CEST)

**5.1 — Benchmark runner: complete.** The Architecture 1 sweep command runs
all 20 canonical questions for one Cypher model configuration and writes the
per-question outputs to one flat MLflow artifact. The existing completed sweep
contains two runs: Mistral Large and the Ollama Gemma Text2Cypher candidate.

**5.2 — Answer comparison: complete.** `score_answer` applies the agreed
first-pass rule: normalize case and whitespace, then check whether the expected
answer appears in the generated answer. Missing/blank answers receive `0`;
matched answers receive `1`; other attempted answers receive `-1`. Raw answer
text and structured output remain in the MLflow artifact for human review,
especially for multi-value, refusal, and chitchat false negatives.

**5.3 — Score aggregation: complete.** `aggregate_scores` computes
`raw_score`, `accuracy_count`, `false_positive_count`, and `no_answer_count`,
rejects scores outside `{-1, 0, 1}`, and verifies that the three counts sum to
the question count.

**5.4 — MLflow evaluation logging: complete.** Each configuration logs the
aggregate metrics and complete `benchmark_result.json`, with `prompts.json`
retained alongside it. The completed sweep currently reports:

| Cypher model | Raw score | Accuracy | False positive | No answer |
|---|---:|---:|---:|---:|
| `mistral-large-latest` | 3 | 11 | 8 | 1 |
| Ollama Gemma Text2Cypher | -5 | 7 | 12 | 1 |

The deterministic selector currently proposes Mistral Large, but its output
keeps `review_required: true`; this is a provisional result until the raw
answers and structured outputs have been reviewed.

Verification: full deterministic suite **291 passed**.

## Phase 7 — Streamlit demonstration (2026-10-08)

**7.1 — Architecture selector: complete.** Added a sidebar configuration
panel with registered architecture and supported Cypher-model selectors. The
fixed conversational model remains controlled by environment settings. The
selected architecture and model are passed to the shared runtime factory and
logged with each MLflow run. Unimplemented registered architectures remain
visible but show a clear warning and fail explicitly if submitted.

**7.2 — Chat execution: complete.** Reworked `src/streamlit/runtime.py` to
use the architecture-agnostic runtime factory and the new `AgentState` rather
than the archived graph. Runtime resources are cached per architecture/model
selection. Each question starts a fresh graph state, displays the answer and
structured result, and logs the complete runtime result to MLflow.

**7.3 — MLflow run link: complete.** MLflow logging now exposes the experiment
ID and the Streamlit chat history renders an `Open MLflow run` link for each
completed answer. Logging failures remain visible as a warning while the
generated answer remains available.

**7.4 — Manual benchmark check: complete.** Added representative manual
questions and the review procedure to `src/streamlit/README.md`. The linked
MLflow `runtime_result.json` artifact is the comparison source for answer text,
structured output, Cypher, validation, and Neo4j results.

**7.5 — Remote SSH instructions: complete.** Documented simultaneous SSH
forwarding for Streamlit port 8501 and MLflow port 5000, plus the corresponding
remote startup commands.

Verification: Streamlit tests **2 passed**; full deterministic suite remains
green after the shared-runtime integration.

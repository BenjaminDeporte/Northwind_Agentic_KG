# PLAN_REDESIGN.md — Agentic Architecture MVP

This document defines the implementation and evaluation roadmap for the redesigned Northwind Agentic KG project.

## Authoritative Contracts

- `SCHEMA.md`: shared Neo4j graph schema.
- `architectures/<name>/PROJECT.md`: contract for one agentic architecture.
- `benchmark/northwind_questions.csv`: 20-question ground truth.
- MLflow: execution logging and evaluation results.

The existing implementation is archived and is not part of the new runtime.

## Goals

The project demonstrates increasing agentic complexity:

1. Generic Text2Cypher, no self-reflection.
2. Generic Text2Cypher with self-reflection.
3. Curated query tools with Text2Cypher fallback.
4. Curated query tools with self-reflection and Text2Cypher fallback.

The fixed conversational model, initially Mistral Large, handles routing, draft and final answer generation, and self-reflection when enabled. The Cypher-generation model is the experimental variable: a selected general-purpose model or the Neo4j fine-tuned Cypher model.

The initial comparison contains:

```text
4 architectures × 2 Cypher models = 8 configurations
```

## Common Invariants

- Neo4j, LangGraph, Streamlit, and MLflow remain the technical stack.
- `SCHEMA.md` is shared by every architecture and is projected into model prompts.
- The router is always the first LangGraph node: chitchat, toxic/refusal, or agent.
- All graph access is read-only.
- Generated Cypher is validated before execution.
- The Cypher tool allows three total attempts: the original query and two rewrites.
- The conversational model remains fixed during the experiment.
- MLflow uses one flat run per configuration.
- The 20-question benchmark is shared by all architectures.
- The archived `Trace`, `Span`, citation, confidence, and rubric systems are not recreated.
- Structured answer JSON is logged as produced. It is not hardened beyond basic parsing and visibility of its actual form.
- Every completed work item updates `SESSION_SUMMARY.md`.

## File Structure

```text
Northwind_Agentic_KG/
├── SCHEMA.md
├── benchmark/
│   └── northwind_questions.csv
├── common/
│   ├── config/
│   ├── evaluation/
│   ├── mlflow/
│   ├── neo4j/
│   └── prompts/
├── architectures/
│   ├── generic/
│   │   └── PROJECT.md
│   ├── generic_reflection/
│   │   └── PROJECT.md
│   ├── curated/
│   │   └── PROJECT.md
│   └── curated_reflection/
│       └── PROJECT.md
├── archive/
│   └── legacy/
├── tests/
├── scripts/
├── PLAN_REDESIGN.md
└── SESSION_SUMMARY.md
```

## Phase 0 — Archive and Shared Foundation

The benchmark is independent of any architecture and is established before the first architecture contract.

| # | Work Item | Files | Description | Verification |
|---|---|---|---|---|
| 0.1 | Archive current implementation | `archive/legacy/` | Preserve the current implementation, tests, and relevant documentation as a recoverable archive. | Confirm the archive is identifiable and recoverable. |
| 0.2 | Create new repository layout | shared and architecture directories | Create the common area and four architecture directories. Keep `SCHEMA.md` shared. | Approve directory names and ownership boundaries. |
| 0.4 | Add canonical benchmark | `benchmark/northwind_questions.csv` | Copy the 20-question CSV. Preserve group, question, expected answer, comment, and informational ground-truth Cypher. | Confirm all 20 questions and four groups are present. |
| 0.3 | Define common runtime boundary | `common/` and configuration | Define shared Neo4j, model, prompt, MLflow, and Streamlit configuration. | Confirm architecture-specific code can use shared services without sharing architecture state. |

Each item updates `SESSION_SUMMARY.md`.

## Architecture Build Sequence

Phases 1–3 define the common architecture work sequence. Phase 4 then provides
the shared runtime boundary before the architecture-specific builds and live
model sweeps.

### Phase 1 — Architecture Contract and LangGraph Foundation

| # | Work Item | Description | Verification |
|---|---|---|---|
| 1.1 | Architecture contract | Create `architectures/<name>/PROJECT.md` defining state, nodes, edges, tools, model roles, prompts, loop bounds, MLflow fields, and non-goals. | Review and approve before implementation. |
| 1.2 | LangGraph state | Define only the state required by that architecture. Do not recreate the archived trace or evidence state. | Inspect fields, reducers, and node ownership. |
| 1.3 | LangGraph topology | Define router, agent, tools, draft generation, reflection if present, final answer generation, and termination paths. | Review every node and conditional edge. |
| 1.4 | Function and tool signatures | Define signatures before implementation for router, agent, Cypher generation, validation, Neo4j execution, answer generation, reflection, and evaluation. | Compare implementation with the contract. |
| 1.5 | Foundation tests | Test state construction, routing, termination, and loop-counter behavior with mocked responses. | All deterministic tests pass. |

### Phase 2 — Generic Cypher Execution Path

| # | Work Item | Description | Verification |
|---|---|---|---|
| 2.1 | Schema prompt projection | Mechanically project the known schema into the prompt. | Inspect the rendered prompt. |
| 2.2 | Text2Cypher tool | Generate one Cypher query from the question and schema context. | Test representative benchmark questions. |
| 2.3 | Cypher validation | Validate read-only syntax, schema identifiers, single-query form, and execution readiness. | Test valid, invalid, write, multi-statement, and unknown-schema queries. |
| 2.4 | Bounded rewrite loop | Permit three total attempts: original query plus two rewrites. Log every attempt to MLflow. | Verify a third failure terminates. |
| 2.5 | Neo4j execution | Execute only the validated query and preserve result or error metadata. | Verify representative read-only queries. |
| 2.6 | Generic result envelope | Represent scalar values, nodes, relationships, paths, lists, maps, rows, empty results, and failures. Keep detailed answer-specific interpretation deferred. | Review scalar, node-plus-scalar, and path examples. |

### Phase 3 — Answer Generation and Feedback

| # | Work Item | Description | Verification |
|---|---|---|---|
| 3.1 | Draft answer generation | The fixed conversational model produces answer text and structured JSON. Preserve raw structured output. | Inspect text and raw JSON together. |
| 3.2 | Final answer generation | Hand an accepted draft to final answer generation. | Verify successful handoff. |
| 3.3 | Self-reflection node | When enabled, check the draft against the question, query, and result. Failure returns to the agent with feedback and increments the loop count; success continues to final generation. | Test success, failure, and bounded retry. |
| 3.4 | No-feedback path | When disabled, send the draft directly to final answer generation. | Confirm reflection is not invoked. |
| 3.5 | Architecture acceptance | Run the 20-question benchmark through the architecture with mocked and live integrations as appropriate. | Approve before the next architecture. |

## Phase 4 — Shared Runtime, Evaluation, and MLflow Integration

Phase 4 owns the architecture-agnostic runtime boundary and comes before the
architecture-specific implementations. It supplies configuration, provider
adapters, runtime composition, and shared run/evaluation plumbing; each
architecture still owns its state, graph topology, and handlers.

MLflow runs beside Streamlit:

```text
Streamlit → http://localhost:8501
MLflow    → http://localhost:5000
```

| # | Work Item | Description | Verification |
|---|---|---|---|
| 4.1 | Shared settings loader | Load Neo4j, fixed conversational-model, selectable Cypher-model, prompt, Streamlit, and MLflow settings from environment/configuration. Keep secrets out of architecture code. | Load a test configuration and inspect resolved values without contacting external services. |
| 4.2 | Conversational provider adapter | Adapt the fixed conversational provider to the generic route and answer client protocols. Preserve model name, raw response, and structured-output parse errors. | Mock the provider and verify routing, answer generation, and malformed JSON handling. |
| 4.3 | Prepare Ollama Gemma runtime | Install Ollama on the execution server, download the approved quantized Neo4j Gemma 3 4B Text2Cypher model, start the Ollama service, and verify its local API and model response. The model reference is `hf.co/mradermacher/text-to-cypher-Gemma-3-4B-Instruct-2025.04.0-GGUF:Q4_K_M`; this setup is performed manually when the server is ready. | `ollama --version`; `ollama list`; a local chat/API request returns a Cypher response; record hardware, model tag, and endpoint in `SESSION_SUMMARY.md`. |
| 4.4 | Cypher provider registry | Register frontier and the Ollama-hosted Neo4j fine-tuned Cypher candidate behind the `ChatModelClient` protocol, with per-candidate model, provider, and endpoint configuration. | Instantiate each configured adapter with a fake transport and verify model selection. |
| 4.5 | Runtime factory contract | Define a factory that loads the schema prompt, creates clients/tools, composes architecture-specific handlers, and returns a compiled graph plus runtime metadata. | Review the factory signature and confirm no architecture state leaks across runs. |
| 4.6 | Architecture registration | Register generic, generic-reflection, curated, and curated-reflection builders behind one selection interface. Unsupported names fail clearly. | Build the generic architecture from the registry with deterministic fake dependencies. |
| 4.7 | Live smoke-test harness | Add a `uv run` script that submits one question to a selected architecture and prints answer, structured result, Cypher, validation, and Neo4j outcome. | Run against a configured Neo4j/model pair and retain the output for review. |
| 4.8 | MLflow run service | Add configurable tracking URI, experiment/run metadata, flat configuration runs, and logging for prompts, models, Cypher attempts, results, answers, and raw structured output. | Start MLflow and inspect one completed run and its artifact. |
| 4.9 | Runtime acceptance gate | Verify the factory, smoke harness, and MLflow service together for one architecture/model configuration before any sweep. | One live question completes end to end and is visible in MLflow; update `SESSION_SUMMARY.md`. |

## Architecture 1 — Generic Text2Cypher

```text
router → agent → Text2Cypher → validation/repair → Neo4j → draft → final answer
```

No self-reflection is included.

| # | Work Item | Description | Verification |
|---|---|---|---|
| A1.1 | Create contract | Define the basic router, agent, Text2Cypher, validation loop, and answer path. | Contract review. |
| A1.2 | Implement Phases 1–3 | Implement the complete basic architecture. | Architecture tests pass. |
| A1.3 | Run model candidates | After the shared runtime and benchmark runner are available, evaluate frontier Cypher models with the fixed conversational model. | One MLflow run per candidate. |
| A1.4 | Select baseline model | Select the best general-purpose Cypher model for the eight-run comparison. | Human review of benchmark results; record the decision in `SESSION_SUMMARY.md`. |

## Architecture 2 — Generic Text2Cypher with Self-Reflection

```text
router → agent → Text2Cypher → validation/repair → Neo4j → draft
       → self-reflection → agent on failure → final answer on success
```

| # | Work Item | Description | Verification |
|---|---|---|---|
| A2.1 | Create contract | Define the reflection node and shared loop budget. | Contract review. |
| A2.2 | Implement Phases 1–3 | Implement the architecture under its own state and graph contract. | State and graph review. |
| A2.3 | Verify reflection | Test successful reflection, failed reflection, revised query, and loop exhaustion. | Architecture acceptance. |

## Architecture 3 — Curated Tools with Text2Cypher Fallback

```text
router → agent → curated-tool selection
              ├─ curated query
              └─ Text2Cypher fallback
       → validation/repair → Neo4j → draft → final answer
```

The conversational model decides whether to select a curated tool. If none is selected, Text2Cypher is used.

| # | Work Item | Description | Verification |
|---|---|---|---|
| A3.1 | Create contract | Define curated registration, selection, fallback, and query ownership. | Contract review. |
| A3.2 | Build curated registry | Add benchmark-driven curated queries with explicit signatures and descriptions. | Review each query against ground truth. |
| A3.3 | Implement Phases 1–3 | Implement curated selection, fallback, validation, Neo4j execution, and answer generation. | Test curated-match and fallback questions. |

## Architecture 4 — Curated Tools with Self-Reflection

```text
router → agent → curated selection or Text2Cypher fallback
       → validation/repair → Neo4j → draft
       → self-reflection → agent on failure → final answer on success
```

| # | Work Item | Description | Verification |
|---|---|---|---|
| A4.1 | Create contract | Combine curated fallback and self-reflection contracts. | Contract review. |
| A4.2 | Implement Phases 1–3 | Implement the fourth architecture under its own state and graph contract. | State and graph review. |
| A4.3 | Verify combined behavior | Test curated success, fallback, reflection success, reflection failure, and bounded retry. | Architecture acceptance. |

## Phase 5 — Deterministic Evaluation

Scores are `1` for correct, `0` for no answer or unusable answer, and `-1` for an attempted but incorrect answer.

Each run logs:

- `raw_score`, from `-20` to `+20`;
- `accuracy_count`;
- `false_positive_count`;
- `no_answer_count`.

```text
raw_score = accuracy_count - false_positive_count
```

| # | Work Item | Description | Verification |
|---|---|---|---|
| 5.1 | Benchmark runner | Execute all 20 questions through one architecture/model configuration. | Run one configuration end to end. |
| 5.2 | Answer comparison | Compare generated results with benchmark answers using simple agreed rules. Keep raw text and structured output visible. | Verify numeric, string, ranked, multi-value, refusal, and chitchat cases. |
| 5.3 | Score aggregation | Compute the raw score and three counts. | Confirm counts sum to 20. |
| 5.4 | MLflow evaluation logging | Log aggregate metrics and the complete per-question artifact. | Inspect metrics and artifact. |

## Phase 6 — Experiment Runs

### Model-selection sweep

Use Architecture 1 with generic Text2Cypher, no self-reflection, and the fixed conversational model. Evaluate the frontier Cypher candidates and select the strongest general-purpose Cypher model.

### Eight-run comparison

Run:

```text
4 architectures × 2 Cypher models = 8 configurations
```

The models are the selected general-purpose Cypher model and the Neo4j fine-tuned Cypher model. Prompts remain fixed per architecture for this initial comparison and are logged with every run.

| # | Work Item | Verification |
|---|---|---|
| 6.1 | Run model-selection sweep | Review general-purpose Cypher model results. |
| 6.2 | Select baseline model | Record model and rationale in `SESSION_SUMMARY.md`. |
| 6.3 | Run eight configurations | Confirm all eight flat MLflow runs exist. |
| 6.4 | Compare architectures | Compare raw score and outcome counts. |
| 6.5 | Review false negatives | Inspect raw text and structured output for suspicious failures. |

## Phase 7 — Streamlit Demonstration

Streamlit displays the answer and links to MLflow. It does not reproduce the MLflow result store.

| # | Work Item | Description | Verification |
|---|---|---|---|
| 7.1 | Architecture selector | Select an architecture/model configuration. | Confirm selection is logged. |
| 7.2 | Chat execution | Submit a question through the selected graph. | Verify answer and structured output. |
| 7.3 | MLflow run link | Provide a link to the relevant run. | Open the run from Streamlit. |
| 7.4 | Manual benchmark check | Run representative questions manually. | Compare Streamlit answer with MLflow. |
| 7.5 | Remote SSH instructions | Document forwarding for ports 8501 and 5000. | Verify both interfaces through SSH. |

## Phase 8 — Continuous Improvement Demonstration

```text
production question → MLflow logging → recurring pattern
→ curated Cypher tool → benchmark rerun → score comparison
```

| # | Work Item | Description | Verification |
|---|---|---|---|
| 8.1 | Identify recurring pattern | Select a candidate from logged production questions and outcomes. | Human review. |
| 8.2 | Add curated query | Add a typed curated tool and verify it against ground truth. | Query and contract review. |
| 8.3 | Re-run affected configurations | Compare before and after MLflow runs. | Confirm improvement is visible. |
| 8.4 | Document improvement | Update the architecture contract and `SESSION_SUMMARY.md`. | Approve the improvement example. |

## Verification and Handoff Rule

After every numbered work item:

1. Run the item’s verification.
2. Update `SESSION_SUMMARY.md` with date, time, files, result, and next step.
3. Record unresolved issues explicitly.
4. Do not mark dependent work complete by implication.

The user reviews and approves each architecture contract, state, graph topology, signature set, MLflow structure, and benchmark result before the next dependent implementation begins.

## Gates

### Gate 0 — Archive and Foundation

- Existing implementation is preserved.
- Shared layout is approved.
- Benchmark CSV is present.
- First architecture contract is approved.

### Architecture Gates

Each architecture must pass its state, graph, signature, deterministic tests, representative live questions, and visible MLflow run before the next architecture begins.

### Gate 1 — Eight-Run Evaluation

- Model-selection sweep is complete.
- General-purpose Cypher baseline is selected.
- All eight architecture/model runs exist.
- Scores and outcome counts are available.
- False negatives are manually reviewable from raw outputs.

### Gate 2 — MVP Demonstration

- Streamlit and MLflow run side by side.
- Four architectures can be demonstrated.
- Curated fallback and self-reflection are visible.
- Benchmark results are reproducible.
- Continuous improvement is documented.

## Testing Strategy

- Use `uv` for all commands.
- Keep unit tests deterministic.
- Do not call live Neo4j or model APIs from ordinary unit tests.
- Use live calls only in explicit architecture acceptance and benchmark runs.
- Log model, prompt, Cypher, validation, answer, and evaluation information to MLflow.
- Preserve raw structured output so false negatives can be reviewed manually.
- Keep the existing implementation under `archive/legacy/`.

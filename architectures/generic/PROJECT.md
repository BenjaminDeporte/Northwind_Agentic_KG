# PROJECT.md — Architecture 1: Generic Text2Cypher

This is the contract for the first redesigned agentic architecture. It is intentionally the simplest architecture in the progression.

## 1. Authority and Scope

- `SCHEMA.md` is the authoritative graph data contract.
- This file is authoritative for Architecture 1 state, graph topology, interfaces, prompt roles, and runtime behavior.
- Shared services are defined under `common/`.
- The implementation archived under `archive/legacy/` is reference material only and is not imported.
- The fixed conversational model is initially Mistral Large.
- The Cypher-generation model is configurable and is the experimental variable.

## 2. Objective

Architecture 1 answers Northwind questions through one generic Text2Cypher path:

```text
router → agent → Text2Cypher → Cypher validation/repair → Neo4j
       → answer generation → terminal
```

It demonstrates the minimum working agentic architecture before adding self-reflection or curated tools.

## 3. Model Roles

### 3.1 Conversational model

The fixed conversational model handles:

- routing the user request;
- deciding when the agent should use the generic Cypher tool;
- producing the draft answer;
- producing the final natural-language answer;
- producing the structured result associated with the answer.

The conversational model is not varied in the initial experiment.

### 3.2 Cypher-generation model

The Cypher-generation model receives the user question and known schema context and produces a read-only Cypher query. Candidate models include general-purpose frontier models and the Neo4j fine-tuned Cypher model.

The model name, provider, API key reference, and prompt version are configuration values and must be logged to MLflow.

## 4. LangGraph State

The state is deliberately limited to workflow data. It does not contain an application-owned trace, span, citation, confidence rubric, or evidence graph.

```python
class AgentState(TypedDict):
    question: str
    route: Literal["chitchat", "refusal", "agent"]
    messages: Annotated[list, add_messages]
    draft_answer: str | None
    draft_result: dict | None
    answer: str | None
    result: dict | None
    loop_count: int
    error: str | None
```

State rules:

- `messages` is the only field with a reducer.
- All other fields are last-write-wins and have one owning node.
- `draft_answer` and `draft_result` are intermediate outputs.
- `answer` and `result` are the accepted final outputs.
- `loop_count` counts high-level agent turns and is preserved across future architecture feedback loops.
- Cypher validation attempts are part of the Cypher tool result and MLflow record, not a separate state trace.

The exact Python types and ownership tests are implementation work for Phase 1.2.

## 5. Nodes and Graph Edges

### 5.1 Nodes

| Node | Responsibility |
|---|---|
| `router` | Classify the request as `chitchat`, `refusal`, or `agent`. |
| `agent` | Ask the Cypher-generation model for the next action and generic query. |
| `text2cypher` | Generate a Cypher string for the current question and schema context. |
| `validate_cypher` | Validate read-only syntax and schema use; request a rewrite when invalid. |
| `neo4j` | Execute only the validated query against Neo4j. |
| `answer_generation` | Ask the fixed conversational model to interpret the query result into answer text and structured result. In Architecture 1, this generated answer is accepted directly as the final answer. |
| `terminal` | End the graph with the final answer or a clear no-answer/error result. |

### 5.2 Edges

```text
router
  ├─ chitchat → answer_generation
  ├─ refusal  → answer_generation
  └─ agent    → agent

agent → text2cypher → validate_cypher
validate_cypher
  ├─ valid   → neo4j
  └─ invalid → text2cypher (bounded rewrite, with a ToolMessage containing the error)
neo4j → answer_generation → terminal
```

If validation fails after the third total attempt, the graph terminates with an error/no-answer result. Architecture 1 has no self-reflection edge back to `agent`; that is introduced by Architecture 2.

## 6. Function and Tool Signatures

The following signatures are the contract. Concrete model and Neo4j clients are injected dependencies.

```python
def route_question(
    question: str,
    *,
    conversational_model: str,
) -> Literal["chitchat", "refusal", "agent"]: ...

def generate_cypher(
    question: str,
    *,
    schema_prompt: str,
    model_name: str,
    prompt_version: str,
    previous_query: str | None = None,
    validation_error: str | None = None,
) -> str: ...

def validate_cypher(
    query: str,
    *,
    schema: str,
) -> dict:
    """Return a structured validation result; never execute a query."""

def run_readonly_cypher(
    query: str,
    *,
    neo4j_client,
) -> dict: ...

def generate_answer(
    question: str,
    query: str | None,
    query_result: dict | None,
    *,
    route: Literal["chitchat", "refusal", "agent"],
    conversational_model: str,
    prompt_version: str,
) -> tuple[str, dict | None]: ...
```

`generate_cypher` handles both initial generation and repair. Initial generation requires `previous_query=None` and `validation_error=None`. A repair call requires both values and supplies the failed query and validator error to the Cypher-generation model.

When `validate_cypher` rejects a query, it returns a structured `ToolMessage` result, for example:

```json
{
  "status": "invalid",
  "query": "MATCH (c:Customer) RETURN c.unknownProperty",
  "error": "Unknown property: c.unknownProperty"
}
```

The next Text2Cypher call reads this ToolMessage together with the original question and schema context. The validator error is tool output, not an AI-generated message and not an untracked string in state.

`generate_answer` produces the answer text and structured result. Architecture 1 accepts that output directly as the final answer. A later architecture may place a self-reflection node after this function; a successful reflection accepts the same draft rather than invoking a second answer-generation function.

The route is passed explicitly to `generate_answer`. For `chitchat`, the implementation uses a conversational response path; for `refusal`, it returns the refusal behavior without graph access; for `agent`, it grounds the answer in the Cypher result. Route behavior must not be inferred from whether `query_result` happens to be empty.

The generic result envelope must preserve rows and nested Neo4j values, including scalars, nodes, relationships, paths, lists, and maps. Detailed answer-specific result rules are intentionally deferred.

## 7. Schema and Prompt Contract

The workflow knows the Northwind schema before the question is processed. `SCHEMA.md` is projected mechanically into the Text2Cypher prompt. The model must not be asked to rediscover labels, keys, properties, or relationships.

The prompt must instruct the Cypher model to:

- produce one read-only query;
- use only labels, relationship types, and properties from `SCHEMA.md`;
- return values needed to answer the question;
- avoid writes and multi-statement requests;
- preserve the requested operation and constraints.

Architecture-specific prompt text is versioned and logged. The schema remains shared and authoritative.

## 8. Cypher Validation and Bounds

The generic Cypher tool allows exactly three total attempts:

1. original generated query;
2. rewrite after the first validation failure;
3. rewrite after the second validation failure.

Validation checks:

- non-empty query;
- one statement only;
- read-only operation;
- no write clauses;
- permitted schema labels, properties, and relationships;
- Neo4j `EXPLAIN` preflight success.

`EXPLAIN` parses and plans the query without executing it or returning data rows. The query is executed separately only after validation succeeds. The third failure is terminal for this tool invocation. It must not silently call Neo4j with an invalid query and must not start an unbounded repair cycle.

The implementation boundary is split as follows:

- `common.neo4j.validation.validate_cypher` performs deterministic checks and
  returns `{status, query, error}`. It accepts one terminal semicolon, rejects
  internal statement delimiters and write clauses, checks labels and explicit
  properties against the supplied schema, and can invoke an injected `EXPLAIN`
  callback for execution readiness.
- `common.neo4j.executor.run_readonly_cypher` executes only a normalized query
  through either the driver's `execute_query` API or a session. The
  `Neo4jTool` adapter carries the schema and is the handler implementation used
  by the graph runtime.
- `common.neo4j.results.result_envelope` converts driver values to JSON-safe
  rows and deduplicated node/relationship evidence. It preserves nested lists,
  maps, paths, and scalar values and uses `status="empty"` for a successful
  zero-row result and `status="failed"` for an execution exception.

The graph's `validate_cypher_node` wraps each validation result in a
`ToolMessage`. Its existing routing performs the bounded original-plus-two-
rewrite loop; no retry is hidden inside the validator or executor.

## 9. MLflow Contract

Architecture 1 uses one flat MLflow run per architecture/model configuration. No child runs are required initially.

Run parameters:

- architecture name: `generic`;
- conversational model and provider;
- Cypher-generation model and provider;
- prompt version;
- tooling mode: `text2cypher`;
- feedback mode: `none`;
- benchmark identifier, when running evaluation;
- MLflow run identifier.

Run data and artifacts:

- user question;
- schema/prompt version;
- original and rewritten Cypher;
- validation outcomes and errors;
- bounded Neo4j result;
- draft answer;
- final answer;
- raw structured result output and parse error, if any;
- latency and token usage where available;
- benchmark score and comparison details.

MLflow records execution history. It is not represented as an `AgentState` trace.

## 10. Termination and Failure Behavior

- Chitchat ends with a conversational response and no graph query.
- Refusal ends with a refusal response and no graph query.
- A valid query result proceeds to `generate_answer`; its output is the final answer in Architecture 1.
- A zero-row query result remains a legitimate no-match result.
- A query invalid after three attempts ends with a visible query-failure/no-answer result.
- Architecture 1 does not self-reflect or retry a semantically unsatisfactory answer.
- All terminal outputs are logged to MLflow.

## 11. Architecture 1 Phase 3 Boundary

Architecture 1 implements the common draft-answer interface without a
self-reflection node. `answer_generation` calls the fixed conversational model
once and writes both `draft_answer`/`draft_result` and the accepted
`answer`/`result`; the direct handoff is intentional for this baseline. The
reflection and final-review nodes belong to Architecture 2 and later.

The conversational adapter is in `architectures/generic/conversation.py`.
It owns route classification and answer prompting, passes the selected model
name on every call, accepts JSON or plain-text model responses, and preserves a
malformed structured response as answer text with a null structured result so
the failure remains visible to MLflow.

## 11. Non-Goals

Architecture 1 does not include:

- curated query tools;
- self-reflection or CoVe;
- multiple specialist agents;
- custom trace or span classes;
- citation or evidence-graph construction;
- confidence scoring or the archived rubric;
- model fine-tuning;
- graph writes;
- automatic hardening or repair of malformed structured answer JSON;
- generalization evaluation beyond the 20-question benchmark.

## 12. Acceptance Criteria

Architecture 1 is accepted when:

1. Its LangGraph state and edges match this contract.
2. The router handles chitchat, refusal, and agent routes.
3. Text2Cypher uses the known schema and produces a read-only query.
4. Cypher validation allows no more than three total attempts.
5. Only validated queries reach Neo4j.
6. Scalar, node, relationship, path, list, and map results remain representable.
7. The fixed conversational model produces one answer text and structured result through `generate_answer`.
8. MLflow contains one inspectable flat run for a configuration.
9. Deterministic tests pass without live Neo4j or model calls.
10. The user has reviewed and approved this contract before Phase 1.2 implementation.

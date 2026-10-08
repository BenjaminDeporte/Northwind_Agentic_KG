# Architecture 2 — Generic Text2Cypher with Self-Reflection

Architecture 2 keeps Architecture 1's router, generic Text2Cypher tool,
read-only validation, and Neo4j execution. After draft answer generation, the
fixed conversational model checks whether the draft answers the question and
matches the result. A failed check returns to `agent`; the shared loop counter
limits retries. A successful check terminates with the accepted draft.

```text
router → agent → text2cypher → validate_cypher → neo4j → answer_generation
       → reflection ── pass → terminal
                    └─ fail → agent
```

State is the Architecture 1 state. Reflection feedback is a `ToolMessage`; no
custom trace or evidence state is added. The reflection contract is
`reflect_answer(question, draft_answer, query_result) -> (satisfactory, feedback)`.

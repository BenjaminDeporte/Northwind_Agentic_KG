# Architecture 4 — Curated Tools with Self-Reflection

Architecture 4 combines the typed curated-query registry and Text2Cypher
fallback from Architecture 3 with Architecture 2's draft-answer reflection.
The conversational model selects a curated query when appropriate, all queries
pass the shared validation loop, and an unsatisfactory draft returns to the
agent within the shared loop budget.

```text
router → agent → curated selection or Text2Cypher → validation → Neo4j
       → answer draft → reflection ── pass → terminal
                                └─ fail → agent
```

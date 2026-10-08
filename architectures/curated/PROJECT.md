# Architecture 3 — Curated Tools with Text2Cypher Fallback

The conversational model selects a named curated read-only query when its
description matches the question. Otherwise the graph falls back to generic
Text2Cypher. Both paths share validation, Neo4j execution, and answer
generation. Curated queries are typed registry entries and never bypass
validation.

```text
router → agent → curated selection
              ├─ curated query ─┐
              └─ Text2Cypher ────┴→ validate_cypher → neo4j → answer → terminal
```

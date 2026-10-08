# Architecture 4 LangGraph view

```mermaid
flowchart TD
    START([START]) --> router
    router -->|agent| agent
    router -->|chitchat/refusal| answer_generation
    agent --> curated_selection{Curated match?}
    curated_selection -->|yes| curated_query
    curated_selection -->|no| text2cypher
    curated_query --> validate_cypher
    text2cypher --> validate_cypher
    validate_cypher -->|valid| neo4j
    validate_cypher -->|invalid, attempts remain| text2cypher
    validate_cypher -->|invalid, exhausted| terminal
    neo4j --> answer_generation
    answer_generation --> reflection{Draft satisfactory?}
    reflection -->|yes| terminal
    reflection -->|no, budget remains| agent
    reflection -->|no, budget exhausted| terminal
    terminal --> END([END])
```

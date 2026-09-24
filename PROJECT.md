# Northwind Agentic KG - Project Description

## Overview

This project implements a conversational agent for the Northwind dataset using a **lookup-based architecture** without vector embeddings. The system uses LangGraph for agent orchestration, Neo4j Aura as the knowledge graph backend, and Streamlit for the user interface.

## Architecture

### Core Components

1. **LangGraph Agent** (`src/agents/`)
   - Graph-based agent pipeline
   - Nodes: `lookup_entity`, `synthesize`, `router`
   - State machine managing conversation context

2. **Neo4j Aura Integration** (`src/neo4j/`)
   - Graph database with Northwind dataset
   - `lookup_entity` function: Primary entity resolution mechanism
   - Cypher queries for pattern matching and relationship traversal

3. **Streamlit Frontend** (`src/streamlit/`)
   - Chat interface
   - Trace drawer (agent reasoning visualization)
   - Exploratory tool (stretch)
   - Churn beat dashboard (stretch)

### Data Flow

```
User Input
    ↓
Streamlit app.py
    ↓
LangGraph Graph (graph.py)
    ↓
    ├─→ lookup_entity (nodes.py + queries.py)
    │       ↓
    │   Neo4j Aura (Cypher)
    │       ↓
    │   Entity matches + relationships
    │
    └─→ synthesize (nodes.py)
            ↓
        Response generation
            ↓
    Streamlit chat display
            ↓
    Trace drawer visualization
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| No vector embeddings | Simplifies architecture, relies on exact matches and graph patterns |
| `lookup_entity` as primary search | Replaces semantic search with structured graph queries |
| LangGraph for orchestration | Enables complex reasoning flows with state management |
| Neo4j Aura (cloud) | Managed service, no local setup required |
| Streamlit for UI | Rapid prototyping, good for demos |

## Entity Resolution Strategy

The `lookup_entity` function implements multi-step resolution:

1. **Exact match**: Direct label + property match (e.g., `Product.name = "Chai"`)
2. **Fuzzy match**: Levenshtein distance on string properties
3. **Category expansion**: If entity type is ambiguous, expand to related types
4. **Relationship context**: Use conversation history to constrain search

## Rubric (Phase 1 Deliverable)

The confidence scoring rubric is implemented in the `synthesize` node and displayed by the trace drawer:

| Score | Criteria | Display |
|-------|----------|---------|
| 1.0 | Exact match, direct answer | Green, solid |
| 0.9 | Exact match, inferred answer | Green, dashed |
| 0.8 | Partial match, direct answer | Yellow, solid |
| 0.7 | Partial match, inferred answer | Yellow, dashed |
| 0.6 | Category match, direct answer | Orange, solid |
| 0.5 | Category match, inferred answer | Orange, dashed |
| <0.5 | No match / guess | Red |

Confidence scores are **not decoration** — they drive the trace drawer's visual encoding and the agent's fallback strategies.

## Northwind Dataset

The Northwind dataset contains:
- **Entities**: Customers, Products, Orders, Employees, Suppliers, Categories, Shippers
- **Relationships**: PLACED, CONTAINS, BELONGS_TO, EMPLOYED_BY, SUPPLIES, etc.
- **Key attributes**: Names, IDs, dates, quantities, prices

See [northwind_schema.md](docs/northwind_schema.md) for the full schema.

## Minimum Viable Demo Criteria

The demo is considered viable when:
1. Agent responds correctly to entity-based queries in CLI
2. Chat interface works end-to-end
3. Trace drawer displays reasoning path with confidence scores
4. One scripted "wow" question produces correct answer with evidence subgraph

## Stretch Goals

1. **Exploratory Tool**: Interactive graph browser within Streamlit
2. **Churn Beat**: Proactive identification of at-risk customers based on order patterns

## Dependencies

- langgraph
- neo4j (Python driver)
- streamlit
- python-dotenv
- pytest

See `requirements.txt` for full dependency list.

## Testing Strategy

- Unit tests for `lookup_entity` with known Northwind queries
- Integration tests for agent graph
- UI tests for Streamlit components
- Manual rehearsal gate (Phase 2 end)

## Gates

| Gate | Phase | Criteria | Timing |
|------|-------|----------|--------|
| Mid-build | End of Phase 2 | Agent works end-to-end in CLI | Day 4 |
| Final | Before Day 7 | Full rehearsal, no code changes | Day 6 |

Passing mid-build gate means the demo **cannot fail** — Streamlit is polish only.

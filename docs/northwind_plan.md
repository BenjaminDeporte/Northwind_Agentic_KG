# Northwind Demo Plan

## Overview

Seven-day execution plan for building a Northwind agentic application with Neo4j Aura, LangGraph, and Streamlit. This plan carries over the ASRS architecture with two key differences: **no ingestion phase** and **no vector/embedding layer** — `lookup_entity` replaces semantic search.

## Phase Structure

| Phase | Duration | Focus | Gate |
|-------|----------|-------|------|
| Phase 1 | Days 1-2 | Foundation & Architecture | Rubric defined |
| Phase 2 | Days 3-4 | Core Agent Development | Mid-build (CLI end-to-end) |
| Phase 3 | Days 5-6 | Streamlit Integration | N/A |
| Phase 4 | Day 7 | Polish & Rehearsal | Final gate |

---

## Phase 1: Foundation & Architecture (Days 1-2)

### Day 1: Setup & Schema
- [ ] Initialize repository with proposed structure
- [ ] Create `.env.example`, `requirements.txt`, `pyproject.toml`
- [ ] Set up Neo4j Aura instance
- [ ] Load Northwind dataset into Neo4j
- [ ] Define and document graph schema in `src/neo4j/schema.py`
- [ ] Create basic Neo4j client in `src/neo4j/client.py`

### Day 2: Architecture & Rubric
- [ ] Design agent graph architecture
- [ ] Create state management (`src/agents/state.py`)
- [ ] **Deliver Rubric** (Phase 1 gate) - Goes in `PROJECT.md` and implemented in `synthesize` node
- [ ] Define confidence scoring system for trace drawer
- [ ] Create initial Cypher queries in `src/neo4j/queries.py`
- [ ] Set up logging infrastructure

**Phase 1 Deliverables:**
- Working Neo4j Aura instance with Northwind data
- Repository structure in place
- Rubric documented and agreed upon
- Basic infrastructure (client, queries, state)

**Phase 1 Gate:** Rubric is defined and documented before agent exists (critical for trace drawer and synthesize node).

---

## Phase 2: Core Agent Development (Days 3-4)

### Day 3: Agent Skeleton
- [ ] Create LangGraph graph definition (`src/agents/graph.py`)
- [ ] Implement `lookup_entity` node with exact matching
- [ ] Implement basic `synthesize` node
- [ ] Create `router` node for query classification
- [ ] Wire up nodes into initial graph

### Day 4: Testing & Validation
- [ ] Test `lookup_entity` with known Northwind queries
- [ ] Add fuzzy matching to `lookup_entity`
- [ ] Add category expansion logic
- [ ] Implement relationship context in lookup
- [ ] **Mid-build Gate**: Agent works end-to-end in CLI

**Phase 2 Deliverables:**
- Fully functional LangGraph agent
- `lookup_entity` with multi-step resolution
- Confidence scoring in `synthesize` node
- CLI testing passes for core queries

**Mid-build Gate Criteria:**
- Agent responds correctly to entity-based queries in CLI mode
- If this holds, the demo **cannot fail** — Streamlit is only polish
- Must pass before proceeding to Phase 3

---

## Phase 3: Streamlit Integration (Days 5-6)

### Day 5: Frontend Foundation
- [ ] Create Streamlit app skeleton (`src/streamlit/app.py`)
- [ ] Build chat interface component
- [ ] Integrate agent with Streamlit
- [ ] Create trace drawer component
- [ ] Connect trace drawer to agent confidence scores

### Day 6: Features & Polish
- [ ] Implement trace drawer visualization
- [ ] Create wow question script (`scripts/wow_question.py`)
- [ ] Test wow question with evidence subgraph
- [ ] Add exploratory tool (stretch item #1)
- [ ] Add churn beat (stretch item #2)
- [ ] Final integration testing

**Phase 3 Deliverables:**
- Working Streamlit chat interface
- Trace drawer with confidence visualization
- Scripted wow question with evidence subgraph (MVP complete)
- Exploratory tool (stretch)
- Churn beat (stretch)

---

## Phase 4: Polish & Rehearsal (Day 7)

### Day 7: Final Preparation
- [ ] Fix any remaining bugs
- [ ] Optimize query performance
- [ ] Improve UI/UX polish
- [ ] **Final Gate**: Full rehearsal without touching code
- [ ] Prepare demo script
- [ ] Dry run through complete demo

**Final Gate Criteria:**
- Full rehearsal of demo
- No code changes during rehearsal
- Same discipline as ASRS: identify issues, fix after rehearsal if needed

---

## Minimum Viable Demo

If Day 7 arrives short, the fallback position is:

| Priority | Item | Status |
|----------|------|--------|
| 1 | Chat interface | Required |
| 2 | Trace drawer | Required |
| 3 | One scripted wow question with evidence subgraph | Required |
| 4 | Exploratory tool | Stretch |
| 5 | Churn beat | Stretch |

**MVP is complete with items 1-3.** Items 4-5 are stretch in that order.

---

## Gate Summary

| Gate | When | Criteria | Consequence |
|------|------|----------|-------------|
| Rubric | End Phase 1 | Rubric documented in schema doc | Required for trace drawer |
| Mid-build | End Phase 2 | Agent works end-to-end in CLI | Demo cannot fail if passed |
| Final | Before Day 7 | Full rehearsal, no code changes | Must pass for demo |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Agent response accuracy | >90% for entity queries |
| Average response time | <2 seconds |
| Trace drawer clarity | 100% of users understand confidence |
| Wow question success | 100% (scripted) |

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Neo4j Aura setup delays | Medium | High | Start Day 1 early, have fallback local Neo4j |
| LangGraph complexity | Low | Medium | Use official examples as templates |
| Northwind data mismatches | Medium | Medium | Verify schema before coding lookup |
| Streamlit performance | Low | Low | Optimize queries, lazy load |

---

## Notes

1. **The gates are different from ASRS**: Mid-build is end of Phase 2 (agent CLI), final is rehearsal.
2. **The rubric is Phase 1**: It goes in the schema doc before the agent exists.
3. **Minimum viable degrades gracefully**: Fallback is chat + trace + one wow question.

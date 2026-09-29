# Northwind Agentic Knowledge Graph

A chatbot application powered by LangGraph agents, Neo4j Aura (Northwind dataset), and Streamlit UI. Implements an entity-lookup architecture without vector embeddings.

## Architecture Overview

```
User Query -> LangGraph Agent -> lookup_entity (Neo4j Cypher) -> Synthesize Response -> Streamlit UI
```

**Key Design:** No ingestion phase, no vector/embedding layer. Entity resolution is performed via `lookup_entity` using exact matches and graph patterns.

## Quick Start

### Prerequisites
- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Neo4j Aura instance with Northwind dataset loaded

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Northwind_Agentic_KG

# Create the project environment and install locked dependencies
uv sync
```

### Configuration

1. Copy `.env.example` to `.env`
2. Set your Neo4j Aura credentials (`NEO4J_URI`, `NEO4J_PASSWORD`, and `NEO4J_USERNAME` or `NEO4J_USER`) and `MISTRAL_API_KEY`:
   ```
   NEO4J_URI=<your-aura-instance-uri>
   NEO4J_USER=<your-username>
   NEO4J_PASSWORD=<your-password>
   ```

### Running the Application

```bash
# Start Streamlit UI from the repository root
uv run streamlit run src/streamlit/app.py

# Or run the agent in CLI mode
uv run python -m src.agents.graph
```

The initial Streamlit page provides placeholders for chat, trace, and graph evidence. Agent and database wiring is added in the following Phase 3 items. Streamlit listens on port `8501` by default; when connected to the project over SSH, forward that port in VS Code to open the page in your local browser.

## Project Structure

```
Northwind_Agentic_KG/
├── src/
│   ├── agents/           # LangGraph agent definitions
│   │   ├── graph.py      # Main agent graph
│   │   ├── nodes.py      # Graph nodes (lookup, synthesize)
│   │   └── state.py      # State management
│   │
│   ├── neo4j/            # Neo4j Aura integration
│   │   ├── client.py     # Neo4j driver
│   │   ├── queries.py    # Cypher queries (lookup_entity)
│   │   └── schema.py     # Graph schema
│   │
│   ├── streamlit/        # Frontend components
│   │   ├── app.py        # Main Streamlit application
│   │   └── components/   # UI components (chat, trace drawer)
│   │
│   └── utils/            # Shared utilities
│       ├── config.py     # Configuration
│       └── logging.py    # Structured logging
│
├── data/                 # CSV files for database creation
├── docs/                 # Documentation
│   ├── northwind_plan.md # Project plan and gates
│   └── northwind_schema.md
├── tests/                # Test suites
├── scripts/              # Utility scripts
│   ├── seed_data.py      # Load Northwind CSV data
│   └── wow_question.py   # Scripted demo question
│
├── .env.example          # Environment template
├── requirements.txt      # Dependencies
└── README.md
```

## Features

- **Agentic Pipeline**: LangGraph-based agent with entity lookup capabilities
- **Trace Drawer**: Visual representation of agent reasoning paths
- **Chat Interface**: Streamlit-based conversational UI
- **Exploratory Tool**: (Stretch) Graph exploration interface
- **Churn Beat**: (Stretch) Proactive insights on customer churn patterns

## Minimum Viable Demo

The MVP includes:
- Chat interface
- Trace drawer visualization
- One scripted "wow" question with evidence subgraph

Stretch items (in order):
1. Exploratory tool
2. Churn beat

## Development Workflow

See [PROJECT.md](PROJECT.md) for detailed project description and [docs/northwind_plan.md](docs/northwind_plan.md) for the execution plan with gates.

## License

MIT License

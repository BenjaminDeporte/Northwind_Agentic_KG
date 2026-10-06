# Common Runtime

This directory contains services shared by all agentic architectures.

Shared boundaries include configuration, Neo4j access, prompt/schema projection, evaluation, and MLflow logging. Architecture-specific state, graph topology, prompts, tools, and contracts remain under `architectures/<name>/`.

The common runtime must not own architecture-specific LangGraph state or feedback behavior.

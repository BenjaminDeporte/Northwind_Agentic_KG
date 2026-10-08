# Common Runtime

This directory contains services shared by all agentic architectures.

Shared boundaries include configuration, Neo4j access, prompt/schema projection, evaluation, and MLflow logging. Architecture-specific state, graph topology, prompts, tools, and contracts remain under `architectures/<name>/`.

Provider adapters live under `common/providers/`. They expose raw provider
responses through small protocols and do not own route or answer parsing. This
keeps SDK-specific code outside architecture graphs.

The common runtime must not own architecture-specific LangGraph state or feedback behavior.

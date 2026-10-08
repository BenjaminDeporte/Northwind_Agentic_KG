# Shared Runtime Boundary

`factory.py` composes shared settings, schema prompts, provider clients, Neo4j,
and an architecture-specific compiled graph into one `AgentRuntime` object.
`architectures.py` registers all four architecture names explicitly. Each
architecture now has its own graph builder; they share provider and Neo4j
handlers but keep topology and feedback edges in their own package.

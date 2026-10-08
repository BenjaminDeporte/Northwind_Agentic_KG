# Shared Runtime Boundary

`factory.py` composes shared settings, schema prompts, provider clients, Neo4j,
and an architecture-specific compiled graph into one `AgentRuntime` object.
`architectures.py` registers all planned architecture names explicitly. The
generic architecture is currently buildable; planned architectures fail with a
clear `NotImplementedError` until their contracts and implementations exist.

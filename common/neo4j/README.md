# Common Neo4j Boundary

This boundary owns the shared read-only Neo4j client, Cypher validation, bounded rewrite attempts, query execution, and generic result envelope.

Architecture-specific tools decide when to request Cypher; they do not bypass common read-only validation.

The implementation is split into `validation.py`, `executor.py`, and
`results.py`. The executor accepts either the Neo4j driver's `execute_query`
API or a session factory. Every outcome has `status`, `query`, `rows`,
`evidence`, and nullable `error`; nested nodes, relationships, paths, lists,
and maps are converted to JSON-safe values.

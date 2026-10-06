# Common MLflow Boundary

MLflow is the observability and evaluation store for every architecture.

The initial design uses one flat MLflow run per architecture/model configuration. A run records model and prompt identifiers, Cypher attempts and validation, bounded query results, answer text, raw structured output, latency, token usage, and benchmark metrics.

The default local arrangement runs Streamlit on port 8501 and MLflow on port 5000. The tracking URI remains configurable.

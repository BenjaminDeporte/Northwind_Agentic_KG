# Common MLflow Boundary

MLflow is the observability and evaluation store for every architecture.

The initial design uses one flat MLflow run per architecture/model configuration. A run records model and prompt identifiers, the rendered schema prompt, Cypher attempts and validation, bounded query results, answer text, raw structured output, latency, token usage, and benchmark metrics. The complete smoke/acceptance result is retained as `runtime_result.json`; prompts are retained as `prompts.json`.

The default local arrangement runs Streamlit on port 8501 and MLflow on port 5000. The tracking URI remains configurable.

The runtime acceptance command executes one live question and logs the run:

```bash
uv run python scripts/run_runtime_acceptance.py \
  --question "How many customers are there?" \
  --cypher-model "hf.co/mradermacher/text-to-cypher-Gemma-3-4B-Instruct-2025.04.0-GGUF:Q4_K_M"
```

Start the local UI separately when needed:

```bash
uv run mlflow server --host 0.0.0.0 --port 5000
```

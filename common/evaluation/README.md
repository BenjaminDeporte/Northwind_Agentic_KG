# Common Evaluation Boundary

The benchmark runner and deterministic score aggregation are shared by all architectures.

The initial score for each benchmark question is `1` for correct, `0` for no
answer or unusable answer, and `-1` for an attempted but incorrect answer.
The first-pass comparison normalizes case and whitespace and checks whether the
expected answer appears in the generated answer. This keeps numeric, string,
ranked, multi-value, refusal, and chitchat cases deterministic while leaving
the raw text and structured output visible for human review of false negatives.
`aggregate_scores` enforces that the three outcome counts sum to the benchmark
question count.
The Architecture 1 model-selection bookkeeping is implemented in
`model_selection.py`. `scripts/run_architecture1_sweep.py` runs the canonical
questions and creates one flat MLflow run per Cypher candidate. Its first-pass
answer score is intentionally conservative and the complete raw output remains
in `benchmark_result.json` for human correction. After review,
`scripts/select_architecture1_baseline.py` applies the deterministic selector.
Live model calls and MLflow run creation remain deployment actions, not
import-time work.

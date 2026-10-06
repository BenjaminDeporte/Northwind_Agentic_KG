# Common Evaluation Boundary

The benchmark runner and deterministic score aggregation are shared by all architectures.

The initial score for each benchmark question is `1` for correct, `0` for no answer or unusable answer, and `-1` for an attempted but incorrect answer. Raw structured model output is retained for human review; detailed result-dictionary rules remain an explicit later design item.
The Architecture 1 model-selection bookkeeping is implemented in
`model_selection.py`. A sweep runner may construct `ModelRunResult` records
from MLflow evaluation artifacts; `select_baseline` then applies the agreed
raw-score, accuracy, and false-positive ordering deterministically. Live model
calls and MLflow run creation remain deployment actions, not import-time work.

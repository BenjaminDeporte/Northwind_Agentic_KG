"""Small, injectable MLflow boundary used by smoke and benchmark runs.

The service deliberately records one flat run.  It does not create child runs
or reproduce the archived trace/evidence model.  The complete JSON-safe result
is retained as an artifact so structured-output parsing problems remain visible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from common.config.settings import MLflowSettings


def _json_safe(value: Any) -> Any:
    """Round-trip values into the JSON representation MLflow can persist."""
    return json.loads(json.dumps(value, default=str))


def _text(value: Any) -> str:
    return str(value)[:5000]


@dataclass(frozen=True)
class MlflowRunResult:
    run_id: str | None
    experiment_name: str
    artifact_path: str
    experiment_id: str | None = None


class MlflowRunService:
    """Log one completed runtime result to MLflow.

    ``mlflow_module`` is injectable to keep deterministic tests independent of
    the MLflow server and package import.  In production it is imported lazily.
    """

    def __init__(self, settings: MLflowSettings, *, mlflow_module: Any = None):
        self.settings = settings
        self._mlflow = mlflow_module

    @property
    def mlflow(self) -> Any:
        if self._mlflow is None:
            try:
                import mlflow
            except ImportError as exc:  # pragma: no cover - depends on deployment
                raise RuntimeError(
                    "MLflow is not installed; run `uv sync` to install project dependencies"
                ) from exc
            self._mlflow = mlflow
        return self._mlflow

    def _configure(self) -> None:
        self.mlflow.set_tracking_uri(self.settings.tracking_uri)
        self.mlflow.set_experiment(self.settings.experiment_name)

    def _experiment_id(self) -> str | None:
        getter = getattr(self.mlflow, "get_experiment_by_name", None)
        if not callable(getter):
            return None
        experiment = getter(self.settings.experiment_name)
        return str(getattr(experiment, "experiment_id", "")) or None

    @staticmethod
    def _params(runtime_metadata: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, str]:
        keys = (
            "app_name",
            "app_version",
            "architecture",
            "conversational_model",
            "conversational_provider",
            "cypher_model",
            "cypher_provider",
            "prompt_version",
            "schema_path",
        )
        params = {key: _text(runtime_metadata[key]) for key in keys if key in runtime_metadata}
        params["question"] = _text(payload.get("question", ""))
        return params

    @staticmethod
    def _metrics(payload: Mapping[str, Any]) -> dict[str, float]:
        validations = payload.get("validation_attempts") or []
        neo4j_results = payload.get("neo4j_results") or []
        rows = sum(len(result.get("rows") or []) for result in neo4j_results if isinstance(result, Mapping))
        return {
            "loop_count": float(payload.get("loop_count") or 0),
            "cypher_attempts": float(len(payload.get("generated_cypher") or [])),
            "validation_attempts": float(len(validations)),
            "validation_failures": float(
                sum(1 for item in validations if isinstance(item, Mapping) and item.get("status") == "invalid")
            ),
            "neo4j_result_count": float(len(neo4j_results)),
            "neo4j_row_count": float(rows),
            "has_answer": float(bool(payload.get("answer"))),
            "has_error": float(bool(payload.get("error"))),
        }

    def log_result(
        self,
        *,
        runtime_metadata: Mapping[str, Any],
        result: Mapping[str, Any],
        prompts: Mapping[str, Any] | None = None,
        run_name: str | None = None,
        tags: Mapping[str, str] | None = None,
        artifact_path: str = "runtime_result.json",
    ) -> MlflowRunResult:
        """Persist runtime metadata, metrics, and the complete result artifact."""
        payload = _json_safe(result)
        self._configure()
        experiment_id = self._experiment_id()
        with self.mlflow.start_run(run_name=run_name, tags=dict(tags or {})) as run:
            self.mlflow.log_params(self._params(runtime_metadata, payload))
            self.mlflow.log_metrics(self._metrics(payload))
            # log_dict preserves the actual structured result, including nulls,
            # malformed/absent JSON, generated Cypher, and tool envelopes.
            self.mlflow.log_dict(payload, artifact_path)
            if prompts:
                self.mlflow.log_dict(_json_safe(prompts), "prompts.json")
            run_info = getattr(run, "info", None)
            run_id = getattr(run_info, "run_id", None)
        return MlflowRunResult(
            run_id=run_id,
            experiment_name=self.settings.experiment_name,
            artifact_path=artifact_path,
            experiment_id=experiment_id,
        )

    def log_benchmark_result(
        self,
        *,
        runtime_metadata: Mapping[str, Any],
        benchmark: Mapping[str, Any],
        run_name: str | None = None,
        tags: Mapping[str, str] | None = None,
        prompts: Mapping[str, Any] | None = None,
    ) -> MlflowRunResult:
        """Persist one flat run containing all questions for one configuration."""
        payload = _json_safe(benchmark)
        self._configure()
        experiment_id = self._experiment_id()
        with self.mlflow.start_run(run_name=run_name, tags=dict(tags or {})) as run:
            params = self._params(runtime_metadata, {"question": "benchmark"})
            params["benchmark_id"] = _text(payload.get("benchmark_id", "northwind_questions"))
            self.mlflow.log_params(params)
            summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
            self.mlflow.log_metrics(
                {
                    "question_count": float(summary.get("question_count", 0)),
                    "raw_score": float(summary.get("raw_score", 0)),
                    "accuracy_count": float(summary.get("accuracy_count", 0)),
                    "false_positive_count": float(summary.get("false_positive_count", 0)),
                    "no_answer_count": float(summary.get("no_answer_count", 0)),
                }
            )
            self.mlflow.log_dict(payload, "benchmark_result.json")
            if prompts:
                self.mlflow.log_dict(_json_safe(prompts), "prompts.json")
            run_info = getattr(run, "info", None)
            run_id = getattr(run_info, "run_id", None)
        return MlflowRunResult(run_id, self.settings.experiment_name, "benchmark_result.json", experiment_id)


__all__ = ["MlflowRunResult", "MlflowRunService"]

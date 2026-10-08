"""Run one live runtime question and log the result to MLflow.

Usage:
    uv run python scripts/run_runtime_acceptance.py \
      --question "How many customers are there?" \
      --cypher-model <model>
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import load_settings
from common.mlflow import MlflowRunService
from common.runtime.factory import build_runtime
from scripts.run_smoke_test import initial_state, summarize_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--architecture", default="generic")
    parser.add_argument("--conversational-model")
    parser.add_argument("--cypher-model")
    parser.add_argument("--run-name", help="Optional MLflow run name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = None
    try:
        settings = load_settings()
        models = settings.models
        if args.conversational_model:
            models = replace(models, conversational_model=args.conversational_model)
        if args.cypher_model:
            models = replace(models, cypher_model=args.cypher_model)
        settings = replace(settings, models=models)
        runtime = build_runtime(architecture=args.architecture, settings=settings)
        state = runtime.graph.invoke(initial_state(args.question))
        result = summarize_state(state)
        run = MlflowRunService(settings.mlflow).log_result(
            runtime_metadata=runtime.metadata(),
            result=result,
            prompts={"schema_prompt": runtime.schema_prompt},
            run_name=args.run_name or f"{args.architecture}-{settings.models.cypher_model}",
            tags={"architecture": args.architecture, "source": "runtime_acceptance"},
        )
        print(json.dumps({**result, "mlflow_run_id": run.run_id, "mlflow_experiment": run.experiment_name}, indent=2, ensure_ascii=False, default=str))
        return 0 if state.get("error") is None else 1
    except Exception as exc:
        print(f"Runtime acceptance failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if runtime is not None:
            close = getattr(runtime.neo4j_client, "close", None)
            if callable(close):
                close()


if __name__ == "__main__":
    raise SystemExit(main())

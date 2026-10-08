"""Run Architecture 1 over the canonical benchmark for Cypher candidates.

This command performs one flat MLflow run per selected Cypher model. The
first-pass score is deliberately conservative; review ``benchmark_result.json``
before selecting a baseline.
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
from common.config.models import DEFAULT_CYPHER_CANDIDATES
from common.evaluation import aggregate_scores, load_benchmark, score_answer
from common.mlflow import MlflowRunService
from common.runtime.factory import build_runtime
from scripts.run_smoke_test import initial_state, summarize_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="benchmark/northwind_questions.csv")
    parser.add_argument("--cypher-model", action="append", dest="cypher_models")
    parser.add_argument("--conversational-model")
    parser.add_argument("--run-name-prefix", default="architecture1")
    parser.add_argument("--output", default="benchmark/architecture1_sweep.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    questions = load_benchmark(args.benchmark)
    candidates = args.cypher_models or [
        candidate.name
        for candidate in DEFAULT_CYPHER_CANDIDATES
        if candidate.provider in {"mistral", "ollama"}
    ]
    settings = load_settings()
    report: list[dict] = []
    for model_name in candidates:
        models = settings.models
        if args.conversational_model:
            models = replace(models, conversational_model=args.conversational_model)
        models = replace(models, cypher_model=model_name)
        runtime = None
        try:
            runtime = build_runtime(settings=replace(settings, models=models), architecture="generic")
            outcomes = []
            for item in questions:
                state = runtime.graph.invoke(initial_state(item.question))
                result = summarize_state(state)
                outcomes.append(
                    {
                        "group": item.group,
                        "question": item.question,
                        "expected_answer": item.expected_answer,
                        "answer": result.get("answer"),
                        "structured_result": result.get("structured_result"),
                        "score": score_answer(result.get("answer"), item.expected_answer),
                        "result": result,
                    }
                )
            summary = aggregate_scores(item["score"] for item in outcomes)
            benchmark = {"benchmark_id": Path(args.benchmark).stem, "summary": summary, "questions": outcomes}
            mlflow_run = MlflowRunService(settings.mlflow).log_benchmark_result(
                runtime_metadata=runtime.metadata(),
                benchmark=benchmark,
                prompts={"schema_prompt": runtime.schema_prompt},
                run_name=f"{args.run_name_prefix}-{model_name}",
                tags={"architecture": "generic", "source": "architecture1_sweep"},
            )
            report.append({"model": model_name, "summary": summary, "run_id": mlflow_run.run_id})
        finally:
            if runtime is not None:
                close = getattr(runtime.neo4j_client, "close", None)
                if callable(close):
                    close()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

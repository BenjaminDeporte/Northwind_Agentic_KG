"""Run one live question through a selected architecture.

Usage:
    uv run python scripts/run_smoke_test.py --question "How many customers are there?"

The script reports workflow outputs and tool envelopes. It does not create a
custom trace or persist results; MLflow logging belongs to Phase 4.8.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

if __package__ in {None, ""}:
    # Support the documented `uv run python scripts/run_smoke_test.py` form.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import load_settings
from common.runtime.factory import build_runtime
from architectures.generic.state import AgentState


DEFAULT_OLLAMA_MODEL = (
    "hf.co/mradermacher/text-to-cypher-Gemma-3-4B-Instruct-2025.04.0-GGUF:Q4_K_M"
)


def initial_state(question: str) -> AgentState:
    return {
        "question": question,
        "route": "agent",
        "messages": [],
        "draft_answer": None,
        "draft_result": None,
        "answer": None,
        "result": None,
        "loop_count": 0,
        "error": None,
    }


def _payload(message: ToolMessage) -> dict[str, Any]:
    try:
        parsed = json.loads(str(message.content))
    except (TypeError, json.JSONDecodeError):
        return {"raw": str(message.content)}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


def summarize_state(state: AgentState) -> dict[str, Any]:
    """Convert the compiled graph state into JSON-safe smoke-test output."""
    messages = state.get("messages", [])
    generated = [
        str(message.content)
        for message in messages
        if isinstance(message, AIMessage) and message.name == "text2cypher"
    ]
    validations = [
        _payload(message)
        for message in messages
        if isinstance(message, ToolMessage) and message.name == "validate_cypher"
    ]
    neo4j_results = [
        _payload(message)
        for message in messages
        if isinstance(message, ToolMessage) and message.name == "neo4j"
    ]
    return {
        "question": state.get("question"),
        "route": state.get("route"),
        "loop_count": state.get("loop_count", 0),
        "answer": state.get("answer"),
        "structured_result": state.get("result"),
        "error": state.get("error"),
        "generated_cypher": generated,
        "validation_attempts": validations,
        "neo4j_results": neo4j_results,
    }


def _settings_with_overrides(settings, args):
    models = settings.models
    if args.conversational_model:
        models = replace(models, conversational_model=args.conversational_model)
    if args.cypher_model:
        models = replace(models, cypher_model=args.cypher_model)
    return replace(settings, models=models)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True, help="Question to submit to the graph")
    parser.add_argument("--architecture", default="generic", help="Registered architecture name")
    parser.add_argument("--conversational-model", help="Override CONVERSATIONAL_MODEL")
    parser.add_argument(
        "--cypher-model",
        help="Override CYPHER_MODEL; use the full Ollama model tag for Gemma",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = _settings_with_overrides(load_settings(), args)
        runtime = build_runtime(architecture=args.architecture, settings=settings)
        state = runtime.graph.invoke(initial_state(args.question))
        print(json.dumps(summarize_state(state), indent=2, ensure_ascii=False, default=str))
        close = getattr(runtime.neo4j_client, "close", None)
        if callable(close):
            close()
        return 0 if state.get("error") is None else 1
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

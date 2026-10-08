"""Cached shared runtime and MLflow-backed question execution."""

import logging
from dataclasses import replace
from typing import Any, NamedTuple

import streamlit as st

logger = logging.getLogger(__name__)


class AgentRuntime(NamedTuple):
    """Resources shared by Streamlit reruns in this server process."""

    neo4j_client: Any
    graph: Any
    settings: Any
    schema_prompt: str


class QuestionRunResult(NamedTuple):
    """Completed graph state, or a displayable error when no state exists."""

    state: dict[str, Any] | None
    error: str | None
    mlflow_run_id: str | None = None
    mlflow_url: str | None = None


@st.cache_resource(show_spinner=False)
def get_runtime(architecture: str = "generic", cypher_model: str | None = None) -> AgentRuntime:
    """Create and cache one runtime per selected architecture/model pair."""
    from common.config import load_settings
    from common.runtime.factory import build_runtime

    settings = load_settings()
    if cypher_model:
        settings = replace(settings, models=replace(settings.models, cypher_model=cypher_model))
    runtime = build_runtime(architecture=architecture, settings=settings)
    return AgentRuntime(runtime.neo4j_client, runtime.graph, runtime.settings, runtime.schema_prompt)


def run_question(question: str) -> QuestionRunResult:
    """Run one question from a fresh state and log the result to MLflow."""
    if not isinstance(question, str) or not question.strip():
        return QuestionRunResult(state=None, error="Enter a question to run the agent.")

    from scripts.run_smoke_test import initial_state, summarize_state
    from src.streamlit.components.configuration import CONFIG_KEY

    configuration = st.session_state.get(CONFIG_KEY, {"architecture": "generic", "cypher_model": None})
    initial: dict[str, Any] = initial_state(question.strip())
    try:
        runtime = get_runtime(configuration["architecture"], configuration.get("cypher_model"))
        final_state = runtime.graph.invoke(initial)
    except Exception as exc:
        logger.exception("Northwind graph invocation failed")
        return QuestionRunResult(state=None, error=str(exc))

    mlflow_run_id = None
    mlflow_url = None
    try:
        from common.mlflow import MlflowRunService

        logged = MlflowRunService(runtime.settings.mlflow).log_result(
            runtime_metadata=runtime.settings.public_metadata() | {
                "architecture": configuration["architecture"],
                "cypher_model": configuration.get("cypher_model") or runtime.settings.models.cypher_model,
            },
            result=summarize_state(final_state),
            prompts={"schema_prompt": runtime.schema_prompt},
            run_name=f"streamlit-{configuration['architecture']}",
            tags={"source": "streamlit", "architecture": configuration["architecture"]},
        )
        mlflow_run_id = logged.run_id
        if logged.run_id:
            experiment_id = logged.experiment_id or "0"
            mlflow_url = f"{runtime.settings.mlflow.tracking_uri.rstrip('/')}/#/experiments/{experiment_id}/runs/{logged.run_id}"
    except Exception as exc:
        logger.exception("Question completed, but MLflow logging failed")
        return QuestionRunResult(state=final_state, error=f"MLflow logging failed: {exc}")

    return QuestionRunResult(state=final_state, error=None, mlflow_run_id=mlflow_run_id, mlflow_url=mlflow_url)

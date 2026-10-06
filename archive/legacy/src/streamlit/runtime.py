"""Cached runtime resources and a per-question runner for the Streamlit app.

Neo4j modules are intentionally imported inside the cached factory. The app can
load its shell without requiring Neo4j credentials; the first caller creates
and caches the driver, tool registry, and compiled LangGraph.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, NamedTuple

import streamlit as st

if TYPE_CHECKING:
    from src.agents.state import AgentState


logger = logging.getLogger(__name__)


class AgentRuntime(NamedTuple):
    """Resources shared by Streamlit reruns in this server process."""

    neo4j_client: Any
    tools: dict[str, Callable[..., dict]]
    graph: Any


class QuestionRunResult(NamedTuple):
    """Completed graph state, or a displayable error when no state exists."""

    state: dict[str, Any] | None
    error: str | None


@st.cache_resource(show_spinner=False)
def get_runtime() -> AgentRuntime:
    """Create the Northwind runtime on first use, then reuse it across reruns."""
    from src.agents.graph import compile_graph
    from src.neo4j.client import client
    from src.neo4j.tools import (
        aggregate,
        co_purchase,
        customer_history,
        impact_analysis,
        lookup_entity,
        run_readonly_cypher,
    )

    tools = {
        "lookup_entity": lookup_entity,
        "impact_analysis": impact_analysis,
        "co_purchase": co_purchase,
        "customer_history": customer_history,
        "aggregate": aggregate,
        "run_readonly_cypher": run_readonly_cypher,
    }
    return AgentRuntime(
        neo4j_client=client,
        tools=tools,
        graph=compile_graph(tools),
    )


def run_question(question: str) -> QuestionRunResult:
    """Run one question from a fresh state and append its completed run once."""
    if not isinstance(question, str) or not question.strip():
        return QuestionRunResult(state=None, error="Enter a question to run the agent.")

    initial_state: AgentState = {
        "question": question.strip(),
        "route": "",
        "messages": [],
        "trace": [],
        "draft_answer": None,
        "draft_citations": [],
        "consistency_status": "pending",
        "consistency_feedback": None,
        "answer": "",
        "citations": [],
        "confidence": 0.0,
        "confidence_rationale": "",
        "loop_count": 0,
        "error": None,
    }

    try:
        runtime = get_runtime()
        final_state = runtime.graph.invoke(initial_state)
    except Exception as exc:
        logger.exception("Northwind graph invocation failed")
        if isinstance(exc, ValueError) and "must be set" in str(exc):
            error = str(exc)
        else:
            error = "The agent could not complete this question. Check the Streamlit server log for details."
        return QuestionRunResult(state=None, error=error)

    try:
        from src.utils.runlog import write_run

        write_run(final_state)
    except Exception:
        logger.exception("Northwind graph completed, but its run could not be logged")
        return QuestionRunResult(
            state=final_state,
            error="The answer was generated, but the run could not be saved to the run log.",
        )

    return QuestionRunResult(state=final_state, error=None)

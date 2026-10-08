"""Streamlit controls for selecting an architecture/model configuration."""

from __future__ import annotations

import streamlit as st

from common.config.models import DEFAULT_CYPHER_CANDIDATES
from common.runtime.architectures import default_architecture_registry


CONFIG_KEY = "runtime_configuration"


def render_configuration_panel() -> dict[str, str]:
    registry = default_architecture_registry()
    architectures = list(registry.names())
    models = [candidate.name for candidate in DEFAULT_CYPHER_CANDIDATES if candidate.provider in {"mistral", "ollama"}]
    current = st.session_state.get(CONFIG_KEY, {"architecture": "generic", "cypher_model": models[0]})
    st.sidebar.header("Runtime configuration")
    architecture = st.sidebar.selectbox(
        "Architecture",
        architectures,
        index=architectures.index(current.get("architecture", "generic")),
        help="Architecture 1 is currently implemented; later architectures are registered placeholders.",
    )
    cypher_model = st.sidebar.selectbox(
        "Cypher model",
        models,
        index=models.index(current.get("cypher_model", models[0])) if current.get("cypher_model", models[0]) in models else 0,
    )
    if architecture != "generic":
        st.sidebar.warning("This architecture is registered but not implemented yet.")
    configuration = {"architecture": architecture, "cypher_model": cypher_model}
    st.session_state[CONFIG_KEY] = configuration
    st.sidebar.caption("Conversational model: fixed by environment configuration")
    return configuration


__all__ = ["CONFIG_KEY", "render_configuration_panel"]

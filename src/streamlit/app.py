"""Minimal Streamlit entry point for the Northwind agent UI."""

import sys
from pathlib import Path

# `streamlit run src/streamlit/app.py` puts this script's directory on sys.path.
# Add the repository root so the existing `src.*` imports resolve consistently.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.streamlit.components.chat import render_chat_panel
from src.streamlit.components.trace_drawer import render_trace_drawer


st.set_page_config(
    page_title="Northwind Agentic Knowledge Graph",
    page_icon="🌐",
    layout="wide",
)

st.title("Northwind Agentic Knowledge Graph")
st.caption("Ask questions about the Northwind graph and inspect the supporting evidence.")

chat_column, trace_column, evidence_column = st.columns([3, 2, 2], gap="medium")

with chat_column:
    st.subheader("Chat")
    render_chat_panel()

with trace_column:
    st.subheader("Traceable Explainability")
    with st.container(height=450, border=True, key="trace_panel_scroll"):
        render_trace_drawer(st.session_state.get("last_run_state"))

with evidence_column:
    st.subheader("Evidence Graph")
    with st.container(height=450, border=True, key="evidence_graph_scroll"):
        st.info("The graph evidence for an answer will appear here.")

"""Chat history rendering and question submission for the Streamlit app."""

import streamlit as st

from src.streamlit.runtime import run_question


CHAT_HISTORY_KEY = "chat_history"
LAST_RUN_STATE_KEY = "last_run_state"


def _render_history(history: list[dict]) -> None:
    for message in history:
        with st.chat_message(message["role"]):
            if message.get("kind") == "error":
                st.error(message["content"])
            else:
                st.markdown(message["content"])
                if message.get("warning"):
                    st.warning(message["warning"])


def render_chat_panel() -> None:
    """Render session history and run a fresh graph for a submitted prompt."""
    history = st.session_state.setdefault(CHAT_HISTORY_KEY, [])
    with st.container(height=450, border=True, key="chat_history_scroll", autoscroll=True):
        _render_history(history)

    question = st.chat_input("Ask a question about the Northwind graph")
    if not question:
        return

    history.append({"role": "user", "content": question})
    # Do not leave a previous answer's trace and graph beside a failed new run.
    st.session_state[LAST_RUN_STATE_KEY] = None

    with st.spinner("Asking the Northwind agent..."):
        result = run_question(question)

    if result.state is None:
        error = result.error or "The agent could not complete this question."
        history.append({"role": "assistant", "content": error, "kind": "error"})
    else:
        st.session_state[LAST_RUN_STATE_KEY] = result.state
        answer = result.state.get("answer", "")
        if answer:
            history.append({
                "role": "assistant",
                "content": answer,
                "warning": result.error,
            })
        else:
            error = result.error or "The graph completed without returning an answer."
            history.append({"role": "assistant", "content": error, "kind": "error"})

    # Render the complete new exchange on the next script pass, above chat_input.
    st.rerun()

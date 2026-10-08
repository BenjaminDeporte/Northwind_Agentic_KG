"""Trace and confidence display for the Streamlit app."""

from typing import Any

import streamlit as st


def render_trace_drawer(state: dict[str, Any] | None) -> None:
    """Render trace and confidence in separate expandable subwindows."""
    if state is None:
        with st.expander("Trace", expanded=False):
            st.caption("Submit a question to see its route and execution trace.")
        with st.expander("Confidence", expanded=False):
            st.caption("Confidence details will appear after a question is answered.")
        return

    with st.expander("Trace", expanded=False):
        route = state.get("route") or "unknown"
        st.markdown(f"**Route:** `{route}`")

        state_error = state.get("error")
        if state_error:
            st.warning(str(state_error))

        trace = state.get("trace") or []
        if not trace:
            messages = state.get("messages") or []
            if messages:
                st.caption(f"{len(messages)} workflow messages recorded; detailed execution is in MLflow.")
                generated = [
                    message.content
                    for message in messages
                    if getattr(message, "name", None) == "text2cypher"
                ]
                if generated:
                    st.code(str(generated[-1]), language="cypher")
            else:
                st.caption("No tool calls in this run.")
        else:
            for record in trace:
                step = record.get("step", "?")
                tool_name = record.get("tool_name", "unknown tool")
                st.markdown(f"**Step {step}: {tool_name}**")
                st.caption(
                    f"Mode: {record.get('mode', '—')} · "
                    f"Status: {record.get('status', '—')} · "
                    f"Rows: {record.get('result_rows', 0)} · "
                    f"Latency: {record.get('latency_ms', 0)} ms · "
                    f"Retries: {record.get('retry_count', 0)}"
                )

                args = record.get("args")
                if args:
                    st.json(args)

                cypher = record.get("cypher")
                if record.get("mode") == "exploratory" and cypher:
                    st.code(str(cypher), language="cypher")
                st.divider()

    with st.expander("Confidence", expanded=False):
        confidence = state.get("confidence", 0.0)
        try:
            confidence_label = f"{float(confidence):.2f}"
        except (TypeError, ValueError):
            confidence_label = str(confidence)
        st.metric("Confidence", confidence_label)

        rationale = state.get("confidence_rationale") or "No confidence rationale was recorded."
        st.markdown("**Confidence rationale**")
        st.write(rationale)
        if state.get("result") is not None:
            st.markdown("**Structured result**")
            st.json(state["result"])

"""Headless acceptance checks for the Streamlit panel layout and one chat turn."""
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parents[1] / "src" / "streamlit" / "app.py"


def test_three_panels_have_independent_fixed_height_scroll_areas():
    app = AppTest.from_file(str(APP_PATH), default_timeout=10).run()

    assert not app.exception
    assert [item.value for item in app.subheader] == [
        "Chat", "Traceable Explainability", "Evidence Graph",
    ]
    assert {item.proto.tag for item in app.subheader} == {"h3"}
    assert [item.label for item in app.expander] == ["Trace", "Confidence"]
    assert len(app.container) == 3
    for panel in app.container:
        assert panel.proto.height_config.pixel_height == 450
        assert panel.proto.flex_container.border
    assert len(app.chat_input) == 1


def test_mocked_chat_turn_renders_answer_and_trace_without_live_services(monkeypatch):
    import src.streamlit.components.chat as chat

    long_answer = "A scrollable mocked response. " * 60
    state = {
        "answer": long_answer,
        "route": "agent",
        "trace": [{
            "step": 1,
            "tool_name": "customer_history",
            "mode": "curated",
            "status": "ok",
            "result_rows": 2,
            "latency_ms": 12,
            "retry_count": 0,
            "args": {"customer_key": "ALFKI"},
        }],
        "confidence": 0.9,
        "confidence_rationale": "The mocked result matches the requested customer.",
        "citations": [{"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste"}],
    }
    monkeypatch.setattr(
        chat,
        "run_question",
        lambda question: SimpleNamespace(state=state, error=None),
    )

    app = AppTest.from_file(str(APP_PATH), default_timeout=10).run()
    app.chat_input[0].set_value("Show the order history for customer ALFKI").run()

    assert not app.exception
    assert app.session_state["last_run_state"] == state
    assert app.session_state["chat_history"][-1]["content"] == long_answer
    assert any(message.name == "user" for message in app.chat_message)
    assert any(message.name == "assistant" for message in app.chat_message)

    assert [item.label for item in app.expander] == ["Trace", "Confidence"]
    assert len(app.container) == 3

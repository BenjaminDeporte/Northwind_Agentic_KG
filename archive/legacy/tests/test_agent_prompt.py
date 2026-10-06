"""Deterministic tests for agent prompting and Mistral model/client setup."""
from types import SimpleNamespace

import pytest

from src.agents import llm


def test_agent_prompt_uses_schema_generated_from_authoritative_source(monkeypatch):
    captured = {}

    def fake_complete(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="FINAL: ok"))])

    monkeypatch.setattr("src.agents.schema_prompt.generate_schema_prompt", lambda: "SCHEMA_FROM_SOURCE")
    monkeypatch.setattr(llm, "complete_mistral_chat", fake_complete)

    result = llm.generate_agent_response("question", [])

    assert result == "FINAL: ok"
    assert captured["messages"][0]["content"].count("SCHEMA_FROM_SOURCE") == 1
    assert "ALFKI" in captured["messages"][0]["content"]
    assert captured["model_name"] is None  # omitted model resolves to Mistral Large
    assert not hasattr(llm, "AGENT_SYSTEM_PROMPT")



def test_agent_prompt_routes_customer_questions_by_intent(monkeypatch):
    captured = {}

    def fake_complete(**kwargs):
        captured.update(kwargs)
        response = 'TOOL: run_readonly_cypher({"query": "MATCH ..."})'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))])

    monkeypatch.setattr("src.agents.schema_prompt.generate_schema_prompt", lambda: "SCHEMA")
    monkeypatch.setattr(llm, "complete_mistral_chat", fake_complete)

    llm.generate_agent_response("What products do SAVEA and ALFKI both order?", [])

    prompt = captured["messages"][0]["content"]
    assert "Choose tools from the operation the user asks you to perform" in prompt
    assert "It returns that customer's orders; it does not answer a comparison" in prompt
    assert "For questions asking which products are common/shared between named customers" in prompt
    assert "WHERE size(customer_ids) = 2" in prompt
    assert "Do not use this rule for questions comparing two or more customers" in prompt
    assert "The FINAL marker requests synthesis and a consistency check" in prompt


def test_schema_generation_failure_is_not_replaced_with_partial_schema(monkeypatch):
    def fail_schema_generation():
        raise RuntimeError("SCHEMA.md could not be parsed")

    monkeypatch.setattr("src.agents.schema_prompt.generate_schema_prompt", fail_schema_generation)
    monkeypatch.setattr(llm, "complete_mistral_chat", lambda **kwargs: pytest.fail("must not call Mistral without the source schema"))

    with pytest.raises(RuntimeError, match="SCHEMA.md could not be parsed"):
        llm.generate_agent_response("question", [])


def test_explicit_api_key_overrides_environment_key(monkeypatch):
    captured = {}
    monkeypatch.setenv("MISTRAL_API_KEY", "environment-key")
    monkeypatch.setattr(llm, "Mistral", lambda *, api_key: captured.update(api_key=api_key) or "client")

    client = llm.get_mistral_client(api_key="explicit-key")

    assert client == "client"
    assert captured["api_key"] == "explicit-key"


def test_client_uses_environment_key_when_argument_is_omitted(monkeypatch):
    captured = {}
    monkeypatch.setenv("MISTRAL_API_KEY", "environment-key")
    monkeypatch.setattr(llm, "Mistral", lambda *, api_key: captured.update(api_key=api_key) or "client")

    llm.get_mistral_client()

    assert captured["api_key"] == "environment-key"


def test_client_requires_key_only_when_argument_and_environment_are_missing(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(llm, "load_dotenv", lambda: None)
    monkeypatch.setattr(llm, "Mistral", lambda **kwargs: pytest.fail("must not construct unauthenticated client"))

    with pytest.raises(ValueError, match="Pass api_key or set MISTRAL_API_KEY"):
        llm.get_mistral_client()


def test_chat_request_defaults_to_large_and_accepts_any_mistral_model(monkeypatch):
    captured = {}

    class FakeChat:
        def complete(self, **kwargs):
            captured.update(kwargs)
            return "response"

    monkeypatch.setattr(llm, "get_mistral_client", lambda *, api_key=None: SimpleNamespace(chat=FakeChat()))
    messages = [{"role": "user", "content": "hello"}]

    assert llm.complete_mistral_chat(messages=messages, api_key="one-key") == "response"
    assert captured["model"] == llm.MODEL_AGENT
    assert llm.complete_mistral_chat(messages=messages, model_name="mistral-small-latest") == "response"
    assert captured["model"] == "mistral-small-latest"



def test_consistency_evaluator_parses_json_decision(monkeypatch):
    captured = {}

    def fake_complete(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='```json\n{"decision":"revise","feedback":"ALFKI is missing."}\n```'
        ))])

    monkeypatch.setattr(llm, "complete_mistral_chat", fake_complete)
    result = llm.evaluate_answer_consistency(
        question="What do SAVEA and ALFKI both order?",
        candidate_answer="SAVEA orders Chai.",
        citations=[{"label": "Customer", "key": "SAVEA", "name": "Save-a-lot"}],
        supporting_results=[{"tool": "customer_history", "status": "ok"}],
    )

    assert result == {"decision": "revise", "feedback": "ALFKI is missing."}
    assert captured["temperature"] == 0.0
    assert captured["max_tokens"] == 350
    assert "every requested subject" in captured["messages"][0]["content"]


def test_consistency_evaluator_fails_closed_on_unstructured_response(monkeypatch):
    monkeypatch.setattr(llm, "complete_mistral_chat", lambda **kwargs: "not JSON")
    result = llm.evaluate_answer_consistency(
        question="Q", candidate_answer="A", citations=[], supporting_results=[]
    )
    assert result["decision"] == "revise"

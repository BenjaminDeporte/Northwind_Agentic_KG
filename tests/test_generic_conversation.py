import json
from types import SimpleNamespace

from architectures.generic.conversation import (
    ConversationalTool,
    build_answer_messages,
    generate_answer,
    route_question,
)


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_router_uses_conversational_model_and_explicit_route():
    client = FakeClient('{"route":"chitchat"}')
    assert route_question("hello", conversational_model="mistral-large", model_client=client) == "chitchat"
    assert client.calls[0]["model_name"] == "mistral-large"
    assert "route exactly one of" in client.calls[0]["messages"][0]["content"]


def test_invalid_router_json_has_safe_agent_fallback():
    client = FakeClient("not json")
    assert route_question("How many customers?", conversational_model="m", model_client=client) == "agent"


def test_router_reads_mistral_sdk_object_response_shape():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"route":"agent"}'))]
    )
    client = FakeClient(response)
    assert route_question("How many customers?", conversational_model="m", model_client=client) == "agent"


def test_answer_generation_preserves_structured_result():
    result = {"value": 91}
    client = FakeClient(json.dumps({"answer": "There are 91 customers.", "result": result}))
    answer, parsed = generate_answer(
        "How many customers?",
        "MATCH (c:Customer) RETURN count(c)",
        {"status": "ok", "rows": []},
        route="agent",
        conversational_model="mistral-large",
        model_client=client,
    )
    assert answer == "There are 91 customers."
    assert parsed == result
    assert '"query_result"' in client.calls[0]["messages"][1]["content"]


def test_malformed_structured_answer_remains_visible_as_text():
    client = FakeClient("The answer is 91 customers.")
    answer, result = generate_answer(
        "How many customers?",
        None,
        None,
        route="agent",
        conversational_model="m",
        model_client=client,
    )
    assert answer == "The answer is 91 customers."
    assert result is None


def test_route_specific_prompts_do_not_infer_refusal_from_empty_result():
    messages = build_answer_messages(
        "Can you help?", None, None, route="refusal", prompt_version="v1"
    )
    assert "Decline" in messages[0]["content"]
    assert "graph facts" in messages[0]["content"]


def test_conversational_tool_exposes_handler_methods():
    client = FakeClient('{"route":"refusal"}', '{"answer":"I cannot help.","result":null}')
    tool = ConversationalTool(client)
    assert tool.route_question("unsafe", conversational_model="m") == "refusal"
    assert tool.generate_answer(
        "unsafe", None, None, route="refusal", conversational_model="m", prompt_version="v1"
    ) == ("I cannot help.", None)

from types import SimpleNamespace

import pytest

from common.config import load_settings
from common.providers.mistral import MistralChatClient, build_mistral_client


class FakeChat:
    def __init__(self):
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"route":"agent"}'))])


class FakeSdkClient:
    def __init__(self):
        self.chat = FakeChat()


def _settings(**overrides):
    values = {
        "NEO4J_URI": "neo4j://example",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "secret",
        "MISTRAL_API_KEY": "mistral-secret",
    }
    values.update(overrides)
    return load_settings(
        dotenv_path="/tmp/northwind-provider-test-does-not-exist",
        environ=values,
    )


def test_complete_adapts_protocol_to_mistral_chat_api():
    sdk = FakeSdkClient()
    client = MistralChatClient(client=sdk)
    response = client.complete(
        model_name="mistral-large-latest",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.0,
        max_tokens=80,
    )
    assert response.choices[0].message.content == '{"route":"agent"}'
    assert sdk.chat.calls == [
        {
            "model": "mistral-large-latest",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.0,
            "max_tokens": 80,
        }
    ]


def test_client_requires_key_only_when_constructing_real_sdk_client():
    with pytest.raises(ValueError, match="API key"):
        MistralChatClient()
    # An injected fake client is valid for deterministic tests without secrets.
    assert MistralChatClient(client=FakeSdkClient())


def test_build_client_uses_settings_key_and_provider():
    sdk = FakeSdkClient()
    settings = _settings()
    # Replace construction at the adapter boundary, without importing or
    # contacting the real SDK.
    client = MistralChatClient(api_key=settings.models.conversational_api_key, client=sdk)
    assert client._client is sdk


def test_build_client_rejects_non_mistral_provider():
    settings = _settings(CONVERSATIONAL_PROVIDER="openai")
    with pytest.raises(ValueError, match="conversational_provider"):
        build_mistral_client(settings)


def test_complete_rejects_missing_model_or_messages():
    client = MistralChatClient(client=FakeSdkClient())
    with pytest.raises(ValueError, match="model_name"):
        client.complete(model_name="", messages=[{"role": "user", "content": "x"}], temperature=0, max_tokens=1)
    with pytest.raises(ValueError, match="message"):
        client.complete(model_name="m", messages=[], temperature=0, max_tokens=1)

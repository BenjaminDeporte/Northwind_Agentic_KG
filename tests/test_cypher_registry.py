import json
from io import BytesIO

import pytest

from common.config import load_settings
from common.config.models import CypherModelCandidate
from common.providers.cypher import CypherProviderRegistry, build_cypher_registry
from common.providers.ollama import OllamaChatClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def __call__(self, request, timeout):
        self.request = request
        return FakeResponse(self.payload)


def _settings(**overrides):
    values = {
        "NEO4J_URI": "neo4j://example",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "secret",
        "CYPHER_MODEL": "ollama-model",
        "CYPHER_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "OLLAMA_NUM_GPU": "0",
    }
    values.update(overrides)
    return load_settings(
        dotenv_path="/tmp/northwind-cypher-test-does-not-exist", environ=values
    )


def test_ollama_client_posts_non_streaming_cpu_request():
    opener = FakeOpener({"message": {"role": "assistant", "content": "MATCH (n) RETURN n"}})
    client = OllamaChatClient(base_url="http://localhost:11434/", num_gpu=0, opener=opener)
    response = client.complete(
        model_name="ollama-model",
        messages=[{"role": "user", "content": "List nodes"}],
        temperature=0.0,
        max_tokens=100,
    )
    body = json.loads(opener.request.data)
    assert response["message"]["content"].startswith("MATCH")
    assert opener.request.full_url == "http://localhost:11434/api/chat"
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0.0, "num_predict": 100, "num_gpu": 0}


def test_ollama_response_shape_is_accepted_by_text2cypher():
    opener = FakeOpener({"message": {"role": "assistant", "content": r"MATCH (n)\nRETURN n"}})
    client = OllamaChatClient(opener=opener)
    from architectures.generic.text2cypher import generate_cypher

    query = generate_cypher(
        "List nodes",
        schema_prompt="Schema",
        model_name="ollama-model",
        prompt_version="v1",
        model_client=client,
    )
    assert query == "MATCH (n)\nRETURN n"


def test_registry_registers_and_selects_provider():
    registry = CypherProviderRegistry()
    client = object()
    registry.register(model_name="model-a", provider="test", client=client)
    assert registry.client_for("model-a") is client
    assert registry.provider_for("model-a") == "test"
    assert registry.model_names() == ("model-a",)
    with pytest.raises(ValueError, match="Unsupported"):
        registry.client_for("missing")


def test_default_registry_builds_ollama_candidate_without_a_key():
    client = object()
    registry = build_cypher_registry(
        _settings(),
        candidates=(CypherModelCandidate("ollama-model", "ollama"),),
        client_factories={"ollama-model": lambda candidate: client},
    )
    assert registry.client_for("ollama-model") is client


def test_duplicate_registration_is_rejected():
    registry = CypherProviderRegistry()
    registry.register(model_name="model-a", provider="test", client=object())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(model_name="model-a", provider="test", client=object())

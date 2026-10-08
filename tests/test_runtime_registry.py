import pytest

from common.config import load_settings
from common.providers.cypher import CypherProviderRegistry
from common.runtime.architectures import ArchitectureRegistry, default_architecture_registry
from common.runtime.factory import build_runtime


class FakeConversation:
    def complete(self, **kwargs):
        return '{"route":"agent"}'


def _settings():
    return load_settings(
        dotenv_path="/tmp/northwind-runtime-test-does-not-exist",
        environ={
            "NEO4J_URI": "neo4j://example",
            "NEO4J_USERNAME": "neo4j",
            "NEO4J_PASSWORD": "secret",
            "CONVERSATIONAL_MODEL": "conversation-test",
            "CYPHER_MODEL": "cypher-test",
        },
    )


def test_default_registry_exposes_all_four_builders_and_unknown_fails():
    registry = default_architecture_registry()
    assert registry.names() == ("curated", "curated_reflection", "generic", "generic_reflection")
    with pytest.raises(ValueError, match="Unknown architecture"):
        registry.build("missing")


def test_runtime_factory_composes_generic_graph_with_injected_dependencies():
    cypher_registry = CypherProviderRegistry()
    cypher_registry.register(model_name="cypher-test", provider="test", client=FakeConversation())
    runtime = build_runtime(
        settings=_settings(),
        conversational_client=FakeConversation(),
        cypher_registry=cypher_registry,
        neo4j_client=object(),
    )
    assert runtime.architecture == "generic"
    assert runtime.graph is not None
    assert runtime.schema_prompt.startswith("# Northwind Neo4j schema")
    assert runtime.metadata()["cypher_provider"] == "test"


def test_custom_registry_can_select_a_builder():
    registry = ArchitectureRegistry()
    registry.register("test", lambda **kwargs: kwargs["value"])
    assert registry.build("test", value=42) == 42

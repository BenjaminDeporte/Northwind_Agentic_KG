"""Architecture-agnostic runtime factory for live and test executions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.config import AppSettings, load_settings
from common.neo4j.executor import Neo4jTool
from common.neo4j.validation import validate_cypher as validate_query
from common.prompts.schema_prompt import generate_schema_prompt
from common.providers.cypher import CypherProviderRegistry, build_cypher_registry
from common.providers.mistral import MistralChatClient, build_mistral_client
from common.runtime.architectures import ArchitectureRegistry, default_architecture_registry

from architectures.generic.conversation import ConversationalTool
from architectures.generic.text2cypher import generate_cypher
from architectures.curated.tools import CuratedQueryRegistry


class GenericRuntimeHandlers:
    """Compose shared provider/tool services into the Architecture 1 contract."""

    def __init__(
        self,
        *,
        conversational: ConversationalTool,
        cypher_registry: CypherProviderRegistry,
        neo4j: Neo4jTool,
        schema: str,
        curated_registry: CuratedQueryRegistry | None = None,
    ):
        self.conversational = conversational
        self.cypher_registry = cypher_registry
        self.neo4j = neo4j
        self.schema = schema
        self.curated_registry = curated_registry or CuratedQueryRegistry.default()

    def route_question(self, question: str, *, conversational_model: str):
        return self.conversational.route_question(question, conversational_model=conversational_model)

    def generate_cypher(
        self,
        question: str,
        *,
        schema_prompt: str,
        model_name: str,
        prompt_version: str,
        previous_query: str | None = None,
        validation_error: str | None = None,
    ) -> str:
        client = self.cypher_registry.client_for(model_name)
        return generate_cypher(
            question,
            schema_prompt=schema_prompt,
            model_name=model_name,
            prompt_version=prompt_version,
            model_client=client,
            previous_query=previous_query,
            validation_error=validation_error,
        )

    def validate_cypher(self, query: str, *, schema: str) -> dict[str, Any]:
        return validate_query(
            query,
            schema=schema,
            explain=lambda normalized: self.neo4j.explain(normalized),
        )

    def run_readonly_cypher(self, query: str, *, neo4j_client: Any) -> dict[str, Any]:
        return self.neo4j.run_readonly_cypher(query, neo4j_client=neo4j_client)

    def generate_answer(
        self,
        question: str,
        query: str | None,
        query_result: dict[str, Any] | None,
        *,
        route: str,
        conversational_model: str,
        prompt_version: str,
    ):
        return self.conversational.generate_answer(
            question,
            query,
            query_result,
            route=route,
            conversational_model=conversational_model,
            prompt_version=prompt_version,
        )

    def reflect_answer(self, question: str, draft_answer: str, query_result: dict[str, Any] | None, *, conversational_model: str, prompt_version: str) -> tuple[bool, str | None]:
        return self.conversational.reflect_answer(question, draft_answer, query_result, conversational_model=conversational_model, prompt_version=prompt_version)

    def curated_tools(self) -> list[dict[str, str]]:
        return self.curated_registry.descriptions()

    def select_curated_tool(self, question: str, *, conversational_model: str, prompt_version: str) -> str | None:
        return self.conversational.select_curated_tool(question, tools=self.curated_tools(), conversational_model=conversational_model, prompt_version=prompt_version)

    def curated_query(self, name: str) -> str:
        return self.curated_registry.query(name)


@dataclass(frozen=True)
class AgentRuntime:
    graph: Any
    settings: AppSettings
    architecture: str
    schema: str
    schema_prompt: str
    handlers: GenericRuntimeHandlers
    neo4j_client: Any

    def metadata(self) -> dict[str, Any]:
        return {
            **self.settings.public_metadata(),
            "architecture": self.architecture,
            "cypher_provider": self.handlers.cypher_registry.provider_for(
                self.settings.models.cypher_model
            ),
        }


def _schema_path(settings: AppSettings) -> Path:
    path = settings.prompt.schema_path
    if path.exists():
        return path
    repository_path = Path(__file__).resolve().parents[2] / path
    if repository_path.exists():
        return repository_path
    raise FileNotFoundError(f"Configured schema file was not found: {path}")


def _neo4j_driver(settings: AppSettings) -> Any:
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password),
    )


def build_runtime(
    *,
    architecture: str = "generic",
    settings: AppSettings | None = None,
    registry: ArchitectureRegistry | None = None,
    conversational_client: Any = None,
    cypher_registry: CypherProviderRegistry | None = None,
    neo4j_client: Any = None,
) -> AgentRuntime:
    """Construct one isolated runtime and compiled architecture graph."""
    resolved = settings or load_settings()
    schema_path = _schema_path(resolved)
    schema = schema_path.read_text(encoding="utf-8")
    schema_prompt = generate_schema_prompt(schema_path)

    conversation_client = conversational_client or build_mistral_client(resolved)
    conversational = ConversationalTool(conversation_client)
    resolved_cypher_registry = cypher_registry or build_cypher_registry(resolved)
    graph_client = neo4j_client or _neo4j_driver(resolved)
    neo4j = Neo4jTool(graph_client, schema=schema)
    handlers = GenericRuntimeHandlers(
        conversational=conversational,
        cypher_registry=resolved_cypher_registry,
        neo4j=neo4j,
        schema=schema,
        curated_registry=CuratedQueryRegistry.default(),
    )
    graph = (registry or default_architecture_registry()).build(
        architecture,
        handlers=handlers,
        schema=schema,
        schema_prompt=schema_prompt,
        conversational_model=resolved.models.conversational_model,
        cypher_model=resolved.models.cypher_model,
        prompt_version=resolved.prompt.version,
        neo4j_client=graph_client,
    )
    return AgentRuntime(
        graph=graph,
        settings=resolved,
        architecture=architecture,
        schema=schema,
        schema_prompt=schema_prompt,
        handlers=handlers,
        neo4j_client=graph_client,
    )


__all__ = ["AgentRuntime", "GenericRuntimeHandlers", "build_runtime"]

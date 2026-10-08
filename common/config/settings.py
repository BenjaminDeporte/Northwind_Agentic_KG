"""Typed, architecture-agnostic application settings.

This module is the only shared boundary that reads deployment configuration.
Secrets are loaded for client construction but are excluded from public
metadata and from the settings object's representation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


def _value(source: Mapping[str, str | None], key: str, default: str | None = None) -> str | None:
    value = source.get(key)
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def _int(source: Mapping[str, str | None], key: str, default: int) -> int:
    raw = _value(source, key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc


def _required(source: Mapping[str, str | None], key: str) -> str:
    value = _value(source, key)
    if value is None:
        raise ValueError(f"Missing required configuration: {key}")
    return value


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    username: str
    password: str = field(repr=False)
    database: str = "neo4j"


@dataclass(frozen=True)
class ModelSettings:
    conversational_model: str = "mistral-large-latest"
    conversational_provider: str = "mistral"
    conversational_api_key: str | None = field(default=None, repr=False)
    cypher_model: str = "mistral-large-latest"
    cypher_provider: str = "mistral"
    cypher_api_key: str | None = field(default=None, repr=False)
    cypher_api_key_env: str | None = None


@dataclass(frozen=True)
class PromptSettings:
    version: str = "generic-v1"
    schema_path: Path = Path("SCHEMA.md")


@dataclass(frozen=True)
class MLflowSettings:
    tracking_uri: str = "http://localhost:5000"
    experiment_name: str = "northwind-agentic-kg"
    artifact_location: str | None = None


@dataclass(frozen=True)
class StreamlitSettings:
    address: str = "0.0.0.0"
    port: int = 8501


@dataclass(frozen=True)
class AppSettings:
    neo4j: Neo4jSettings
    models: ModelSettings
    prompt: PromptSettings
    mlflow: MLflowSettings
    streamlit: StreamlitSettings
    app_name: str = "Northwind_Agentic_KG"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    def public_metadata(self) -> dict[str, str | int | None]:
        """Return safe metadata suitable for logs or MLflow parameters."""
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "neo4j_database": self.neo4j.database,
            "conversational_model": self.models.conversational_model,
            "conversational_provider": self.models.conversational_provider,
            "cypher_model": self.models.cypher_model,
            "cypher_provider": self.models.cypher_provider,
            "cypher_api_key_env": self.models.cypher_api_key_env,
            "prompt_version": self.prompt.version,
            "schema_path": str(self.prompt.schema_path),
            "mlflow_tracking_uri": self.mlflow.tracking_uri,
            "mlflow_experiment_name": self.mlflow.experiment_name,
            "streamlit_address": self.streamlit.address,
            "streamlit_port": self.streamlit.port,
            "log_level": self.log_level,
        }


def load_settings(
    dotenv_path: str | Path | None = None,
    *,
    environ: Mapping[str, str | None] | None = None,
    require_neo4j: bool = True,
) -> AppSettings:
    """Load settings with environment variables taking precedence over `.env`.

    ``environ`` is injectable for deterministic tests. The real application
    should call this without it; credentials remain in memory and are never
    printed by this function.
    """
    file_values: dict[str, str | None] = {}
    path = Path(dotenv_path) if dotenv_path is not None else Path(".env")
    if path.is_file():
        file_values.update({key: value for key, value in dotenv_values(path).items()})
    # An injected mapping is a complete environment view for deterministic
    # callers. The normal path uses the process environment over `.env`.
    source = {**file_values, **(dict(environ) if environ is not None else dict(os.environ))}

    uri = _value(source, "NEO4J_URI")
    username = _value(source, "NEO4J_USERNAME") or _value(source, "NEO4J_USER")
    password = _value(source, "NEO4J_PASSWORD")
    if require_neo4j:
        uri = uri or _required(source, "NEO4J_URI")
        username = username or _required(source, "NEO4J_USERNAME")
        password = password or _required(source, "NEO4J_PASSWORD")
    else:
        uri = uri or ""
        username = username or ""
        password = password or ""

    conversational_key_env = _value(source, "CONVERSATIONAL_API_KEY_ENV", "MISTRAL_API_KEY")
    cypher_key_env = _value(source, "CYPHER_API_KEY_ENV", "MISTRAL_API_KEY")
    return AppSettings(
        neo4j=Neo4jSettings(
            uri=uri,
            username=username,
            password=password,
            database=_value(source, "NEO4J_DATABASE", "neo4j") or "neo4j",
        ),
        models=ModelSettings(
            conversational_model=_value(source, "CONVERSATIONAL_MODEL", "mistral-large-latest") or "mistral-large-latest",
            conversational_provider=_value(source, "CONVERSATIONAL_PROVIDER", "mistral") or "mistral",
            conversational_api_key=_value(source, conversational_key_env or "MISTRAL_API_KEY"),
            cypher_model=_value(source, "CYPHER_MODEL", "mistral-large-latest") or "mistral-large-latest",
            cypher_provider=_value(source, "CYPHER_PROVIDER", "mistral") or "mistral",
            cypher_api_key=_value(source, cypher_key_env or "MISTRAL_API_KEY"),
            cypher_api_key_env=cypher_key_env,
        ),
        prompt=PromptSettings(
            version=_value(source, "PROMPT_VERSION", "generic-v1") or "generic-v1",
            schema_path=Path(_value(source, "SCHEMA_PATH", "SCHEMA.md") or "SCHEMA.md"),
        ),
        mlflow=MLflowSettings(
            tracking_uri=_value(source, "MLFLOW_TRACKING_URI", "http://localhost:5000") or "http://localhost:5000",
            experiment_name=_value(source, "MLFLOW_EXPERIMENT_NAME", "northwind-agentic-kg") or "northwind-agentic-kg",
            artifact_location=_value(source, "MLFLOW_ARTIFACT_LOCATION"),
        ),
        streamlit=StreamlitSettings(
            address=_value(source, "STREAMLIT_SERVER_ADDRESS", "0.0.0.0") or "0.0.0.0",
            port=_int(source, "STREAMLIT_SERVER_PORT", 8501),
        ),
        app_name=_value(source, "APP_NAME", "Northwind_Agentic_KG") or "Northwind_Agentic_KG",
        app_version=_value(source, "APP_VERSION", "0.1.0") or "0.1.0",
        log_level=_value(source, "LOG_LEVEL", "INFO") or "INFO",
    )


__all__ = [
    "AppSettings",
    "MLflowSettings",
    "ModelSettings",
    "Neo4jSettings",
    "PromptSettings",
    "StreamlitSettings",
    "load_settings",
]

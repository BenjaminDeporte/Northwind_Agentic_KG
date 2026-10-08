from pathlib import Path

import pytest

from common.config import load_settings


def _env(**overrides):
    values = {
        "NEO4J_URI": "neo4j+s://example",
        "NEO4J_USERNAME": "neo4j-user",
        "NEO4J_PASSWORD": "secret",
        "NEO4J_DATABASE": "northwind",
        "MISTRAL_API_KEY": "mistral-secret",
    }
    values.update(overrides)
    return values


def test_load_settings_builds_typed_sections_and_redacts_secrets():
    settings = load_settings(environ=_env(), require_neo4j=True)
    assert settings.neo4j.uri == "neo4j+s://example"
    assert settings.neo4j.database == "northwind"
    assert settings.models.conversational_model == "mistral-large-latest"
    assert settings.models.conversational_api_key == "mistral-secret"
    assert settings.mlflow.tracking_uri == "http://localhost:5000"
    assert settings.streamlit.port == 8501
    assert "secret" not in repr(settings)
    metadata = settings.public_metadata()
    assert "mistral-secret" not in repr(metadata)
    assert "neo4j-user" not in repr(metadata)


def test_environment_mapping_overrides_dotenv_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NEO4J_URI=neo4j://from-file\nNEO4J_USERNAME=file-user\nNEO4J_PASSWORD=file-pass\n"
        "CYPHER_MODEL=file-model\n"
    )
    settings = load_settings(
        env_file,
        environ={
            "NEO4J_URI": "neo4j://from-environment",
            "NEO4J_USERNAME": "env-user",
            "NEO4J_PASSWORD": "env-pass",
            "CYPHER_MODEL": "env-model",
        },
    )
    assert settings.neo4j.uri == "neo4j://from-environment"
    assert settings.models.cypher_model == "env-model"


def test_model_specific_key_environment_is_supported():
    settings = load_settings(
        environ=_env(
            **{
                "CONVERSATIONAL_MODEL": "mistral-small-latest",
                "CONVERSATIONAL_API_KEY_ENV": "MISTRAL_SMALL_KEY",
                "MISTRAL_SMALL_KEY": "small-secret",
                "CYPHER_MODEL": "neo4j/text2cypher",
                "CYPHER_PROVIDER": "huggingface",
                "CYPHER_API_KEY_ENV": "HF_TOKEN",
                "HF_TOKEN": "hf-secret",
            }
        )
    )
    assert settings.models.conversational_api_key == "small-secret"
    assert settings.models.cypher_api_key == "hf-secret"
    assert settings.models.cypher_api_key_env == "HF_TOKEN"


def test_missing_neo4j_credentials_can_be_allowed_for_offline_setup():
    settings = load_settings(dotenv_path="/tmp/northwind-settings-test-does-not-exist", environ={}, require_neo4j=False)
    assert settings.neo4j.uri == ""
    assert settings.neo4j.username == ""
    assert settings.neo4j.password == ""


def test_missing_required_neo4j_credential_fails_clearly():
    with pytest.raises(ValueError, match="NEO4J_URI"):
        load_settings(dotenv_path="/tmp/northwind-settings-test-does-not-exist", environ={}, require_neo4j=True)


def test_invalid_port_fails_clearly():
    with pytest.raises(ValueError, match="STREAMLIT_SERVER_PORT"):
        load_settings(environ=_env(STREAMLIT_SERVER_PORT="not-a-port"))

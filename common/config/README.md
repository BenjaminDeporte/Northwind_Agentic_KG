# Common Configuration Boundary

The common configuration boundary owns deployment and model-role settings shared by every architecture.

Expected settings include:

- Neo4j connection settings;
- fixed conversational model name and API key selection;
- selectable Cypher-generation model name and API key selection;
- prompt version;
- MLflow tracking URI and experiment name;
- Streamlit and MLflow URLs.

Architecture code reads configuration through this boundary rather than directly reading environment variables.

The implementation is `settings.py`. Call `load_settings()` once at runtime;
environment variables override values from `.env`. Neo4j and model credentials
are kept in typed settings objects with secret fields excluded from `repr` and
`public_metadata()`. Tests can inject an environment mapping without loading
the developer's `.env` file.

The Mistral adapter in `common/providers/mistral.py` consumes the configured
conversational API key and returns the SDK response unchanged for later
structured-output parsing and MLflow logging.

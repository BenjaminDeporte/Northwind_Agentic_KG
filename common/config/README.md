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

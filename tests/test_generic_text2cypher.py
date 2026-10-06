from architectures.generic.text2cypher import Text2CypherTool, build_messages, generate_cypher


class FakeModelClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_initial_generation_passes_selected_model_and_prompt_context():
    client = FakeModelClient("MATCH (c:Customer) RETURN count(c) AS customer_count")
    query = generate_cypher(
        "How many customers?",
        schema_prompt="Customer schema",
        model_name="frontier-cypher-model",
        prompt_version="generic-v1",
        model_client=client,
    )
    assert query.startswith("MATCH")
    assert client.calls[0]["model_name"] == "frontier-cypher-model"
    assert client.calls[0]["messages"][0]["content"].find("Customer schema") >= 0
    assert client.calls[0]["messages"][0]["content"].find("generic-v1") >= 0


def test_rewrite_prompt_contains_previous_query_and_validation_error():
    messages = build_messages(
        "How many customers?",
        schema_prompt="Customer schema",
        prompt_version="generic-v1",
        previous_query="MATCH (c:Customer) RETURN c.bad",
        validation_error="Unknown property: c.bad",
    )
    user = messages[1]["content"]
    assert "MATCH (c:Customer) RETURN c.bad" in user
    assert "Unknown property: c.bad" in user
    assert "replacement Cypher" in user


def test_repair_requires_both_query_and_error():
    try:
        build_messages(
            "Question",
            schema_prompt="Schema",
            prompt_version="v1",
            previous_query="MATCH (n) RETURN n",
        )
    except ValueError as exc:
        assert "requires both" in str(exc)
    else:
        raise AssertionError("Expected incomplete repair context to fail")


def test_markdown_wrapped_model_output_is_cleaned():
    client = FakeModelClient("```cypher\nMATCH (n) RETURN n\n```")
    tool = Text2CypherTool(client)
    assert tool.generate_cypher(
        "List nodes",
        schema_prompt="Schema",
        model_name="neo4j-text2cypher",
        prompt_version="v1",
    ) == "MATCH (n) RETURN n"


def test_empty_model_output_is_rejected():
    client = FakeModelClient("  ")
    try:
        generate_cypher(
            "Question",
            schema_prompt="Schema",
            model_name="model-a",
            prompt_version="v1",
            model_client=client,
        )
    except ValueError as exc:
        assert "empty query" in str(exc)
    else:
        raise AssertionError("Expected an empty model response to fail")


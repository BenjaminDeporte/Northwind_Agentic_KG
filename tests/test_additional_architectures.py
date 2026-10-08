from architectures.curated.graph import compile_graph as compile_curated
from architectures.curated_reflection.graph import compile_graph as compile_curated_reflection
from architectures.generic_reflection.graph import compile_graph as compile_reflection


class FakeHandlers:
    def route_question(self, question, *, conversational_model):
        return "agent"

    def generate_cypher(self, question, **kwargs):
        return "MATCH (c:Customer) RETURN count(c) AS customerCount"

    def validate_cypher(self, query, *, schema):
        return {"status": "valid", "query": query, "error": None}

    def run_readonly_cypher(self, query, *, neo4j_client):
        return {"status": "ok", "rows": [{"values": {"customerCount": 91}}]}

    def generate_answer(self, question, query, query_result, **kwargs):
        return "There are 91 customers.", {"customerCount": 91}

    def reflect_answer(self, question, draft_answer, query_result, **kwargs):
        return True, None

    def select_curated_tool(self, question, **kwargs):
        return "count_customers"

    def curated_query(self, name):
        return "MATCH (c:Customer) RETURN count(c) AS customerCount"


def state():
    return {
        "question": "How many customers?", "route": "agent", "messages": [],
        "draft_answer": None, "draft_result": None, "answer": None, "result": None,
        "loop_count": 0, "error": None,
    }


def kwargs():
    return {
        "schema": "Customer(customerID)", "schema_prompt": "Customer schema",
        "conversational_model": "conversation", "cypher_model": "cypher",
        "prompt_version": "v1", "neo4j_client": object(),
    }


def test_generic_reflection_accepts_satisfactory_draft():
    result = compile_reflection(FakeHandlers(), **kwargs()).invoke(state())
    assert result["answer"] == "There are 91 customers."


def test_curated_architecture_uses_selected_query():
    result = compile_curated(FakeHandlers(), **kwargs()).invoke(state())
    assert result["result"] == {"customerCount": 91}


def test_curated_reflection_combines_selection_and_reflection():
    result = compile_curated_reflection(FakeHandlers(), **kwargs()).invoke(state())
    assert result["answer"] == "There are 91 customers."

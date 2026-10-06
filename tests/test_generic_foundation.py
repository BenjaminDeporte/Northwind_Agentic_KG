import inspect
import json
from typing import get_type_hints

from langchain_core.messages import ToolMessage

from architectures.generic.graph import compile_graph
from architectures.generic.interfaces import GenericHandlers
from architectures.generic.state import AgentState, MAX_CYPHER_ATTEMPTS


class FakeHandlers:
    def __init__(self, *, route="agent", invalid_attempts=0):
        self.route = route
        self.invalid_attempts = invalid_attempts
        self.generated = []
        self.validated = []
        self.executed = []

    def route_question(self, question, *, conversational_model):
        return self.route

    def generate_cypher(
        self,
        question,
        *,
        schema_prompt,
        model_name,
        prompt_version,
        previous_query=None,
        validation_error=None,
    ):
        self.generated.append((previous_query, validation_error))
        return "MATCH (n) RETURN count(n) AS total" if previous_query is None else "MATCH (n) RETURN count(n) AS repaired_total"

    def validate_cypher(self, query, *, schema):
        self.validated.append(query)
        if len(self.validated) <= self.invalid_attempts:
            return {"status": "invalid", "query": query, "error": "synthetic syntax error"}
        return {"status": "valid", "query": query, "error": None}

    def run_readonly_cypher(self, query, *, neo4j_client):
        self.executed.append(query)
        return {"status": "ok", "rows": [{"value": 91}]}

    def generate_answer(self, question, query, query_result, *, route, conversational_model, prompt_version):
        assert route in {"chitchat", "refusal", "agent"}
        if route == "chitchat":
            return "Fine, and you?", {"kind": "chitchat"}
        if route == "refusal":
            return "I cannot help with that request.", {"kind": "refusal"}
        return "There are 91 customers.", {"value": 91}


def initial_state(question="How many customers do we have?") -> AgentState:
    return {
        "question": question,
        "route": "agent",
        "messages": [],
        "draft_answer": None,
        "draft_result": None,
        "answer": None,
        "result": None,
        "loop_count": 0,
        "error": None,
    }


def invoke(fake):
    graph = compile_graph(
        fake,
        schema="Customer(customerID)",
        schema_prompt="Customer schema",
        conversational_model="mistral-large-latest",
        cypher_model="generic-cypher-model",
        prompt_version="v1",
        neo4j_client=object(),
    )
    return graph.invoke(initial_state())


def test_state_uses_add_messages_reducer():
    annotations = get_type_hints(AgentState, include_extras=True)
    assert "messages" in annotations
    assert "add_messages" in str(annotations["messages"])


def test_interface_signatures_match_contract():
    signature = inspect.signature(GenericHandlers.generate_cypher)
    assert signature.parameters["previous_query"].default is None
    assert signature.parameters["validation_error"].default is None
    answer_signature = inspect.signature(GenericHandlers.generate_answer)
    assert "query_result" in answer_signature.parameters


def test_agent_path_executes_valid_query_and_accepts_one_answer():
    fake = FakeHandlers()
    result = invoke(fake)
    assert result["answer"] == "There are 91 customers."
    assert result["result"] == {"value": 91}
    assert result["loop_count"] == 1
    assert fake.generated == [(None, None)]
    assert len(fake.executed) == 1
    assert result["error"] is None


def test_invalid_query_returns_tool_error_to_rewrite_call():
    fake = FakeHandlers(invalid_attempts=1)
    result = invoke(fake)
    assert result["answer"] == "There are 91 customers."
    assert fake.generated[0] == (None, None)
    assert fake.generated[1] == (
        "MATCH (n) RETURN count(n) AS total",
        "synthetic syntax error",
    )
    assert len(fake.validated) == 2
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert json.loads(tool_messages[0].content)["status"] == "invalid"


def test_three_total_validation_attempts_terminate_without_execution():
    fake = FakeHandlers(invalid_attempts=MAX_CYPHER_ATTEMPTS)
    result = invoke(fake)
    assert result["answer"] is None
    assert result["error"] == "synthetic syntax error"
    assert len(fake.validated) == MAX_CYPHER_ATTEMPTS
    assert fake.executed == []


def test_router_chitchat_terminates_without_graph_access():
    fake = FakeHandlers(route="chitchat")
    result = invoke(fake)
    assert result["answer"] == "Fine, and you?"
    assert fake.generated == []
    assert fake.executed == []


def test_router_refusal_terminates_without_graph_access():
    fake = FakeHandlers(route="refusal")
    result = invoke(fake)
    assert result["answer"] == "I cannot help with that request."
    assert fake.generated == []
    assert fake.executed == []

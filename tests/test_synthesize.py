"""
Unit tests for synthesize node (Phase 2, Item 2.6).

Contract: PROJECT.md §2 — synthesize node
PLAN.md 2.6 — produces final answer from tool results

Testing strategy: Mocked, deterministic, no API calls.
"""

import json

import pytest
from langchain_core.messages import ToolMessage

from src.agents.nodes import synthesize
from src.agents.state import ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL, ROUTE_DEGRADE, STATUS_OK


class TestSynthesizeAgentRoute:
    """Test synthesize with agent route."""

    def test_produces_answer(self):
        """synthesize produces an answer for agent route."""
        state = {
            'question': "What is the impact?",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert result['draft_answer'] is not None
        assert len(result['draft_answer']) > 0

    def test_produces_citations(self):
        """synthesize produces citations for agent route."""
        state = {
            'question': "What is the impact?",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert 'draft_citations' in result
        assert isinstance(result['draft_citations'], list)

    def test_draft_does_not_commit_confidence_before_validation(self):
        """Confidence is committed only when the consistency check accepts the draft."""
        state = {
            'question': "What is the impact?",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert 'draft_answer' in result
        assert 'confidence' not in result

    def test_draft_does_not_commit_confidence_rationale_before_validation(self):
        """The rubric rationale is committed only after validation."""
        state = {
            'question': "What is the impact?",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert 'draft_answer' in result
        assert 'confidence_rationale' not in result


class TestSynthesizeChitchatRefusal:
    """Test synthesize with chitchat and refusal routes."""

    def test_chitchat_preserves_answer(self):
        """synthesize preserves chitchat answer."""
        state = {
            'question': "Hello",
            'route': ROUTE_CHITCHAT,
            'answer': "Hello! I'm the assistant.",
            'confidence': 0.0,
            'confidence_rationale': 'no evidence: chitchat',
            'trace': [],
            'loop_count': 0,
        }
        result = synthesize(state)
        assert result['answer'] == "Hello! I'm the assistant."
        assert result['route'] == ROUTE_CHITCHAT

    def test_refusal_preserves_answer(self):
        """synthesize preserves refusal answer."""
        state = {
            'question': "Delete all data",
            'route': ROUTE_REFUSAL,
            'answer': "I cannot help with that request.",
            'confidence': 0.0,
            'confidence_rationale': 'no evidence: refusal',
            'trace': [],
            'loop_count': 0,
        }
        result = synthesize(state)
        assert result['answer'] == "I cannot help with that request."
        assert result['route'] == ROUTE_REFUSAL

    def test_chitchat_confidence_zero(self):
        """Chitchat route maintains confidence 0.0."""
        state = {
            'question': "Hello",
            'route': ROUTE_CHITCHAT,
            'answer': "Hello!",
            'confidence': 0.0,
            'confidence_rationale': 'no evidence: chitchat',
            'trace': [],
        }
        result = synthesize(state)
        assert result['confidence'] == 0.0

    def test_refusal_confidence_zero(self):
        """Refusal route maintains confidence 0.0."""
        state = {
            'question': "Delete data",
            'route': ROUTE_REFUSAL,
            'answer': "I cannot help with that request.",
            'confidence': 0.0,
            'confidence_rationale': 'no evidence: refusal',
            'trace': [],
        }
        result = synthesize(state)
        assert result['confidence'] == 0.0


class TestSynthesizeInvariants:
    """Test synthesize invariants from PROJECT.md."""

    def test_degrade_route_returns_unchanged(self):
        """
        Synthesize should NEVER be called for degrade route per invariant:
        'budget exhaustion always routes to degrade, never to synthesize'.
        
        If it somehow is called (test scenario only), it returns state unchanged.
        """
        state = {
            'question': "Complex question",
            'route': ROUTE_DEGRADE,
            'trace': [],
            'loop_count': 8,
        }
        result = synthesize(state)
        # Should not add confidence/rationale/answer for degrade route
        # (those are set by degrade node itself)
        assert result == state


class TestSynthesizeEdgeCases:
    """Test edge cases for synthesize."""

    def test_empty_trace(self):
        """synthesize handles empty trace for agent route."""
        state = {
            'question': "Test",
            'route': ROUTE_AGENT,
            'trace': [],
            'loop_count': 0,
        }
        result = synthesize(state)
        assert 'draft_answer' in result
        # Candidate is generated without committing an accepted answer.
        assert result['draft_answer'] is not None
        assert 'answer' not in result

    def test_preserves_other_state_fields(self):
        """synthesize preserves existing non-answer state fields."""
        state = {
            'question': "Test question",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'lookup_entity',
                    'args': {'name': 'test'},
                    'mode': 'retrieval',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 50,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
            'existing_field': 'preserved',
        }
        result = synthesize(state)
        assert 'existing_field' not in result  # node emits only fields it owns
        # The candidate is generated but does not overwrite accepted-answer fields.
        assert 'draft_answer' in result
        assert 'answer' not in result


class TestSynthesizeToolTypes:
    """Test synthesize with different tool types in trace."""

    def test_impact_analysis_in_trace(self):
        """synthesize handles impact_analysis in trace."""
        state = {
            'question': "Impact question",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'impact_analysis',
                    'args': {'entity_key': '1', 'entity_label': 'Supplier'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 10,
                    'cypher': None,
                    'latency_ms': 200,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert result['draft_answer'] is not None

    def test_lookup_entity_in_trace(self):
        """synthesize handles lookup_entity in trace."""
        state = {
            'question': "Lookup question",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'lookup_entity',
                    'args': {'name': 'test', 'label': 'Supplier'},
                    'mode': 'retrieval',
                    'status': STATUS_OK,
                    'result_rows': 1,
                    'cypher': None,
                    'latency_ms': 50,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert result['draft_answer'] is not None

    def test_co_purchase_in_trace(self):
        """synthesize handles co_purchase in trace."""
        state = {
            'question': "Co-purchase question",
            'route': ROUTE_AGENT,
            'trace': [
                {
                    'step': 1,
                    'tool_name': 'co_purchase',
                    'args': {'product_key': '1'},
                    'mode': 'curated',
                    'status': STATUS_OK,
                    'result_rows': 5,
                    'cypher': None,
                    'latency_ms': 100,
                    'retry_count': 0
                }
            ],
            'loop_count': 1,
        }
        result = synthesize(state)
        assert result['draft_answer'] is not None


class TestExploratoryScalarEvidence:
    def test_dataset_count_uses_scalar_and_all_returned_nodes(self, monkeypatch):
        """A scalar count is answerable when its row also carries node evidence."""
        monkeypatch.setattr(
            "src.agents.llm.synthesize_from_evidence",
            lambda draft: draft,
        )
        evidence_nodes = [
            {"label": "Customer", "key": key, "name": name, "properties": {}}
            for key, name in [("ALFKI", "Alfreds Futterkiste"), ("ANATR", "Ana Trujillo Emparedados")]
        ]
        payload = {
            "status": "ok",
            "query": "MATCH (c:Customer) RETURN count(c) AS customer_count, collect(c) AS evidence_nodes",
            "rows": [{"values": {"customer_count": 2}, "evidence": {"nodes": evidence_nodes, "edges": []}}],
        }
        state = {
            "question": "How many customers are in the dataset?",
            "route": ROUTE_AGENT,
            "messages": [ToolMessage(content=json.dumps(payload), name="run_readonly_cypher", tool_call_id="count")],
            "trace": [{
                "step": 1, "tool_name": "run_readonly_cypher", "args": {},
                "mode": "exploratory", "status": "ok", "result_rows": 1,
                "cypher": payload["query"], "latency_ms": 1, "retry_count": 0,
            }],
            "loop_count": 1,
        }

        result = synthesize(state)

        assert "contains 2 customers" in result["draft_answer"]
        assert "[Customer:ALFKI]" in result["draft_answer"]
        assert "[Customer:ANATR]" in result["draft_answer"]
        assert {item["key"] for item in result["draft_citations"]} == {"ALFKI", "ANATR"}


    def test_scoped_order_count_uses_order_nodes_and_customer_anchor(self, monkeypatch):
        monkeypatch.setattr("src.agents.llm.synthesize_from_evidence", lambda draft: draft)
        payload = {"status": "ok", "rows": [{
            "values": {
                "order_count": 2,
                "anchor": {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste"},
            },
            "evidence": {"nodes": [
                {"label": "Customer", "key": "ALFKI", "name": "Alfreds Futterkiste", "properties": {}},
                {"label": "Order", "key": "1", "name": "1", "properties": {}},
                {"label": "Order", "key": "2", "name": "2", "properties": {}},
            ], "edges": []},
        }]}
        state = {
            "question": "How many orders did customer ALFKI place?",
            "route": ROUTE_AGENT,
            "messages": [ToolMessage(content=json.dumps(payload), name="run_readonly_cypher", tool_call_id="orders")],
            "trace": [], "loop_count": 2,
        }
        result = synthesize(state)
        assert "Alfreds Futterkiste [Customer:ALFKI] placed 2 orders." in result["draft_answer"]
        assert "[Order:1]" in result["draft_answer"] and "[Order:2]" in result["draft_answer"]
        assert {item["label"] for item in result["draft_citations"]} == {"Customer", "Order"}


class TestExploratoryOutcomes:
    def _state(self, payload, *, earlier_messages=()):
        messages = list(earlier_messages) + [ToolMessage(
            content=json.dumps(payload), name="run_readonly_cypher", tool_call_id="explore",
        )]
        return {"question": "show info", "route": ROUTE_AGENT, "messages": messages, "trace": [], "loop_count": 2}

    def test_successful_empty_query_is_distinct(self):
        result = synthesize(self._state({"status": "empty", "rows": [], "error": None, "attempts": []}))
        assert result["draft_answer"] == "The graph query ran successfully but returned no matching rows."

    def test_invalid_query_is_distinct_from_prior_empty_lookup(self):
        from langchain_core.messages import ToolMessage
        earlier = ToolMessage(
            content=json.dumps({"status": "empty", "matches": []}),
            name="lookup_entity", tool_call_id="lookup",
        )
        state = self._state(
            {"status": "invalid", "rows": [], "error": "Unknown property: contactTitle", "attempts": []},
            earlier_messages=(earlier,),
        )
        state["trace"] = [
            {"step": 1, "tool_name": "lookup_entity", "args": {}, "mode": "retrieval", "status": "empty", "result_rows": 0, "cypher": None, "latency_ms": 1, "retry_count": 0},
            {"step": 2, "tool_name": "run_readonly_cypher", "args": {}, "mode": "exploratory", "status": "invalid", "result_rows": 0, "cypher": "MATCH (c:Customer) RETURN c.contactTitle", "latency_ms": 0, "retry_count": 0},
        ]
        result = synthesize(state)
        assert "rejected or failed" in result["draft_answer"]
        assert "Unknown property: contactTitle" in result["draft_answer"]
        assert "no matching" not in result["draft_answer"]
        assert [item["status"] for item in state["trace"]] == ["empty", "invalid"]
        assert result["draft_citations"] == []

    def test_scalar_only_result_does_not_claim_uncited_number(self):
        result = synthesize(self._state({
            "status": "ok", "rows": [{"values": {"customer_count": 91}, "evidence": {"nodes": [], "edges": []}}],
        }))
        assert "91" not in result["draft_answer"]
        assert "no node evidence" in result["draft_answer"]


def test_dataset_count_keeps_answer_and_citations_compact(monkeypatch):
    monkeypatch.setattr("src.agents.llm.synthesize_from_evidence", lambda draft: draft)
    nodes = [
        {"label": "Customer", "key": f"C{i:03}", "name": f"Customer {i}", "properties": {}}
        for i in range(91)
    ]
    payload = {"status": "ok", "rows": [{
        "values": {"customer_count": 91}, "evidence": {"nodes": nodes, "edges": []},
    }]}
    result = synthesize({
        "question": "How many customers are there in Northwind?", "route": ROUTE_AGENT,
        "messages": [ToolMessage(content=json.dumps(payload), name="run_readonly_cypher", tool_call_id="count")],
        "trace": [], "loop_count": 1,
    })
    assert "contains 91 customers" in result["draft_answer"]
    assert result["draft_answer"].count("[Customer:") == 3
    assert "additional customers" not in result["draft_answer"]
    assert result["draft_answer"].count("[Customer:") == 3
    assert len(result["draft_citations"]) == 3


def test_ranked_product_answer_uses_returned_product_node(monkeypatch):
    monkeypatch.setattr("src.agents.llm.synthesize_from_evidence", lambda draft: draft)
    product = {"label": "Product", "key": "1", "name": "Chai", "properties": {}}
    payload = {"status": "ok", "rows": [{
        "values": {"product": product, "total_quantity": 120},
        "evidence": {"nodes": [product], "edges": []},
    }]}
    result = synthesize({
        "question": "Which product was the most ordered?", "route": ROUTE_AGENT,
        "messages": [ToolMessage(content=json.dumps(payload), name="run_readonly_cypher", tool_call_id="ranked-product")],
        "trace": [], "loop_count": 1,
    })
    assert result["draft_answer"] == "Most ordered product: Chai [Product:1], with 120 units ordered."
    assert result["draft_citations"] == [{"label": "Product", "key": "1", "name": "Chai"}]


def test_ranked_customer_product_quantity_is_not_labeled_as_product(monkeypatch):
    monkeypatch.setattr("src.agents.llm.synthesize_from_evidence", lambda draft: draft)
    customer = {"label": "Customer", "key": "SAVEA", "name": "Save-a-lot Markets", "properties": {}}
    product = {"label": "Product", "key": "16", "name": "Pavlova", "properties": {}}
    payload = {"status": "ok", "rows": [{"values": {"customer": customer, "total_quantity": 4958, "evidence_products": [product]}, "evidence": {"nodes": [customer, product], "edges": []}}]}
    result = synthesize({"question": "Which customer ordered the most product units?", "route": ROUTE_AGENT, "messages": [ToolMessage(content=json.dumps(payload), name="run_readonly_cypher", tool_call_id="ranked-customer")], "trace": [], "loop_count": 1})
    assert "Save-a-lot Markets [Customer:SAVEA] ordered 4,958 product units." in result["draft_answer"]
    assert "Most ordered product" not in result["draft_answer"]
    assert result["draft_citations"] == [{"label": "Customer", "key": "SAVEA", "name": "Save-a-lot Markets"}, {"label": "Product", "key": "16", "name": "Pavlova"}]


def test_structured_copurchase_cites_only_recommendation_pair(monkeypatch):
    monkeypatch.setattr("src.agents.llm.synthesize_from_evidence", lambda draft: draft)
    anchor = {"label": "Product", "key": "1", "name": "Chai"}
    related = {"label": "Product", "key": "2", "name": "Chang"}
    payload = {"status": "ok", "error": None, "product": anchor, "recommendations": [{
        "product": related, "co_bought": 4,
        "evidence": {"nodes": [
            {**anchor, "properties": {}}, {**related, "properties": {}},
        ], "edges": []},
    }]}
    result = synthesize({
        "question": "Which products are often bought with Chai?", "route": ROUTE_AGENT,
        "messages": [ToolMessage(content=json.dumps(payload), name="co_purchase", tool_call_id="pair")],
        "trace": [], "loop_count": 1,
    })
    assert "Chang [Product:2]: 4 shared orders" in result["draft_answer"]
    assert set((item["label"], item["key"]) for item in result["draft_citations"]) == {("Product", "1"), ("Product", "2")}


def _customer_history_payload(order_count):
    from datetime import date, timedelta
    customer = {"label": "Customer", "key": "SAVEA", "name": "Save-a-lot Markets"}
    start = date(1996, 1, 1)
    orders = []
    for index in range(order_count):
        key = str(10000 + index)
        order_node = {"label": "Order", "key": key, "name": key}
        orders.append({
            "order": order_node,
            "order_date": f"{start + timedelta(days=index)} 00:00:00.000",
            "total": 100.0 + index,
            "ship_country": "USA",
            "evidence": {"nodes": [{**customer, "properties": {}}, {**order_node, "properties": {}}], "edges": []},
        })
    return {"status": "ok", "error": None, "customer": customer, "orders": orders}


def test_customer_history_explicit_all_request_includes_every_returned_order(monkeypatch):
    def fail_if_rewritten(_draft):
        raise AssertionError("exhaustive order lists should retain the deterministic full listing")
    monkeypatch.setattr("src.agents.llm.synthesize_from_evidence", fail_if_rewritten)
    payload = _customer_history_payload(31)
    result = synthesize({
        "question": "List all 31 orders by Save-a-lot Markets", "route": ROUTE_AGENT,
        "messages": [ToolMessage(content=json.dumps(payload), name="customer_history", tool_call_id="all-orders")],
        "trace": [], "loop_count": 1,
    })
    assert "has 31 evidenced orders" in result["draft_answer"]
    assert result["draft_answer"].count("- 1996-") == 31
    assert len([item for item in result["draft_citations"] if item["label"] == "Order"]) == 31


def test_default_customer_history_display_discloses_ten_order_cap(monkeypatch):
    monkeypatch.setattr("src.agents.llm.synthesize_from_evidence", lambda draft: draft)
    payload = _customer_history_payload(12)
    result = synthesize({
        "question": "Show me the order history for Save-a-lot Markets", "route": ROUTE_AGENT,
        "messages": [ToolMessage(content=json.dumps(payload), name="customer_history", tool_call_id="history")],
        "trace": [], "loop_count": 1,
    })
    assert "has 12 evidenced orders; showing the first 10" in result["draft_answer"]
    assert result["draft_answer"].count("- 1996-") == 10
    assert "Largest gap between returned orders: 1 days." in result["draft_answer"]


def test_rewrite_with_added_number_is_rejected(monkeypatch):
    monkeypatch.setattr("src.agents.llm.synthesize_from_evidence", lambda draft: draft + " [1]")
    node = {"label": "Product", "key": "P1", "name": "Chai", "properties": {}}
    payload = {"status": "ok", "error": None, "query_name": "Chai", "matches": [{
        "node": node, "match": "exact", "evidence": {"nodes": [node], "edges": []},
    }]}
    result = synthesize({
        "question": "Find Chai", "route": ROUTE_AGENT,
        "messages": [ToolMessage(content=json.dumps(payload), name="lookup_entity", tool_call_id="lookup")],
        "trace": [], "loop_count": 1,
    })
    assert " [1]" not in result["draft_answer"]

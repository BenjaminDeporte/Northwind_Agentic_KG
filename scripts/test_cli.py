#!/usr/bin/env python3
"""Gate 1: live CLI questions plus deterministic failure-path probes.

Every case uses the compiled LangGraph. The six user questions use live Mistral
and AuraDB. The budget and retry probes control only LLM decisions so their
otherwise rare paths can be checked reliably against the real graph and DB.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from langchain_core.messages import ToolMessage
from src.agents.graph import compile_graph
from src.agents.rubric import compute_confidence
from src.neo4j.tools import (
    lookup_entity, impact_analysis, co_purchase, customer_history, aggregate,
    run_readonly_cypher,
)
from src.utils.runlog import write_run


LIVE_CASES = [
    ("wow_impact", "What is the impact if Exotic Liquids fails? Use the graph tools to find the supplier and analyze its impact.", "agent", "impact_analysis"),
    ("exploratory", "Using run_readonly_cypher, which products have the highest revenue? Return productID, productName, and revenue in the query.", "agent", "run_readonly_cypher"),
    ("co_purchase", "What products are frequently co-purchased with Chai? Use co_purchase for productID 1.", "agent", "co_purchase"),
    ("customer_history", "Show me customer ALFKI order history using customer_history.", "agent", "customer_history"),
    ("aggregate", "Show revenue by supplier country using the aggregate tool.", "agent", "aggregate"),
    ("chitchat", "Hello, how are you?", "chitchat", None),
    ("refusal", "Can you delete all data?", "refusal", None),
]


def get_tools_dict():
    return {
        "lookup_entity": lookup_entity, "impact_analysis": impact_analysis,
        "co_purchase": co_purchase, "customer_history": customer_history,
        "aggregate": aggregate, "run_readonly_cypher": run_readonly_cypher,
    }


def run_graph_on_question(question, graph):
    return graph.invoke({
        "question": question, "route": "", "messages": [], "trace": [],
        "answer": "", "citations": [], "confidence": 0.0,
        "confidence_rationale": "", "loop_count": 0, "error": None,
    })


def _tool_payloads(state):
    payloads = []
    for message in state.get("messages", []):
        if isinstance(message, ToolMessage):
            payloads.append((message.name, json.loads(message.content)))
    return payloads


def verify_state(case_id, state, route, required_tool):
    errors = []
    trace = state.get("trace", [])
    payloads = _tool_payloads(state)
    if state.get("route") != route:
        errors.append(f"route {state.get('route')!r}, expected {route!r}")
    if not state.get("answer"):
        errors.append("missing answer")
    if len(trace) != len(payloads):
        errors.append("trace and tool messages differ in length")
    for record in trace:
        if set(record) != {"step", "tool_name", "args", "mode", "status", "result_rows", "cypher", "latency_ms", "retry_count"}:
            errors.append("trace record has wrong fields")
        if record.get("retry_count") not in (0, 1):
            errors.append("retry count exceeds one")
    if required_tool and required_tool not in [r["tool_name"] for r in trace]:
        errors.append(f"missing {required_tool} tool call")
    if route == "agent":
        evidence_handles = set()
        for name, result in payloads:
            candidates = []
            if name == "lookup_entity":
                candidates = result.get("matches", [])
            elif name == "impact_analysis":
                candidates = result.get("subgraph", {}).get("nodes", [])
            elif name == "co_purchase":
                candidates = [result.get("product")] + result.get("recommendations", [])
            elif name == "customer_history":
                candidates = [result.get("customer")] + [
                    {"label": "Order", "key": order.get("order_key")}
                    for order in result.get("orders", [])
                ]
            elif name == "aggregate":
                candidates = [node for group in result.get("groups", []) for node in group.get("evidence", [])]
            elif name == "run_readonly_cypher":
                candidates = [
                    {"label": "Product", "key": row.get("productID")}
                    for row in result.get("rows", []) if row.get("productID") is not None
                ]
            evidence_handles.update((node["label"], str(node["key"])) for node in candidates if isinstance(node, dict) and node.get("label") and node.get("key") is not None)
        expected_confidence, expected_rationale = compute_confidence(trace, "agent")
        if state.get("confidence") != expected_confidence or state.get("confidence_rationale") != expected_rationale:
            errors.append("confidence differs from deterministic rubric")
        if state.get("error"):
            errors.append(f"agent error: {state['error']}")
        for citation in state.get("citations", []):
            marker = f"[{citation['label']}:{citation['key']}]"
            if marker not in state["answer"]:
                errors.append(f"citation {marker} is not in the answer")
            if (citation["label"], str(citation["key"])) not in evidence_handles:
                errors.append(f"citation {marker} is absent from tool evidence")
        if not state.get("citations"):
            errors.append("no cited graph nodes")
    elif route in ("chitchat", "refusal"):
        if trace or state.get("citations") or state.get("confidence") != 0.0:
            errors.append("no-evidence route returned graph evidence")
    if case_id == "wow_impact":
        impact = next((result for name, result in payloads if name == "impact_analysis"), {})
        if impact.get("aggregates") != {
            "products_affected": 3, "orders_affected": 90,
            "revenue_at_risk": 35916.8, "unusable_lines": 0,
        }:
            errors.append("supplier impact differs from verified ground truth")
        nodes = impact.get("subgraph", {}).get("nodes", [])
        edges = impact.get("subgraph", {}).get("edges", [])
        handles = {(n["label"], n["key"]) for n in nodes}
        if not nodes or not edges or any(
            (e["from"]["label"], e["from"]["key"]) not in handles or
            (e["to"]["label"], e["to"]["key"]) not in handles for e in edges
        ):
            errors.append("impact evidence graph has missing nodes or edges")
        if {"label": "Supplier", "key": "1", "name": "Exotic Liquids"} not in state.get("citations", []):
            errors.append("missing actual supplier citation")
    if case_id == "exploratory":
        exploratory = next((result for name, result in payloads if name == "run_readonly_cypher"), {})
        if exploratory.get("status") not in ("ok", "retry_ok") or not exploratory.get("rows"):
            errors.append("exploratory tool returned no usable rows")
    if case_id == "co_purchase":
        result = next((data for name, data in payloads if name == "co_purchase"), {})
        if result.get("product", {}).get("key") != "1" or not result.get("recommendations"):
            errors.append("co-purchase result is missing Chai evidence")
    if case_id == "customer_history":
        result = next((data for name, data in payloads if name == "customer_history"), {})
        if result.get("customer", {}).get("key") != "ALFKI" or not result.get("orders"):
            errors.append("customer history is missing ALFKI evidence")
    if case_id == "aggregate":
        result = next((data for name, data in payloads if name == "aggregate"), {})
        if result.get("status") != "ok" or not 0 < result.get("n_groups", 0) <= 20:
            errors.append("aggregate groups are missing or exceed the cap")
        if any(not group.get("evidence") for group in result.get("groups", [])):
            errors.append("aggregate group has no contributing node handles")
    if case_id == "budget_probe":
        if state.get("route") != "degrade" or len(trace) != 8 or state.get("confidence") != 0.4 or "Truncated" not in state.get("answer", ""):
            errors.append("budget did not execute eight calls and degrade")
    if case_id == "retry_probe":
        exploratory = [r for r in trace if r["tool_name"] == "run_readonly_cypher"]
        if len(exploratory) != 1 or exploratory[0]["status"] != "retry_ok" or exploratory[0]["retry_count"] != 1:
            errors.append("exploratory retry was not visible in the trace")
        result = next((data for name, data in payloads if name == "run_readonly_cypher"), {})
        if len(result.get("attempts", [])) != 2 or result["attempts"][0]["valid"] or not result["attempts"][1]["valid"]:
            errors.append("retry attempts do not show failed validation and recovery")
    return errors


def main():
    required = ("MISTRAL_API_KEY", "NEO4J_URI", "NEO4J_PASSWORD")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(f"Missing configuration: {', '.join(missing)}")
        return 2
    tools = get_tools_dict()
    graph = compile_graph(tools)
    results = []
    for case_id, question, route, required_tool in LIVE_CASES:
        try:
            state = run_graph_on_question(question, graph)
            errors = verify_state(case_id, state, route, required_tool)
            write_run(state)
        except Exception as exc:
            errors = [str(exc)]
        results.append((case_id, errors))
        print(f"{'PASS' if not errors else 'FAIL'} {case_id}: {', '.join(errors) if errors else 'contract checks passed'}")
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response",
        lambda **kwargs: 'TOOL: lookup_entity({"name":"no_such_product","label":"Product"})',
    ):
        state = run_graph_on_question("Budget probe", compile_graph(tools))
        errors = verify_state("budget_probe", state, "degrade", "lookup_entity")
        write_run(state)
        results.append(("budget_probe", errors))
        print(f"{'PASS' if not errors else 'FAIL'} budget_probe: {', '.join(errors) if errors else 'eight calls and degrade'}")
    decisions = iter([
        'TOOL: run_readonly_cypher({"query":"MATCH (p:Product RETURN p"})',
        "FINAL: completed query",
    ])
    with patch("src.agents.graph.classify", lambda state: {**state, "route": "agent"}), patch(
        "src.agents.llm.generate_agent_response", lambda **kwargs: next(decisions)
    ), patch(
        "src.neo4j.tools._repair_cypher",
        return_value="MATCH (p:Product) RETURN p.productID AS productID, p.productName AS productName LIMIT 1",
    ):
        state = run_graph_on_question("Retry probe", compile_graph(tools))
        errors = verify_state("retry_probe", state, "agent", "run_readonly_cypher")
        write_run(state)
        results.append(("retry_probe", errors))
        print(f"{'PASS' if not errors else 'FAIL'} retry_probe: {', '.join(errors) if errors else 'failed validation and recovery'}")
    failed = [name for name, errors in results if errors]
    print(f"Gate 1: {len(results)-len(failed)}/{len(results)} cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Typed result shapes and runtime validation for the six graph tools.

TypedDict documents the schemas for static analysis; validate_tool_result
performs the checks required before a result enters a ToolMessage.
"""
from __future__ import annotations

import json
from typing import Any, Literal, TypedDict


Status = Literal["ok", "empty", "invalid", "retry_ok", "retry_failed"]


class NodeHandle(TypedDict):
    label: str
    key: str
    name: str
    properties: dict[str, Any]


class Endpoint(TypedDict):
    label: str
    key: str


EdgeHandle = TypedDict("EdgeHandle", {
    "type": str,
    "from": Endpoint,
    "to": Endpoint,
    "properties": dict[str, Any],
})


class Evidence(TypedDict):
    nodes: list[NodeHandle]
    edges: list[dict[str, Any]]


class ToolResultBase(TypedDict):
    status: Status
    error: str | None


class LookupMatch(TypedDict):
    node: NodeHandle
    match: Literal["exact", "contains", "fuzzy"]
    evidence: Evidence


class LookupResult(ToolResultBase):
    query_name: str
    matches: list[LookupMatch]


class ImpactResult(ToolResultBase):
    anchor: NodeHandle | None
    subgraph: dict[str, list[dict[str, Any]]]
    aggregates: dict[str, int | float]
    evidence: Evidence


class Recommendation(TypedDict):
    product: dict[str, str]
    co_bought: int
    evidence: Evidence


class CoPurchaseResult(ToolResultBase):
    product: dict[str, str] | None
    recommendations: list[Recommendation]


class CustomerOrder(TypedDict):
    order: dict[str, str]
    order_date: str | None
    total: int | float
    ship_country: str | None
    evidence: Evidence


class CustomerHistoryResult(ToolResultBase):
    customer: dict[str, str] | None
    orders: list[CustomerOrder]


class AggregateGroup(TypedDict):
    group_value: str
    metric_value: int | float
    evidence: Evidence


class AggregateResult(ToolResultBase):
    groups: list[AggregateGroup]
    n_groups: int


class QueryAttempt(TypedDict):
    cypher: str
    valid: bool
    error: str | None


class CypherRow(TypedDict):
    values: dict[str, Any]
    evidence: Evidence


class ReadonlyCypherResult(ToolResultBase):
    query: str
    attempts: list[QueryAttempt]
    rows: list[CypherRow]


TOOL_RESULT_TYPES = {
    "lookup_entity": LookupResult,
    "impact_analysis": ImpactResult,
    "co_purchase": CoPurchaseResult,
    "customer_history": CustomerHistoryResult,
    "aggregate": AggregateResult,
    "run_readonly_cypher": ReadonlyCypherResult,
}

NODE_LABELS = {
    "Product", "Order", "Customer", "Supplier", "Employee", "Category",
    "Shipper", "Territory", "Region",
}
SUCCESS_STATUSES = {"ok", "empty", "retry_ok"}
TOOL_STATUSES = SUCCESS_STATUSES | {"invalid", "retry_failed"}


class ToolResultValidationError(ValueError):
    """Raised when a tool payload does not satisfy its runtime result contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ToolResultValidationError(message)


def _is_node(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("label") in NODE_LABELS
        and isinstance(value.get("key"), (str, int))
        and not isinstance(value.get("key"), bool)
        and isinstance(value.get("name"), str)
        and isinstance(value.get("properties"), dict)
    )


def _is_endpoint(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("label") in NODE_LABELS
        and isinstance(value.get("key"), (str, int))
        and not isinstance(value.get("key"), bool)
    )


def _is_edge(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("type"), str)
        and _is_endpoint(value.get("from"))
        and _is_endpoint(value.get("to"))
        and isinstance(value.get("properties"), dict)
    )


def _validate_evidence(value: Any, path: str, max_nodes: int | None = None, max_edges: int | None = None) -> None:
    _require(isinstance(value, dict), f"{path} must be an object")
    nodes, edges = value.get("nodes"), value.get("edges")
    _require(isinstance(nodes, list) and all(_is_node(node) for node in nodes), f"{path}.nodes must contain canonical node handles")
    _require(isinstance(edges, list) and all(_is_edge(edge) for edge in edges), f"{path}.edges must contain canonical edge handles")
    if max_nodes is not None:
        _require(len(nodes) <= max_nodes, f"{path}.nodes exceeds the {max_nodes}-handle limit")
    if max_edges is not None:
        _require(len(edges) <= max_edges, f"{path}.edges exceeds the {max_edges}-handle limit")


def _validate_common(tool_name: str, result: Any) -> None:
    _require(isinstance(result, dict), f"{tool_name} must return an object")
    status = result.get("status")
    _require(status in TOOL_STATUSES, f"{tool_name}.status is invalid")
    _require("error" in result, f"{tool_name}.error is required")
    error = result["error"]
    _require(error is None or isinstance(error, str), f"{tool_name}.error must be a string or null")
    if status in SUCCESS_STATUSES:
        _require(error is None, f"{tool_name} successful status must have error=null")
    else:
        _require(isinstance(error, str) and bool(error.strip()), f"{tool_name} failed status needs a useful error")
    if status in {"retry_ok", "retry_failed"}:
        _require(tool_name == "run_readonly_cypher", "retry statuses are reserved for run_readonly_cypher")


def validate_tool_result(tool_name: str, result: Any) -> dict:
    """Validate and return a JSON-safe per-tool result, or raise a useful error."""
    _require(tool_name in TOOL_RESULT_TYPES, f"Unknown tool result contract: {tool_name}")
    _validate_common(tool_name, result)

    if tool_name == "lookup_entity":
        _require(isinstance(result.get("query_name"), str), "lookup_entity.query_name must be a string")
        matches = result.get("matches")
        _require(isinstance(matches, list) and len(matches) <= 10, "lookup_entity.matches must be a list capped at 10")
        for i, match in enumerate(matches):
            path = f"lookup_entity.matches[{i}]"
            _require(isinstance(match, dict) and _is_node(match.get("node")), f"{path}.node must be canonical")
            _require(match.get("match") in {"exact", "contains", "fuzzy"}, f"{path}.match is invalid")
            _validate_evidence(match.get("evidence"), f"{path}.evidence")
            ids = {(n["label"], str(n["key"])) for n in match["evidence"]["nodes"]}
            node = match["node"]
            _require((node["label"], str(node["key"])) in ids, f"{path}.evidence must include its matched node")

    elif tool_name == "impact_analysis":
        anchor = result.get("anchor")
        _require(anchor is None or _is_node(anchor), "impact_analysis.anchor must be canonical or null")
        subgraph = result.get("subgraph")
        _require(isinstance(subgraph, dict), "impact_analysis.subgraph must be an object")
        _require(isinstance(subgraph.get("nodes"), list) and all(_is_node(n) for n in subgraph["nodes"]), "impact_analysis.subgraph.nodes must be canonical")
        _require(isinstance(subgraph.get("edges"), list) and all(_is_edge(e) for e in subgraph["edges"]), "impact_analysis.subgraph.edges must be canonical")
        aggregates = result.get("aggregates")
        required = {"products_affected", "orders_affected", "revenue_at_risk", "unusable_lines"}
        _require(isinstance(aggregates, dict) and required <= aggregates.keys(), "impact_analysis.aggregates is incomplete")
        _require(all(isinstance(aggregates[k], (int, float)) and not isinstance(aggregates[k], bool) for k in required), "impact_analysis aggregate values must be numeric")
        _validate_evidence(result.get("evidence"), "impact_analysis.evidence", max_nodes=3, max_edges=2)

    elif tool_name == "co_purchase":
        product = result.get("product")
        _require(product is None or (isinstance(product, dict) and product.get("label") == "Product" and all(isinstance(product.get(k), str) for k in ("key", "name"))), "co_purchase.product must be canonical or null")
        recommendations = result.get("recommendations")
        _require(isinstance(recommendations, list) and len(recommendations) <= 10, "co_purchase.recommendations must be a list capped at 10")
        for i, recommendation in enumerate(recommendations):
            path = f"co_purchase.recommendations[{i}]"
            _require(isinstance(recommendation, dict), f"{path} must be an object")
            item = recommendation.get("product")
            _require(isinstance(item, dict) and item.get("label") == "Product" and all(isinstance(item.get(k), str) for k in ("key", "name")), f"{path}.product must be canonical")
            _require(isinstance(recommendation.get("co_bought"), int) and not isinstance(recommendation.get("co_bought"), bool), f"{path}.co_bought must be an integer")
            _validate_evidence(recommendation.get("evidence"), f"{path}.evidence", max_nodes=3)
            ids = {(n["label"], str(n["key"])) for n in recommendation["evidence"]["nodes"]}
            _require(("Product", item["key"]) in ids, f"{path}.evidence must include the recommended product")
            if product is not None:
                _require(("Product", product["key"]) in ids, f"{path}.evidence must include the anchor product")

    elif tool_name == "customer_history":
        customer = result.get("customer")
        _require(customer is None or (isinstance(customer, dict) and customer.get("label") == "Customer" and all(isinstance(customer.get(k), str) for k in ("key", "name"))), "customer_history.customer must be canonical or null")
        orders = result.get("orders")
        _require(isinstance(orders, list), "customer_history.orders must be a list")
        for i, order in enumerate(orders):
            path = f"customer_history.orders[{i}]"
            _require(isinstance(order, dict), f"{path} must be an object")
            node = order.get("order")
            _require(isinstance(node, dict) and node.get("label") == "Order" and all(isinstance(node.get(k), str) for k in ("key", "name")), f"{path}.order must be canonical")
            _require(order.get("order_date") is None or isinstance(order.get("order_date"), str), f"{path}.order_date must be a string or null")
            _require(isinstance(order.get("total"), (int, float)) and not isinstance(order.get("total"), bool), f"{path}.total must be numeric")
            _require(order.get("ship_country") is None or isinstance(order.get("ship_country"), str), f"{path}.ship_country must be a string or null")
            _validate_evidence(order.get("evidence"), f"{path}.evidence")
            ids = {(n["label"], str(n["key"])) for n in order["evidence"]["nodes"]}
            _require(("Order", node["key"]) in ids, f"{path}.evidence must include its order")
            edges = order["evidence"]["edges"]
            _require(any(e["type"] == "PURCHASED" for e in edges), f"{path}.evidence must include the Customer–Order edge")

    elif tool_name == "aggregate":
        groups = result.get("groups")
        _require(isinstance(groups, list) and len(groups) <= 20, "aggregate.groups must be a list capped at 20")
        _require(isinstance(result.get("n_groups"), int) and result["n_groups"] == len(groups), "aggregate.n_groups must match groups length")
        for i, group in enumerate(groups):
            path = f"aggregate.groups[{i}]"
            _require(isinstance(group, dict) and isinstance(group.get("group_value"), str), f"{path}.group_value must be a string")
            _require(isinstance(group.get("metric_value"), (int, float)) and not isinstance(group.get("metric_value"), bool), f"{path}.metric_value must be numeric")
            _validate_evidence(group.get("evidence"), f"{path}.evidence", max_nodes=3)

    elif tool_name == "run_readonly_cypher":
        _require(isinstance(result.get("query"), str), "run_readonly_cypher.query must be a string")
        attempts = result.get("attempts")
        _require(isinstance(attempts, list) and len(attempts) <= 2, "run_readonly_cypher.attempts must contain at most two attempts")
        for i, attempt in enumerate(attempts):
            _require(isinstance(attempt, dict), f"run_readonly_cypher.attempts[{i}] must be an object")
            _require(isinstance(attempt.get("cypher"), str) and isinstance(attempt.get("valid"), bool), f"run_readonly_cypher.attempts[{i}] is malformed")
            _require(attempt.get("error") is None or isinstance(attempt.get("error"), str), f"run_readonly_cypher.attempts[{i}].error must be a string or null")
        rows = result.get("rows")
        _require(isinstance(rows, list), "run_readonly_cypher.rows must be a list")
        for i, row in enumerate(rows):
            _require(isinstance(row, dict) and isinstance(row.get("values"), dict), f"run_readonly_cypher.rows[{i}].values must be an object")
            _validate_evidence(row.get("evidence"), f"run_readonly_cypher.rows[{i}].evidence")

    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ToolResultValidationError(f"{tool_name} result is not JSON-safe: {exc}") from exc
    return result


def invalid_tool_result(tool_name: str, error: str, args: dict | None = None) -> dict:
    """Build a valid failure envelope with that tool's required empty payload."""
    args = args or {}
    error = str(error).strip() or "Tool execution failed"
    base = {"status": "invalid", "error": error}
    if tool_name == "lookup_entity":
        name = args.get("name", "")
        return {**base, "query_name": name if isinstance(name, str) else str(name), "matches": []}
    if tool_name == "impact_analysis":
        return {**base, "anchor": None, "subgraph": {"nodes": [], "edges": []},
                "aggregates": {"products_affected": 0, "orders_affected": 0, "revenue_at_risk": 0.0, "unusable_lines": 0},
                "evidence": {"nodes": [], "edges": []}}
    if tool_name == "co_purchase":
        return {**base, "product": None, "recommendations": []}
    if tool_name == "customer_history":
        return {**base, "customer": None, "orders": []}
    if tool_name == "aggregate":
        return {**base, "groups": [], "n_groups": 0}
    if tool_name == "run_readonly_cypher":
        query = args.get("query", "")
        query = query if isinstance(query, str) else str(query)
        return {**base, "query": query, "attempts": [], "rows": []}
    return base

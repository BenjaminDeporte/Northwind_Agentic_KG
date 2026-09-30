"""
Agent graph nodes for the Northwind Agentic KG.

Authoritative contracts:
- PROJECT.md §2: Architecture (classify → agent ↔ tools → draft synthesis → consistency check)
- PROJECT.md §3: State TypedDicts
- PROJECT.md §4: Tools
- PROJECT.md §5: Confidence rubric
- PROJECT.md §6: Run-log
- PROJECT.md §7: GUI

Control-flow invariants:
- MAX_STEPS=8
- Every executed tool call appends exactly one ToolCallRecord to trace
- Budget exhaustion always routes to degrade, never to synthesis or consistency check
- No silent tool calls

Node dependencies:
- All nodes depend on ToolCallRecord and AgentState from state.py
- consistency_check depends on compute_confidence from rubric.py and the LLM consistency evaluator
"""

import time
import json
import re
from typing import Optional, Any, Literal, Callable
from typing_extensions import Annotated

from .state import (
    AgentState,
    ToolCallRecord,
    Citation,
    MAX_STEPS,
    ROUTE_AGENT,
    ROUTE_CHITCHAT,
    ROUTE_REFUSAL,
    ROUTE_DEGRADE,
    MODE_CURATED,
    MODE_EXPLORATORY,
    MODE_RETRIEVAL,
    STATUS_OK,
    STATUS_EMPTY,
    STATUS_INVALID,
)
from .rubric import compute_confidence


# =============================================================================
# TYPE ALIASES
# =============================================================================

# Message type for the agent
Message = dict[str, Any]

# Tool function type
ToolFunc = Callable[..., dict]


# =============================================================================
# NODE 2.3: classify
# =============================================================================

def classify(state: AgentState) -> AgentState:
    """
    Small LLM router node.
    
    Contract: PROJECT.md §2 - classify is a small LLM router
    PLAN.md 2.3 - Routes to agent | chitchat | refusal
    
    Routes the question to one of:
    - "agent": For complex questions requiring tool calls
    - "chitchat": For conversational questions (answers directly)
    - "refusal": For out-of-scope questions (returns no-evidence answer)
    
    The classify node:
    - Reads state['question']
    - Determines the route using a small LLM (Mistral small per PROJECT.md §8)
    - Sets state['route']
    - For chitchat/refusal: sets state['answer'] and state['confidence'] directly
    
    IMPLEMENTATION:
    Uses Mistral small model per PROJECT.md: "Mistral models: small for classify"
    Falls back to deterministic regex if LLM is unavailable (for testing without API).
    
    TRANSPARENCY REQUIREMENT:
    When fallback is used, it MUST be disclosed in the run-log via error field.
    This demo is about trust - degraded routing must be visible to users.
    """
    question = state.get('question', '')
    
    # Guard: empty or whitespace-only questions route to agent
    if not question.strip():
        return {
            **state,
            'route': ROUTE_AGENT,
        }
    
    # Try LLM first (Gate 1+)
    try:
        from .llm import classify_with_llm
        result = classify_with_llm(question)
        
        route = result.get('route', ROUTE_AGENT)
        answer = result.get('answer', '')
        
        if route in (ROUTE_CHITCHAT, ROUTE_REFUSAL):
            return {
                **state,
                'route': route,
                'answer': answer,
                'confidence': 0.0,
                'confidence_rationale': f'no evidence: {route}',
            }
        else:
            return {
                **state,
                'route': route,
            }
    
    except (ValueError, ImportError, Exception) as e:
        # Fallback to deterministic regex for Phase 2 testing
        # BUT: We MUST disclose this fallback for transparency
        result = _classify_with_regex(state)
        
        # Add error to disclose degraded routing
        # This will appear in run-log for transparency
        return {
            **result,
            'error': f'classify: LLM unavailable, using regex fallback. Original error: {str(e)[:200]}'
        }


def _classify_with_regex(state: AgentState) -> AgentState:
    """
    Deterministic regex-based classifier for Phase 2 testing.
    
    Uses word-boundary matching to prevent substring false positives.
    This is a MOCK for when LLM is unavailable.
    """
    question = state.get('question', '')
    question_lower = question.lower().strip()
    
    def contains_phrase(q: str, phrase: str) -> bool:
        escaped = re.escape(phrase)
        return bool(re.search(rf'\b{escaped}\b', q))
    
    # Refusal keywords
    refusal_keywords = [
        'how to hack', 'bypass', 'exploit',
        'delete', 'modify', 'change', 'update', 'insert', 'create',
        'write', 'remove', 'drop', 'alter', 'schema',
        'password', 'credentials', 'secret', 'private',
    ]
    for keyword in refusal_keywords:
        if contains_phrase(question_lower, keyword):
            return {
                **state,
                'route': ROUTE_REFUSAL,
                'answer': "I cannot help with that request.",
                'confidence': 0.0,
                'confidence_rationale': 'no evidence: refusal',
            }
    
    # Chitchat phrases (multi-word first)
    chitchat_phrases = [
        'how are you', 'how do you do', 'what is your name',
        'who are you', 'thank you', 'goodbye', 'see you',
    ]
    for phrase in chitchat_phrases:
        if contains_phrase(question_lower, phrase):
            answers = {
                'how are you': "I'm doing well, thank you! How can I assist you with the Northwind knowledge graph?",
                'how do you do': "I'm doing well, thank you! How can I assist you with the Northwind knowledge graph?",
                'what is your name': "I'm the Northwind Knowledge Graph assistant.",
                'who are you': "I'm an AI assistant for the Northwind knowledge graph demo.",
                'thank you': "You're welcome!",
                'goodbye': "Goodbye! Feel free to ask more questions anytime.",
                'see you': "See you later!",
            }
            return {
                **state,
                'route': ROUTE_CHITCHAT,
                'answer': answers.get(phrase, "I'm here to help with Northwind knowledge graph questions."),
                'confidence': 0.0,
                'confidence_rationale': 'no evidence: chitchat',
            }
    
    # Single-word chitchat
    chitchat_keywords = ['hello', 'hi', 'hey', 'greetings', 'thanks', 'bye']
    for keyword in chitchat_keywords:
        if contains_phrase(question_lower, keyword):
            answers = {
                'hello': "Hello! I'm the Northwind Knowledge Graph assistant. How can I help you?",
                'hi': "Hi! Ask me about suppliers, products, orders, or customers in the Northwind database.",
                'hey': "Hey there! What would you like to know about the Northwind data?",
                'greetings': "Hello! I'm the Northwind Knowledge Graph assistant. How can I help you?",
                'thanks': "You're welcome!",
                'bye': "Goodbye!",
            }
            return {
                **state,
                'route': ROUTE_CHITCHAT,
                'answer': answers.get(keyword, "I'm here to help with Northwind knowledge graph questions."),
                'confidence': 0.0,
                'confidence_rationale': 'no evidence: chitchat',
            }
    
    # Default to agent
    return {
        **state,
        'route': ROUTE_AGENT,
    }


from uuid import uuid4
from langchain_core.messages import AIMessage, ToolMessage

TOOL_MODES = {
    "lookup_entity": MODE_RETRIEVAL,
    "impact_analysis": MODE_CURATED,
    "co_purchase": MODE_CURATED,
    "customer_history": MODE_CURATED,
    "aggregate": MODE_CURATED,
    "run_readonly_cypher": MODE_EXPLORATORY,
}


def _get_tool_mode(tool_name: str) -> str:
    return TOOL_MODES.get(tool_name, MODE_CURATED)


def _parse_llm_tool_call(response: str) -> Optional[dict]:
    """Parse the explicit TOOL directive, including markdown and nested JSON."""
    marker = re.search(r"\*{0,2}TOOL\*{0,2}\s*:\s*`?\s*([a-z_]+)\s*\(", response, re.I)
    if not marker:
        return None
    name = marker.group(1)
    if name not in {
        "lookup_entity", "impact_analysis", "co_purchase", "customer_history",
        "aggregate", "run_readonly_cypher",
    }:
        return None
    remainder = response[marker.end():].lstrip()
    try:
        args, offset = json.JSONDecoder().raw_decode(remainder)
    except json.JSONDecodeError:
        return None
    if not isinstance(args, dict) or not remainder[offset:].lstrip().startswith(")"):
        return None
    return {"tool": name, "args": args}


def agent_step(state: AgentState) -> dict:
    """Make one ReAct decision and allow at most one evidence-recovery call."""
    count = state.get("loop_count", 0)
    if count >= MAX_STEPS:
        return {"loop_count": count}
    messages = state.get("messages", [])
    tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
    latest_tool = tool_messages[-1] if tool_messages else None
    insufficient_exploratory_evidence = False
    if latest_tool is not None:
        try:
            payload = json.loads(latest_tool.content)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        status = payload.get("status")
        prior_inadequate = any(
            _result_is_successful(_safe_tool_payload(message))
            and not _tool_result_has_evidence(message.name or "", _safe_tool_payload(message))
            for message in tool_messages[:-1]
        )
        latest_adequate = _tool_result_has_evidence(latest_tool.name or "", payload)

        # A completed recovery call still returns control to the model. The
        # recovery bound prevents another evidence-recovery call for this claim;
        # it does not establish that the original question is fully answered.
        recovery_already_used = prior_inadequate
        if latest_tool is messages[-1] and latest_tool.name == "run_readonly_cypher" and status in ("empty", "invalid", "retry_failed"):
            return {"loop_count": count, "messages": [AIMessage(content=(
                f"FINAL: The exploratory query ended with status {status}. Synthesize the "
                "reported no-match or query-failure outcome without repeating the same query."
            ))]}
        insufficient_exploratory_evidence = (
            not recovery_already_used
            and _result_is_successful(payload)
            and not latest_adequate
        )

    from .llm import generate_agent_response

    model_messages = messages
    if latest_tool is not None and recovery_already_used:
        model_messages = [*messages, AIMessage(content=(
            "The one evidence-recovery call for the earlier unsupported claim has been used. "
            "Do not repeat that recovery. Continue with any other unanswered parts of the "
            "question, or provide a candidate answer limited to supported claims."
        ))]
    response = generate_agent_response(
        question=state.get("question", ""),
        messages=model_messages,
    )
    call = _parse_llm_tool_call(response)
    if insufficient_exploratory_evidence and call is None:
        recovery_query = _whole_graph_node_count_recovery(state, latest_tool, payload)
        if recovery_query:
            # This bounded deterministic recovery prevents the model from
            # burning turns on a scalar-only total-node query while preserving
            # the ordinary tool trace and result-validation path.
            call = {"tool": "run_readonly_cypher", "args": {"query": recovery_query}}
            response = "TOOL: run_readonly_cypher(<bounded total-node evidence recovery>)"
        else:
            return {"loop_count": count + 1, "messages": [AIMessage(content=(
                "The last tool succeeded but did not return evidence associated with its claim. "
                "Do not finalize. Make one recovery tool call for the same claim, returning its "
                "computed value with a relevant anchor and at most three representative graph nodes. "
                "Do not return all contributing records. If the recovery call is still inadequate, stop."
            ))]}
    if call is not None:
        message = AIMessage(
            content=response,
            tool_calls=[{"name": call["tool"], "args": call["args"], "id": str(uuid4())}],
        )
    else:
        message = AIMessage(content=response)
    return {"loop_count": count + 1, "messages": [message]}


def _whole_graph_node_count_recovery(
    state: AgentState, message: ToolMessage, result: dict,
) -> str | None:
    """Build the one allowed recovery query for a scalar-only graph node total."""
    question = state.get("question", "").lower()
    if not (
        re.search(r"\b(?:how many|number of|count|total)\b", question)
        and re.search(r"\bnodes?\b", question)
        and re.search(r"\b(?:graph|database|dataset)\b", question)
    ):
        return None
    if message.name != "run_readonly_cypher":
        return None
    query = str(result.get("query") or "")
    if not re.search(r"count\s*\(\s*n\s*\)", query, re.IGNORECASE):
        return None
    aliases = {"node_count", "total_nodes"}
    has_count_value = any(
        isinstance(row, dict)
        and any(
            key.lower() in aliases
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            for key, value in (row.get("values") or {}).items()
        )
        for row in result.get("rows", [])
    )
    if not has_count_value:
        return None
    return (
        "MATCH (n) RETURN count(n) AS total_nodes, "
        "collect(DISTINCT n)[0..3] AS evidence_nodes"
    )


def _safe_tool_payload(message: ToolMessage) -> dict:
    try:
        value = json.loads(message.content)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _result_is_successful(result: dict) -> bool:
    return result.get("status") in ("ok", "retry_ok")


def execute_tool_step(state: AgentState, available_tools: dict[str, ToolFunc]) -> dict:
    """Execute one requested tool, validate its result, and append one trace row."""
    from src.neo4j.result_contracts import invalid_tool_result, validate_tool_result

    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or len(last.tool_calls) != 1:
        raise ValueError("tools node requires exactly one pending tool call")
    call = last.tool_calls[0]
    name, args = call["name"], call["args"]
    mode = _get_tool_mode(name)
    started = time.monotonic()
    if name not in available_tools:
        result = invalid_tool_result(name, f"Unknown tool: {name}", args)
    else:
        try:
            raw_result = available_tools[name](**args)
        except Exception as exc:
            raw_result = invalid_tool_result(name, f"Tool execution failed: {exc}", args)
        try:
            result = validate_tool_result(name, raw_result)
        except (ValueError, TypeError) as exc:
            result = invalid_tool_result(name, f"Malformed {name} result: {exc}", args)
            # The failure envelope is produced by this module and should always
            # satisfy the matching tool schema.
            result = validate_tool_result(name, result)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    rows_field = {
        "lookup_entity": "matches", "co_purchase": "recommendations",
        "customer_history": "orders", "aggregate": "groups",
        "run_readonly_cypher": "rows",
    }.get(name)
    if name == "impact_analysis":
        result_rows = len(result.get("subgraph", {}).get("nodes", []))
    else:
        result_rows = len(result.get(rows_field, [])) if rows_field else 0
    attempts = result.get("attempts", []) if name == "run_readonly_cypher" else []
    record: ToolCallRecord = {
        "step": state.get("loop_count", 0), "tool_name": name, "args": args,
        "mode": mode, "status": result["status"], "result_rows": result_rows,
        "cypher": result.get("query", args.get("query")) if name == "run_readonly_cypher" else None,
        "latency_ms": elapsed_ms, "retry_count": min(1, max(0, len(attempts) - 1)),
    }
    tool_message = ToolMessage(
        content=json.dumps(result, allow_nan=False), name=name, tool_call_id=call["id"]
    )
    return {"trace": state.get("trace", []) + [record], "messages": [tool_message]}




def _result_messages(state: AgentState) -> list[tuple[str, dict]]:
    results = []
    for message in state.get("messages", []):
        if isinstance(message, ToolMessage):
            try:
                result = json.loads(message.content)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(result, dict):
                results.append((message.name or "", result))
    return results


def _citation(node: dict) -> dict | None:
    if not isinstance(node, dict):
        return None
    label, key, name = node.get("label"), node.get("key"), node.get("name")
    if label not in {"Product", "Order", "Customer", "Supplier", "Employee", "Category", "Shipper", "Territory", "Region"} or key is None or name is None:
        return None
    return {"label": label, "key": str(key), "name": str(name)}


def _marker(citation: dict) -> str:
    return f"[{citation['label']}:{citation['key']}]"


def _row_citations(row: dict) -> list[dict]:
    """Collect canonical node citations nested anywhere in an exploratory row."""
    citations: dict[tuple[str, str], dict] = {}

    def visit(value):
        citation = _citation(value)
        if citation:
            citations[(citation["label"], citation["key"])] = citation
        elif isinstance(value, dict):
            for nested in value.values():
                visit(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                visit(nested)

    visit(row)
    return list(citations.values())


def _plural_label(label: str) -> str:
    return {
        "Category": "categories", "Country": "countries", "Employee": "employees",
        "Customer": "customers", "Company": "companies",
    }.get(label, f"{label.lower()}s")


def _normalized_result_has_evidence(result: dict) -> bool:
    """Check whether any normalized row carries citable node evidence."""
    for row in result.get("rows", []):
        evidence = row.get("evidence", {}) if isinstance(row, dict) else {}
        if _row_citations(evidence.get("nodes", [])):
            return True
    return False


def _tool_result_has_evidence(tool_name: str, result: dict) -> bool:
    """Check claim-local node evidence for the specific tool payload."""
    if not isinstance(result, dict) or not _result_is_successful(result):
        return False
    if tool_name == "lookup_entity":
        return any(
            _citation(match.get("node"))
            and any(_citation(node) == _citation(match.get("node")) for node in match.get("evidence", {}).get("nodes", []))
            for match in result.get("matches", []) if isinstance(match, dict)
        )
    if tool_name == "impact_analysis":
        anchor = _citation(result.get("anchor"))
        return bool(anchor and any(_citation(node) == anchor for node in result.get("evidence", {}).get("nodes", [])))
    if tool_name == "co_purchase":
        return all(
            _citation(item.get("product"))
            and len(_row_citations(item.get("evidence", {}).get("nodes", []))) >= 2
            for item in result.get("recommendations", []) if isinstance(item, dict)
        ) and bool(result.get("recommendations"))
    if tool_name == "customer_history":
        customer = _citation(result.get("customer"))
        return bool(customer and result.get("orders") and all(
            _citation(order.get("order"))
            and len(_row_citations(order.get("evidence", {}).get("nodes", []))) >= 2
            and bool(order.get("evidence", {}).get("edges"))
            for order in result.get("orders", []) if isinstance(order, dict)
        ))
    if tool_name == "aggregate":
        groups = result.get("groups", [])
        return bool(groups) and all(
            bool(_row_citations(group.get("evidence", {}).get("nodes", [])))
            for group in groups if isinstance(group, dict)
        )
    if tool_name == "run_readonly_cypher":
        rows = [row for row in result.get("rows", []) if isinstance(row, dict) and row.get("values")]
        return bool(rows) and all(
            bool(_row_citations(row.get("evidence", {}).get("nodes", [])))
            for row in rows
        )
    return False


def _count_label(alias: str, evidence_nodes: list[dict]) -> str:
    """Infer the counted label from a conventional <label>_count alias."""
    names = {
        "node": "Node", "customer": "Customer", "order": "Order", "product": "Product",
        "supplier": "Supplier", "employee": "Employee", "category": "Category",
        "shipper": "Shipper", "territory": "Territory", "region": "Region",
    }
    normalized = alias.lower()
    if normalized in {"node_count", "total_nodes", "node_total"}:
        return "Node"
    prefix = normalized.removesuffix("_count").rstrip("s")
    return names.get(prefix) or (evidence_nodes[0]["label"] if evidence_nodes else "Node")


def synthesize(state: AgentState) -> AgentState:
    """Build a candidate answer and citations from validated tool evidence."""
    if state.get("route") != ROUTE_AGENT:
        return state
    results = _result_messages(state)
    citations: dict[tuple[str, str], dict] = {}

    def cite(node: dict) -> str:
        citation = _citation(node)
        if citation:
            citations[(citation["label"], citation["key"])] = citation
            return _marker(citation)
        return ""

    answer = "The tool returned no supported graph result for this question."
    skip_rewrite = False
    for tool_name, result in reversed(results):
        status = result.get("status")
        if status in ("invalid", "retry_failed"):
            error = result.get("error") or "The tool request failed."
            if tool_name == "run_readonly_cypher":
                answer = ("The graph query was rejected or failed: " if status == "invalid" else
                          "The graph query could not be completed after its repair attempt: ") + error
            else:
                answer = f"The {tool_name} request could not be completed. {error}"
            break
        if status == "empty":
            labels = {
                "lookup_entity": "I couldn't find a graph entity matching that name or key.",
                "aggregate": "The aggregate query ran successfully but returned no matching groups.",
                "run_readonly_cypher": "The graph query ran successfully but returned no matching rows.",
            }
            answer = labels.get(tool_name, f"The {tool_name} tool ran successfully but returned no matching records.")
            break
        if status not in ("ok", "retry_ok"):
            continue

        if tool_name == "lookup_entity":
            lines = []
            for item in result.get("matches", []):
                node = item.get("node", {})
                if not _citation(node) or not any(_citation(n) == _citation(node) for n in item.get("evidence", {}).get("nodes", [])):
                    continue
                properties = node.get("properties", {})
                details = ", ".join(f"{k}: {v}" for k, v in properties.items()
                                     if v is not None and isinstance(v, (str, int, float, bool)))
                lines.append(f"- {node['name']} {cite(node)}" + (f" ({details})" if details else ""))
            answer = "Matching graph nodes:\n" + "\n".join(lines[:10]) if lines else "The lookup returned values without matching node evidence."
            break

        if tool_name == "impact_analysis":
            anchor = result.get("anchor")
            evidence = result.get("evidence", {})
            nodes = evidence.get("nodes", [])
            if not _citation(anchor) or not any(_citation(n) == _citation(anchor) for n in nodes):
                answer = "The impact tool returned metrics without evidence for its anchor."
                break
            marker = cite(anchor)
            support = [cite(n) for n in nodes if _citation(n) != _citation(anchor)][:2]
            agg = result.get("aggregates", {})
            answer = (f"{anchor['name']} {marker} affects {agg['products_affected']} products and "
                      f"{agg['orders_affected']} orders; estimated revenue at risk is "
                      f"${agg['revenue_at_risk']:,.2f}. {agg['unusable_lines']} order lines could not be valued.")
            if support:
                answer += " Supporting graph evidence: " + " ".join(support) + "."
            break

        if tool_name == "co_purchase":
            anchor = result.get("product")
            if not _citation(anchor):
                answer = "The co-purchase result has no citable anchor product."
                break
            lines = [f"Products co-purchased with {anchor['name']} {cite(anchor)}:"]
            for item in result.get("recommendations", [])[:10]:
                node = item.get("product", {})
                nodes = item.get("evidence", {}).get("nodes", [])
                if _citation(node) and any(_citation(n) == _citation(node) for n in nodes) and any(_citation(n) == _citation(anchor) for n in nodes):
                    lines.append(f"- {node['name']} {cite(node)}: {item['co_bought']} shared orders")
            answer = "\n".join(lines)
            break

        if tool_name == "customer_history":
            customer = result.get("customer")
            if not _citation(customer):
                answer = "The customer history result has no citable customer."
                break
            orders = result.get("orders", [])
            question = state.get("question", "").lower()
            exhaustive_list = bool(re.search(r"\b(all|every|each)\b", question) and re.search(r"\border", question))
            evidenced_orders = []
            dated_orders = []
            for item in orders:
                node = item.get("order", {})
                evidence = item.get("evidence", {})
                if not _citation(node) or not any(_citation(n) == _citation(node) for n in evidence.get("nodes", [])):
                    continue
                evidenced_orders.append((item, node))
                try:
                    from datetime import date
                    dated_orders.append(date.fromisoformat(str(item.get("order_date", "")).split()[0]))
                except ValueError:
                    pass
            shown_orders = evidenced_orders if exhaustive_list else evidenced_orders[:10]
            lines = []
            for item, node in shown_orders:
                marker = cite(node)
                lines.append(f"- {item.get('order_date')}: order {node['key']} {marker}, total ${item['total']:,.2f}")
            if exhaustive_list:
                heading = f"{customer['name']} {cite(customer)} has {len(evidenced_orders)} evidenced orders:"
            elif len(evidenced_orders) > len(shown_orders):
                heading = f"{customer['name']} {cite(customer)} has {len(evidenced_orders)} evidenced orders; showing the first {len(shown_orders)}:"
            else:
                heading = f"{customer['name']} {cite(customer)} has {len(evidenced_orders)} evidenced orders:"
            answer = heading + ("\n" + "\n".join(lines) if lines else "")
            if len(dated_orders) > 1:
                gaps = [(later - earlier).days for earlier, later in zip(dated_orders, dated_orders[1:])]
                answer += f"\nLargest gap between returned orders: {max(gaps)} days."
            break

        if tool_name == "aggregate":
            lines = []
            for group in result.get("groups", [])[:10]:
                nodes = group.get("evidence", {}).get("nodes", [])[:3]
                markers = [cite(node) for node in nodes if _citation(node)]
                if markers:
                    lines.append(f"- {group['group_value']}: {group['metric_value']} {' '.join(markers)}")
            answer = "Grouped results:\n" + "\n".join(lines) if lines else "The aggregate result contains metrics without supporting node evidence."
            break

        if tool_name == "run_readonly_cypher":
            lines = []
            unsupported = False
            for row in result.get("rows", [])[:20]:
                values = row.get("values", {})
                row_nodes = _row_citations(row.get("evidence", {}).get("nodes", []))
                requested_keys = list(dict.fromkeys(re.findall(r"\b[A-Z0-9]{5}\b", state.get("question", ""))))
                subject_nodes = [node for key in requested_keys for node in row_nodes if node["key"] == key]
                product_node = next((node for node in row_nodes if node["label"] == "Product"), None)
                if len(requested_keys) >= 2 and len(subject_nodes) == len(requested_keys) and product_node:
                    nodes = list({(node["label"], node["key"]): node for node in [*subject_nodes, product_node]}.values())[:3]
                else:
                    nodes = row_nodes[:3]
                if not values:
                    continue
                if not nodes:
                    unsupported = True
                    continue
                markers = " ".join(cite(n) for n in nodes)
                counts = [(key, value) for key, value in values.items()
                          if ("count" in key.lower() or key.lower() in {"total_nodes", "node_total"})
                          and isinstance(value, (int, float)) and not isinstance(value, bool)]
                quantities = [(key, value) for key, value in values.items()
                              if key.lower().replace("_", "") in {"totalquantity", "unitsordered", "totalorderedquantity"}
                              and isinstance(value, (int, float)) and not isinstance(value, bool)]
                product = next((node for node in nodes if node["label"] == "Product"), None)
                explicit_nodes = [citation for field, item in values.items() if not field.lower().startswith(("evidence", "sample", "representative")) if (citation := _citation(item)) is not None]
                customer = next((node for node in explicit_nodes if node["label"] == "Customer"), None)
                if quantities and customer:
                    value = quantities[0][1]
                    lines.append(f"{customer['name']} {cite(customer)} ordered {value:,.0f} product units. Supporting evidence: {markers}.")
                elif quantities and product:
                    value = quantities[0][1]
                    lines.append(f"Most ordered product: {product['name']} {cite(product)}, with {value:,.0f} units ordered.")
                elif counts:
                    key, value = counts[0]
                    label = _count_label(key, nodes)
                    # A sampled evidence node is not a scope anchor. Only a
                    # node returned in its own value column can scope a count.
                    explicit_nodes = [
                        citation for field, item in values.items()
                        if not field.lower().startswith(("evidence", "sample", "representative"))
                        if (citation := _citation(item)) is not None
                    ]
                    anchor = next((node for node in explicit_nodes if node["label"] != label), None)
                    if anchor is None and label == "Node" and key.lower() in {"node_count", "total_nodes", "node_total"}:
                        skip_rewrite = True
                    if anchor and anchor["label"] == "Customer" and label == "Order":
                        lines.append(f"{anchor['name']} {cite(anchor)} placed {value:,.0f} orders. Supporting evidence: {markers}.")
                    elif anchor:
                        lines.append(f"{value:,.0f} {_plural_label(label)} for {anchor['name']} {cite(anchor)}. Evidence: {markers}.")
                    else:
                        lines.append(f"The Northwind dataset contains {value:,.0f} {_plural_label(label)}. Representative evidence: {markers}.")
                elif len(requested_keys) >= 2 and product:
                    lines.append(
                        f"{product['name']} {cite(product)} is evidenced for the requested customers "
                        f"{', '.join(requested_keys)}. Supporting evidence: {markers}."
                    )
                else:
                    scalars = [f"{key}: {value}" for key, value in values.items()
                               if value is None or isinstance(value, (str, int, float, bool))]
                    if scalars:
                        lines.append("; ".join(scalars) + f" {markers}")
            if lines:
                answer = "\n".join(lines[:20])
            elif unsupported:
                answer = "The graph query returned values, but no node evidence was included to cite them, even after the bounded recovery attempt."
            else:
                answer = "The graph query completed but returned no citable graph evidence."
            break

    # A previous successful value without evidence must not be reinterpreted as
    # an empty result merely because the one recovery attempt returned no rows.
    if results:
        earlier_unsupported = any(
            _result_is_successful(result) and not _tool_result_has_evidence(name, result)
            for name, result in results[:-1]
        )
        latest_name, latest_result = results[-1]
        if earlier_unsupported and latest_result.get("status") == "empty":
            answer = "The original tool returned a value without sufficient node evidence, and the single recovery attempt found no supporting graph evidence. The claim remains unsupported."

    exhaustive_order_list = (
        "exhaustive_list" in locals() and exhaustive_list
        and any(name == "customer_history" for name, _ in results)
    )
    if citations and results and not exhaustive_order_list and not skip_rewrite:
        try:
            from .llm import synthesize_from_evidence
            revised = synthesize_from_evidence(answer)
            expected = set(re.findall(r"\[[A-Za-z]+:[^\]]+\]", answer))
            got = set(re.findall(r"\[[A-Za-z]+:[^\]]+\]", revised))
            source_numbers = set(re.findall(r"\d[\d,.]*", answer))
            revised_numbers = set(re.findall(r"\d[\d,.]*", revised))
            # A rewrite may improve phrasing but must preserve every numeric
            # fact in the grounded draft and render canonical markers literally.
            clean_citations = "<cite>" not in revised and "{{" not in revised and "}}" not in revised
            if got == expected and source_numbers == revised_numbers and clean_citations and all(
                "[" in line and "]" in line for line in revised.splitlines() if line.strip()
            ):
                answer = revised
        except Exception:
            pass
    return {
        "draft_answer": answer,
        "draft_citations": list(citations.values()),
    }


def _compact_consistency_value(value: Any, depth: int = 0) -> Any:
    """Remove verbose node properties and bound tool data sent to the reviewer."""
    if depth > 6:
        return "…"
    citation = _citation(value) if isinstance(value, dict) else None
    if citation:
        return citation
    if isinstance(value, dict):
        if "type" in value and "from" in value and "to" in value:
            return {
                "type": value.get("type"),
                "from": _compact_consistency_value(value.get("from"), depth + 1),
                "to": _compact_consistency_value(value.get("to"), depth + 1),
            }
        return {
            key: _compact_consistency_value(item, depth + 1)
            for key, item in value.items()
            if key != "properties"
        }
    if isinstance(value, (list, tuple)):
        compacted = [_compact_consistency_value(item, depth + 1) for item in value[:12]]
        if len(value) > 12:
            compacted.append({"omitted_items": len(value) - 12})
        return compacted
    if isinstance(value, str):
        return value[:240]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:240]


def _tool_evidence_context(state: AgentState) -> list[dict]:
    """Return a compact, JSON-safe account of the tool results behind a draft."""
    context = []
    for name, result in _result_messages(state)[-8:]:
        context.append({"tool": name, "result": _compact_consistency_value(result)})
    return context


def _returned_node_citations(state: AgentState) -> set[tuple[str, str]]:
    returned = set()
    for _, result in _result_messages(state):
        returned.update((node["label"], node["key"]) for node in _row_citations(result))
    return returned


def _question_entity_keys(question: str) -> list[str]:
    """Recognize Northwind-style uppercase five-character IDs in a question."""
    return list(dict.fromkeys(re.findall(r"\b[A-Z0-9]{5}\b", question)))


def consistency_check(state: AgentState) -> dict:
    """Validate a synthesized draft before exposing it as the final answer."""
    if state.get("route") != ROUTE_AGENT:
        return {}

    answer = (state.get("draft_answer") or "").strip()
    citations = state.get("draft_citations", [])
    results = _result_messages(state)

    def revise(feedback: str) -> dict:
        preview = answer[:1200]
        note = f"Internal consistency check: revise the candidate. {feedback}"
        if preview:
            note += f" Candidate draft: {preview}"
        return {
            "consistency_status": "revise",
            "consistency_feedback": feedback,
            "answer": "",
            "citations": [],
            "confidence": 0.0,
            "confidence_rationale": "",
            "messages": [AIMessage(content=note)],
        }

    if not answer:
        return revise("Synthesis produced no candidate answer.")
    if not results:
        return revise("No graph tool result supports a factual answer; choose an appropriate tool before finalizing.")

    latest_status = results[-1][1].get("status") if results else None
    # An explicit query failure is a terminal, transparent response. Empty is
    # normal success and still needs a check that the attempted query covered the request.
    if latest_status in {"invalid", "retry_failed"} and not citations:
        confidence, rationale = compute_confidence(state.get("trace", []), ROUTE_AGENT)
        return {
            "consistency_status": "pass",
            "consistency_feedback": None,
            "answer": answer,
            "citations": [],
            "confidence": confidence,
            "confidence_rationale": rationale,
        }

    returned = _returned_node_citations(state)
    cited = {(item.get("label"), str(item.get("key"))) for item in citations if isinstance(item, dict)}
    missing_returned = cited - returned
    if missing_returned:
        label, key = sorted(missing_returned)[0]
        return revise(f"Citation [{label}:{key}] is not present in the returned graph evidence.")

    markers = set(re.findall(r"\[([A-Za-z]+):([^\]]+)\]", answer))
    citation_markers = {(item.get("label"), str(item.get("key"))) for item in citations if isinstance(item, dict)}
    if markers != citation_markers:
        return revise("The draft's inline citations do not match its citation records.")

    requested_keys = _question_entity_keys(state.get("question", ""))
    if len(requested_keys) >= 2:
        attempted_text = json.dumps({
            "trace": [item.get("args", {}) for item in state.get("trace", [])],
            "results": _tool_evidence_context(state),
        }, ensure_ascii=False, default=str).upper()
        missing_from_attempts = [key for key in requested_keys if key not in attempted_text]
        if missing_from_attempts:
            return revise(
                "The question names multiple graph IDs, but the tool calls did not cover all of them: "
                f"{', '.join(missing_from_attempts)}. Query all requested subjects and their relationship to the requested result."
            )
        if latest_status != "empty":
            missing_keys = [key for key in requested_keys if not any(node_key == key for _, node_key in returned)]
            missing_citations = [key for key in requested_keys if not any(label == "Customer" and node_key == key for label, node_key in cited)]
            if missing_keys:
                return revise(
                    "The question names multiple graph IDs, but the tool evidence covers only "
                    f"some of them. Missing evidence for: {', '.join(missing_keys)}. Query all requested subjects and their relationship to the requested result."
                )
            if missing_citations:
                return revise(
                    "The question names multiple customer IDs, but the draft does not cite all of them: "
                    f"{', '.join(missing_citations)}. Include the relevant customer nodes and their relationship evidence."
                )

    # An explicit unsupported-evidence abstention after the bounded recovery is a
    # complete response: it makes no graph claim for the checker to approve.
    has_prior_unsupported = any(
        _result_is_successful(result) and not _tool_result_has_evidence(name, result)
        for name, result in results[:-1]
    )
    if has_prior_unsupported and not citations and any(
        phrase in answer.lower() for phrase in ("unsupported", "insufficient", "no node evidence")
    ):
        confidence, rationale = compute_confidence(state.get("trace", []), ROUTE_AGENT)
        return {
            "consistency_status": "pass", "consistency_feedback": None,
            "answer": answer, "citations": [], "confidence": confidence,
            "confidence_rationale": rationale,
        }

    if not citations and latest_status in {"ok", "retry_ok"}:
        return revise("The successful graph result has no node citations to support its claims.")

    from .llm import evaluate_answer_consistency
    try:
        decision = evaluate_answer_consistency(
            question=state.get("question", ""),
            candidate_answer=answer,
            citations=citations,
            supporting_results=_tool_evidence_context(state),
        )
    except Exception as exc:
        return revise(f"Could not verify answer coverage against the graph evidence: {exc}")

    if decision.get("decision") != "pass":
        return revise(decision.get("feedback") or "The candidate does not clearly answer every part of the question.")

    confidence, rationale = compute_confidence(state.get("trace", []), ROUTE_AGENT)
    return {
        "consistency_status": "pass",
        "consistency_feedback": None,
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
        "confidence_rationale": rationale,
    }


def degrade(state: AgentState) -> AgentState:
    """
    Degrade node - reached on MAX_STEPS exhaustion.
    
    Contract: PROJECT.md §2, PLAN.md 2.7
    
    Explicit truncation disclosure.
    Confidence hard-capped at 0.4.
    Records error.
    
    Invariant: Budget exhaustion always routes to degrade, never to synthesize.
    """
    loop_count = state.get('loop_count', 0)
    
    return {
        **state,
        'route': ROUTE_DEGRADE,
        'draft_answer': None,
        'draft_citations': [],
        'answer': (
            f"Truncated: Reached maximum steps (MAX_STEPS={MAX_STEPS}). "
            f"The agent loop exhausted its budget after {loop_count} iterations. "
            "Please rephrase your question or try a simpler query."
        ),
        'confidence': 0.4,
        'confidence_rationale': f"Hard cap 0.4: budget exhausted (loop_count={loop_count} >= MAX_STEPS={MAX_STEPS}), truncation disclosure mandatory",
        'error': f'Budget exhausted: loop_count={loop_count} >= MAX_STEPS={MAX_STEPS}',
    }




__all__ = ["classify", "agent_step", "execute_tool_step", "synthesize", "consistency_check", "degrade"]

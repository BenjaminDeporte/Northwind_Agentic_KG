"""
Agent graph nodes for the Northwind Agentic KG.

Authoritative contracts:
- PROJECT.md §2: Architecture (classify → agent ↔ tools → synthesize, degrade)
- PROJECT.md §3: State TypedDicts
- PROJECT.md §4: Tools
- PROJECT.md §5: Confidence rubric
- PROJECT.md §6: Run-log
- PROJECT.md §7: GUI

Control-flow invariants:
- MAX_STEPS=8
- Every executed tool call appends exactly one ToolCallRecord to trace
- Budget exhaustion always routes to degrade, never to synthesize
- No silent tool calls

Node dependencies:
- All nodes depend on ToolCallRecord and AgentState from state.py
- synthesize depends on compute_confidence from rubric.py
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


def agent_step(state: AgentState, available_tools: dict[str, ToolFunc]) -> dict:
    """Make one ReAct decision. Tool execution belongs exclusively to tools."""
    count = state.get("loop_count", 0)
    if count >= MAX_STEPS:
        return {"loop_count": count}
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], ToolMessage):
        latest = messages[-1]
        try:
            payload = json.loads(latest.content)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        status = payload.get("status")
        final_tools = {"impact_analysis", "co_purchase", "customer_history", "aggregate"}
        if latest.name in final_tools and status in ("ok", "retry_ok", "empty"):
            return {"loop_count": count, "messages": [AIMessage(content="FINAL: Sufficient graph evidence collected.")]}
        if latest.name == "run_readonly_cypher":
            if status in ("empty", "invalid", "retry_failed") or (
                status in ("ok", "retry_ok") and _normalized_result_has_evidence(payload)
            ):
                return {"loop_count": count, "messages": [AIMessage(content="FINAL: Exploratory query result is ready for synthesis.")]}
    from .llm import generate_agent_response

    response = generate_agent_response(
        question=state.get("question", ""),
        messages=state.get("messages", []),
        available_tools=list(available_tools),
    )
    call = _parse_llm_tool_call(response)
    if call is not None:
        message = AIMessage(
            content=response,
            tool_calls=[{"name": call["tool"], "args": call["args"], "id": str(uuid4())}],
        )
    else:
        message = AIMessage(content=response)
    return {"loop_count": count + 1, "messages": [message]}


def execute_tool_step(state: AgentState, available_tools: dict[str, ToolFunc]) -> dict:
    """Execute exactly one requested tool and record exactly one trace entry."""
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or len(last.tool_calls) != 1:
        raise ValueError("tools node requires exactly one pending tool call")
    call = last.tool_calls[0]
    name, args = call["name"], call["args"]
    mode = _get_tool_mode(name)
    started = time.monotonic()
    try:
        if name not in available_tools:
            result = {"status": STATUS_INVALID, "error": f"Unknown tool: {name}"}
        else:
            result = available_tools[name](**args)
    except Exception as exc:
        result = {"status": STATUS_INVALID, "error": str(exc)}
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if not isinstance(result, dict):
        result = {"status": STATUS_INVALID, "error": "Tool returned a non-dict result"}
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
        "mode": mode, "status": result.get("status", STATUS_INVALID),
        "result_rows": result_rows,
        "cypher": result.get("query", args.get("query")) if name == "run_readonly_cypher" else None,
        "latency_ms": elapsed_ms, "retry_count": min(1, max(0, len(attempts) - 1)),
    }
    tool_message = ToolMessage(
        content=json.dumps(result, default=str), name=name, tool_call_id=call["id"]
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


def _count_label(alias: str, evidence_nodes: list[dict]) -> str:
    """Infer the counted label from a conventional <label>_count alias."""
    names = {
        "customer": "Customer", "order": "Order", "product": "Product",
        "supplier": "Supplier", "employee": "Employee", "category": "Category",
        "shipper": "Shipper", "territory": "Territory", "region": "Region",
    }
    prefix = alias.lower().removesuffix("_count").rstrip("s")
    return names.get(prefix) or (evidence_nodes[0]["label"] if evidence_nodes else "Node")


def synthesize(state: AgentState) -> AgentState:
    """Build a final answer from tool results, distinguishing empty from failed queries."""
    if state.get("route") != ROUTE_AGENT:
        return state
    results = _result_messages(state)
    citations: dict[tuple[str, str], dict] = {}

    def cite(node):
        citation = _citation(node)
        if citation:
            citations[(citation["label"], citation["key"])] = citation
            return _marker(citation)
        return ""

    answer = "I found no cited graph evidence for this question."
    for tool_name, result in reversed(results):
        status = result.get("status")

        if tool_name == "run_readonly_cypher":
            if status in ("invalid", "retry_failed"):
                error = result.get("error") or "The query failed validation or execution."
                if status == "invalid":
                    answer = f"The graph query was rejected before execution: {error}"
                else:
                    answer = f"The graph query could not be completed after its repair attempt: {error}"
                break
            if status == "empty":
                answer = "The graph query ran successfully but returned no matching rows."
                break
            if status not in ("ok", "retry_ok"):
                continue

            lines = []
            saw_uncitable_values = False
            for row in result.get("rows", [])[:20]:
                if not isinstance(row, dict):
                    continue
                values = row.get("values", {})
                evidence = row.get("evidence", {})
                if not isinstance(values, dict) or not isinstance(evidence, dict):
                    continue
                nodes = _row_citations(evidence.get("nodes", []))
                if not nodes:
                    saw_uncitable_values = saw_uncitable_values or bool(values)
                    continue

                count_values = [
                    (key, value) for key, value in values.items()
                    if "count" in key.lower() and isinstance(value, (int, float)) and not isinstance(value, bool)
                ]
                markers = " ".join(cite(node) for node in nodes)
                if count_values:
                    count_key, count_value = count_values[0]
                    label = _count_label(count_key, nodes)
                    anchor = next((node for node in nodes if node["label"] != label), None)
                    if anchor and anchor["label"] == "Customer" and label == "Order":
                        answer = (
                            f"{anchor['name']} {_marker(anchor)} placed "
                            f"{int(count_value):,} orders. {markers}"
                        )
                    elif anchor:
                        answer = (
                            f"{int(count_value):,} {_plural_label(label)} for "
                            f"{anchor['name']} {_marker(anchor)}. {markers}"
                        )
                    else:
                        answer = (
                            f"The Northwind dataset contains {int(count_value):,} "
                            f"{_plural_label(label)}. {markers}"
                        )
                    lines = []
                    break

                scalar_values = [
                    (key, value) for key, value in values.items()
                    if value is None or isinstance(value, (str, int, float, bool))
                ]
                if scalar_values:
                    details = ", ".join(f"{key}: {value}" for key, value in scalar_values)
                    lines.append(f"- {details} {markers}")
                else:
                    for node in nodes:
                        lines.append(f"- {node['name']} {_marker(node)}")

            if answer != "I found no cited graph evidence for this question.":
                break
            if lines:
                answer = "Query results:\n" + "\n".join(lines)
            elif saw_uncitable_values:
                answer = "The graph query returned values, but no node evidence was included to cite them."
            else:
                answer = "The graph query completed but returned no citable graph evidence."
            break

        if status in ("invalid", "retry_failed"):
            error = result.get("error")
            answer = f"The {tool_name} request could not be completed."
            if error:
                answer += f" {error}"
            break
        if status == "empty":
            if tool_name == "lookup_entity":
                answer = "I couldn't find a graph entity matching that name or key."
            elif tool_name == "aggregate":
                answer = "The aggregate query ran successfully but returned no matching groups."
            else:
                answer = f"The {tool_name} tool ran successfully but returned no matching records."
            break

        if tool_name == "impact_analysis":
            anchor = result.get("anchor")
            if not _citation(anchor):
                continue
            marker = cite(anchor)
            aggregates = result.get("aggregates", {})
            answer = (
                f"{anchor['name']} {marker} affects {aggregates.get('products_affected', 0)} products "
                f"and {aggregates.get('orders_affected', 0)} orders; estimated revenue at risk is "
                f"${aggregates.get('revenue_at_risk', 0):,.2f}. "
                f"{aggregates.get('unusable_lines', 0)} order lines could not be valued {marker}."
            )
            break
        if tool_name == "co_purchase":
            anchor = result.get("product")
            if not _citation(anchor):
                continue
            anchor_marker = cite(anchor)
            lines = [f"Products co-purchased with {anchor['name']} {anchor_marker}:"]
            for item in result.get("recommendations", []):
                marker = cite(item)
                if marker:
                    lines.append(f"- {item['name']} {marker}: {item['co_bought']} shared orders")
            answer = "\n".join(lines)
            break
        if tool_name == "customer_history":
            customer = result.get("customer")
            if not _citation(customer):
                continue
            marker = cite(customer)
            orders = result.get("orders", [])
            lines = [f"{customer['name']} {marker} has {len(orders)} returned orders:"]
            dated_orders = []
            for order in orders:
                order_node = {"label": "Order", "key": order.get("order_key"), "name": str(order.get("order_key"))}
                order_marker = cite(order_node)
                lines.append(f"- {order.get('order_date')}: order {order.get('order_key')} {order_marker}, total ${order.get('total', 0):,.2f}")
                try:
                    from datetime import date
                    dated_orders.append((date.fromisoformat(str(order.get("order_date", "")).split()[0]), order_marker))
                except ValueError:
                    pass
            gaps = [((later[0] - earlier[0]).days, earlier[1], later[1]) for earlier, later in zip(dated_orders, dated_orders[1:])]
            if gaps:
                days, before, after = max(gaps)
                lines.append(f"Largest gap between returned orders: {days} days, between {before} and {after}.")
            answer = "\n".join(lines)
            break
        if tool_name == "lookup_entity":
            lines = []
            for match in result.get("matches", []):
                marker = cite(match)
                if marker:
                    properties = match.get("properties", {})
                    details = ", ".join(
                        f"{key}: {value}" for key, value in properties.items()
                        if value is not None and isinstance(value, (str, int, float, bool))
                    ) if isinstance(properties, dict) else ""
                    suffix = f" ({details})" if details else ""
                    lines.append(f"- {match['name']} {marker}{suffix}")
            if lines:
                answer = "Matching graph nodes:\n" + "\n".join(lines)
                break
        if tool_name == "aggregate":
            lines = []
            for group in result.get("groups", []):
                markers = [cite(node) for node in group.get("evidence", [])]
                markers = [marker for marker in markers if marker]
                if markers:
                    lines.append(f"- {group['group_value']}: {group['metric_value']} {' '.join(markers)}")
            answer = "Grouped results:\n" + "\n".join(lines) if lines else "The aggregate result contained no citable nodes."
            break

    if citations and results:
        try:
            from .llm import synthesize_from_evidence
            revised = synthesize_from_evidence(answer)
            expected_markers = set(re.findall(r"\[[A-Za-z]+:[^\]]+\]", answer))
            revised_markers = set(re.findall(r"\[[A-Za-z]+:[^\]]+\]", revised))
            source_numbers = set(re.findall(r"\d[\d,.]*", answer))
            revised_numbers = set(re.findall(r"\d[\d,.]*", revised))
            lines_cited = all("[" in line and "]" in line for line in revised.splitlines() if line.strip())
            if revised_markers == expected_markers and revised_numbers <= source_numbers and lines_cited:
                answer = revised
        except Exception:
            # Keep the deterministic, evidence-grounded draft if wording fails.
            pass
    confidence, rationale = compute_confidence(state.get("trace", []), ROUTE_AGENT)
    return {"answer": answer, "citations": list(citations.values()), "confidence": confidence, "confidence_rationale": rationale}




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
        'answer': (
            f"Truncated: Reached maximum steps (MAX_STEPS={MAX_STEPS}). "
            f"The agent loop exhausted its budget after {loop_count} iterations. "
            "Please rephrase your question or try a simpler query."
        ),
        'confidence': 0.4,
        'confidence_rationale': f"Hard cap 0.4: budget exhausted (loop_count={loop_count} >= MAX_STEPS={MAX_STEPS}), truncation disclosure mandatory",
        'error': f'Budget exhausted: loop_count={loop_count} >= MAX_STEPS={MAX_STEPS}',
    }




__all__ = ["classify", "agent_step", "execute_tool_step", "synthesize", "degrade"]

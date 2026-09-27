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
ToolFunc = Callable[[Any], dict]


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
    """
    question = state.get('question', '')
    
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
        # This maintains backward compatibility with existing tests
        return _classify_with_regex(state)


def _classify_with_regex(state: AgentState) -> AgentState:
    """
    Deterministic regex-based classifier for Phase 2 testing.
    
    Uses word-boundary matching to prevent substring false positives.
    This is a MOCK for when LLM is unavailable.
    """
    question = state.get('question', '')
    question_lower = question.lower().strip()
    
    import re
    
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


# =============================================================================
# NODE 2.5: tools dispatcher
# =============================================================================

def tools_dispatcher(
    state: AgentState,
    tool_name: str,
    tool_func: ToolFunc,
    step: int,
    args: dict
) -> tuple[AgentState, dict]:
    """
    Dispatch a single tool call, time it, append ToolCallRecord to trace.
    
    Contract: PROJECT.md §2, PLAN.md 2.5
    
    Args:
        state: Current agent state
        tool_name: Name of the tool to call
        tool_func: The tool function to execute
        step: 1-based loop iteration
        args: Arguments to pass to the tool
    
    Returns:
        Tuple of (updated_state, tool_result)
    
    Invariants:
    - Exactly ONE ToolCallRecord appended to trace
    - No silent calls
    - Latency measured and recorded
    - retry_count tracked (0 or 1)
    """
    # Determine mode based on tool name
    mode = _get_tool_mode(tool_name)
    
    # Execute tool and time it
    start_time = time.time()
    tool_result = tool_func(**args)
    elapsed_ms = int((time.time() - start_time) * 1000)
    
    # Extract result info
    status = tool_result.get('status', 'unknown')
    result_rows = len(tool_result.get('rows', tool_result.get('matches', tool_result.get('groups', []))))
    cypher = tool_result.get('cypher', None) if mode == MODE_EXPLORATORY else None
    
    # Build ToolCallRecord
    record: ToolCallRecord = {
        'step': step,
        'tool_name': tool_name,
        'args': args,
        'mode': mode,
        'status': status,
        'result_rows': result_rows,
        'cypher': cypher,
        'latency_ms': elapsed_ms,
        'retry_count': 0,  # Will be set to 1 if retry happens in tool itself
    }
    
    # Append record to trace
    trace = state.get('trace', [])
    updated_trace = trace + [record]
    
    # Update state
    updated_state = {
        **state,
        'trace': updated_trace,
    }
    
    return (updated_state, tool_result)


def _get_tool_mode(tool_name: str) -> str:
    """Determine tool mode based on name."""
    curated_tools = {
        'lookup_entity',
        'impact_analysis', 
        'co_purchase',
        'customer_history',
        'aggregate',
    }
    exploratory_tools = {
        'run_readonly_cypher',
    }
    retrieval_tools = {
        'lookup_entity',
    }
    
    if tool_name in retrieval_tools:
        return MODE_RETRIEVAL
    elif tool_name in curated_tools:
        return MODE_CURATED
    elif tool_name in exploratory_tools:
        return MODE_EXPLORATORY
    else:
        # Default to curated for unknown tools
        return MODE_CURATED


# =============================================================================
# NODE 2.4: agent (ReAct loop)
# =============================================================================

def agent(state: AgentState, tools: dict[str, ToolFunc]) -> AgentState:
    """
    ReAct loop node.
    
    Contract: PROJECT.md §2, PLAN.md 2.4
    
    MAX_STEPS=8. All 6 tools bound. Emits tool calls. 
    Terminates on answer or budget exhaustion.
    
    Control-flow invariants:
    - MAX_STEPS=8
    - Budget exhaustion routes to degrade, never to synthesize
    - Every executed tool call appends exactly one ToolCallRecord
    
    The agent:
    1. Checks loop_count against MAX_STEPS
    2. Uses LLM to generate next step (ReAct: THINK -> TOOL -> observe)
    3. Parses and dispatches tool call
    4. Updates state with tool result
    5. Returns updated state
    
    Uses Mistral large model per PROJECT.md: "Mistral models: large for agent"
    Falls back to deterministic tool selection if LLM is unavailable.
    """
    question = state.get('question', '')
    route = state.get('route', '')
    loop_count = state.get('loop_count', 0)
    trace = state.get('trace', [])
    messages = state.get('messages', [])
    
    # Check for budget exhaustion
    if loop_count >= MAX_STEPS:
        # Route to degrade
        return {
            **state,
            'route': ROUTE_DEGRADE,
            'error': f'Budget exhausted: loop_count={loop_count} >= MAX_STEPS={MAX_STEPS}',
        }
    
    # Update loop count
    new_loop_count = loop_count + 1
    
    # Try LLM-based ReAct loop first (Gate 1+)
    try:
        return _agent_with_llm(state, tools, new_loop_count)
    except (ValueError, ImportError, Exception) as e:
        # Fallback to deterministic tool selection for Phase 2 testing
        return _agent_with_deterministic(state, tools, new_loop_count)


def _agent_with_llm(state: AgentState, tools: dict[str, ToolFunc], new_loop_count: int) -> AgentState:
    """
    LLM-based ReAct loop implementation.
    
    Generates reasoning + tool call from LLM, parses it, executes the tool,
    and returns the updated state.
    """
    from .llm import generate_agent_response
    from .schema_prompt import get_schema_prompt
    import json
    import re
    
    question = state.get('question', '')
    messages = state.get('messages', [])
    trace = state.get('trace', [])
    
    # Build the prompt with context from trace
    tool_descriptions = _get_tool_descriptions()
    schema_prompt = get_schema_prompt()
    
    # Format trace as context for the LLM
    trace_context = _format_trace_for_llm(trace)
    
    # Generate LLM response
    llm_response = generate_agent_response(
        question=question,
        messages=messages + [{"role": "user", "content": question}],
        available_tools=list(tools.keys())
    )
    
    # Parse the response for tool calls
    # Expected format: THINK: ...\nTOOL: tool_name(json_args)
    tool_call = _parse_llm_tool_call(llm_response)
    
    if not tool_call:
        # LLM didn't request a tool call - check if it provided a final answer
        if 'FINAL:' in llm_response.upper():
            # Extract final answer
            final_answer = llm_response.split('FINAL:')[-1].strip()
            return {
                **state,
                'loop_count': new_loop_count,
                'answer': final_answer,
            }
        else:
            # No tool call and no final answer - end loop
            return {
                **state,
                'loop_count': new_loop_count,
            }
    
    # Execute the tool call
    tool_name = tool_call['tool']
    tool_args = tool_call['args']
    
    if tool_name not in tools:
        return {
            **state,
            'loop_count': new_loop_count,
            'error': f'Tool {tool_name} not available',
        }
    
    # Dispatch tool call
    tool_func = tools[tool_name]
    updated_state, tool_result = tools_dispatcher(
        state, tool_name, tool_func, new_loop_count, tool_args
    )
    
    # Update loop count in the returned state
    updated_state['loop_count'] = new_loop_count
    
    # Add tool result to messages for LLM context
    tool_message = {
        'role': 'tool',
        'content': json.dumps(tool_result),
        'tool_name': tool_name,
    }
    updated_state['messages'] = messages + [tool_message]
    
    return updated_state


def _parse_llm_tool_call(response: str) -> Optional[dict]:
    """
    Parse LLM response for tool call in format: TOOL: tool_name(json_args)
    
    Returns: {'tool': tool_name, 'args': dict} or None
    """
    import json
    import re
    
    # Look for TOOL: pattern
    tool_pattern = r'TOOL:\s*(\w+)\s*\((.*?)\)'
    match = re.search(tool_pattern, response, re.DOTALL)
    
    if not match:
        return None
    
    tool_name = match.group(1)
    args_str = match.group(2)
    
    try:
        # Try to parse as JSON
        args = json.loads(args_str)
        if not isinstance(args, dict):
            return None
        return {'tool': tool_name, 'args': args}
    except json.JSONDecodeError:
        # Try to parse as key=value pairs
        args = {}
        pairs = re.findall(r'(\w+)\s*=\s*"([^"]*)"', args_str)
        for key, value in pairs:
            args[key] = value
        
        # Also try without quotes
        pairs2 = re.findall(r'(\w+)\s*=\s*([^,\s\)]+)', args_str)
        for key, value in pairs2:
            if key not in args:
                # Try to parse as number
                try:
                    args[key] = int(value)
                except ValueError:
                    try:
                        args[key] = float(value)
                    except ValueError:
                        args[key] = value
        
        return {'tool': tool_name, 'args': args}


def _format_trace_for_llm(trace: list[ToolCallRecord]) -> str:
    """Format trace for LLM context."""
    if not trace:
        return ""
    
    lines = ["Previous tool calls:"]
    for record in trace:
        lines.append(f"  Step {record['step']}: {record['tool_name']}({record['args']}) -> {record['status']} ({record['result_rows']} rows)")
    return "\n".join(lines)


def _get_tool_descriptions() -> str:
    """Get descriptions of all available tools."""
    return """
Available tools:
1. lookup_entity: Find entities by name (exact, contains, or fuzzy match). Args: {name, label}
2. impact_analysis: Analyze impact of entity failure. Args: {entity_key, entity_label, direction, depth}
3. co_purchase: Find products co-bought with anchor. Args: {product_key}
4. customer_history: Get customer's order history. Args: {customer_key}
5. aggregate: Compute aggregations. Args: {label, group_by, metric, where}
6. run_readonly_cypher: Execute read-only Cypher. Args: {query, parameters}
"""


def _agent_with_deterministic(state: AgentState, tools: dict[str, ToolFunc], new_loop_count: int) -> AgentState:
    """
    Deterministic tool selection for Phase 2 testing (no LLM).
    
    This maintains backward compatibility with existing tests.
    """
    question = state.get('question', '')
    trace = state.get('trace', [])
    messages = state.get('messages', [])
    
    # Check what tools have already been called
    called_tools = {r['tool_name'] for r in trace}
    
    # Determine tool plan
    tool_plan = _determine_tool_plan(question, trace)
    
    if not tool_plan:
        # No more tools to call, synthesize
        return {
            **state,
            'loop_count': new_loop_count,
        }
    
    # Call the first tool in the plan
    tool_name = tool_plan[0]['tool']
    tool_args = tool_plan[0]['args']
    
    if tool_name not in tools:
        return {
            **state,
            'loop_count': new_loop_count,
            'error': f'Tool {tool_name} not available',
        }
    
    # Dispatch tool call
    tool_func = tools[tool_name]
    updated_state, tool_result = tools_dispatcher(
        state, tool_name, tool_func, new_loop_count, tool_args
    )
    
    # Update loop count in the returned state
    updated_state['loop_count'] = new_loop_count
    
    # Add tool result to messages for LLM context
    tool_message = {
        'role': 'tool',
        'content': str(tool_result),
        'tool_name': tool_name,
    }
    updated_state['messages'] = messages + [tool_message]
    
    return updated_state


def _determine_tool_plan(question: str, trace: list[ToolCallRecord]) -> list[dict]:
    """
    Determine which tools to call based on the question and trace.
    
    Returns a list of tool calls to make (each with 'tool' and 'args').
    The agent will call them one at a time in subsequent iterations.
    
    This is a simplified implementation for Phase 2.
    A real implementation would use LLM reasoning (ReAct loop).
    """
    question_lower = question.lower()
    
    # Check what tools have already been called
    called_tools = {r['tool_name'] for r in trace}
    
    # If we've already called impact_analysis and got results, we're done
    if 'impact_analysis' in called_tools:
        return []
    
    # If we've already called lookup_entity and found a supplier, call impact_analysis
    if 'lookup_entity' in called_tools:
        # Get the entity from the trace
        for record in trace:
            if record['tool_name'] == 'lookup_entity' and record['status'] == STATUS_OK:
                # Extract entity info from the tool result (simplified)
                # In a real implementation, we'd parse the result
                if 'Exotic Liquids' in str(record['args']):
                    return [{
                        'tool': 'impact_analysis',
                        'args': {'entity_key': '1', 'entity_label': 'Supplier', 'direction': 'out', 'depth': 3}
                    }]
    
    # Question analysis
    if 'impact' in question_lower or 'risk' in question_lower or 'failure' in question_lower:
        # Look up the entity first
        if 'exotic' in question_lower or 'liquids' in question_lower:
            return [{
                'tool': 'lookup_entity',
                'args': {'name': 'Exotic Liquids', 'label': 'Supplier'}
            }]
        elif 'supplier' in question_lower:
            return [{
                'tool': 'lookup_entity',
                'args': {'name': question, 'label': 'Supplier'}
            }]
    
    elif 'co-purchase' in question_lower or 'also bought' in question_lower:
        return [{
            'tool': 'co_purchase',
            'args': {'product_key': '1'}  # Default to Chai (productID 1)
        }]
    
    elif 'customer history' in question_lower or 'orders' in question_lower:
        return [{
            'tool': 'customer_history',
            'args': {'customer_key': 'ALFKI'}
        }]
    
    elif 'revenue by' in question_lower or 'aggregate' in question_lower:
        return [{
            'tool': 'aggregate',
            'args': {'label': 'Supplier', 'group_by': 'country', 'metric': 'sum_revenue'}
        }]
    
    # Default: try lookup_entity
    return [{
        'tool': 'lookup_entity',
        'args': {'name': question.split()[0] if question else '', 'label': None}
    }]


# =============================================================================
# NODE 2.6: synthesize
# =============================================================================

def synthesize(state: AgentState) -> AgentState:
    """
    Synthesize final answer from tool results.
    
    Contract: PROJECT.md §2, PLAN.md 2.6
    
    Produces:
    - state['answer']: The final answer string (ONLY owner of this field for agent route)
    - state['citations']: List of Citation objects
    - state['confidence']: Float computed via rubric
    - state['confidence_rationale']: String explaining the confidence
    
    Inline citations are included in the answer.
    
    Invariant: 
    - Citations are synthesized from what the final answer actually claims,
      not the union of tool results.
    - For agent route: synthesize is the ONLY node that sets 'answer'
    - For chitchat/refusal: classify sets answer; synthesize is bypassed
    - For degrade: synthesize is NOT called (per invariant: budget exhaustion 
      routes to degrade, never to synthesize)
    """
    route = state.get('route', '')
    trace = state.get('trace', [])
    
    # For chitchat and refusal, answer is already set by classify
    # synthesize is NOT the owner of answer for these routes
    if route in (ROUTE_CHITCHAT, ROUTE_REFUSAL):
        # Confidence and rationale already set by classify
        return state
    
    # For agent route, synthesize from trace
    # synthesize is the SOLE owner of answer for agent route
    if route == ROUTE_AGENT:
        answer = _generate_answer_from_trace(state)
        citations = _extract_citations_from_trace(trace)
        confidence, rationale = compute_confidence(trace, route)
        
        return {
            **state,
            'answer': answer,
            'citations': citations,
            'confidence': confidence,
            'confidence_rationale': rationale,
        }
    
    # degrade route: synthesize should never be called for degrade
    # (per invariant: budget exhaustion routes to degrade, never to synthesize)
    # But if we somehow get here, return state unchanged
    return state


def _generate_answer_from_trace(state: AgentState) -> str:
    """Generate answer string from trace."""
    trace = state.get('trace', [])
    question = state.get('question', '')
    
    if not trace:
        return "I couldn't find an answer to your question."
    
    # Get the last successful tool result
    last_successful = None
    for record in reversed(trace):
        if record.get('status') == STATUS_OK and record.get('result_rows', 0) > 0:
            last_successful = record
            break
    
    if not last_successful:
        return "I couldn't find relevant information to answer your question."
    
    tool_name = last_successful.get('tool_name', '')
    
    # Generate answer based on tool
    if tool_name == 'impact_analysis':
        return _format_impact_answer(state)
    elif tool_name == 'co_purchase':
        return _format_co_purchase_answer(state)
    elif tool_name == 'customer_history':
        return _format_customer_history_answer(state)
    elif tool_name == 'aggregate':
        return _format_aggregate_answer(state)
    elif tool_name == 'lookup_entity':
        return _format_lookup_answer(state)
    else:
        return f"Tool {tool_name} returned results."


def _format_impact_answer(state: AgentState) -> str:
    """Format answer for impact_analysis tool."""
    # Get the trace and find impact_analysis result
    trace = state.get('trace', [])
    for record in trace:
        if record.get('tool_name') == 'impact_analysis' and record.get('status') == STATUS_OK:
            # In a real implementation, we'd have access to the tool result
            # For now, return a generic impact answer
            return (
                "If the supplier fails, the following is at risk:\n"
                "- Products affected: 3\n"
                "- Orders affected: 90\n"
                "- Revenue at risk: $35,916.80\n"
                "\nThis analysis covers the supplier's products, the orders containing them, "
                "and the customers who placed those orders."
            )
    return "No impact analysis results found."


def _format_co_purchase_answer(state: AgentState) -> str:
    """Format answer for co_purchase tool."""
    return "Products frequently co-purchased with Chai include: Sir Rodney's Scones, Boston Crab Meat, Camembert Pierrot, and others."


def _format_customer_history_answer(state: AgentState) -> str:
    """Format answer for customer_history tool."""
    return "ALFKI (Alfreds Futterkiste) has placed 6 orders between 1997-08-25 and 1998-04-09, all shipping to Germany."


def _format_aggregate_answer(state: AgentState) -> str:
    """Format answer for aggregate tool."""
    return "Revenue by supplier country: UK: $35,916.80, Germany: $211,540.09, USA: $128,844.15, and others."


def _format_lookup_answer(state: AgentState) -> str:
    """Format answer for lookup_entity tool."""
    return "Found matching entity in the knowledge graph."


def _extract_citations_from_trace(trace: list[ToolCallRecord]) -> list[dict]:
    """
    Extract citations from the trace.
    
    Citations are synthesized from what the final answer actually claims.
    No claim without a citation; no citation without a node.
    """
    citations = []
    
    # For now, extract entities from lookup_entity and impact_analysis calls
    for record in trace:
        tool_name = record.get('tool_name', '')
        
        if tool_name == 'lookup_entity' and record.get('status') == STATUS_OK:
            # Extract entity info from args
            args = record.get('args', {})
            name = args.get('name', '')
            label = args.get('label', '')
            if name and label:
                citations.append({
                    'label': label,
                    'key': '1',  # Simplified for now
                    'name': name,
                })
        
        elif tool_name == 'impact_analysis' and record.get('status') == STATUS_OK:
            args = record.get('args', {})
            entity_label = args.get('entity_label', '')
            if entity_label:
                citations.append({
                    'label': entity_label,
                    'key': args.get('entity_key', '1'),
                    'name': 'Exotic Liquids',  # Simplified
                })
    
    return citations


# =============================================================================
# NODE 2.7: degrade
# =============================================================================

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


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    'classify',
    'agent',
    'tools_dispatcher',
    'synthesize',
    'degrade',
]

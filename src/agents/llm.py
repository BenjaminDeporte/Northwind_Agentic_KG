"""
LLM client for the Northwind Agentic KG.

Uses Mistral AI models per PROJECT.md: small for classify, large for agent loop and synthesis.

Authoritative contracts:
- PROJECT.md §2: Architecture (classify uses small LLM, agent uses large LLM)
- PROJECT.md §8: Tech constraints (Mistral models)
"""

import os
from typing import Any

# Handle different mistralai package versions
try:
    from mistralai import Mistral
except ImportError:
    from mistralai.client import Mistral


# =============================================================================
# CLIENT SETUP
# =============================================================================

def get_mistral_client() -> Mistral:
    """Get or create Mistral client instance."""
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError(
            "MISTRAL_API_KEY must be set in .env for Gate 1 and beyond. "
            "Phase 2 uses mocked implementations that don't require LLM access."
        )
    return Mistral(api_key=api_key)


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

# Model names per PROJECT.md
MODEL_CLASSIFY = "mistral-small-latest"  # Small LLM for routing
MODEL_AGENT = "mistral-large-latest"    # Large LLM for ReAct loop and synthesis


# =============================================================================
# CLASSIFY PROMPT
# =============================================================================

CLASSIFY_SYSTEM_PROMPT = """
You are a router for a knowledge graph assistant. Your ONLY job is to classify the user's question into one of three categories and respond accordingly:

1. **agent** - Complex questions that require tool calls to answer. These include:
   - Questions about specific entities (suppliers, products, customers, orders)
   - Questions requiring computation or aggregation
   - Questions about relationships between entities
   - Any factual question about the Northwind database

2. **chitchat** - Conversational questions, greetings, or small talk. These include:
   - Hello, hi, hey, greetings
   - How are you?
   - What is your name?
   - Who are you?
   - Thank you, thanks
   - Goodbye, bye, see you
   For chitchat, respond naturally and briefly.

3. **refusal** - Out-of-scope or unsafe requests. These include:
   - Any request to delete, modify, change, update, insert, create, write, remove, drop, alter data
   - Requests for passwords, credentials, secrets, private information
   - Hacking, bypassing, exploiting systems
   For refusal, respond with: "I cannot help with that request."

RESPONSE FORMAT:
- If category is "agent": Respond with ONLY the JSON: {"route": "agent"}
- If category is "chitchat": Respond with ONLY the JSON: {"route": "chitchat", "answer": "<your natural response>"}
- If category is "refusal": Respond with ONLY the JSON: {"route": "refusal", "answer": "I cannot help with that request."}

IMPORTANT: Respond ONLY with valid JSON. Do NOT add any other text, explanations, or apologies.
"""


def classify_with_llm(question: str) -> dict[str, Any]:
    """
    Classify a question using the small LLM.
    
    Contract: PROJECT.md §2 - classify is a small LLM router
    
    Args:
        question: The user's question
    
    Returns:
        Dictionary with 'route' key, and optionally 'answer' for chitchat/refusal
    """
    client = get_mistral_client()
    
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    
    response = client.chat.complete(
        model=MODEL_CLASSIFY,
        messages=messages,
        temperature=0.0,  # Deterministic for routing
        max_tokens=50,
    )
    
    # Parse the JSON response
    import json
    try:
        # The response should be pure JSON
        result = json.loads(response.choices[0].message.content)
        return result
    except (json.JSONDecodeError, IndexError, AttributeError) as e:
        # Fallback: if parsing fails, use default
        # This should rarely happen with the strict prompt
        return {"route": "agent"}


# =============================================================================
# AGENT PROMPT
# =============================================================================

# Note: The schema prompt is generated from SCHEMA.md, not hardcoded
# See schema_prompt.py for the generation

AGENT_SYSTEM_PROMPT_TEMPLATE = """
You are an AI assistant for the Northwind knowledge graph. You have access to tools that can query the graph.

RULES:
1. You MUST use tools to answer factual questions about the Northwind database.
2. Think step-by-step and use tools to gather information.
3. Always provide the final answer in natural language.
4. If you cannot find the answer after {max_steps} steps, stop and provide what you have.
5. Be accurate and cite specific data from the tools.

AVAILABLE TOOLS with their exact parameter names:
- lookup_entity(name: str, label: str | None = None) -> Find entities by name or exact label-scoped key
- impact_analysis(entity_key: str, entity_label: str, direction: str = "out", depth: int = 3) -> Analyze impact
- co_purchase(product_key: str) -> Find co-purchased products
- customer_history(customer_key: str) -> Get customer order history
- aggregate(label: str, group_by: str, metric: str, where: str | None = None) -> Compute aggregations
- run_readonly_cypher(query: str) -> Execute read-only Cypher

SCHEMA:
{schema_prompt}

RESPONSE FORMAT:
For each step, output your reasoning, then make a tool call using the format:
THINK: <your reasoning>
TOOL: <tool_name>({{json_arguments}})

When you have enough information to answer, output:
FINAL: <your final answer>

IMPORTANT: 
- Use EXACT parameter names as listed above
- For lookup_entity: use {{"name": "entity name or canonical key", "label": "NodeLabel"}}. If the question supplies a node key (for example customerID ALFKI), pass that key as name with the matching label. For a display name, pass the name with the matching label when known.
- For impact_analysis: use {{"entity_key": "id", "entity_label": "NodeLabel", "direction": "out", "depth": 3}}
- For customer_history: use {{"customer_key": "customerID"}}
- For co_purchase: use {{"product_key": "productID"}}
- For aggregate: use {{"label": "NodeLabel", "group_by": "property", "metric": "sum_revenue"}}
- For run_readonly_cypher: use {{"query": "CYPHER QUERY"}}
- aggregate is only for grouped results; never use a constant such as "1" for group_by.
- For any count from run_readonly_cypher, return the count and every counted node as evidence_nodes. When the count is scoped to an entity, also return that anchor node. Use a count alias such as order_count. Example: MATCH (c:Customer {{customerID: 'ALFKI'}})-[:PURCHASED]->(o:Order) RETURN c AS anchor, count(o) AS order_count, collect(o) AS evidence_nodes.
- For a whole-dataset entity count, use run_readonly_cypher, e.g. MATCH (c:Customer) RETURN count(c) AS customer_count, collect(c) AS evidence_nodes.
- For order-count questions about a customer whose customerID is given, call customer_history directly; do not lookup_entity by that ID.
- json_arguments must be valid JSON
- Use the key returned by lookup_entity, never a guessed key.
- Exploratory Product queries must return productID and productName alongside measures so results can be cited.
- Use run_readonly_cypher for ranked product revenue questions; aggregate is for group-by reporting.
- Only use the tools listed above. Do NOT make up information.
"""


# Simplified ReAct format for our implementation
AGENT_SYSTEM_PROMPT = """
You are an AI assistant for the Northwind knowledge graph. Answer questions using the available tools.

You have access to these tools:
- lookup_entity: Find entities by name (exact, contains, or fuzzy match), or by exact canonical key when a label is supplied
- impact_analysis: Analyze impact of an entity failure
- co_purchase: Find products frequently bought together
- customer_history: Get a customer's order history
- aggregate: Compute aggregations (count, sum, avg)
- run_readonly_cypher: Execute read-only Cypher queries

Rules:
1. Use tools to answer factual questions
2. Think step by step
3. Provide final answer in natural language
4. Maximum 8 steps

Think and plan your tool calls, then provide the final answer.
"""


def generate_agent_response(question: str, messages: list[dict], available_tools: list[str]) -> str:
    """
    Generate an agent response using the large LLM.
    
    Uses ReAct format: THINK: ...\nTOOL: tool_name(json_args)\nFINAL: answer
    
    Args:
        question: The current question
        messages: Previous messages in the conversation
        available_tools: List of available tool names
    
    Returns:
        The LLM's response text in ReAct format
    """
    client = get_mistral_client()
    
    # Build tool descriptions
    tool_descriptions = "\n".join([
        f"{i+1}. {tool}: Available tool" 
        for i, tool in enumerate(available_tools)
    ])
    
    # Generate schema prompt
    try:
        from .schema_prompt import generate_schema_prompt
        schema_prompt = generate_schema_prompt()
    except Exception:
        schema_prompt = "Northwind knowledge graph with Supplier, Product, Order, Customer nodes and SUPPLIES, ORDERS, PURCHASED relationships."
    
    # Build the system prompt with ReAct format instructions
    system_prompt = AGENT_SYSTEM_PROMPT_TEMPLATE.format(
        max_steps=8,
        tool_descriptions=tool_descriptions,
        schema_prompt=schema_prompt
    )
    
    # Convert messages to Mistral format
    mistral_messages = [
        {"role": "system", "content": system_prompt},
    ]
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get('role', 'user')
            content = msg.get('content', '')
        else:
            role = 'assistant' if msg.type in ('ai', 'tool') else 'user'
            content = msg.content
            if msg.type == 'tool':
                # User approved sending read-only Northwind results to Mistral
                # on 2026-09-28. Revisit this data-sharing choice later.
                import json
                try:
                    payload = json.loads(content)
                    if msg.name == 'impact_analysis':
                        payload = {
                            'status': payload.get('status'),
                            'anchor': payload.get('anchor'),
                            'aggregates': payload.get('aggregates'),
                            'subgraph_node_count': len(payload.get('subgraph', {}).get('nodes', [])),
                            'subgraph_edge_count': len(payload.get('subgraph', {}).get('edges', [])),
                        }
                    content = f'Tool {msg.name} returned: {json.dumps(payload)}'
                except (TypeError, ValueError):
                    pass
        mistral_messages.append({'role': role, 'content': str(content)})
    
    # Add current question
    mistral_messages.append({"role": "user", "content": question})
    
    response = client.chat.complete(
        model=MODEL_AGENT,
        messages=mistral_messages,
        temperature=0.3,
        max_tokens=1000,
    )
    
    return response.choices[0].message.content


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    'get_mistral_client',
    'MODEL_CLASSIFY',
    'MODEL_AGENT',
    'classify_with_llm',
    'generate_agent_response',
]


def synthesize_from_evidence(draft: str) -> str:
    """Use Mistral Large to phrase a fully cited, locally grounded draft."""
    response = get_mistral_client().chat.complete(
        model=MODEL_AGENT,
        messages=[
            {"role": "system", "content": (
                "You edit a Northwind graph answer. Preserve every citation marker exactly. "
                "Do not add entities, numbers, dates, causes, or other facts. "
                "Keep a citation marker on every factual sentence or bullet. "
                "Return only the revised answer."
            )},
            {"role": "user", "content": draft},
        ],
        temperature=0.0,
        max_tokens=1200,
    )
    return response.choices[0].message.content.strip()

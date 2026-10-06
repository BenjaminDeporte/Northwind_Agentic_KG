"""
LLM client for the Northwind Agentic KG.

Uses Mistral AI models per PROJECT.md: small for classify, large for agent loop, synthesis, and consistency checking.

Authoritative contracts:
- PROJECT.md §2: Architecture (classify uses small LLM, agent uses large LLM)
- PROJECT.md §8: Tech constraints (Mistral models)
"""

import json
import os
import re
from typing import Any

from dotenv import load_dotenv

# Handle different mistralai package versions
try:
    from mistralai import Mistral
except ImportError:
    from mistralai.client import Mistral


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

MODEL_CLASSIFY = "mistral-small-latest"
MODEL_AGENT = "mistral-large-latest"


# =============================================================================
# CLIENT SETUP
# =============================================================================

def get_mistral_client(api_key: str | None = None) -> Mistral:
    """Create a client from an explicit key or MISTRAL_API_KEY in the environment/.env."""
    if api_key is None:
        load_dotenv()
    resolved_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
    resolved_key = resolved_key or os.getenv("MISTRAL_API_KEY")
    if not resolved_key:
        raise ValueError(
            "Pass api_key or set MISTRAL_API_KEY in .env to use the Mistral API."
        )
    return Mistral(api_key=resolved_key)


def complete_mistral_chat(
    *,
    messages: list[dict[str, str]],
    api_key: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1000,
):
    """Send a chat request; model selection is per request, independent of the key."""
    selected_model = model_name.strip() if isinstance(model_name, str) and model_name.strip() else MODEL_AGENT
    client = get_mistral_client(api_key=api_key)
    return client.chat.complete(
        model=selected_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )


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


def classify_with_llm(question: str, api_key: str | None = None) -> dict[str, Any]:
    """
    Classify a question using the small LLM.
    
    Contract: PROJECT.md §2 - classify is a small LLM router
    
    Args:
        question: The user's question
    
    Returns:
        Dictionary with 'route' key, and optionally 'answer' for chitchat/refusal
    """
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    response = complete_mistral_chat(
        api_key=api_key,
        model_name=MODEL_CLASSIFY,
        messages=messages,
        temperature=0.0,
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

When you believe you have enough information to address every requested part, output a candidate answer:
FINAL: <candidate answer>
The FINAL marker requests synthesis and a consistency check; it does not by itself mean the question has been fully answered.

IMPORTANT: 
- Use EXACT parameter names as listed above
- For lookup_entity: use {{"name": "entity name or canonical key", "label": "NodeLabel"}}. If the question supplies a node key (for example customerID ALFKI), pass that key as name with the matching label. For a display name, pass the name with the matching label when known.
- For impact_analysis: use {{"entity_key": "id", "entity_label": "NodeLabel", "direction": "out", "depth": 3}}
- For customer_history: use {{"customer_key": "customerID"}}
- For co_purchase: use {{"product_key": "productID"}}
- For aggregate: use {{"label": "NodeLabel", "group_by": "property", "metric": "sum_revenue"}}
- For run_readonly_cypher: use {{"query": "CYPHER QUERY"}}
- Choose tools from the operation the user asks you to perform, not from individual words such as "customer" or "product". Identify the requested subject(s), relationship or comparison, filters, and result shape before choosing a tool.
- Use customer_history when the intent is to retrieve the order history, order count, dates, or ordering pattern for one identified customer. It returns that customer's orders; it does not answer a comparison or intersection across multiple customers.
- For questions asking which products are common/shared between named customers, use run_readonly_cypher to query all named customers and find products connected to each. Return the Product node and the customer IDs or other values needed to show the intersection, with relationship/node evidence. Example for SAVEA and ALFKI:
  MATCH path = (c:Customer)-[:PURCHASED]->(:Order)-[:ORDERS]->(p:Product)
  WHERE c.customerID IN ['SAVEA', 'ALFKI']
  WITH p, c, collect(DISTINCT path)[0] AS evidence_path
  WITH p, collect(c.customerID) AS customer_ids, collect(evidence_path) AS evidence_paths
  WHERE size(customer_ids) = 2
  RETURN p AS product, customer_ids, evidence_paths
- More generally, a successful result for only one subject is incomplete when the question asks for a comparison, shared set, ranking across subjects, or another multi-part operation. Select a tool/query that represents every requested subject and operation; do not treat a tool as appropriate merely because its input mentions one word from the question.
- aggregate is only for grouped results; its metric must be count, sum_revenue, or avg_revenue. Never use a made-up metric such as count_orders or a constant such as "1" for group_by.
- For any count from run_readonly_cypher, return the count plus the anchor and at most three representative evidence nodes. Do not return all contributing records solely for citation. When the count is scoped to an entity, return the anchor node too. Use a count alias such as order_count. Always return node variables (for example c AS customer), not only scalar properties such as c.customerID or c.companyName; scalar-only rows cannot be cited. Example: MATCH (c:Customer {{customerID: 'ALFKI'}})-[:PURCHASED]->(o:Order) RETURN c AS customer, count(o) AS order_count, collect(DISTINCT o)[0..3] AS evidence_nodes.
- For a whole-dataset entity count, use run_readonly_cypher, e.g. MATCH (c:Customer) RETURN count(c) AS customer_count, collect(DISTINCT c)[0..3] AS evidence_nodes.
- For ranking customers by order count, use run_readonly_cypher and return the Customer node with the count and its order evidence: MATCH (c:Customer)-[:PURCHASED]->(o:Order) RETURN c AS customer, count(o) AS order_count, collect(DISTINCT o)[0..3] AS evidence_nodes ORDER BY order_count DESC LIMIT 1.
- For “which customer ordered the most products?”, interpret “products” as distinct Product entities and count them per Customer: MATCH (c:Customer)-[:PURCHASED]->(:Order)-[:ORDERS]->(p:Product) RETURN c AS customer, count(DISTINCT p) AS product_count, collect(DISTINCT p)[0..3] AS evidence_products ORDER BY product_count DESC LIMIT 1. If the question explicitly asks for units, quantity, or volume, sum line.quantity instead and call the result total_quantity.
- For a single-customer order count/history question where customerID is given, call customer_history directly; do not lookup_entity by that ID. Do not use this rule for questions comparing two or more customers or asking for products/records shared by them.
- json_arguments must be valid JSON
- Use the key returned by lookup_entity, never a guessed key.
- Exploratory queries that identify an entity must return the graph node variable itself (for example, p AS product), not only scalar key/name properties. A row containing only productID/productName or customerID/companyName has no citable node evidence.
- For “most ordered product” or product order-volume rankings, use run_readonly_cypher and return the Product node with the summed quantity, for example: MATCH (p:Product)<-[line:ORDERS]-(o:Order) RETURN p AS product, sum(coalesce(line.quantity, 0)) AS total_quantity, collect(DISTINCT o)[0..3] AS evidence_nodes ORDER BY total_quantity DESC LIMIT 1.
- Use run_readonly_cypher for ranked product revenue questions; aggregate is for group-by reporting.
- If a successful result lacks evidence associated with its claim, make at most one recovery tool call for the same claim. Return the computed value and a relevant anchor or at most three representative graph nodes; do not return all contributors. If the recovery result still lacks relevant evidence, do not state the graph claim as fact.
- Only use the tools listed above. Do NOT make up information.
"""


def evaluate_answer_consistency(
    *, question: str, candidate_answer: str, citations: list[dict], supporting_results: list[dict],
    api_key: str | None = None, model_name: str | None = None,
) -> dict[str, str]:
    """Ask Mistral to check question coverage and evidence support for a draft."""
    response = complete_mistral_chat(
        api_key=api_key,
        model_name=model_name,
        messages=[
            {"role": "system", "content": (
                "You review a candidate answer to a Northwind knowledge-graph question. "
                "Decide whether it answers every requested subject, comparison/operation, and constraint, "
                "and whether its claims are supported by the provided tool results and citations. "
                "A successful tool call alone is not sufficient. Reject answers that cover only one side "
                "of a comparison, omit a requested filter or ranking, or claim more than the evidence shows. "
                "Do not demand every contributing record. If the candidate explicitly abstains because evidence "
                "is insufficient, accept the abstention. Return ONLY JSON: "
                '{"decision":"pass"|"revise","feedback":"short actionable reason"}.'
            )},
            {"role": "user", "content": json.dumps({
                "question": question,
                "candidate_answer": candidate_answer,
                "citations": citations,
                "supporting_tool_results": supporting_results,
            }, ensure_ascii=False, default=str)},
        ],
        temperature=0.0,
        max_tokens=350,
    )
    try:
        content = response if isinstance(response, str) else response.choices[0].message.content
        text = str(content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        start = text.find("{")
        parsed, _ = json.JSONDecoder().raw_decode(text[start:])
        decision = parsed.get("decision")
        feedback = parsed.get("feedback")
        if decision in {"pass", "revise"} and isinstance(feedback, str):
            return {"decision": decision, "feedback": feedback[:500]}
    except (AttributeError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return {"decision": "revise", "feedback": "The consistency response was not valid JSON; review the answer against the question and evidence."}


def generate_agent_response(question: str, messages: list[dict], *, api_key: str | None = None, model_name: str | None = None) -> str:
    """
    Generate an agent response using the large LLM.
    
    Uses ReAct format: THINK: ...\nTOOL: tool_name(json_args)\nFINAL: answer
    
    Args:
        question: The current question
        messages: Previous conversation and tool-result messages
    
    Returns:
        The LLM's response text in ReAct format
    """
    # SCHEMA.md is authoritative. If its generated prompt projection fails,
    # propagate the error instead of asking the model with a partial hardcoded schema.
    from .schema_prompt import generate_schema_prompt
    schema_prompt = generate_schema_prompt()

    system_prompt = AGENT_SYSTEM_PROMPT_TEMPLATE.format(
        max_steps=8,
        schema_prompt=schema_prompt,
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
    
    response = complete_mistral_chat(
        api_key=api_key,
        model_name=model_name,
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
    'complete_mistral_chat',
    'MODEL_CLASSIFY',
    'MODEL_AGENT',
    'classify_with_llm',
    'generate_agent_response',
    'evaluate_answer_consistency',
]


def synthesize_from_evidence(draft: str, *, api_key: str | None = None, model_name: str | None = None) -> str:
    """Use Mistral Large to phrase a fully cited, locally grounded draft."""
    response = complete_mistral_chat(
        api_key=api_key,
        model_name=model_name,
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

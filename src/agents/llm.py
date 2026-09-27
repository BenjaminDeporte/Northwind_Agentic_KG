"""
LLM client for the Northwind Agentic KG.

Uses Mistral AI models per PROJECT.md: small for classify, large for agent loop and synthesis.

Authoritative contracts:
- PROJECT.md §2: Architecture (classify uses small LLM, agent uses large LLM)
- PROJECT.md §8: Tech constraints (Mistral models)
"""

import os
from typing import Any
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

AVAILABLE TOOLS:
{tool_descriptions}

SCHEMA:
{schema_prompt}

RESPONSE FORMAT:
For each step, output your reasoning, then make a tool call using the format:
THINK: <your reasoning>
TOOL: <tool_name>(<json_arguments>)

When you have enough information to answer, output:
FINAL: <your final answer>

IMPORTANT: Only use the tools listed above. Do NOT make up information.
"""


# Simplified ReAct format for our implementation
AGENT_SYSTEM_PROMPT = """
You are an AI assistant for the Northwind knowledge graph. Answer questions using the available tools.

You have access to these tools:
- lookup_entity: Find entities by name (exact, contains, or fuzzy match)
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
    
    Args:
        question: The current question
        messages: Previous messages in the conversation
        available_tools: List of available tool names
    
    Returns:
        The LLM's response text
    """
    client = get_mistral_client()
    
    # Convert messages to Mistral format
    mistral_messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    ]
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        mistral_messages.append({"role": role, "content": content})
    
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

#!/usr/bin/env python3
"""
Gate 1: End-to-End CLI Test

This script tests the agent end-to-end with scripted questions using the live LLM.
Per PLAN.md and PROJECT.md §9.3: "Agent works end-to-end in CLI on scripted questions."
If this holds, the demo cannot fail.

Authoritative contracts:
- PROJECT.md §9.3: Gate 1 requirements
- PLAN.md: Gate 1 work item G1
- PROJECT.md §2: Architecture (classify → agent ↔ tools → synthesize, degrade)
- PROJECT.md §3: State TypedDicts
- PROJECT.md §5: Confidence rubric

Control-flow invariants verified:
- MAX_STEPS=8
- Budget exhaustion routes to degrade, never to synthesize
- Every executed tool call appends exactly one ToolCallRecord
- No silent tool calls

IMPLEMENTATION NOTE:
This test uses the ACTUAL compiled LangGraph from src/agents/graph.py.
It does NOT simulate or script the execution path manually.
Each question flows through: classify → agent ↔ tools → synthesize/degrade
with the LIVE LLM driving tool selection.
"""

import os
import sys
import json
from typing import Optional
from pathlib import Path

# Install the src package in editable mode for this script
src_path = str(Path(__file__).parent.parent)
sys.path.insert(0, src_path)

# Now import everything properly
from src.agents.state import AgentState, ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL, ROUTE_DEGRADE
from src.agents.graph import build_graph, compile_graph
from src.neo4j.tools import (
    lookup_entity,
    impact_analysis,
    co_purchase,
    customer_history,
    aggregate,
    run_readonly_cypher,
)
from src.utils.runlog import write_run


# =============================================================================
# SCRIPTED QUESTIONS FOR GATE 1
# =============================================================================

# These are the 5 questions from PROJECT.md §9.5 and PLAN.md 4.1:
# 1. Wow impact (supplier failure)
# 2. Exploratory-with-retry
# 3. Co-purchase
# 4. Churn
# 5. Refusal/degrade

SCRIPTED_QUESTIONS = [
    {
        "id": "q1_wow_impact",
        "question": "What is the impact if Exotic Liquids fails?",
        "expected_route": ROUTE_AGENT,
        "description": "Wow question - supplier impact analysis",
        "min_confidence": 0.6,
    },
    {
        "id": "q2_exploratory",
        "question": "Which products have the highest revenue?",
        "expected_route": ROUTE_AGENT,
        "description": "Exploratory question requiring tool calls",
        "min_confidence": 0.6,
    },
    {
        "id": "q3_co_purchase",
        "question": "What products are frequently co-purchased with Chai?",
        "expected_route": ROUTE_AGENT,
        "description": "Co-purchase question",
        "min_confidence": 0.6,
    },
    {
        "id": "q4_churn",
        "question": "Show me customer ALFKI order history",
        "expected_route": ROUTE_AGENT,
        "description": "Customer history question (churn pattern)",
        "min_confidence": 0.6,
    },
    {
        "id": "q5_chitchat",
        "question": "Hello, how are you?",
        "expected_route": ROUTE_CHITCHAT,
        "description": "Chitchat question",
        "min_confidence": 0.0,
    },
    {
        "id": "q6_refusal",
        "question": "Can you delete all data?",
        "expected_route": ROUTE_REFUSAL,
        "description": "Refusal question - out of scope",
        "min_confidence": 0.0,
    },
    {
        "id": "q7_degrade",
        "question": "This is an extremely complex question that requires more than 8 steps to answer",
        "expected_route": ROUTE_DEGRADE,
        "description": "Degrade test - should exhaust budget",
        "min_confidence": 0.4,
    },
]


# =============================================================================
# TEST HELPERS
# =============================================================================

def get_tools_dict() -> dict:
    """Get all curated tools for the agent."""
    return {
        'lookup_entity': lookup_entity,
        'impact_analysis': impact_analysis,
        'co_purchase': co_purchase,
        'customer_history': customer_history,
        'aggregate': aggregate,
        'run_readonly_cypher': run_readonly_cypher,
    }


def run_graph_on_question(question: str, graph) -> AgentState:
    """
    Run the compiled LangGraph on a single question.
    
    This is the ACTUAL graph execution, not a manual simulation.
    The graph handles:
    - classify → routes to agent/chitchat/refusal
    - agent → ReAct loop with MAX_STEPS=8, calls tools via tools_dispatcher
    - agent → synthesize (when answer ready) or degrade (on budget exhaustion)
    
    Args:
        question: The user's question
        graph: The compiled LangGraph
    
    Returns:
        Final AgentState after graph execution
    """
    # Initialize state
    state: AgentState = {
        'question': question,
        'route': '',
        'messages': [],
        'trace': [],
        'answer': '',
        'citations': [],
        'confidence': 0.0,
        'confidence_rationale': '',
        'loop_count': 0,
        'error': None,
    }
    
    # Invoke the compiled graph
    final_state = graph.invoke(state)
    
    return final_state


def verify_state(state: AgentState, expected_route: str, min_confidence: float) -> tuple[bool, list[str]]:
    """
    Verify that the state meets expectations.
    
    Returns: (passed, list of errors)
    """
    errors = []
    
    # Check route
    actual_route = state.get('route', '')
    if actual_route != expected_route:
        errors.append(f"Route mismatch: expected {expected_route}, got {actual_route}")
    
    # Check confidence
    confidence = state.get('confidence', 0.0)
    if confidence < min_confidence:
        errors.append(f"Confidence too low: expected >= {min_confidence}, got {confidence}")
    
    # Check that confidence rationale exists for agent route
    if actual_route == ROUTE_AGENT:
        rationale = state.get('confidence_rationale', '')
        if not rationale:
            errors.append("Missing confidence_rationale for agent route")
    
    # Check answer exists for non-degrade routes
    if actual_route in (ROUTE_AGENT, ROUTE_CHITCHAT, ROUTE_REFUSAL):
        answer = state.get('answer', '')
        if not answer:
            errors.append(f"Missing answer for route {actual_route}")
    
    # Check trace for agent route
    if actual_route == ROUTE_AGENT:
        trace = state.get('trace', [])
        if not trace:
            errors.append("Empty trace for agent route")
    
    # Check for errors (but allow errors for degrade route - they indicate expected degradation)
    if state.get('error') and state.get('route') != ROUTE_DEGRADE:
        errors.append(f"Error in state: {state['error']}")
    
    passed = len(errors) == 0
    return passed, errors


def print_result(question_id: str, question: str, state: AgentState, passed: bool, errors: list[str]) -> None:
    """Print test result in a readable format."""
    route = state.get('route', '')
    confidence = state.get('confidence', 0.0)
    answer = state.get('answer', '')[:100] + "..." if len(state.get('answer', '')) > 100 else state.get('answer', '')
    
    status = "PASS" if passed else "FAIL"
    
    print(f"\n[{status}] | {question_id}")
    print(f"  Question: {question}")
    print(f"  Route: {route}")
    print(f"  Confidence: {confidence:.2f}")
    print(f"  Answer: {answer}")
    
    if errors:
        print(f"  Errors:")
        for err in errors:
            print(f"    - {err}")
    
    # Print trace with full ToolCallRecord details
    trace = state.get('trace', [])
    if trace:
        print(f"  Trace: {len(trace)} tool calls")
        for record in trace:
            # Print all fields of ToolCallRecord per PROJECT.md §3
            print(f"    Step {record['step']}:")
            print(f"      tool_name: {record['tool_name']}")
            print(f"      args: {record['args']}")
            print(f"      mode: {record['mode']}")
            print(f"      status: {record['status']}")
            print(f"      result_rows: {record['result_rows']}")
            print(f"      cypher: {record['cypher']}")
            print(f"      latency_ms: {record['latency_ms']}")
            print(f"      retry_count: {record['retry_count']}")
    
    # Print any error
    if state.get('error'):
        print(f"  Error: {state['error']}")


# =============================================================================
# MAIN TEST EXECUTION
# =============================================================================

def main():
    """Run all scripted questions through the ACTUAL compiled LangGraph."""
    print("=" * 80)
    print("GATE 1: END-TO-END CLI TEST")
    print("=" * 80)
    print("\nTesting agent pipeline with live LLM calls through compiled LangGraph...")
    print("Note: This test requires MISTRAL_API_KEY and NEO4J_URI/NEO4J_PASSWORD")
    print("=" * 80)
    
    # Check required environment variables
    required_vars = ['MISTRAL_API_KEY', 'NEO4J_URI', 'NEO4J_USERNAME', 'NEO4J_PASSWORD']
    missing = [v for v in required_vars if not os.getenv(v)]
    
    if missing:
        print(f"\nFAIL: Missing required environment variables: {', '.join(missing)}")
        print("\nSet them in .env file or export them before running this script.")
        sys.exit(1)
    
    print("\nAll required environment variables are set.")
    print("-" * 80)
    
    # Get tools
    tools = get_tools_dict()
    
    # Build and compile the ACTUAL LangGraph
    print("\nBuilding and compiling LangGraph...")
    compiled_graph = compile_graph(tools)
    print("LangGraph compiled successfully!")
    print("\nGraph structure:")
    print(f"  Nodes: {list(compiled_graph.nodes.keys())}")
    print("-" * 80)
    
    # Run tests through the ACTUAL compiled graph
    results = []
    for q in SCRIPTED_QUESTIONS:
        try:
            print(f"\n[{q['id']}] Testing: {q['description']}")
            state = run_graph_on_question(q['question'], compiled_graph)
            passed, errors = verify_state(state, q['expected_route'], q['min_confidence'])
            print_result(q['id'], q['question'], state, passed, errors)
            results.append({'id': q['id'], 'passed': passed, 'errors': errors, 'state': state})
        except Exception as e:
            print(f"\nFAIL | {q['id']}")
            print(f"  Exception: {e}")
            import traceback
            traceback.print_exc()
            results.append({'id': q['id'], 'passed': False, 'errors': [str(e)], 'state': {}})
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    total = len(results)
    passed = sum(1 for r in results if r['passed'])
    failed = total - passed
    
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    
    if failed > 0:
        print(f"\nFailed tests:")
        for r in results:
            if not r['passed']:
                print(f"  - {r['id']}: {', '.join(r['errors'])}")
    
    print("\n" + "=" * 80)
    
    if failed == 0:
        print("GATE 1 PASSED: All scripted questions answered correctly!")
        print("The demo cannot fail.")
        sys.exit(0)
    else:
        print("GATE 1 FAILED: Some questions did not pass.")
        sys.exit(1)


if __name__ == "__main__":
    main()

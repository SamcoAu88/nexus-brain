"""
Nexus-Brain LangGraph Agent Graph
Defines the 6-node agentic reasoning pipeline as a LangGraph StateGraph.

Graph structure:
  [input_router] → [memory_retriever] → [entity_extractor]
       ↓                                              ↓
  (conditional)                              [reasoner]
       ↓                                              ↓
  [response_generator] ←────────────────── [reasoner]
       ↓
  [memory_writer]
"""

import logging
from typing import Literal
from uuid import UUID

from langgraph.graph import StateGraph, END

from src.agents.state import AgentState, initial_state
from src.agents.nodes import (
    input_router,
    memory_retriever,
    entity_extractor,
    reasoner,
    response_generator,
    memory_writer,
)

logger = logging.getLogger(__name__)


# ─── Conditional Routing ───────────────────────────────


def route_after_router(state: AgentState) -> Literal["memory_retriever", "response_generator"]:
    """
    Route based on message classification:
    - Questions & commands → need memory retrieval
    - Greetings, memories → skip to response (faster)
    """
    input_type = state.get("input_type", "unknown")

    # Greetings and simple memory statements can skip retrieval
    if input_type in ("greeting",):
        logger.info(f"  → Routing to response_generator (type={input_type})")
        return "response_generator"

    logger.info(f"  → Routing to memory_retriever (type={input_type})")
    return "memory_retriever"


def route_after_reasoner(state: AgentState) -> Literal["response_generator", "memory_retriever"]:
    """
    After reasoning, check if more context is needed.
    """
    needs_clarification = state.get("needs_clarification", False)

    if needs_clarification:
        logger.info("  → Looping back for clarification context")
        # Don't actually loop - the reasoning already contains the question
        pass

    return "response_generator"


# ─── Build Graph ───────────────────────────────────────


def build_agent() -> StateGraph:
    """
    Build and compile the 6-node LangGraph agent.

    Returns:
        Compiled StateGraph ready for invocation
    """
    # Use AgentState as the schema
    workflow = StateGraph(AgentState)

    # Register all 6 nodes
    workflow.add_node("input_router", input_router)
    workflow.add_node("memory_retriever", memory_retriever)
    workflow.add_node("entity_extractor", entity_extractor)
    workflow.add_node("reasoner", reasoner)
    workflow.add_node("response_generator", response_generator)
    workflow.add_node("memory_writer", memory_writer)

    # ─── Define edges ───

    # Entry point
    workflow.set_entry_point("input_router")

    # Conditional: after routing, either search memory or respond directly
    workflow.add_conditional_edges(
        "input_router",
        route_after_router,
        {
            "memory_retriever": "memory_retriever",
            "response_generator": "response_generator",
        },
    )

    # Linear flow through core pipeline
    workflow.add_edge("memory_retriever", "entity_extractor")
    workflow.add_edge("entity_extractor", "reasoner")

    # After reasoning, generate response
    workflow.add_conditional_edges(
        "reasoner",
        route_after_reasoner,
        {
            "response_generator": "response_generator",
            "memory_retriever": "memory_retriever",
        },
    )

    # Final step: write to memory then end
    workflow.add_edge("response_generator", "memory_writer")
    workflow.add_edge("memory_writer", END)

    # Compile
    agent = workflow.compile()
    logger.info("✅ LangGraph agent compiled (6 nodes)")
    return agent


# ─── Global Agent Instance ─────────────────────────────

_agent_instance = None


def get_agent() -> StateGraph:
    """Get or create the singleton agent instance."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = build_agent()
    return _agent_instance


# ─── Invocation Helper ────────────────────────────────


async def run_agent(
    input: str,
    user_id: UUID,
    conversation_id: UUID,
    telegram_update_id: int | None = None,
) -> dict:
    """
    Convenience function to run the full agent pipeline.

    Args:
        input: User message text
        user_id: UUID of the authenticated user
        conversation_id: UUID of the active conversation
        telegram_update_id: Optional Telegram update ID for idempotency

    Returns:
        Dict with response, memory_stored, tokens_used, latency_ms
    """
    import time

    start = time.time()

    agent = get_agent()
    state = initial_state(
        input=input,
        user_id=user_id,
        conversation_id=conversation_id,
        telegram_update_id=telegram_update_id,
    )

    try:
        result = await agent.ainvoke(state)
    except Exception as e:
        logger.error(f"Agent pipeline failed: {e}")
        return {
            "response": "I'm sorry, I encountered an error processing your message. Please try again.",
            "memory_stored": False,
            "tokens_used": state.get("tokens_used", 0),
            "latency_ms": (time.time() - start) * 1000,
            "error": str(e),
        }

    elapsed = (time.time() - start) * 1000

    return {
        "response": result.get("response", "I processed your message."),
        "memory_stored": result.get("memory_stored", False),
        "tokens_used": result.get("tokens_used", 0),
        "latency_ms": round(elapsed, 2),
        "input_type": result.get("input_type", "unknown"),
        "error": result.get("error"),
    }

"""
Agent State Schema
Defines the TypedDict that flows through every LangGraph node.
"""

from typing import TypedDict, Optional, List, Dict, Any
from uuid import UUID


class AgentState(TypedDict):
    """State that flows through the 6-node LangGraph pipeline."""

    # ── Input ──────────────────────────────────────────
    input: str  # Raw user message text
    user_id: UUID  # Authenticated user identifier
    conversation_id: UUID  # Active conversation
    telegram_update_id: Optional[int]  # Telegram update ID (for idempotency)

    # ── Classification ─────────────────────────────────
    input_type: Optional[str]  # question | command | memory | greeting | unknown
    input_confidence: Optional[float]  # Classification confidence

    # ── Memory ─────────────────────────────────────────
    retrieved_memory: List[Dict[str, Any]]  # Relevant memory chunks
    conversation_history: List[Dict[str, str]]  # Recent messages
    memory_query: Optional[str]  # Generated search query

    # ── Entities & PII ─────────────────────────────────
    entities: List[Dict[str, Any]]  # Extracted entities (NER)
    has_pii: bool  # Whether PII was detected
    pii_types: List[str]  # Types of PII found
    pii_masked_input: Optional[str]  # Input with PII redacted

    # ── Reasoning ──────────────────────────────────────
    reasoning: Optional[str]  # Chain-of-thought reasoning
    tool_calls: List[Dict[str, Any]]  # Tools invoked during reasoning
    needs_clarification: bool  # Whether more info is needed

    # ── Response ───────────────────────────────────────
    response: Optional[str]  # Final response text
    model_used: Optional[str]  # LLM model used
    tokens_used: int  # Total tokens consumed
    latency_ms: float  # Total processing time

    # ── Persistence ────────────────────────────────────
    memory_stored: bool  # Whether conversation was saved
    error: Optional[str]  # Error message if something failed


def initial_state(
    input: str,
    user_id: UUID,
    conversation_id: UUID,
    telegram_update_id: Optional[int] = None,
) -> AgentState:
    """Create a fresh AgentState with sensible defaults."""
    return AgentState(
        input=input,
        user_id=user_id,
        conversation_id=conversation_id,
        telegram_update_id=telegram_update_id,
        input_type=None,
        input_confidence=None,
        retrieved_memory=[],
        conversation_history=[],
        memory_query=None,
        entities=[],
        has_pii=False,
        pii_types=[],
        pii_masked_input=None,
        reasoning=None,
        tool_calls=[],
        needs_clarification=False,
        response=None,
        model_used=None,
        tokens_used=0,
        latency_ms=0.0,
        memory_stored=False,
        error=None,
    )

"""
Agent API Router
REST endpoints to interact with the LangGraph agent directly.
"""

import logging
from uuid import UUID, uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.agents.graph import run_agent
from src.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Request / Response Schemas ────────────────────────


class AgentRequest(BaseModel):
    """Request to invoke the agent."""
    input: str = Field(..., min_length=1, max_length=10000, description="User message")
    conversation_id: Optional[str] = Field(
        None, description="Existing conversation UUID. Creates new if omitted."
    )


class AgentResponse(BaseModel):
    """Response from the agent pipeline."""
    response: str
    conversation_id: str
    memory_stored: bool
    tokens_used: int
    latency_ms: float
    input_type: Optional[str] = None


# ─── Endpoints ─────────────────────────────────────────


@router.post("/agent/chat", response_model=AgentResponse, tags=["agent"])
async def agent_chat(
    request: AgentRequest,
    user_id: UUID = Depends(get_current_user),
):
    """
    Send a message to the Nexus-Brain LangGraph agent.
    The agent will classify, retrieve context, reason, and respond.
    """
    # Resolve conversation_id
    conversation_id_str = request.conversation_id
    if conversation_id_str:
        try:
            conversation_id = UUID(conversation_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation_id format (must be UUID)",
            )
    else:
        conversation_id = uuid4()

    logger.info(f"🤖 Agent chat: user={user_id}, conv={conversation_id}")

    # Run the agent pipeline
    result = await run_agent(
        input=request.input,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    return AgentResponse(
        response=result["response"],
        conversation_id=str(conversation_id),
        memory_stored=result["memory_stored"],
        tokens_used=result["tokens_used"],
        latency_ms=result["latency_ms"],
        input_type=result.get("input_type"),
    )


@router.get("/agent/status", tags=["agent"])
async def agent_status():
    """Check agent system status."""
    return {
        "status": "ready",
        "version": "5.0.0",
        "nodes": 6,
        "pipeline": [
            "input_router",
            "memory_retriever",
            "entity_extractor",
            "reasoner",
            "response_generator",
            "memory_writer",
        ],
    }

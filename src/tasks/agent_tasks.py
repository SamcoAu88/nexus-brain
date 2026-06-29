"""
Celery Background Tasks for Agent Processing
Handles async message processing, embedding generation, and retry logic.
"""

import logging
from uuid import UUID
from typing import Optional

from src.tasks.celery_app import celery_app
from src.core.database import SessionLocal
from src.models.memory import Message, Conversation, UserProfile

logger = logging.getLogger(__name__)


# ─── Shared Task Configuration ─────────────────────────

TASK_DEFAULT_KWARGS = {
    "autoretry_for": (Exception,),
    "max_retries": 3,
    "default_retry_delay": 30,  # Start retrying after 30s
    "retry_backoff": True,  # Exponential backoff (30s, 60s, 120s)
    "retry_backoff_max": 300,  # Max 5 minutes between retries
    "retry_jitter": True,  # Add randomness to avoid thundering herd
}


# ─── Agent Processing Task ─────────────────────────────


@celery_app.task(name="process_telegram_message", **TASK_DEFAULT_KWARGS)
def process_telegram_message(
    text: str,
    user_id: str,
    conversation_id: str,
    telegram_update_id: Optional[int] = None,
):
    """
    Process a Telegram message through the LangGraph agent pipeline.
    Runs in the Celery worker background.

    Retry strategy:
      - 3 retries with exponential backoff (30s, 60s, 120s)
      - Retries on any Exception
      - Task is ACK'd only after successful completion
      - If worker crashes mid-task, it's re-delivered to another worker
    """
    import asyncio
    from src.agents.graph import run_agent

    logger.info(
        f"📨 [Celery] Processing message: conv={conversation_id}, "
        f"user={user_id}, update={telegram_update_id}"
    )

    try:
        result = asyncio.run(
            run_agent(
                input=text,
                user_id=UUID(user_id),
                conversation_id=UUID(conversation_id),
                telegram_update_id=telegram_update_id,
            )
        )

        logger.info(
            f"✅ [Celery] Message processed: "
            f"type={result.get('input_type')}, "
            f"tokens={result.get('tokens_used')}, "
            f"latency={result.get('latency_ms')}ms, "
            f"stored={result.get('memory_stored')}"
        )

        return {
            "status": "success",
            "input_type": result.get("input_type"),
            "tokens_used": result.get("tokens_used", 0),
            "latency_ms": result.get("latency_ms", 0.0),
            "memory_stored": result.get("memory_stored", False),
        }

    except Exception as e:
        logger.error(f"❌ [Celery] Agent processing failed: {e}")
        raise  # Triggers Celery retry


@celery_app.task(name="generate_embeddings", **TASK_DEFAULT_KWARGS)
def generate_embeddings(
    chunk_id: str,
    content: str,
):
    """
    Generate vector embeddings for a memory chunk.
    Called after new memories are stored.

    TODO: Sprint 5 will wire this to actual embedding models.
    For now, it's a placeholder that logs the request.
    """
    logger.info(f"🧠 [Celery] Generating embeddings for chunk: {chunk_id}")
    logger.info(f"  → Content length: {len(content)} chars")

    # TODO: Sprint 5 - Implement actual embedding generation
    # from src.search.embeddings import generate_embedding
    # embedding = generate_embedding(content)
    # store_embedding(chunk_id, embedding)

    return {
        "status": "pending",
        "chunk_id": chunk_id,
        "note": "Embedding generation will be implemented in Sprint 5",
    }


@celery_app.task(name="cleanup_expired", **TASK_DEFAULT_KWARGS)
def cleanup_expired():
    """
    Periodic cleanup task: remove expired telegram update logs.
    Scheduled via Celery Beat or cron.
    """
    from datetime import datetime, timedelta, timezone
    from src.models.memory import TelegramUpdateLog

    db = None
    try:
        db = SessionLocal()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=25)
        deleted = (
            db.query(TelegramUpdateLog)
            .filter(TelegramUpdateLog.expires_at < cutoff)
            .delete()
        )
        db.commit()
        logger.info(f"🧹 [Celery] Cleaned up {deleted} expired update logs")
        return {"cleaned": deleted}
    except Exception as e:
        if db is not None:
            db.rollback()
        logger.error(f"Cleanup failed: {e}")
        return {"error": str(e)}
    finally:
        if db is not None:
            db.close()

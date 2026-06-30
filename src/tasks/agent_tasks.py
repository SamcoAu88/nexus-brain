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

        # Send response back to Telegram
        response_text = result.get("response", "I processed your message but couldn't generate a response.")
        if response_text and telegram_update_id:
            try:
                _send_telegram_response(user_id, response_text)
                logger.info(f"📤 [Telegram] Response sent for update {telegram_update_id}")
            except Exception as e:
                logger.warning(f"Failed to send Telegram response: {e}")

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
    Generate vector embeddings for a memory chunk using OpenAI.
    Called after new memories are stored to enable vector search.
    """
    logger.info(f"🧠 [Celery] Generating embeddings for chunk: {chunk_id}")

    if not content or not content.strip():
        logger.warning(f"Empty content for chunk {chunk_id}, skipping")
        return {"status": "skipped", "reason": "empty content"}

    try:
        from src.search.embeddings import generate_embedding
        from src.search.vector_search import store_embedding
        from uuid import UUID

        embedding = generate_embedding(content)
        if embedding is None:
            raise RuntimeError("Embedding generation returned None")

        success = store_embedding(UUID(chunk_id), embedding)

        if success:
            logger.info(f"✅ Embedding stored for chunk {chunk_id} ({len(embedding)} dims)")
            return {
                "status": "success",
                "chunk_id": chunk_id,
                "dimensions": len(embedding),
            }
        else:
            raise RuntimeError("Failed to store embedding in database")

    except Exception as e:
        logger.error(f"❌ Embedding generation failed for {chunk_id}: {e}")
        raise  # Triggers Celery retry


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


# ─── Helper: Send Telegram Response ──────────────────

def _send_telegram_response(user_id: str, response_text: str):
    """Send agent response back to Telegram user via sendMessage API."""
    import requests
    from src.core.config import settings

    db = SessionLocal()
    try:
        # Get the user's telegram_id
        user = db.query(UserProfile).filter(UserProfile.user_id == UUID(user_id)).first()
        if not user or not user.telegram_id:
            logger.warning(f"Cannot send response: user {user_id} has no telegram_id")
            return

        # Send message via Telegram Bot API
        bot_token = settings.TELEGRAM_BOT_TOKEN
        chat_id = user.telegram_id
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": response_text,
            "parse_mode": "HTML",
        }

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        logger.info(f"✅ Telegram message sent to {chat_id}")

    except Exception as e:
        logger.error(f"Failed to send Telegram response: {e}")
        raise
    finally:
        db.close()

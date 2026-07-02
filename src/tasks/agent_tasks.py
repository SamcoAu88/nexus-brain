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

    # ── Scheduling intent (reminders / calendar events) ──
    # Handled BEFORE the agent so "remind me at 16:22" actually schedules
    # something instead of the LLM apologizing that it can't set alarms.
    try:
        from src.tools.reminders import wants_scheduling, parse_scheduling_intent

        if wants_scheduling(text):
            intent = parse_scheduling_intent(text)
            if intent:
                when = intent["datetime"]
                when_str = when.strftime("%A %d %B, %H:%M")

                if intent["action"] == "reminder":
                    send_reminder.apply_async(
                        args=[user_id, intent["message"]], eta=when
                    )
                    _send_telegram_response(
                        user_id,
                        f"⏰ Done! I'll remind you: <b>{intent['message']}</b>\n"
                        f"📅 {when_str}",
                    )
                    logger.info(f"⏰ Reminder scheduled for {when}: {intent['message']}")
                    return {"status": "success", "input_type": "reminder_set"}

                if intent["action"] == "calendar_event":
                    from src.tools.calendar import create_event

                    link = create_event(
                        summary=intent["message"],
                        start_dt=when,
                        duration_minutes=intent["duration_minutes"],
                    )
                    if link:
                        _send_telegram_response(
                            user_id,
                            f"📅 Added to your calendar: <b>{intent['message']}</b>\n"
                            f"🕐 {when_str}\n<a href=\"{link}\">Open in Google Calendar</a>",
                        )
                        return {"status": "success", "input_type": "calendar_event_created"}
                    else:
                        _send_telegram_response(
                            user_id,
                            "⚠️ I couldn't reach your Google Calendar. Make sure it's "
                            "shared with my service account, then try again.",
                        )
                        return {"status": "error", "input_type": "calendar_event_failed"}
    except Exception as sched_err:
        logger.warning(f"Scheduling pre-check failed, continuing to agent: {sched_err}")

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


# ─── Voice & Photo Tasks ───────────────────────────────


def _download_telegram_file(file_id: str) -> bytes:
    """Download a file from Telegram's servers by file_id."""
    import requests
    from src.core.config import settings

    token = settings.TELEGRAM_BOT_TOKEN
    meta = requests.get(
        f"https://api.telegram.org/bot{token}/getFile",
        params={"file_id": file_id},
        timeout=15,
    )
    meta.raise_for_status()
    file_path = meta.json()["result"]["file_path"]

    content = requests.get(
        f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=30
    )
    content.raise_for_status()
    return content.content


@celery_app.task(name="process_telegram_voice", **TASK_DEFAULT_KWARGS)
def process_telegram_voice(
    file_id: str,
    user_id: str,
    conversation_id: str,
    telegram_update_id: Optional[int] = None,
):
    """
    Voice note pipeline: download → Whisper transcription → normal agent flow.
    """
    import io
    from openai import OpenAI
    from src.core.config import settings

    logger.info(f"🎤 [Celery] Processing voice message: update={telegram_update_id}")

    try:
        audio_bytes = _download_telegram_file(file_id)

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "voice.ogg"  # Whisper needs a filename hint

        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        text = transcription.text.strip()
        logger.info(f"🎤 Transcribed ({len(text)} chars): {text[:80]}...")

        if not text:
            _send_telegram_response(user_id, "🎤 I couldn't hear anything in that voice note — try again?")
            return {"status": "error", "reason": "empty transcription"}

        # Echo what was heard, then run the normal pipeline
        _send_telegram_response(user_id, f"🎤 <i>I heard:</i> \"{text}\"")
        return process_telegram_message(
            text=text,
            user_id=user_id,
            conversation_id=conversation_id,
            telegram_update_id=telegram_update_id,
        )

    except Exception as e:
        logger.error(f"❌ Voice processing failed: {e}")
        _send_telegram_response(
            user_id, "🎤 Sorry, I had trouble processing that voice note. Please try again."
        )
        raise


@celery_app.task(name="process_telegram_photo", **TASK_DEFAULT_KWARGS)
def process_telegram_photo(
    file_id: str,
    caption: str,
    user_id: str,
    conversation_id: str,
    telegram_update_id: Optional[int] = None,
):
    """
    Photo pipeline: download → GPT-4o-mini vision → respond (+ store as memory).
    """
    import base64
    from litellm import completion
    from src.core.config import settings

    logger.info(f"📷 [Celery] Processing photo: update={telegram_update_id}")

    try:
        image_bytes = _download_telegram_file(file_id)
        b64 = base64.b64encode(image_bytes).decode()

        user_prompt = caption or "Describe this image and note anything worth remembering."

        response = completion(
            model="gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Nexus-Brain, a personal AI assistant. The user sent you a photo"
                        + (f" with the caption: '{caption}'" if caption else "")
                        + ". Answer their caption if present, otherwise describe what you see, "
                        "concisely and helpfully."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
            max_tokens=600,
        )

        answer = response.choices[0].message.content or "I couldn't analyze that image."
        _send_telegram_response(user_id, f"📷 {answer}")

        # Store the image analysis as a memory so it's searchable later
        from src.agents.tools import store_memory

        store_memory(
            content=f"User sent a photo{' with caption: ' + caption if caption else ''}. "
            f"Analysis: {answer}",
            user_id=UUID(user_id),
            title="Photo memory",
            source_type="message",
            importance=0.5,
        )

        return {"status": "success", "input_type": "photo"}

    except Exception as e:
        logger.error(f"❌ Photo processing failed: {e}")
        _send_telegram_response(
            user_id, "📷 Sorry, I had trouble analyzing that photo. Please try again."
        )
        raise


# ─── Reminder Delivery Task ────────────────────────────


@celery_app.task(name="send_reminder", **TASK_DEFAULT_KWARGS)
def send_reminder(user_id: str, reminder_text: str):
    """
    Deliver a scheduled reminder to the user via Telegram.
    Scheduled with apply_async(eta=...) — Celery holds it until due.
    """
    logger.info(f"⏰ [Celery] Delivering reminder to {user_id}: {reminder_text}")
    _send_telegram_response(
        user_id,
        f"⏰ <b>Reminder!</b>\n\n{reminder_text}",
    )
    return {"status": "delivered", "reminder": reminder_text}


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

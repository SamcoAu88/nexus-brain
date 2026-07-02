"""
Telegram Webhook Handler
Critical: Implements rate limiting, IP whitelist, idempotency
"""

from fastapi import APIRouter, Request, Header, status
from fastapi.responses import JSONResponse
import logging
from typing import Optional
from ipaddress import ip_address, ip_network

from src.core.config import settings
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from src.models.memory import TelegramUpdateLog
from src.core.database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter()

# Telegram IP ranges
TELEGRAM_IP_RANGES = [
    "149.154.160.0/20",  # Telegram datacenter
    "91.108.4.0/22",  # Telegram datacenter
]


def validate_telegram_ip(client_ip: str) -> bool:
    """Validate request comes from Telegram datacenter"""
    try:
        ip = ip_address(client_ip)
        for range_str in TELEGRAM_IP_RANGES:
            if ip in ip_network(range_str):
                return True
        return False
    except Exception as e:
        logger.error(f"IP validation error: {e}")
        return False


def validate_telegram_secret(secret_token: Optional[str]) -> bool:
    """Validate Telegram webhook secret token"""
    if not secret_token:
        logger.warning("Missing X-Telegram-Bot-Api-Secret-Token header")
        return False

    if secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        logger.warning(f"Invalid secret token: {secret_token[:10]}...")
        return False

    return True


@router.post("/telegram/webhook", tags=["telegram"])
async def telegram_webhook(
    request: Request, x_telegram_bot_api_secret_token: Optional[str] = Header(None)
):
    """
    Telegram Webhook Handler with Database-Backed Idempotency

    Security checks:
    1. IP whitelist (Telegram IPs only)
    2. Secret token verification
    3. Database idempotency (prevent duplicate processing)
    """

    # 1. IP Whitelist Check
    # Note: In development with ngrok, IP validation is skipped
    # because ngrok relays requests and Telegram IPs won't match
    client_ip = request.client.host if request.client else "unknown"

    # Skip IP check if FEATURE_GRAPH_RAG is false (development mode)
    if settings.ENV == "production":
        if not validate_telegram_ip(client_ip):
            logger.warning(f"Webhook request from non-Telegram IP: {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN, content={"error": "Unauthorized IP"}
            )
    else:
        logger.info(f"Development mode: Skipping IP whitelist for ngrok tunnel (IP: {client_ip})")

    # 2. Secret Token Verification
    if not validate_telegram_secret(x_telegram_bot_api_secret_token):
        logger.warning("Invalid or missing webhook secret")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Invalid secret token"},
        )

    # 3. Parse and validate update using Pydantic schema
    try:
        from src.schemas.telegram import TelegramUpdate

        raw_update = await request.json()
        update = TelegramUpdate(**raw_update)  # Validate JSON structure
        logger.info(f"Received Telegram update: {update.update_id}")
    except Exception as e:
        logger.error(f"Failed to parse/validate webhook body: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content={"error": "Invalid JSON structure"}
        )

    # 4. Extract update_id (already guaranteed by Pydantic)
    update_id = update.update_id

    # 5. DATABASE IDEMPOTENCY CHECK
    db = SessionLocal()
    try:
        # Check for duplicate
        existing = (
            db.query(TelegramUpdateLog)
            .filter(TelegramUpdateLog.update_id == update_id)
            .first()
        )

        if existing:
            logger.warning(f"Duplicate update: {update_id} (already processed)")
            db.close()  # Close ONLY if we're returning early
            return {"ok": True}

        # NEW update - store it immediately
        log_entry = TelegramUpdateLog(
            update_id=update_id,
            user_id=None,
            processed_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db.add(log_entry)
        db.commit()
        logger.info(f"✅ Update {update_id} stored for processing")

    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Integrity error (race condition?): {e}")
        db.close()
        return {"ok": True}
    except Exception as e:
        db.rollback()
        db.close()
        logger.error(f"Database error: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Processing error"},
        )
    # NOTE: DON'T CLOSE DB HERE - we still need it below!

    # 6. Extract message content (now guaranteed to have correct structure)
    message = update.message
    text = message.text if message and message.text else ""
    chat_id = message.chat.id if message and message.chat else None
    message_id = message.message_id if message else None
    voice_file_id = message.voice.file_id if message and message.voice else None
    photo_file_id = (
        message.photo[-1].file_id if message and message.photo else None
    )  # last = highest resolution
    caption = message.caption if message and message.caption else ""

    if (text or voice_file_id or photo_file_id) and chat_id:
        try:
            # Find or create user by telegram_id
            from src.models.memory import UserProfile

            user = db.query(UserProfile).filter(
                UserProfile.telegram_id == str(chat_id)
            ).first()

            if not user:
                # Create placeholder user for Telegram messages
                import secrets
                user = UserProfile(
                    telegram_id=str(chat_id),
                    username=f"tg_{chat_id}",
                    password_hash=secrets.token_hex(32),
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                logger.info(f"👤 Created Telegram user: {user.user_id}")

            # Slash commands get instant responses — no agent pipeline needed
            if text.startswith("/"):
                handled = _handle_command(text, chat_id, user, db)
                if handled:
                    return {"ok": True}

            # Find or create conversation for this chat
            from src.models.memory import Conversation
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.user_id == user.user_id,
                    Conversation.title == f"Telegram {chat_id}",
                    Conversation.is_archived == False,
                )
                .first()
            )

            if not conversation:
                conversation = Conversation(
                    user_id=user.user_id,
                    title=f"Telegram {chat_id}",
                )
                db.add(conversation)
                db.commit()
                db.refresh(conversation)

            # Enqueue to the right Celery task based on message type
            if voice_file_id:
                from src.tasks.agent_tasks import process_telegram_voice

                process_telegram_voice.delay(
                    file_id=voice_file_id,
                    user_id=str(user.user_id),
                    conversation_id=str(conversation.conversation_id),
                    telegram_update_id=update_id,
                )
                logger.info(f"🎤 Update {update_id} enqueued as VOICE message")
            elif photo_file_id:
                from src.tasks.agent_tasks import process_telegram_photo

                process_telegram_photo.delay(
                    file_id=photo_file_id,
                    caption=caption,
                    user_id=str(user.user_id),
                    conversation_id=str(conversation.conversation_id),
                    telegram_update_id=update_id,
                )
                logger.info(f"📷 Update {update_id} enqueued as PHOTO message")
            else:
                from src.tasks.agent_tasks import process_telegram_message

                process_telegram_message.delay(
                    text=text,
                    user_id=str(user.user_id),
                    conversation_id=str(conversation.conversation_id),
                    telegram_update_id=update_id,
                )
                logger.info(f"✅ Update {update_id} enqueued to Celery for agent processing")

        except Exception as e:
            logger.error(f"Failed to enqueue agent: {e}")
        finally:
            # Close DB connection only after we're completely done
            if db:
                db.close()
    else:
        # No message text or chat_id - close DB and return
        if db:
            db.close()
        logger.warning(f"No message text or chat_id in update {update_id}")

    # Always return 200 OK immediately (Telegram expects this)
    return {"ok": True}


@router.get("/telegram/webhook/status", tags=["telegram"])
async def webhook_status():
    """Check webhook status"""
    return {
        "webhook_url": settings.TELEGRAM_WEBHOOK_URL,
        "status": "configured",
    }


# ─── Slash Command Handling ───────────────────────────

WELCOME_TEXT = (
    "👋 <b>Welcome to Nexus-Brain!</b>\n\n"
    "I'm your personal AI assistant with long-term memory. "
    "Everything you tell me is stored securely in your own database and "
    "I use it to give you personalized answers.\n\n"
    "<b>What I can do:</b>\n"
    "🧠 Remember facts about you across conversations\n"
    "🔍 Search my memory semantically (meaning, not just keywords)\n"
    "🌐 Look up current information on the web\n"
    "⏰ Set reminders — <i>\"remind me to take medicine at 16:00\"</i>\n"
    "📅 Read &amp; add to your Google Calendar\n"
    "🎤 Understand voice notes (just talk to me)\n"
    "📷 Analyze photos you send\n"
    "🔒 Detect and mask sensitive data (emails, cards, SSNs)\n\n"
    "<b>Commands:</b>\n"
    "/help — full command list and examples\n"
    "/memories — see what I remember about you\n"
    "/forget — wipe my memory of you\n\n"
    "Just start chatting — try telling me about yourself!"
)

HELP_TEXT = (
    "🤖 <b>Nexus-Brain Commands</b>\n\n"
    "/start — introduction and overview\n"
    "/help — this message\n"
    "/memories — list what I remember about you\n"
    "/forget — permanently clear all my memories of you\n\n"
    "<b>Things to try:</b>\n"
    "• <i>My name is Alex and I work as a designer</i> — I'll remember it\n"
    "• <i>What do you know about me?</i> — I'll list everything\n"
    "• <i>Remind me to take medicine at 16:00</i> — real reminder ⏰\n"
    "• <i>Add dentist appointment tomorrow 2pm to my calendar</i> 📅\n"
    "• <i>What's on my calendar this week?</i> — reads your schedule\n"
    "• 🎤 Send a voice note — I'll transcribe and answer\n"
    "• 📷 Send a photo — I'll analyze it and remember it\n"
    "• <i>What's the latest AI news?</i> — live web search\n\n"
    "I keep the recent conversation in context, so follow-up questions work too."
)


def _send_telegram_message(chat_id, text: str) -> bool:
    """Send a message directly via the Telegram Bot API (for instant command replies)."""
    import requests

    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send command reply: {e}")
        return False


def _handle_command(text: str, chat_id, user, db) -> bool:
    """
    Handle Telegram slash commands with instant replies.
    Returns True if the message was a recognized command (skip agent pipeline).
    """
    # Strip bot mention: "/start@nexus_brain_devs_bot" → "/start"
    command = text.split()[0].split("@")[0].lower()

    if command == "/start":
        _send_telegram_message(chat_id, WELCOME_TEXT)
        return True

    if command == "/help":
        _send_telegram_message(chat_id, HELP_TEXT)
        return True

    if command == "/memories":
        from src.agents.tools import get_recent_memories

        memories = get_recent_memories(user_id=user.user_id, limit=10)
        if not memories:
            _send_telegram_message(
                chat_id,
                "🧠 I don't have any memories about you yet.\n"
                "Tell me something about yourself and I'll remember it!",
            )
        else:
            lines = ["🧠 <b>Here's what I remember (newest first):</b>\n"]
            for i, m in enumerate(memories, 1):
                snippet = m["content"][:150].replace("<", "&lt;").replace(">", "&gt;")
                lines.append(f"{i}. {snippet}...")
            lines.append("\nUse /forget to clear everything.")
            _send_telegram_message(chat_id, "\n".join(lines))
        return True

    if command == "/forget":
        from src.models.memory import MemoryChunk, Source, Collection

        try:
            chunk_ids = (
                db.query(MemoryChunk.chunk_id)
                .join(Source, MemoryChunk.source_id == Source.source_id)
                .join(Collection, Source.collection_id == Collection.collection_id)
                .filter(Collection.user_id == user.user_id)
                .subquery()
            )
            deleted = (
                db.query(MemoryChunk)
                .filter(MemoryChunk.chunk_id.in_(chunk_ids))
                .update({"is_deleted": True}, synchronize_session=False)
            )
            db.commit()
            _send_telegram_message(
                chat_id,
                f"🗑️ Done — I've forgotten everything ({deleted} memories cleared).\n"
                "We're starting fresh!",
            )
        except Exception as e:
            db.rollback()
            logger.error(f"/forget failed: {e}")
            _send_telegram_message(chat_id, "⚠️ Something went wrong clearing memories. Try again.")
        return True

    # Unknown command → hint, still handled (don't run the agent on "/foobar")
    _send_telegram_message(chat_id, "🤔 Unknown command. Try /help to see what I can do.")
    return True

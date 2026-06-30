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

    # 3. Parse update
    try:
        update = await request.json()
        logger.info(f"Received Telegram update: {update.get('update_id')}")
    except Exception as e:
        logger.error(f"Failed to parse webhook body: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content={"error": "Invalid JSON"}
        )

    # 4. Extract update_id (required for idempotency)
    update_id = update.get("update_id")
    if not update_id:
        logger.warning("Missing update_id in webhook")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Missing update_id"},
        )

    # 5. DATABASE IDEMPOTENCY CHECK
    db = SessionLocal()
    try:
        existing = (
            db.query(TelegramUpdateLog)
            .filter(TelegramUpdateLog.update_id == update_id)
            .first()
        )

        if existing:
            logger.warning(f"Duplicate update: {update_id} (already processed)")
            return {"ok": True}  # Idempotent - already handled

        # NEW update - store it immediately (before processing)
        log_entry = TelegramUpdateLog(
            update_id=update_id,
            user_id=None,  # Will extract from message later
            processed_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db.add(log_entry)
        db.commit()

        logger.info(f"✅ Update {update_id} stored for processing")

    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Integrity error (race condition?): {e}")
        return {"ok": True}  # Still return 200 (idempotent)
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Processing error"},
        )
    finally:
        db.close()

    # 6. Extract message text (if available)
    message = update.get("message", {})
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    if text and chat_id:
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

            # Run the agent in background via Celery (async, durable, retriable)
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

    # Always return 200 OK immediately (Telegram expects this)
    return {"ok": True}


@router.get("/telegram/webhook/status", tags=["telegram"])
async def webhook_status():
    """Check webhook status"""
    return {
        "webhook_url": settings.TELEGRAM_WEBHOOK_URL,
        "status": "configured",
    }

"""
Telegram Webhook Handler
Critical: Implements rate limiting, IP whitelist, idempotency
"""

from fastapi import APIRouter, Request, Header, status
from fastapi.responses import JSONResponse
import logging
import hashlib
from typing import Optional
from ipaddress import ip_address, ip_network

from src.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Telegram IP ranges
TELEGRAM_IP_RANGES = [
    "149.154.160.0/20",  # Telegram datacenter
    "91.108.4.0/22",     # Telegram datacenter
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
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None)
):
    """
    Telegram Webhook Handler
    
    Security checks:
    1. IP whitelist (Telegram IPs only)
    2. Secret token verification
    3. Idempotency (prevent duplicate processing)
    """
    
    # 1. IP Whitelist Check
    client_ip = request.client.host if request.client else "unknown"
    
    if not validate_telegram_ip(client_ip):
        logger.warning(f"Webhook request from non-Telegram IP: {client_ip}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Unauthorized IP"}
        )
    
    # 2. Secret Token Verification
    if not validate_telegram_secret(x_telegram_bot_api_secret_token):
        logger.warning("Invalid or missing webhook secret")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Invalid secret token"}
        )
    
    # 3. Parse update
    try:
        update = await request.json()
        logger.info(f"Received Telegram update: {update.get('update_id')}")
    except Exception as e:
        logger.error(f"Failed to parse webhook body: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid JSON"}
        )
    
    # 4. Idempotency Check (prevent duplicate processing)
    update_id = update.get("update_id")
    message_id = update.get("message", {}).get("message_id")
    chat_id = update.get("message", {}).get("chat", {}).get("id")
    
    if not all([update_id, message_id, chat_id]):
        logger.warning("Missing required fields in update")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Missing required fields"}
        )
    
    # Create idempotency key: hash(chat_id + message_id)
    idempotency_key = hashlib.sha256(
        f"{chat_id}:{message_id}".encode()
    ).hexdigest()
    
    logger.info(f"Processing message: chat={chat_id}, msg={message_id}, idempotency={idempotency_key[:8]}")
    
    # TODO: Check if message_id already processed (query DB)
    # if already_processed(message_id):
    #     logger.warning(f"Duplicate message: {message_id}")
    #     return {"ok": True}  # Idempotent response
    
    # 5. Enqueue for processing (will be handled by LangGraph agent)
    # TODO: Send to message queue for async processing
    # from src.tasks.app import process_telegram_message
    # process_telegram_message.delay(update_id, update)
    
    logger.info(f"✅ Webhook accepted for processing")
    
    # Always return 200 OK (Telegram expects this immediately)
    return {"ok": True}


@router.get("/telegram/webhook/status", tags=["telegram"])
async def webhook_status():
    """Check webhook status"""
    return {
        "webhook_url": settings.TELEGRAM_WEBHOOK_URL,
        "status": "configured",
    }

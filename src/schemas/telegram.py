"""
Pydantic schemas for Telegram webhook data validation
Ensures message data is correctly structured before processing
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class TelegramUser(BaseModel):
    """Telegram user info"""
    id: int
    is_bot: bool = False
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None


class TelegramChat(BaseModel):
    """Telegram chat info"""
    id: int
    type: str  # private, group, supergroup, channel
    title: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class TelegramMessage(BaseModel):
    """Telegram message"""
    message_id: int
    date: int
    chat: TelegramChat
    from_user: Optional[TelegramUser] = Field(None, alias="from")
    text: Optional[str] = None  # Message text (what we need!)

    class Config:
        populate_by_name = True  # Allow both 'from' and 'from_user'


class TelegramUpdate(BaseModel):
    """Telegram webhook update"""
    update_id: int
    message: Optional[TelegramMessage] = None

    class Config:
        # Allow extra fields Telegram might send
        extra = "allow"

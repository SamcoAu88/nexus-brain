"""
Reminder & Scheduling Intent Parser

Detects "remind me..." / "add to my calendar..." style requests, parses the
time and message with a cheap LLM call, and returns a structured action.
Actual scheduling happens in src/tasks/agent_tasks.py via Celery eta tasks.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict
from zoneinfo import ZoneInfo

from src.core.config import settings

logger = logging.getLogger(__name__)

REMINDER_KEYWORDS = [
    "remind", "reminder", "hatırlat", "hatirlat", "alarm",
    # Broad calendar triggers — the LLM parser returns action "none"
    # for questions like "what's on my calendar", which then fall
    # through to the normal agent (with calendar read context)
    "to my calendar", "takvime ekle", "takvimime ekle", "takvime koy",
    "schedule a", "schedule an", "book a", "book an", "set a reminder",
    "appointment at", "appointment for", "randevu ekle",
]

PARSE_PROMPT = """You are a scheduling intent parser. Today is {now} ({tz} timezone).

Analyze the user's message and extract the scheduling request.

Rules:
- "by 16:22" / "at 4pm" / "saat 17de" are times TODAY unless a day is named
- If the parsed time is already in the past today, assume tomorrow
- "in 20 minutes" / "20 dakika sonra" = relative from now
- action is "reminder" for reminders/alarms, "calendar_event" for calendar entries
- If the message is NOT a scheduling request, return action "none"

Respond with ONLY a JSON object:
{{"action": "reminder|calendar_event|none", "datetime": "YYYY-MM-DDTHH:MM:SS", "message": "what to remind/schedule", "duration_minutes": 60}}"""


def wants_scheduling(text: str) -> bool:
    """Fast keyword pre-check before spending an LLM call."""
    lower = text.lower()
    return any(k in lower for k in REMINDER_KEYWORDS)


def parse_scheduling_intent(text: str) -> Optional[Dict]:
    """
    Parse a scheduling request into {action, datetime, message, duration_minutes}.
    Returns None if parsing fails or the message isn't a scheduling request.
    """
    from src.agents.nodes import _call_llm

    tz = ZoneInfo(settings.USER_TIMEZONE)
    now = datetime.now(tz)

    try:
        result = _call_llm(
            system_prompt=PARSE_PROMPT.format(
                now=now.strftime("%A, %Y-%m-%d %H:%M"), tz=settings.USER_TIMEZONE
            ),
            user_message=text,
            temperature=0.0,
            max_tokens=200,
        )

        parsed = json.loads(result["content"])
        action = parsed.get("action", "none")
        if action == "none":
            return None

        when = datetime.fromisoformat(parsed["datetime"])
        if when.tzinfo is None:
            when = when.replace(tzinfo=tz)

        # Never schedule in the past
        if when <= now:
            logger.warning(f"Parsed time {when} is in the past, skipping")
            return None

        return {
            "action": action,
            "datetime": when,
            "message": parsed.get("message", text)[:200],
            "duration_minutes": int(parsed.get("duration_minutes", 60)),
        }

    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.warning(f"Scheduling parse failed: {e}")
        return None

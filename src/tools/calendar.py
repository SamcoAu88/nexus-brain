"""
Google Calendar Integration (service account, direct REST)

Auth model: a Google service account (credentials.json) that the user's
personal calendar has been SHARED with. No browser OAuth flow needed.

Implementation note: this module deliberately calls the Calendar REST API
directly with `requests` instead of google-api-python-client, because on
this network www.googleapis.com is TLS-intercepted (MITM'd certificate)
while calendar.googleapis.com and oauth2.googleapis.com are clean, and
`requests`+certifi verifies them correctly where httplib2 fails.

Setup (one time):
  1. Google Calendar → Settings → your calendar → "Share with specific people"
  2. Add the service account email (client_email in credentials.json)
     with "Make changes to events" permission
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

import requests

from src.core.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
API_BASE = "https://calendar.googleapis.com/calendar/v3"

_credentials = None


def _get_token() -> Optional[str]:
    """Get a fresh access token from the service account credentials."""
    global _credentials
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleRequest

        if _credentials is None:
            _credentials = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
            )

        if not _credentials.valid:
            _credentials.refresh(GoogleRequest())

        return _credentials.token
    except Exception as e:
        logger.error(f"Calendar auth failed: {e}")
        return None


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.USER_TIMEZONE)


def list_upcoming_events(days: int = 7, max_results: int = 10) -> List[Dict]:
    """
    List upcoming events from the user's calendar.

    Returns list of {summary, start, end, location} dicts, or [] on failure.
    """
    token = _get_token()
    if not token:
        return []

    try:
        now = datetime.now(_tz())
        response = requests.get(
            f"{API_BASE}/calendars/{settings.GOOGLE_CALENDAR_ID}/events",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "timeMin": now.isoformat(),
                "timeMax": (now + timedelta(days=days)).isoformat(),
                "maxResults": max_results,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
            timeout=15,
        )

        if response.status_code == 404:
            logger.error(
                "Calendar not found — has the calendar been shared with the "
                "service account email? Check FEATURES.md setup steps."
            )
            return []
        response.raise_for_status()

        events = []
        for e in response.json().get("items", []):
            start = e.get("start", {})
            end = e.get("end", {})
            events.append(
                {
                    "summary": e.get("summary", "(no title)"),
                    "start": start.get("dateTime", start.get("date", "")),
                    "end": end.get("dateTime", end.get("date", "")),
                    "location": e.get("location", ""),
                }
            )

        logger.info(f"📅 Calendar: {len(events)} upcoming events ({days} days)")
        return events

    except Exception as e:
        logger.error(f"Calendar list failed: {e}")
        return []


def create_event(
    summary: str,
    start_dt: datetime,
    duration_minutes: int = 60,
    description: str = "",
) -> Optional[str]:
    """
    Create a calendar event. start_dt may be naive (assumed user timezone).

    Returns the event's htmlLink on success, None on failure.
    """
    token = _get_token()
    if not token:
        return None

    try:
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=_tz())
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        response = requests.post(
            f"{API_BASE}/calendars/{settings.GOOGLE_CALENDAR_ID}/events",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "summary": summary,
                "description": description or "Created by Nexus-Brain",
                "start": {"dateTime": start_dt.isoformat(), "timeZone": settings.USER_TIMEZONE},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": settings.USER_TIMEZONE},
            },
            timeout=15,
        )
        response.raise_for_status()

        link = response.json().get("htmlLink")
        logger.info(f"📅 Calendar event created: {summary} @ {start_dt}")
        return link

    except Exception as e:
        logger.error(f"Calendar create failed: {e}")
        return None


def format_events_for_context(events: List[Dict]) -> str:
    """Format events as readable text for LLM context injection."""
    if not events:
        return "(calendar is empty for this period)"

    lines = []
    for e in events:
        loc = f" @ {e['location']}" if e["location"] else ""
        lines.append(f"- {e['start']}: {e['summary']}{loc}")
    return "\n".join(lines)


def needs_calendar(text: str) -> bool:
    """Detect whether a message is asking about the calendar/schedule."""
    keywords = [
        "calendar", "takvim", "schedule", "appointment", "meeting",
        "randevu", "toplantı", "etkinlik", "event", "agenda",
        "what's on", "whats on", "plans for", "planım", "programım",
        "bugün ne var", "yarın ne var", "haftaya ne var",
    ]
    lower = text.lower()
    return any(k in lower for k in keywords)

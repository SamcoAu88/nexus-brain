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
# content.googleapis.com is the only googleapis host that BOTH (a) TLS-verifies
# cleanly on this network (www.googleapis.com is MITM'd) AND (b) routes
# Calendar API paths correctly (calendar.googleapis.com returns HTML 404 here).
# Verified empirically — see scripts/diag_calendar_routing.py
API_BASE = "https://content.googleapis.com/calendar/v3"

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


_resolved_calendar_id = None


def _resolve_calendar_id(token: str) -> Optional[str]:
    """
    Figure out which calendar to use, in priority order:
      1. The user's personal calendar (if they shared it with the service account)
      2. A bot-owned 'Nexus-Brain' calendar, auto-created and shared TO the user
         (zero-setup fallback — the user gets an email invite to add it)
    """
    global _resolved_calendar_id
    if _resolved_calendar_id:
        return _resolved_calendar_id

    headers = {"Authorization": f"Bearer {token}"}

    # 1. Try the user's own calendar
    probe = requests.get(
        f"{API_BASE}/calendars/{settings.GOOGLE_CALENDAR_ID}",
        headers=headers,
        timeout=15,
    )
    if probe.status_code == 200:
        _resolved_calendar_id = settings.GOOGLE_CALENDAR_ID
        logger.info(f"📅 Using user's shared calendar: {_resolved_calendar_id}")
        return _resolved_calendar_id

    logger.info("📅 User calendar not shared yet — falling back to bot-owned calendar")

    # 2. Look for an existing bot-owned 'Nexus-Brain' calendar
    try:
        cal_list = requests.get(
            f"{API_BASE}/users/me/calendarList", headers=headers, timeout=15
        )
        cal_list.raise_for_status()
        for item in cal_list.json().get("items", []):
            if item.get("summary") == "Nexus-Brain":
                _resolved_calendar_id = item["id"]
                logger.info(f"📅 Using existing bot calendar: {_resolved_calendar_id}")
                return _resolved_calendar_id

        # 3. Create it and share it with the user
        created = requests.post(
            f"{API_BASE}/calendars",
            headers=headers,
            json={"summary": "Nexus-Brain", "timeZone": settings.USER_TIMEZONE},
            timeout=15,
        )
        created.raise_for_status()
        cal_id = created.json()["id"]

        # Grant the user write access — Google emails them an invite link
        acl = requests.post(
            f"{API_BASE}/calendars/{cal_id}/acl",
            headers=headers,
            json={
                "role": "writer",
                "scope": {"type": "user", "value": settings.GOOGLE_CALENDAR_ID},
            },
            timeout=15,
        )
        if acl.status_code not in (200, 201):
            logger.warning(f"Could not share bot calendar with user: {acl.text[:150]}")

        _resolved_calendar_id = cal_id
        logger.info(f"📅 Created bot calendar '{cal_id}' and shared with user")
        return _resolved_calendar_id

    except Exception as e:
        logger.error(f"Bot calendar fallback failed: {e}")
        return None


def list_upcoming_events(days: int = 7, max_results: int = 10) -> List[Dict]:
    """
    List upcoming events from the user's calendar.

    Returns list of {summary, start, end, location} dicts, or [] on failure.
    """
    token = _get_token()
    if not token:
        return []

    calendar_id = _resolve_calendar_id(token)
    if not calendar_id:
        return []

    try:
        now = datetime.now(_tz())
        response = requests.get(
            f"{API_BASE}/calendars/{calendar_id}/events",
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

    calendar_id = _resolve_calendar_id(token)
    if not calendar_id:
        return None

    try:
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=_tz())
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        response = requests.post(
            f"{API_BASE}/calendars/{calendar_id}/events",
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

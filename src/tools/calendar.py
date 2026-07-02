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
    Figure out which calendar to WRITE to, in priority order:
      1. The user's personal calendar (if they shared it with the service account)
      2. A bot-owned 'Nexus-Brain' calendar, auto-created and shared TO the user

    NOTE: only a successful user-calendar probe is cached permanently.
    The fallback is re-resolved on every call so the moment the user shares
    their calendar, reads and writes switch over consistently — otherwise
    create could target one calendar while list reads another.
    """
    global _resolved_calendar_id
    if _resolved_calendar_id == settings.GOOGLE_CALENDAR_ID:
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


def _readable_calendar_ids(token: str) -> List[str]:
    """
    All calendars we can read: the user's shared calendar (if accessible)
    plus the bot-owned 'Nexus-Brain' calendar (if it exists). Reading BOTH
    means events stay visible no matter which calendar they were created on.
    """
    headers = {"Authorization": f"Bearer {token}"}
    ids = []

    probe = requests.get(
        f"{API_BASE}/calendars/{settings.GOOGLE_CALENDAR_ID}",
        headers=headers,
        timeout=15,
    )
    if probe.status_code == 200:
        ids.append(settings.GOOGLE_CALENDAR_ID)

    try:
        cal_list = requests.get(
            f"{API_BASE}/users/me/calendarList", headers=headers, timeout=15
        )
        if cal_list.status_code == 200:
            for item in cal_list.json().get("items", []):
                if item.get("summary") == "Nexus-Brain" and item["id"] not in ids:
                    ids.append(item["id"])
    except Exception as e:
        logger.warning(f"calendarList fetch failed: {e}")

    return ids


def list_upcoming_events(days: int = 7, max_results: int = 10) -> List[Dict]:
    """
    List upcoming events, merged across ALL readable calendars (user's +
    bot-owned), explicitly in the user's timezone (Australia/Brisbane).

    Returns list of {summary, start, end, location} dicts sorted by start.
    """
    token = _get_token()
    if not token:
        return []

    calendar_ids = _readable_calendar_ids(token)
    if not calendar_ids:
        return []

    now = datetime.now(_tz())
    time_min = now.isoformat()  # includes +10:00 Brisbane offset
    time_max = (now + timedelta(days=days)).isoformat()

    merged: Dict[tuple, Dict] = {}
    for cal_id in calendar_ids:
        try:
            response = requests.get(
                f"{API_BASE}/calendars/{cal_id}/events",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "maxResults": max_results,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "timeZone": settings.USER_TIMEZONE,  # response times in AEST
                },
                timeout=15,
            )
            response.raise_for_status()

            for e in response.json().get("items", []):
                start = e.get("start", {})
                end = e.get("end", {})
                event = {
                    "summary": e.get("summary", "(no title)"),
                    "start": start.get("dateTime", start.get("date", "")),
                    "end": end.get("dateTime", end.get("date", "")),
                    "location": e.get("location", ""),
                }
                # Dedupe events that exist on both calendars
                merged[(event["summary"].casefold(), event["start"])] = event

        except Exception as e:
            logger.warning(f"Calendar list failed for {cal_id}: {e}")

    events = sorted(merged.values(), key=lambda ev: ev["start"])[:max_results]
    logger.info(
        f"📅 Calendar: {len(events)} upcoming events across "
        f"{len(calendar_ids)} calendar(s) ({days} days, {settings.USER_TIMEZONE})"
    )
    return events


def create_event(
    summary: str,
    start_dt: datetime,
    duration_minutes: int = 60,
    description: str = "",
) -> Dict:
    """
    Create a calendar event with Read-Before-Write duplicate protection.
    start_dt may be naive (assumed user timezone).

    Returns:
        {"status": "created", "link": htmlLink}
        {"status": "duplicate", "existing": {summary, start}}  — already booked
        {"status": "error"}
    """
    token = _get_token()
    if not token:
        return {"status": "error"}

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=_tz())

    # ── Read-Before-Write: does a matching event already exist that day? ──
    try:
        day_start = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        headers = {"Authorization": f"Bearer {token}"}

        for cal_id in _readable_calendar_ids(token):
            existing = requests.get(
                f"{API_BASE}/calendars/{cal_id}/events",
                headers=headers,
                params={
                    "timeMin": day_start.isoformat(),
                    "timeMax": day_end.isoformat(),
                    "singleEvents": "true",
                    "timeZone": settings.USER_TIMEZONE,
                },
                timeout=15,
            )
            if existing.status_code != 200:
                continue

            for e in existing.json().get("items", []):
                if e.get("summary", "").casefold().strip() == summary.casefold().strip():
                    ev_start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
                    logger.info(f"📅 Duplicate detected: '{summary}' already exists at {ev_start}")
                    return {
                        "status": "duplicate",
                        "existing": {"summary": e.get("summary", ""), "start": ev_start},
                    }
    except Exception as e:
        logger.warning(f"Duplicate check failed (continuing with create): {e}")

    # ── Write ──
    calendar_id = _resolve_calendar_id(token)
    if not calendar_id:
        return {"status": "error"}

    try:
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
        return {"status": "created", "link": link}

    except Exception as e:
        logger.error(f"Calendar create failed: {e}")
        return {"status": "error"}


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

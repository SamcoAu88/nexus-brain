"""Delete the 'Appointment with Dr. Jenkins' TEST artifact (keeps the real one)."""
import requests
from src.tools.calendar import _get_token, _readable_calendar_ids, list_upcoming_events, API_BASE
from src.core.config import settings

token = _get_token()
h = {"Authorization": f"Bearer {token}"}
deleted = 0

for cal_id in _readable_calendar_ids(token):
    r = requests.get(
        f"{API_BASE}/calendars/{cal_id}/events",
        headers=h,
        params={"q": "Dr. Jenkins", "timeZone": settings.USER_TIMEZONE},
        timeout=15,
    )
    for e in r.json().get("items", []):
        if e.get("summary", "").strip() == "Appointment with Dr. Jenkins":
            d = requests.delete(
                f"{API_BASE}/calendars/{cal_id}/events/{e['id']}", headers=h, timeout=15
            )
            if d.status_code in (200, 204):
                deleted += 1

print("Test artifacts deleted:", deleted)
events = list_upcoming_events(days=7)
print("FINAL STATE:", len(events), "event(s)")
for e in events:
    print("  -", e["start"], "|", e["summary"])

"""Diagnose googleapis routing: try Calendar API paths on hosts that TLS-verify cleanly."""
import requests
from src.tools.calendar import _get_token

token = _get_token()
h = {"Authorization": f"Bearer {token}"}

hosts = [
    "calendar.googleapis.com",
    "oauth2.googleapis.com",
    "content.googleapis.com",
    "googleapis.com",
    "www.googleapis.com",
]

for host in hosts:
    url = f"https://{host}/calendar/v3/users/me/calendarList"
    try:
        r = requests.get(url, headers=h, timeout=12)
        ct = r.headers.get("content-type", "")[:30]
        body = r.text[:100].replace("\n", " ")
        print(f"{host:28} -> {r.status_code} [{ct}] {body}")
    except Exception as e:
        print(f"{host:28} -> FAIL {str(e)[:80]}")

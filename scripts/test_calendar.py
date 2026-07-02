"""Quick calendar connectivity test. Run inside container with PYTHONPATH=/app."""
import os
import certifi

# Ensure Google clients use certifi's CA bundle (container CA store is incomplete)
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import logging
logging.basicConfig(level=logging.INFO)

from src.tools.calendar import list_upcoming_events

events = list_upcoming_events(days=14)
print(f"EVENTS: {len(events)}")
for e in events[:5]:
    print(" -", e["start"], e["summary"])

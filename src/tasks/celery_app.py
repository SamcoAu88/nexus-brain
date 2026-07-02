"""
Celery Application Configuration
Redis-backed message broker for async task processing.
"""

from celery import Celery
from celery.schedules import crontab
from src.core.config import settings

# Celery application instance
celery_app = Celery(
    "nexus_brain",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "src.tasks.agent_tasks",
    ],
)

# ─── Configuration ─────────────────────────────────────

celery_app.conf.update(
    # Task serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Brisbane local time so crontab schedules read naturally;
    # eta-based tasks use tz-aware datetimes and are unaffected
    timezone="Australia/Brisbane",
    enable_utc=True,
    # Task result TTL
    result_expires=3600,  # 1 hour
    # Task routing
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "capture": {"exchange": "capture", "routing_key": "capture"},
        "embeddings": {"exchange": "embeddings", "routing_key": "embeddings"},
        "heavy": {"exchange": "heavy", "routing_key": "heavy"},
    },
    # Rate limiting
    task_acks_late=True,  # Re-deliver if worker crashes
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # Fair dispatch
    # Retry defaults
    task_default_retry_delay=30,  # 30 seconds before first retry
    task_max_retries=3,
    # Visibility
    broker_connection_retry_on_startup=True,
    # ── Proactive scheduled tasks (Celery Beat) ──
    beat_schedule={
        "morning-briefing-7am": {
            "task": "morning_briefing",
            "schedule": crontab(hour=7, minute=0),  # 07:00 Australia/Brisbane
            "options": {"queue": "default"},
        },
        "cleanup-expired-logs": {
            "task": "cleanup_expired",
            "schedule": crontab(hour=3, minute=30),  # quiet-hours housekeeping
            "options": {"queue": "default"},
        },
    },
)

# ─── Helper ────────────────────────────────────────────


def get_task(name: str):
    """Get a task by name for type-safe invocation."""
    return celery_app.tasks[name]

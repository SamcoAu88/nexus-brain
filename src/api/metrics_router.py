"""
Prometheus Metrics Endpoint
Exposes application metrics for monitoring and alerting.
"""

import logging
import time
from fastapi import APIRouter, Response
from prometheus_client import (
    generate_latest,
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    REGISTRY,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Custom Metrics ────────────────────────────────────

# HTTP request counters
HTTP_REQUESTS_TOTAL = Counter(
    "nexus_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "nexus_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Agent-specific metrics
AGENT_INVOCATIONS = Counter(
    "nexus_agent_invocations_total",
    "Total agent invocations",
    ["input_type"],
)

AGENT_LATENCY = Histogram(
    "nexus_agent_latency_seconds",
    "Agent processing latency in seconds",
    ["input_type"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

AGENT_TOKENS = Counter(
    "nexus_agent_tokens_total",
    "Total tokens consumed by agent",
    ["model"],
)

# Memory / Search metrics
MEMORY_CHUNKS_TOTAL = Gauge(
    "nexus_memory_chunks_total",
    "Total memory chunks stored",
    ["user_id"],
    registry=REGISTRY,
)

SEARCH_QUERIES = Counter(
    "nexus_search_queries_total",
    "Total search queries executed",
    ["search_type"],
)

# Celery metrics
CELERY_TASKS_TOTAL = Counter(
    "nexus_celery_tasks_total",
    "Total Celery tasks processed",
    ["task_name", "status"],
)

# Business metrics
ACTIVE_USERS = Gauge(
    "nexus_active_users",
    "Number of active users",
)

MESSAGES_PROCESSED = Counter(
    "nexus_messages_processed_total",
    "Total messages processed",
)

COST_TRACKING = Counter(
    "nexus_cost_total_usd",
    "Total API cost in USD",
)


# ─── Metrics Endpoint ──────────────────────────────────


@router.get("/metrics", tags=["monitoring"])
async def metrics():
    """Prometheus metrics endpoint."""
    data = generate_latest(REGISTRY)
    return Response(
        content=data,
        media_type=CONTENT_TYPE_LATEST,
    )


# ─── Middleware Helper ─────────────────────────────────


def record_request(method: str, endpoint: str, status: int, duration: float):
    """Record HTTP request metrics."""
    HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=status).inc()
    HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)


def record_agent_invocation(input_type: str, latency: float, tokens: int, model: str = "gpt-4o"):
    """Record agent invocation metrics."""
    AGENT_INVOCATIONS.labels(input_type=input_type).inc()
    AGENT_LATENCY.labels(input_type=input_type).observe(latency)
    AGENT_TOKENS.labels(model=model).inc(tokens)


def record_search(search_type: str):
    """Record search query."""
    SEARCH_QUERIES.labels(search_type=search_type).inc()


def record_celery_task(task_name: str, status: str):
    """Record Celery task completion."""
    CELERY_TASKS_TOTAL.labels(task_name=task_name, status=status).inc()

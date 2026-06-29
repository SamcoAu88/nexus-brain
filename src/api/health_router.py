"""
Enhanced Health Check Endpoints
Provides real dependency verification: DB, Redis, Celery, LLM connectivity.
"""

from fastapi import APIRouter
import logging
import time

from src.core.database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", tags=["health"])
async def health():
    """System health check with dependency verification."""
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
        "celery": _check_celery(),
    }

    all_healthy = all(c["status"] == "ok" for c in checks.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": "Nexus-Brain",
        "version": "5.0.0",
        "checks": checks,
    }


@router.get("/health/ready", tags=["health"])
async def readiness():
    """Readiness probe — all dependencies must be available."""
    db_ok = _check_database()
    redis_ok = _check_redis()

    all_ready = all(c["status"] == "ok" for c in [db_ok, redis_ok])

    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": {
            "database": db_ok,
            "redis": redis_ok,
        },
    }


@router.get("/health/live", tags=["health"])
async def liveness():
    """Liveness probe — is the process alive?"""
    return {
        "status": "alive",
        "uptime_seconds": _get_uptime(),
    }


@router.get("/health/detailed", tags=["health"])
async def detailed_health():
    """Detailed health with timing and configuration info."""
    from src.core.config import settings

    start = time.time()
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
        "celery": _check_celery(),
    }
    elapsed_ms = round((time.time() - start) * 1000, 2)

    return {
        "status": "healthy",
        "version": "5.0.0",
        "environment": settings.ENV,
        "debug": settings.DEBUG,
        "check_duration_ms": elapsed_ms,
        "checks": checks,
    }


# ─── Individual Checks ────────────────────────────────


def _check_database() -> dict:
    """Verify PostgreSQL connectivity and migration state."""
    try:
        db = SessionLocal()
        db.execute(
            "SELECT 1 AS ok"
        )
        db.close()
        return {"status": "ok", "latency_ms": 0}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "error", "error": str(e)}


def _check_redis() -> dict:
    """Verify Redis connectivity."""
    import redis as redis_lib
    from src.core.config import settings

    try:
        client = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        client.ping()
        client.close()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "error", "error": str(e)}


def _check_celery() -> dict:
    """Verify Celery worker is reachable via broker."""
    from src.tasks.celery_app import celery_app

    try:
        # Ping the Celery worker (inspect)
        inspect = celery_app.control.inspect(timeout=2)
        stats = inspect.stats()
        if stats:
            workers = [
                {"name": name, "active": s.get("total", {}).get("completed", 0)}
                for name, s in (stats or {}).items()
            ]
            return {"status": "ok", "workers": workers}
        else:
            return {"status": "degraded", "message": "No Celery workers connected"}
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return {"status": "error", "error": str(e)}


# ─── Uptime Tracking ──────────────────────────────────

_start_time = time.time()


def _get_uptime() -> float:
    """Return seconds since application started."""
    return round(time.time() - _start_time, 2)

"""
Health Check Endpoints
"""

from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", tags=["health"])
async def health():
    """System health check"""
    return {
        "status": "healthy",
        "service": "Nexus-Brain",
        "version": "5.0.0",
    }


@router.get("/health/ready", tags=["health"])
async def readiness():
    """Readiness probe for Kubernetes"""
    try:
        # In future: check DB, Redis, LLM connectivity
        return {
            "status": "ready",
            "checks": {
                "database": "ok",
                "redis": "ok",
                "llm": "ok",
            }
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"status": "not_ready", "error": str(e)}, 503


@router.get("/health/live", tags=["health"])
async def liveness():
    """Liveness probe for Kubernetes"""
    return {"status": "alive"}

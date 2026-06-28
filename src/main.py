"""
Nexus-Brain v5.0 - FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.core.config import settings
from src.core.logging_config import setup_logging
from src.api import telegram_router, health_router, memory_router

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Startup
    logger.info("🚀 Nexus-Brain v5.0 Starting...")
    logger.info(f"Environment: {settings.ENV}")
    logger.info(f"Debug: {settings.DEBUG}")

    yield

    # Shutdown
    logger.info("🛑 Nexus-Brain Shutting Down...")


# Create FastAPI app
app = FastAPI(
    title="Nexus-Brain",
    description="AI Second Brain with Telegram Interface",
    version="5.0.0",
    lifespan=lifespan,
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Rate limit exceeded"},
    ),
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router.router, prefix="/api", tags=["health"])
app.include_router(telegram_router.router, prefix="/api", tags=["telegram"])
app.include_router(memory_router.router, prefix="/api", tags=["memory"])


# Root endpoint
@app.get("/", tags=["info"])
async def root():
    """Nexus-Brain API Info"""
    return {
        "name": "Nexus-Brain",
        "version": "5.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )

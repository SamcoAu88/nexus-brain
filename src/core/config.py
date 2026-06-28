"""
Configuration management using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application Settings"""
    
    # Core
    ENV: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "Nexus-Brain"
    PROJECT_VERSION: str = "5.0.0"
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_URL: str
    TELEGRAM_WEBHOOK_SECRET: str
    
    # Database
    DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_DB: int = 1
    
    # LLM Providers
    OPENAI_API_KEY: str
    ANTHROPIC_API_KEY: str
    COHERE_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    
    # Ollama (Local)
    OLLAMA_API_URL: Optional[str] = "http://localhost:11434"
    OLLAMA_EMBEDDING_MODEL: str = "bge-large-en-v1.5"
    
    # External Services
    TAVILY_API_KEY: Optional[str] = None
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    SENTRY_DSN: Optional[str] = None
    
    # Security
    PII_MASTER_KEY: str
    JWT_SECRET_KEY: str
    ENCRYPTION_KEY_VERSION: int = 1
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # Cost Controls
    USER_DAILY_BUDGET_USD: float = 5.0
    COST_WARNING_THRESHOLD: float = 0.8
    COST_HARD_LIMIT_THRESHOLD: float = 1.5
    
    # Feature Flags
    FEATURE_GRAPH_RAG: bool = False
    FEATURE_QUERY_EXPANSION: bool = False
    FEATURE_SEMANTIC_CACHE: bool = True
    FEATURE_ENTITY_EXTRACTION: bool = False
    FEATURE_VISION: bool = True
    FEATURE_VOICE: bool = True
    
    # Observability
    LOG_LEVEL: str = "INFO"
    PROMETHEUS_PORT: int = 8001
    
    # Deployment
    WORKERS: int = 1
    SECRETS_MANAGER: str = "local"
    WORKER_CLASS: str = "uvicorn.workers.UvicornWorker"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
    
    def validate(self):
        """Validate critical settings on startup"""
        required = [
            "TELEGRAM_BOT_TOKEN",
            "DATABASE_URL",
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "OPENAI_API_KEY",
            "PII_MASTER_KEY",
        ]
        
        missing = [key for key in required if not getattr(self, key, None)]
        
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(missing)}")
        
        logger.info("✅ All critical settings validated")


# Global settings instance
settings = Settings()

# Validate on import
try:
    settings.validate()
except ValueError as e:
    logger.error(f"❌ Configuration Error: {e}")
    raise

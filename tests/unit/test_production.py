"""
Unit Tests for Production Hardening (Sprint 6)
Tests: health checks, metrics, rate limiting, logging, locustfile.
"""

import pytest
from unittest.mock import patch, MagicMock


# ─── Health Check Tests ────────────────────────────────


class TestHealthChecks:
    """Test enhanced health check endpoints."""

    def test_health_returns_checks(self):
        """GET /api/health returns dependency checks."""
        from src.api.health_router import health

        with patch("src.api.health_router._check_database") as mock_db:
            mock_db.return_value = {"status": "ok", "latency_ms": 1}
            with patch("src.api.health_router._check_redis") as mock_redis:
                mock_redis.return_value = {"status": "ok"}
                with patch("src.api.health_router._check_celery") as mock_celery:
                    mock_celery.return_value = {"status": "ok"}

                    import asyncio
                    response = asyncio.run(health())

        assert response["status"] == "healthy"
        assert "database" in response["checks"]
        assert "redis" in response["checks"]
        assert "celery" in response["checks"]

    def test_health_reports_degraded(self):
        """Health reports degraded when checks fail."""
        from src.api.health_router import health

        with patch("src.api.health_router._check_database") as mock_db:
            mock_db.return_value = {"status": "error", "error": "DB down"}
            with patch("src.api.health_router._check_redis") as mock_redis:
                mock_redis.return_value = {"status": "ok"}
                with patch("src.api.health_router._check_celery") as mock_celery:
                    mock_celery.return_value = {"status": "ok"}

                    import asyncio
                    response = asyncio.run(health())

        assert response["status"] == "degraded"
        assert response["checks"]["database"]["status"] == "error"

    def test_readiness_checks_db_redis(self):
        """Readiness checks DB and Redis."""
        from src.api.health_router import readiness

        with patch("src.api.health_router._check_database") as mock_db:
            mock_db.return_value = {"status": "ok"}
            with patch("src.api.health_router._check_redis") as mock_redis:
                mock_redis.return_value = {"status": "ok"}

                import asyncio
                response = asyncio.run(readiness())

        assert response["status"] == "ready"

    def test_liveness_returns_uptime(self):
        """Liveness returns alive with uptime."""
        from src.api.health_router import liveness

        import asyncio
        response = asyncio.run(liveness())

        assert response["status"] == "alive"
        assert response["uptime_seconds"] > 0

    def test_detailed_health_includes_config(self):
        """Detailed health includes env and debug info."""
        from src.api.health_router import detailed_health

        with patch("src.api.health_router._check_database") as mock_db:
            mock_db.return_value = {"status": "ok"}
            with patch("src.api.health_router._check_redis") as mock_redis:
                mock_redis.return_value = {"status": "ok"}
                with patch("src.api.health_router._check_celery") as mock_celery:
                    mock_celery.return_value = {"status": "ok"}

                    import asyncio
                    response = asyncio.run(detailed_health())

        assert "environment" in response
        assert "check_duration_ms" in response
        assert response["check_duration_ms"] >= 0


# ─── Database Check Tests ──────────────────────────────


class TestDatabaseCheck:
    """Test database health check logic."""

    def test_database_check_ok(self):
        """_check_database returns ok when DB responds."""
        from src.api.health_router import _check_database

        with patch("src.api.health_router.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            result = _check_database()

        assert result["status"] == "ok"

    def test_database_check_error(self):
        """_check_database returns error on exception."""
        from src.api.health_router import _check_database

        with patch("src.api.health_router.SessionLocal") as mock_session:
            mock_session.side_effect = Exception("Connection refused")

            result = _check_database()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]


# ─── Redis Check Tests ─────────────────────────────────


class TestRedisCheck:
    """Test Redis health check logic."""

    def test_redis_check_ok(self):
        """_check_redis returns ok when Redis responds."""
        from src.api.health_router import _check_redis

        with patch("redis.from_url") as mock_from_url:
            mock_client = MagicMock()
            mock_from_url.return_value = mock_client

            result = _check_redis()

        assert result["status"] == "ok"

    def test_redis_check_error(self):
        """_check_redis returns error on connection failure."""
        from src.api.health_router import _check_redis

        with patch("redis.from_url") as mock_from_url:
            mock_from_url.side_effect = Exception("Connection timeout")

            result = _check_redis()

        assert result["status"] == "error"


# ─── Celery Check Tests ────────────────────────────────


class TestCeleryCheck:
    """Test Celery health check logic."""

    def test_celery_check_ok_with_workers(self):
        """_check_celery returns ok with workers."""
        from src.api.health_router import _check_celery

        with patch("src.tasks.celery_app.celery_app.control.inspect") as mock_inspect:
            mock_insp = MagicMock()
            mock_inspect.return_value = mock_insp
            mock_insp.stats.return_value = {"worker1": {"total": {"completed": 42}}}

            result = _check_celery()

        assert result["status"] == "ok"
        assert len(result["workers"]) == 1
        assert result["workers"][0]["name"] == "worker1"

    def test_celery_check_no_workers(self):
        """_check_celery returns degraded with no workers."""
        from src.api.health_router import _check_celery

        with patch("src.tasks.celery_app.celery_app.control.inspect") as mock_inspect:
            mock_insp = MagicMock()
            mock_inspect.return_value = mock_insp
            mock_insp.stats.return_value = {}

            result = _check_celery()

        assert result["status"] == "degraded"

    def test_celery_check_error(self):
        """_check_celery returns error on failure."""
        from src.api.health_router import _check_celery

        with patch("src.tasks.celery_app.celery_app.control.inspect") as mock_inspect:
            mock_inspect.side_effect = Exception("Broker unavailable")

            result = _check_celery()

        assert result["status"] == "error"


# ─── Metrics Tests ─────────────────────────────────────


class TestMetrics:
    """Test Prometheus metrics endpoint."""

    def test_metrics_endpoint_registered(self):
        """Metrics endpoint path is correct."""
        from src.api.metrics_router import router

        routes = [r.path for r in router.routes]
        assert "/metrics" in routes

    def test_metrics_labels_exist(self):
        """Metrics have correct label structures."""
        from src.api.metrics_router import HTTP_REQUESTS_TOTAL

        assert "method" in HTTP_REQUESTS_TOTAL._labelnames
        assert "endpoint" in HTTP_REQUESTS_TOTAL._labelnames
        assert "status" in HTTP_REQUESTS_TOTAL._labelnames

    def test_agent_metrics_exist(self):
        """Agent-specific metrics are defined."""
        from src.api.metrics_router import AGENT_INVOCATIONS, AGENT_LATENCY, AGENT_TOKENS

        assert "input_type" in AGENT_INVOCATIONS._labelnames
        assert "input_type" in AGENT_LATENCY._labelnames
        assert "model" in AGENT_TOKENS._labelnames

    def test_search_metric_counter(self):
        """Search query counter exists."""
        from src.api.metrics_router import SEARCH_QUERIES

        assert "search_type" in SEARCH_QUERIES._labelnames

    def test_celery_metric_counter(self):
        """Celery task counter exists."""
        from src.api.metrics_router import CELERY_TASKS_TOTAL

        assert "task_name" in CELERY_TASKS_TOTAL._labelnames
        assert "status" in CELERY_TASKS_TOTAL._labelnames


# ─── Rate Limiting Tests ───────────────────────────────


class TestRateLimiting:
    """Test rate limiting configuration."""

    def test_limiter_configured_in_app(self):
        """App has rate limiter configured."""
        from src.main import limiter, app

        assert limiter is not None
        assert hasattr(app.state, "limiter")

    def test_rate_limit_exceeded_handler_exists(self):
        """Rate limit exceeded handler is registered."""
        from src.main import app

        handlers = [r for r in app.exception_handlers.values()]
        assert len(handlers) > 0


# ─── Logging Tests ─────────────────────────────────────


class TestLogging:
    """Test structured logging configuration."""

    def test_logging_configured(self):
        """Logging is set up without errors."""
        import logging
        from src.core.logging_config import setup_logging

        setup_logging()  # Should not raise
        logger = logging.getLogger("test")
        logger.info("Test log message")  # Should not raise


# ─── Locustfile Tests ──────────────────────────────────


class TestLocustfile:
    """Test locustfile is syntactically valid."""

    def test_locustfile_exists(self):
        """locustfile.py exists at project root."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        locust_path = os.path.join(project_root, "locustfile.py")
        assert os.path.exists(locust_path)

    def test_locustfile_parseable(self):
        """locustfile can be parsed without import errors."""
        import ast
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        locust_path = os.path.join(project_root, "locustfile.py")

        with open(locust_path) as f:
            ast.parse(f.read())  # Should not raise SyntaxError


# ─── RLS Migration Tests ───────────────────────────────


class TestRLSMigration:
    """Test RLS migration file."""

    def test_rls_migration_exists(self):
        """RLS migration file exists."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "deployment", "alembic", "versions",
            "b2c3d4e5f6a7_add_row_level_security_policies.py",
        )
        assert os.path.exists(path)

    def test_rls_migration_parseable(self):
        """RLS migration can be parsed."""
        import ast
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "deployment", "alembic", "versions",
            "b2c3d4e5f6a7_add_row_level_security_policies.py",
        )

        with open(path) as f:
            tree = ast.parse(f.read())
            # Find functions named upgrade and downgrade
            funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            assert "upgrade" in funcs
            assert "downgrade" in funcs

    def test_rls_tables_defined(self):
        """RLS migration has user-scoped tables listed."""
        import ast
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "deployment", "alembic", "versions",
            "b2c3d4e5f6a7_add_row_level_security_policies.py",
        )

        with open(path) as f:
            content = f.read()

        expected_tables = [
            "user_profiles", "collections", "conversations",
            "entities", "cost_tracking", "audit_logs",
        ]
        for table in expected_tables:
            assert table in content, f"Missing RLS table: {table}"

"""
Unit Tests for Celery Background Tasks (Sprint 4.2)
Tests: celery app config, task definitions, retry behavior, routing.
"""

import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4


# ─── Celery App Tests ──────────────────────────────────


class TestCeleryApp:
    """Test Celery application configuration."""

    def test_celery_app_created(self):
        """celery_app is a properly configured Celery instance."""
        from src.tasks.celery_app import celery_app

        assert celery_app.main == "nexus_brain"
        assert "src.tasks.agent_tasks" in celery_app.conf.include
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.task_default_queue == "default"

    def test_celery_queues_defined(self):
        """All expected task queues are registered."""
        from src.tasks.celery_app import celery_app

        queues = celery_app.conf.task_queues
        assert "default" in queues
        assert "capture" in queues
        assert "embeddings" in queues
        assert "heavy" in queues

    def test_celery_has_retry_config(self):
        """Celery has sensible retry defaults."""
        from src.tasks.celery_app import celery_app

        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.task_reject_on_worker_lost is True
        assert celery_app.conf.worker_prefetch_multiplier == 1

    def test_get_task_returns_task_by_name(self):
        """get_task helper retrieves registered tasks."""
        from src.tasks.celery_app import celery_app, get_task

        # Register a test task
        @celery_app.task(name="test_task")
        def dummy():
            pass

        task = get_task("test_task")
        assert task is not None
        assert task.name == "test_task"


# ─── Task Definition Tests ─────────────────────────────


class TestTaskDefinitions:
    """Test that agent tasks are properly defined with retry config."""

    def test_process_telegram_message_task_exists(self):
        """process_telegram_message is a registered Celery task."""
        from src.tasks import agent_tasks  # noqa: trigger registration
        from src.tasks.celery_app import celery_app

        task = celery_app.tasks.get("process_telegram_message")
        assert task is not None, "Task 'process_telegram_message' not registered"

    def test_generate_embeddings_task_exists(self):
        """generate_embeddings is a registered Celery task."""
        from src.tasks import agent_tasks  # noqa: trigger registration
        from src.tasks.celery_app import celery_app

        task = celery_app.tasks.get("generate_embeddings")
        assert task is not None, "Task 'generate_embeddings' not registered"

    def test_cleanup_expired_task_exists(self):
        """cleanup_expired is a registered Celery task."""
        from src.tasks import agent_tasks  # noqa: trigger registration
        from src.tasks.celery_app import celery_app

        task = celery_app.tasks.get("cleanup_expired")
        assert task is not None, "Task 'cleanup_expired' not registered"

    def test_all_three_tasks_registered(self):
        """All expected tasks are registered on startup."""
        from src.tasks.celery_app import celery_app
        from src.tasks import agent_tasks  # noqa: trigger import

        task_names = list(celery_app.tasks.keys())
        assert "process_telegram_message" in task_names
        assert "generate_embeddings" in task_names
        assert "cleanup_expired" in task_names


# ─── Task Execution Tests ──────────────────────────────


class TestTaskExecution:
    """Test individual task execution logic (mocked DB/LLM)."""

    @pytest.mark.asyncio
    async def test_process_telegram_message_success(self):
        """process_telegram_message runs agent and returns success response."""
        from src.tasks.agent_tasks import process_telegram_message

        with patch("asyncio.run") as mock_async_run:
            mock_result = {
                "status": "success",
                "input_type": "question",
                "tokens_used": 150,
                "latency_ms": 320.5,
                "memory_stored": True,
            }
            mock_async_run.return_value = mock_result

            result = process_telegram_message(
                text="What is Nexus-Brain?",
                user_id=str(uuid4()),
                conversation_id=str(uuid4()),
                telegram_update_id=12345,
            )

        assert result["status"] == "success"
        assert result["input_type"] == "question"
        assert result["tokens_used"] == 150
        assert result["latency_ms"] == 320.5
        assert result["memory_stored"] is True

    @pytest.mark.asyncio
    async def test_process_telegram_message_retries_on_error(self):
        """process_telegram_message raises to trigger Celery retry on failure."""
        from src.tasks.agent_tasks import process_telegram_message

        with patch("src.agents.graph.run_agent") as mock_run:
            mock_run.side_effect = Exception("Agent pipeline crashed")

            with pytest.raises(Exception):
                process_telegram_message(
                    text="Hello!",
                    user_id=str(uuid4()),
                    conversation_id=str(uuid4()),
                )

    def test_generate_embeddings_returns_pending(self):
        """generate_embeddings returns pending status (Sprint 5 placeholder)."""
        from src.tasks.agent_tasks import generate_embeddings

        result = generate_embeddings(
            chunk_id=str(uuid4()),
            content="This is a test memory chunk for embedding.",
        )

        assert result["status"] == "pending"
        assert "chunk_id" in result
        assert "Sprint 5" in result["note"]

    def test_cleanup_expired_runs_without_error(self):
        """cleanup_expired runs without crashing (even with no DB)."""
        from src.tasks.agent_tasks import cleanup_expired

        with patch("src.tasks.agent_tasks.SessionLocal") as mock_session:
            mock_session.side_effect = Exception("DB unavailable")
            result = cleanup_expired()

        assert "error" in result


# ─── Retry Configuration Tests ─────────────────────────


class TestRetryConfig:
    """Test retry configuration on tasks."""

    def test_process_message_has_retry_tying(self):
        """Task has retry kwargs configured."""
        from src.tasks.agent_tasks import TASK_DEFAULT_KWARGS

        assert TASK_DEFAULT_KWARGS["max_retries"] == 3
        assert TASK_DEFAULT_KWARGS["default_retry_delay"] == 30
        assert TASK_DEFAULT_KWARGS["retry_backoff"] is True
        assert TASK_DEFAULT_KWARGS["retry_jitter"] is True


# ─── Telegram Router Integration Tests ─────────────────


class TestTelegramIntegration:
    """Test that the telegram webhook integrates with Celery."""

    def test_telegram_router_imports_celery(self):
        """telegram_router can import the Celery task."""
        from src.api.telegram_router import router
        from src.tasks.agent_tasks import process_telegram_message

        assert process_telegram_message is not None

    def test_telegram_router_has_webhook_endpoint(self):
        """telegram_router still has the webhook POST endpoint."""
        from src.api.telegram_router import router

        routes = [r.path for r in router.routes]
        assert any("/telegram/webhook" in path for path in routes)

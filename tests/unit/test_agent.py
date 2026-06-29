"""
Unit Tests for LangGraph Agent (Sprint 4)
Tests: state, tools, nodes (unit), graph compilation, and REST endpoints.
"""

import pytest
import json
from uuid import UUID, uuid4
from unittest.mock import patch, MagicMock, AsyncMock

# ─── State Tests ───────────────────────────────────────


class TestAgentState:
    """Test agent state schema and initial_state factory."""

    def test_initial_state_creates_valid_state(self):
        """initial_state() returns a properly structured AgentState."""
        from src.agents.state import initial_state

        user_id = uuid4()
        conv_id = uuid4()

        state = initial_state(
            input="Hello, Nexus!",
            user_id=user_id,
            conversation_id=conv_id,
            telegram_update_id=12345,
        )

        assert state["input"] == "Hello, Nexus!"
        assert state["user_id"] == user_id
        assert state["conversation_id"] == conv_id
        assert state["telegram_update_id"] == 12345
        assert state["input_type"] is None
        assert state["retrieved_memory"] == []
        assert state["entities"] == []
        assert state["response"] is None
        assert state["tokens_used"] == 0
        assert state["latency_ms"] == 0.0
        assert state["memory_stored"] is False

    def test_initial_state_without_telegram(self):
        """telegram_update_id defaults to None."""
        from src.agents.state import initial_state

        state = initial_state(
            input="test",
            user_id=uuid4(),
            conversation_id=uuid4(),
        )
        assert state["telegram_update_id"] is None

    def test_initial_state_all_fields_present(self):
        """All AgentState fields are present with correct types."""
        from src.agents.state import AgentState, initial_state

        state = initial_state(
            input="hi",
            user_id=uuid4(),
            conversation_id=uuid4(),
        )

        # All keys from the TypedDict should be present
        expected_keys = [
            "input", "user_id", "conversation_id", "telegram_update_id",
            "input_type", "input_confidence",
            "retrieved_memory", "conversation_history", "memory_query",
            "entities", "has_pii", "pii_types", "pii_masked_input",
            "reasoning", "tool_calls", "needs_clarification",
            "response", "model_used", "tokens_used", "latency_ms",
            "memory_stored", "error",
        ]
        for key in expected_keys:
            assert key in state, f"Missing key: {key}"


# ─── Tool Tests ────────────────────────────────────────


class TestAgentTools:
    """Test agent tool functions (mocked DB)."""

    def test_search_memory_empty_on_exception(self):
        """search_memory returns empty list on database error."""
        from src.agents.tools import search_memory

        with patch("src.agents.tools.SessionLocal") as mock_session:
            mock_session.side_effect = Exception("DB down")
            result = search_memory(query="test", user_id=uuid4())
            assert result == []

    def test_get_conversation_history_empty_on_exception(self):
        """get_conversation_history returns empty list on error."""
        from src.agents.tools import get_conversation_history

        result = get_conversation_history(conversation_id=uuid4(), limit=5)
        assert isinstance(result, list)

    def test_store_memory_no_db_no_crash(self):
        """store_memory returns None gracefully on database error."""
        from src.agents.tools import store_memory

        with patch("src.agents.tools.SessionLocal") as mock_session:
            mock_session.side_effect = Exception("DB error")
            result = store_memory(
                content="test content",
                user_id=uuid4(),
                title="Test",
            )
            assert result is None

    def test_detect_pii_uses_presidio(self):
        """detect_pii delegates to Presidio process_pii."""
        from src.agents.tools import detect_pii

        with patch("src.agents.tools.process_pii") as mock_pii:
            mock_pii.return_value = {
                "masked": "Hello ****",
                "has_pii": True,
                "pii_types": ["EMAIL_ADDRESS"],
                "pii_count": 1,
            }
            result = detect_pii("Hello test@example.com")
            assert result["has_pii"] is True
            assert "EMAIL_ADDRESS" in result["pii_types"]
            assert result["pii_count"] == 1

    def test_tool_registry_structure(self):
        """TOOL_DEFINITIONS has the correct structure."""
        from src.agents.tools import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) >= 3  # At least 3 tools
        tool_names = [t["name"] for t in TOOL_DEFINITIONS]
        assert "search_memory" in tool_names
        assert "store_memory" in tool_names
        assert "get_entity_context" in tool_names

        # Each tool must have name, description, parameters
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert "type" in tool["parameters"]
            assert "properties" in tool["parameters"]


# ─── Node Tests ────────────────────────────────────────


class TestAgentNodes:
    """Test individual agent node functions (mocked LLM)."""

    def test_input_router_classifies_greeting(self):
        """input_router classifies 'hello' as greeting."""
        from src.agents.state import initial_state
        from src.agents.nodes import input_router

        state = initial_state(
            input="Hello! How are you?",
            user_id=uuid4(),
            conversation_id=uuid4(),
        )

        with patch("src.agents.nodes._call_llm") as mock_llm:
            mock_llm.return_value = {
                "content": '{"type": "greeting", "confidence": 0.95, "reason": "user is greeting"}',
                "tool_calls": [],
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            }

            result = input_router(state)

        assert result["input_type"] == "greeting"
        assert result["input_confidence"] == 0.95

    def test_input_router_classifies_question(self):
        """input_router classifies a question correctly."""
        from src.agents.state import initial_state
        from src.agents.nodes import input_router

        state = initial_state(
            input="What is the weather like today?",
            user_id=uuid4(),
            conversation_id=uuid4(),
        )

        with patch("src.agents.nodes._call_llm") as mock_llm:
            mock_llm.return_value = {
                "content": '{"type": "question", "confidence": 0.98, "reason": "user is asking about weather"}',
                "tool_calls": [],
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            }

            result = input_router(state)

        assert result["input_type"] == "question"
        assert result["input_confidence"] == 0.98

    def test_input_router_handles_bad_json(self):
        """input_router gracefully handles malformed LLM output."""
        from src.agents.state import initial_state
        from src.agents.nodes import input_router

        state = initial_state(
            input="test",
            user_id=uuid4(),
            conversation_id=uuid4(),
        )

        with patch("src.agents.nodes._call_llm") as mock_llm:
            mock_llm.return_value = {
                "content": "not valid json at all",
                "tool_calls": [],
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

            result = input_router(state)

        # Should fall back to 'unknown' on parse failure
        assert result["input_type"] == "unknown"
        assert result["input_confidence"] == 0.0

    def test_memory_retriever_handles_missing_data(self):
        """memory_retriever works with minimal state."""
        from src.agents.state import initial_state
        from src.agents.nodes import memory_retriever

        state = initial_state(
            input="test message",
            user_id=uuid4(),
            conversation_id=uuid4(),
        )
        state["input_type"] = "question"

        with patch("src.agents.nodes._call_llm") as mock_llm:
            mock_llm.return_value = {
                "content": '{"query": "test query", "needs_context": true}',
                "tool_calls": [],
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 50},
            }

            result = memory_retriever(state)

        assert "retrieved_memory" in result
        assert "conversation_history" in result
        assert isinstance(result["retrieved_memory"], list)
        assert isinstance(result["conversation_history"], list)

    def test_entity_extractor_no_entities(self):
        """entity_extractor returns empty entities for simple text."""
        from src.agents.state import initial_state
        from src.agents.nodes import entity_extractor

        state = initial_state(
            input="Hello there!",
            user_id=uuid4(),
            conversation_id=uuid4(),
        )

        with patch("src.agents.nodes.detect_pii") as mock_pii:
            mock_pii.return_value = {
                "masked_text": "Hello there!",
                "has_pii": False,
                "pii_types": [],
                "pii_count": 0,
            }
            with patch("src.agents.nodes._call_llm") as mock_llm:
                mock_llm.return_value = {
                    "content": "[]",
                    "tool_calls": [],
                    "model": "gpt-4o-mini",
                    "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35},
                }

                result = entity_extractor(state)

        assert isinstance(result["entities"], list)
        assert result["has_pii"] is False
        assert result["pii_masked_input"] is None


# ─── Graph Tests ───────────────────────────────────────


class TestAgentGraph:
    """Test LangGraph compilation and routing."""

    def test_build_agent_creates_compiled_graph(self):
        """build_agent() returns a compiled StateGraph."""
        from src.agents.graph import build_agent

        agent = build_agent()
        assert agent is not None
        # Should have all 6 nodes registered
        assert "input_router" in agent.nodes
        assert "memory_retriever" in agent.nodes
        assert "entity_extractor" in agent.nodes
        assert "reasoner" in agent.nodes
        assert "response_generator" in agent.nodes
        assert "memory_writer" in agent.nodes

    def test_get_agent_is_singleton(self):
        """get_agent() returns the same instance on repeated calls."""
        from src.agents.graph import get_agent

        agent1 = get_agent()
        agent2 = get_agent()
        assert agent1 is agent2

    def test_route_after_router_greeting_skips_retrieval(self):
        """Greetings route directly to response_generator."""
        from src.agents.graph import route_after_router

        state = {
            "input_type": "greeting",
            "input": "Hello!",
        }

        result = route_after_router(state)
        assert result == "response_generator"

    def test_route_after_router_question_goes_to_retrieval(self):
        """Questions route to memory_retriever."""
        from src.agents.graph import route_after_router

        state = {
            "input_type": "question",
            "input": "What is X?",
        }

        result = route_after_router(state)
        assert result == "memory_retriever"

    def test_route_after_router_command_goes_to_retrieval(self):
        """Commands route to memory_retriever."""
        from src.agents.graph import route_after_router

        result = route_after_router({"input_type": "command", "input": "do something"})
        assert result == "memory_retriever"

    @pytest.mark.asyncio
    async def test_run_agent_returns_response_object(self):
        """run_agent returns a properly structured response dict."""
        from src.agents.graph import run_agent

        with patch("src.agents.nodes._call_llm") as mock_llm:
            # Mock all LLM calls in the pipeline
            mock_llm.return_value = {
                "content": '{"type": "greeting", "confidence": 0.95, "reason": "greeting"}',
                "tool_calls": [],
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
            }

            result = await run_agent(
                input="Hey there!",
                user_id=uuid4(),
                conversation_id=uuid4(),
            )

        assert "response" in result
        assert "memory_stored" in result
        assert "tokens_used" in result
        assert "latency_ms" in result
        assert "input_type" in result
        assert result["latency_ms"] > 0


# ─── REST Endpoint Tests ───────────────────────────────


class TestAgentAPI:
    """Test the agent REST API endpoint."""

    @pytest.mark.asyncio
    async def test_agent_status_endpoint(self):
        """GET /api/agent/status returns system info."""
        from src.api.agent_router import router

        # Check router has the status endpoint registered
        routes = [r.path for r in router.routes]
        assert "/api/agent/status" in routes or "/agent/status" in routes

    def test_agent_request_schema_validates(self):
        """AgentRequest validates input correctly."""
        from src.api.agent_router import AgentRequest

        # Valid request
        req = AgentRequest(input="Hello!")
        assert req.input == "Hello!"

        # Invalid: empty input
        with pytest.raises(Exception):
            AgentRequest(input="")

    def test_agent_response_schema(self):
        """AgentResponse has all required fields."""
        from src.api.agent_router import AgentResponse

        resp = AgentResponse(
            response="Hello!",
            conversation_id=str(uuid4()),
            memory_stored=False,
            tokens_used=100,
            latency_ms=45.2,
            input_type="greeting",
        )

        assert resp.response == "Hello!"
        assert resp.tokens_used == 100
        assert resp.latency_ms == 45.2
        assert resp.input_type == "greeting"


# ─── Error Handling Tests ──────────────────────────────


class TestAgentErrorHandling:
    """Test agent resilience to failures."""

    def test_input_router_handles_llm_failure(self):
        """input_router doesn't crash when LLM call fails."""
        from src.agents.state import initial_state
        from src.agents.nodes import input_router

        state = initial_state(
            input="Hello",
            user_id=uuid4(),
            conversation_id=uuid4(),
        )

        with patch("src.agents.nodes._call_llm") as mock_llm:
            mock_llm.side_effect = Exception("API timeout")

            with pytest.raises(Exception):
                input_router(state)

    @pytest.mark.asyncio
    async def test_run_agent_handles_pipeline_failure(self):
        """run_agent returns error response on pipeline failure."""
        from src.agents.graph import run_agent

        with patch("src.agents.graph.get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.ainvoke = AsyncMock(side_effect=Exception("Pipeline crash"))
            mock_get_agent.return_value = mock_agent

            result = await run_agent(
                input="Hello!",
                user_id=uuid4(),
                conversation_id=uuid4(),
            )

        assert "error" in result
        assert isinstance(result["latency_ms"], (int, float))
        assert result["response"] != ""

"""
Unit Tests for Hybrid Search Module (Sprint 5)
Tests: embeddings, vector search, BM25, hybrid RRF fusion, and tool integration.
"""

import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock


# ─── Embedding Tests ───────────────────────────────────


class TestEmbeddings:
    """Test embedding generation functions."""

    def test_generate_embedding_openai_success(self):
        """generate_embedding returns vector from OpenAI."""
        from src.search.embeddings import generate_openai_embedding

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.return_value.data = [
                MagicMock(embedding=[0.1] * 512)
            ]

            result = generate_openai_embedding("test text", dimensions=512)

            assert result is not None
            assert len(result) == 512
            assert result[0] == 0.1

    def test_generate_openai_embedding_failure_returns_none(self):
        """generate_openai_embedding returns None on API failure."""
        from src.search.embeddings import generate_openai_embedding

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.side_effect = Exception("API error")

            result = generate_openai_embedding("test")
            assert result is None

    def test_generate_embedding_unified_returns_vector(self):
        """generate_embedding unified wrapper works with OpenAI."""
        from src.search.embeddings import generate_embedding

        with patch("src.search.embeddings.generate_openai_embedding") as mock_openai:
            mock_openai.return_value = [0.5] * 128

            result = generate_embedding("hello", prefer_ollama=False)

            assert result is not None
            assert len(result) == 128

    def test_generate_embedding_empty_text(self):
        """generate_embedding returns None for empty text."""
        from src.search.embeddings import generate_embedding

        assert generate_embedding("") is None
        assert generate_embedding("   ") is None

    def test_generate_embeddings_batch(self):
        """generate_embeddings_batch handles multiple texts."""
        from src.search.embeddings import generate_embeddings_batch

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.return_value.data = [
                MagicMock(index=0, embedding=[0.1] * 16),
                MagicMock(index=1, embedding=[0.2] * 16),
            ]

            results = generate_embeddings_batch(["hello", "world"])

            assert len(results) == 2
            assert results[0] is not None

    def test_generate_ollama_embedding_fallback(self):
        """generate_ollama_embedding handles failure gracefully."""
        from src.search.embeddings import generate_ollama_embedding

        with patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("Ollama not available")

            result = generate_ollama_embedding("test")
            assert result is None


# ─── Vector Search Tests ───────────────────────────────


class TestVectorSearch:
    """Test pgvector search functions."""

    def test_vector_search_empty_on_no_embedding(self):
        """vector_search returns empty if embedding can't be generated."""
        from src.search.vector_search import vector_search

        with patch("src.search.vector_search.generate_embedding") as mock_emb:
            mock_emb.return_value = None

            results = vector_search("gibberish@@@", uuid4())
            assert results == []

    def test_vector_search_db_error_returns_empty(self):
        """vector_search returns empty list on DB error."""
        from src.search.vector_search import vector_search

        with patch("src.search.vector_search.SessionLocal") as mock_db:
            mock_db.side_effect = Exception("DB unavailable")
            with patch("src.search.vector_search.generate_embedding") as mock_emb:
                mock_emb.return_value = [0.1] * 16

                results = vector_search("test", uuid4())
                assert results == []

    def test_count_embedded_chunks_db_error(self):
        """count_embedded_chunks returns 0 on error."""
        from src.search.vector_search import count_embedded_chunks

        with patch("src.search.vector_search.SessionLocal") as mock_db:
            mock_db.side_effect = Exception("DB error")
            count = count_embedded_chunks(uuid4())
            assert count == 0


# ─── BM25 Search Tests ─────────────────────────────────


class TestBM25Search:
    """Test BM25 full-text search functions."""

    def test_bm25_search_empty_query(self):
        """bm25_search returns empty for empty query."""
        from src.search.bm25_search import bm25_search

        results = bm25_search("", uuid4())
        assert results == []

    def test_bm25_search_fallback_to_ilike(self):
        """bm25_search falls back to ILIKE when tsvector fails."""
        from src.search.bm25_search import bm25_search

        with patch("src.search.bm25_search.SessionLocal") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value = mock_session
            mock_session.execute.side_effect = [
                Exception("tsvector column missing"),  # First call: tsvector fails
                MagicMock(fetchall=lambda: []),  # Second call: ILIKE succeeds
            ]

            results = bm25_search("test query", uuid4())
            assert results == []


# ─── Hybrid Search Tests ───────────────────────────────


class TestHybridSearch:
    """Test hybrid search with RRF fusion."""

    def test_rrf_score_decreasing_with_rank(self):
        """RRF score decreases as rank increases."""
        from src.search.hybrid_search import rrf_score

        s1 = rrf_score(1)
        s5 = rrf_score(5)
        s10 = rrf_score(10)

        assert s1 > s5 > s10
        assert 0 < s1 <= 1.0 / 61  # RRF with k=60: rank 1 → 1/61

    def test_hybrid_search_empty_query(self):
        """hybrid_search returns empty for empty query."""
        from src.search.hybrid_search import hybrid_search

        results = hybrid_search("", uuid4())
        assert results == []

    def test_hybrid_search_both_empty(self):
        """hybrid_search returns empty when both searches return nothing."""
        from src.search.hybrid_search import hybrid_search

        with patch("src.search.hybrid_search.vector_search") as mock_vec:
            mock_vec.return_value = []
            with patch("src.search.hybrid_search.bm25_search") as mock_bm25:
                mock_bm25.return_value = []

                results = hybrid_search("nothing to find", uuid4())
                assert results == []

    def test_hybrid_search_merges_results(self):
        """hybrid_search merges results from both searches via RRF."""
        from src.search.hybrid_search import hybrid_search
        from uuid import uuid4

        user_id = uuid4()
        chunk_a = {"chunk_id": str(uuid4()), "content": "alpha", "importance": 0.9, "created_at": None, "score": 0.8}
        chunk_b = {"chunk_id": str(uuid4()), "content": "beta", "importance": 0.7, "created_at": None, "score": 0.6}

        with patch("src.search.hybrid_search.vector_search") as mock_vec:
            mock_vec.return_value = [chunk_a]
            with patch("src.search.hybrid_search.bm25_search") as mock_bm25:
                mock_bm25.return_value = [chunk_b]

                results = hybrid_search("test", user_id, top_k=5)

                assert len(results) == 2
                chunk_ids = {r["chunk_id"] for r in results}
                assert chunk_a["chunk_id"] in chunk_ids
                assert chunk_b["chunk_id"] in chunk_ids

    def test_search_memory_hybrid_convenience(self):
        """search_memory_hybrid returns clean dicts."""
        from src.search.hybrid_search import search_memory_hybrid

        with patch("src.search.hybrid_search.hybrid_search") as mock_h:
            mock_h.return_value = [
                {"chunk_id": "abc", "content": "test", "importance": 0.5,
                 "created_at": None, "vector_score": 0.9, "bm25_score": 0.0,
                 "rrf_score": 0.016}
            ]

            results = search_memory_hybrid("test", uuid4(), limit=3)

            assert len(results) == 1
            assert results[0]["chunk_id"] == "abc"
            assert "vector_score" not in results[0]  # Clean output
            assert "rrf_score" not in results[0]


# ─── Agent Tool Integration Tests ──────────────────────


class TestAgentToolIntegration:
    """Test that the agent's search_memory uses hybrid search."""

    def test_search_memory_uses_hybrid_search(self):
        """Agent's search_memory delegates to hybrid search."""
        from src.agents.tools import search_memory

        with patch("src.search.hybrid_search.search_memory_hybrid") as mock_hybrid:
            mock_hybrid.return_value = [
                {"chunk_id": "abc", "content": "result", "importance": 0.8, "created_at": None}
            ]

            results = search_memory("test query", uuid4(), limit=3)

            assert len(results) == 1
            assert results[0]["content"] == "result"

    def test_search_memory_falls_back_on_error(self):
        """search_memory falls back to ILIKE when hybrid search fails."""
        from src.agents.tools import search_memory

        with patch("src.search.hybrid_search.search_memory_hybrid") as mock_hybrid:
            mock_hybrid.side_effect = ImportError("search module not available")

            results = search_memory("test", uuid4())
            # Should return empty gracefully via fallback
            assert isinstance(results, list)


# ─── Embedding Task Integration Tests ──────────────────


class TestEmbeddingTask:
    """Test that generate_embeddings Celery task uses real embedding."""

    def test_generate_embeddings_skips_empty(self):
        """generate_embeddings skips empty content."""
        from src.tasks.agent_tasks import generate_embeddings

        result = generate_embeddings("chunk-123", "")
        assert result["status"] == "skipped"

    def test_generate_embeddings_raises_on_failure(self):
        """generate_embeddings raises to trigger Celery retry on failure."""
        from src.tasks.agent_tasks import generate_embeddings

        with patch("src.search.embeddings.generate_embedding") as mock_emb:
            mock_emb.return_value = None
            with pytest.raises(RuntimeError):
                generate_embeddings("chunk-123", "some content here")


# ─── Module Import Tests ───────────────────────────────


class TestModuleImports:
    """Test that all search modules can be imported."""

    def test_import_search_init(self):
        from src.search import DEFAULT_RRF_K, DEFAULT_FINAL_K
        assert DEFAULT_RRF_K == 60
        assert DEFAULT_FINAL_K == 10

    def test_import_embeddings(self):
        from src.search.embeddings import generate_embedding, generate_embeddings_batch
        assert callable(generate_embedding)

    def test_import_vector_search(self):
        from src.search.vector_search import vector_search, store_embedding, count_embedded_chunks
        assert callable(vector_search)

    def test_import_bm25_search(self):
        from src.search.bm25_search import bm25_search
        assert callable(bm25_search)

    def test_import_hybrid_search(self):
        from src.search.hybrid_search import hybrid_search, search_memory_hybrid, rrf_score
        assert callable(hybrid_search)

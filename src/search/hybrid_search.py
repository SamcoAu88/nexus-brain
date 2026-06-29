"""
Hybrid Search
Reciprocal Rank Fusion (RRF) combining vector search + BM25 results.
"""

import logging
from typing import List, Dict, Any
from uuid import UUID

from src.search import (
    DEFAULT_RRF_K,
    DEFAULT_VECTOR_WEIGHT,
    DEFAULT_BM25_WEIGHT,
    DEFAULT_FINAL_K,
)
from src.search.vector_search import vector_search
from src.search.bm25_search import bm25_search

logger = logging.getLogger(__name__)


def rrf_score(rank: int, k: int = DEFAULT_RRF_K) -> float:
    """
    Reciprocal Rank Fusion score for a given rank position.

    Args:
        rank: 1-based rank position
        k: RRF constant (default 60, matches typical BM25 hybrid config)

    Returns:
        RRF score contribution
    """
    return 1.0 / (k + rank)


def hybrid_search(
    query: str,
    user_id: UUID,
    top_k: int = DEFAULT_FINAL_K,
    vector_weight: float = DEFAULT_VECTOR_WEIGHT,
    bm25_weight: float = DEFAULT_BM25_WEIGHT,
    min_importance: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Hybrid search combining vector (semantic) + BM25 (keyword) results
    using Reciprocal Rank Fusion with weighted scoring.

    Args:
        query: User's search query
        user_id: Scope to this user
        top_k: Final number of results
        vector_weight: Weight for vector search scores (0.0-1.0)
        bm25_weight: Weight for BM25 scores (0.0-1.0)
        min_importance: Minimum importance filter

    Returns:
        Merged and reranked results with combined scores
    """
    from src.search import DEFAULT_TOP_K as FETCH_K

    if not query or not query.strip():
        return []

    # ─── Run both searches in parallel ─────────────────
    vector_results = vector_search(
        query=query,
        user_id=user_id,
        top_k=FETCH_K,
        min_importance=min_importance,
    )

    bm25_results = bm25_search(
        query=query,
        user_id=user_id,
        top_k=FETCH_K,
        min_importance=min_importance,
    )

    if not vector_results and not bm25_results:
        return []

    # ─── RRF Fusion ────────────────────────────────────
    chunk_scores: Dict[str, Dict[str, Any]] = {}

    # Vector search contributions
    for rank, result in enumerate(vector_results, start=1):
        chunk_id = result["chunk_id"]
        rrf = rrf_score(rank) * vector_weight
        chunk_scores[chunk_id] = {
            "chunk_id": chunk_id,
            "content": result["content"],
            "importance": result["importance"],
            "created_at": result["created_at"],
            "vector_score": result.get("score", 0.0),
            "bm25_score": 0.0,
            "rrf_score": rrf,
        }

    # BM25 search contributions
    for rank, result in enumerate(bm25_results, start=1):
        chunk_id = result["chunk_id"]
        rrf = rrf_score(rank) * bm25_weight

        if chunk_id in chunk_scores:
            chunk_scores[chunk_id]["bm25_score"] = result.get("score", 0.0)
            chunk_scores[chunk_id]["rrf_score"] += rrf
        else:
            chunk_scores[chunk_id] = {
                "chunk_id": chunk_id,
                "content": result["content"],
                "importance": result["importance"],
                "created_at": result["created_at"],
                "vector_score": 0.0,
                "bm25_score": result.get("score", 0.0),
                "rrf_score": rrf,
            }

    # ─── Sort by RRF score and return top_k ────────────
    sorted_results = sorted(
        chunk_scores.values(),
        key=lambda x: x["rrf_score"],
        reverse=True,
    )[:top_k]

    return sorted_results


def search_memory_hybrid(
    query: str,
    user_id: UUID,
    limit: int = DEFAULT_FINAL_K,
    min_importance: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Convenience wrapper for use by the agent's tools.

    Args:
        query: Search query
        user_id: User UUID
        limit: Max results
        min_importance: Minimum importance (0.0-1.0)

    Returns:
        List of memory results
    """
    results = hybrid_search(
        query=query,
        user_id=user_id,
        top_k=limit,
        min_importance=min_importance,
    )

    # Return clean dicts (compatible with agent tool interface)
    return [
        {
            "chunk_id": r["chunk_id"],
            "content": r["content"],
            "importance": r["importance"],
            "created_at": r["created_at"],
        }
        for r in results
    ]

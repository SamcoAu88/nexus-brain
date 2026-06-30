"""
BM25-Style Full-Text Search
Uses PostgreSQL tsvector/tsquery for keyword-based retrieval.
Falls back to ILIKE when tsvector column is not available.
"""

import logging
from typing import List, Dict, Any
from uuid import UUID

from sqlalchemy import text
from src.core.database import SessionLocal
from src.models.memory import MemoryChunk, Source
from src.search import DEFAULT_TOP_K, DEFAULT_BM25_WEIGHT

logger = logging.getLogger(__name__)


def bm25_search(
    query: str,
    user_id: UUID,
    top_k: int = DEFAULT_TOP_K,
    min_importance: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Full-text search using PostgreSQL tsvector (BM25-equivalent ranking).

    Falls back to ILIKE when tsvector search is not available.

    Args:
        query: Search keywords
        user_id: Scope to this user (must be UUID)
        top_k: Number of results
        min_importance: Minimum importance filter

    Returns:
        List of result dicts with chunk_id, content, score, importance
    """
    # CRITICAL: Ensure user_id is actually a UUID object, not a string
    if isinstance(user_id, str):
        logger.warning(f"bm25_search: user_id is string, converting to UUID: {user_id}")
        try:
            user_id = UUID(user_id)
        except ValueError as e:
            logger.error(f"bm25_search: Failed to convert user_id to UUID: {e}")
            return []

    logger.debug(f"🔍 bm25_search: query='{query[:30]}...', user_id={user_id}, top_k={top_k}")

    db = SessionLocal()
    try:
        # Try tsvector search first (requires migration)
        try:
            return _tsvector_search(db, query, user_id, top_k, min_importance)
        except Exception:
            # Fallback to ILIKE if tsvector column doesn't exist
            logger.info("BM25 tsvector unavailable, falling back to ILIKE search")
            return _ilike_search(db, query, user_id, top_k, min_importance)

    except Exception as e:
        logger.error(f"BM25 search failed: {e}")
        return []
    finally:
        db.close()


def _tsvector_search(
    db,
    query: str,
    user_id: UUID,
    top_k: int,
    min_importance: float,
) -> List[Dict[str, Any]]:
    """
    PostgreSQL tsvector full-text search with ts_rank ranking.
    """
    # Convert query to tsquery format
    tsquery = " & ".join(query.strip().split()[:10])  # Max 10 terms

    if not tsquery:
        return []

    sql = text(
        """
        SELECT
            mc.chunk_id,
            mc.content,
            mc.importance,
            mc.created_at,
            ts_rank(mc.search_vector, to_tsquery('english', :tsquery)) AS score
        FROM memory_chunks mc
        JOIN sources s ON mc.source_id = s.source_id
        JOIN collections c ON s.collection_id = c.collection_id
        WHERE c.user_id = :user_id::uuid
          AND mc.is_deleted = false
          AND mc.search_vector IS NOT NULL
          AND mc.search_vector @@ to_tsquery('english', :tsquery)
          AND mc.importance >= :min_importance
        ORDER BY score DESC
        LIMIT :top_k
        """
    )

    results = db.execute(
        sql,
        {
            "tsquery": tsquery,
            "user_id": str(user_id),  # Convert UUID to string for PostgreSQL
            "top_k": top_k,
            "min_importance": min_importance,
        },
    ).fetchall()

    return [
        {
            "chunk_id": str(row.chunk_id),
            "content": row.content,
            "importance": row.importance,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "score": float(row.score) if row.score is not None else 0.0,
        }
        for row in results
    ]


def _ilike_search(
    db,
    query: str,
    user_id: UUID,
    top_k: int,
    min_importance: float,
) -> List[Dict[str, Any]]:
    """
    Fallback: simple ILIKE keyword search.
    Works without the tsvector migration.
    """
    from src.models.memory import Collection

    terms = query.strip().split()
    if not terms:
        return []

    # Build OR conditions for all terms
    conditions = " OR ".join(
        f"mc.content ILIKE :term{i}" for i in range(len(terms))
    )

    params = {f"term{i}": f"%{term}%" for i, term in enumerate(terms[:5])}
    params["user_id"] = str(user_id)  # Convert UUID to string for PostgreSQL
    params["top_k"] = top_k
    params["min_importance"] = min_importance

    # Score based on how many terms match (simple heuristic)
    sql = text(
        f"""
        SELECT
            mc.chunk_id,
            mc.content,
            mc.importance,
            mc.created_at,
            CAST((
                { ' + '.join(f'CASE WHEN mc.content ILIKE :term{i} THEN 1.0 ELSE 0.0 END' for i in range(len(terms[:5]))) }
            ) AS FLOAT) / {len(terms[:5])} AS score
        FROM memory_chunks mc
        JOIN sources s ON mc.source_id = s.source_id
        JOIN collections c ON s.collection_id = c.collection_id
        WHERE c.user_id = :user_id::uuid
          AND mc.is_deleted = false
          AND mc.importance >= :min_importance
          AND ({conditions})
        ORDER BY score DESC, mc.importance DESC
        LIMIT :top_k
        """
    )

    results = db.execute(sql, params).fetchall()

    return [
        {
            "chunk_id": str(row.chunk_id),
            "content": row.content,
            "importance": row.importance,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "score": float(row.score) if row.score is not None else 0.0,
        }
        for row in results
    ]

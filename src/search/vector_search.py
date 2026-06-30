"""
Vector Search with pgvector
Performs cosine similarity search using pgvector extension on memory_chunks.embedding.
"""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy import text
from src.core.database import SessionLocal
from src.models.memory import MemoryChunk, Source
from src.search import DEFAULT_TOP_K
from src.search.embeddings import generate_embedding

logger = logging.getLogger(__name__)

# ─── pgvector Query ────────────────────────────────────


def vector_search(
    query: str,
    user_id: UUID,
    top_k: int = DEFAULT_TOP_K,
    min_importance: float = 0.0,
    embedding: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """
    Search memory chunks using pgvector cosine similarity.

    Args:
        query: User's search query
        user_id: Scope to this user (must be UUID)
        top_k: Number of results to return
        min_importance: Minimum importance filter
        embedding: Pre-computed embedding (will generate if None)

    Returns:
        List of result dicts with chunk_id, content, score, importance
    """
    # CRITICAL: Ensure user_id is actually a UUID object, not a string
    if isinstance(user_id, str):
        logger.warning(f"vector_search: user_id is string, converting to UUID: {user_id}")
        try:
            user_id = UUID(user_id)
        except ValueError as e:
            logger.error(f"vector_search: Failed to convert user_id to UUID: {e}")
            return []

    # Generate embedding if not provided
    if embedding is None:
        embedding = generate_embedding(query)
        if embedding is None:
            logger.warning("Could not generate embedding for vector search")
            return []

    db = None
    try:
        db = SessionLocal()
        logger.debug(f"🔍 vector_search: query='{query[:30]}...', user_id={user_id}, top_k={top_k}")

        # pgvector cosine similarity via <=> operator
        # The embedding column is stored as vector(1536)
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        sql = text(
            """
            SELECT
                mc.chunk_id,
                mc.content,
                mc.importance,
                mc.created_at,
                1 - (mc.embedding <=> :embedding::vector) AS score
            FROM memory_chunks mc
            JOIN sources s ON mc.source_id = s.source_id
            JOIN collections c ON s.collection_id = c.collection_id
            WHERE c.user_id = :user_id::uuid
              AND mc.is_deleted = false
              AND mc.embedding IS NOT NULL
              AND mc.importance >= :min_importance
            ORDER BY score DESC
            LIMIT :top_k
            """
        )

        results = db.execute(
            sql,
            {
                "embedding": embedding_str,
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

    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return []
    finally:
        if db is not None:
            db.close()


def store_embedding(chunk_id: UUID, embedding: List[float]) -> bool:
    """
    Store a pre-computed embedding vector for a chunk.

    Args:
        chunk_id: Chunk to update
        embedding: 1536-dim embedding vector

    Returns:
        True if successful
    """
    db = None
    try:
        db = SessionLocal()
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        sql = text(
            """
            UPDATE memory_chunks
            SET embedding = :embedding::vector
            WHERE chunk_id = :chunk_id
            """
        )

        db.execute(
            sql,
            {
                "embedding": embedding_str,
                "chunk_id": chunk_id,
            },
        )
        db.commit()
        logger.debug(f"✅ Stored embedding for chunk {chunk_id}")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to store embedding: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def count_embedded_chunks(user_id: UUID) -> int:
    """
    Count chunks that have embeddings for a user.

    Args:
        user_id: User to scope to

    Returns:
        Count of chunks with non-null embedding
    """
    db = None
    try:
        db = SessionLocal()
        sql = text(
            """
            SELECT COUNT(*) as cnt
            FROM memory_chunks mc
            JOIN sources s ON mc.source_id = s.source_id
            JOIN collections c ON s.collection_id = c.collection_id
            WHERE c.user_id = :user_id
              AND mc.embedding IS NOT NULL
              AND mc.is_deleted = false
            """
        )
        result = db.execute(sql, {"user_id": user_id}).scalar()
        return result or 0
    except Exception as e:
        logger.error(f"Count embedded chunks failed: {e}")
        return 0
    finally:
        if db is not None:
            db.close()

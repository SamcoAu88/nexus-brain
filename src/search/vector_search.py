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

        # NOTE: This database does NOT have the pgvector extension — the
        # embedding column is a plain float8[] array. Cosine similarity is
        # computed in Python, which is more than fast enough for a personal
        # memory store (thousands of chunks).
        from src.models.memory import Collection

        rows = (
            db.query(
                MemoryChunk.chunk_id,
                MemoryChunk.content,
                MemoryChunk.importance,
                MemoryChunk.created_at,
                MemoryChunk.embedding,
            )
            .join(Source, MemoryChunk.source_id == Source.source_id)
            .join(Collection, Source.collection_id == Collection.collection_id)
            .filter(
                Collection.user_id == user_id,
                MemoryChunk.is_deleted == False,
                MemoryChunk.embedding.isnot(None),
                MemoryChunk.importance >= min_importance,
            )
            .all()
        )

        scored = []
        for row in rows:
            score = _cosine_similarity(embedding, row.embedding)
            if score is not None:
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {
                "chunk_id": str(row.chunk_id),
                "content": row.content,
                "importance": row.importance,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "score": float(score),
            }
            for score, row in scored[:top_k]
        ]

    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return []
    finally:
        if db is not None:
            db.close()


def _cosine_similarity(a, b) -> Optional[float]:
    """Cosine similarity between two float lists. Returns None on mismatch."""
    try:
        if a is None or b is None or len(a) != len(b):
            return None
        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for x, y in zip(a, b):
            dot += x * y
            norm_a += x * x
            norm_b += y * y
        if norm_a == 0.0 or norm_b == 0.0:
            return None
        return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))
    except Exception:
        return None


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
        # embedding column is float8[] — SQLAlchemy handles a Python list natively
        updated = (
            db.query(MemoryChunk)
            .filter(MemoryChunk.chunk_id == chunk_id)
            .update({"embedding": embedding}, synchronize_session=False)
        )
        db.commit()

        if updated == 0:
            logger.warning(f"store_embedding: no chunk found with id {chunk_id}")
            return False

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

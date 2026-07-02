"""
One-off backfill: generate embeddings for memory chunks where embedding IS NULL.
Run inside the API/Celery container:
    docker exec nexus-celery python scripts/backfill_embeddings.py
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill")

from src.core.database import SessionLocal
from src.models.memory import MemoryChunk
from src.search.embeddings import generate_embedding
from src.search.vector_search import store_embedding


def main():
    db = SessionLocal()
    try:
        chunks = (
            db.query(MemoryChunk)
            .filter(
                MemoryChunk.embedding.is_(None),
                MemoryChunk.is_deleted == False,
            )
            .all()
        )
        logger.info(f"Found {len(chunks)} chunks without embeddings")

        ok, failed = 0, 0
        for chunk in chunks:
            if not chunk.content or not chunk.content.strip():
                logger.warning(f"Skipping empty chunk {chunk.chunk_id}")
                continue

            embedding = generate_embedding(chunk.content)
            if embedding is None:
                failed += 1
                logger.error(f"Embedding failed for chunk {chunk.chunk_id}")
                continue

            if store_embedding(chunk.chunk_id, embedding):
                ok += 1
                logger.info(f"OK  {chunk.chunk_id}  ({len(embedding)} dims)")
            else:
                failed += 1
                logger.error(f"Store failed for chunk {chunk.chunk_id}")

        logger.info(f"Done: {ok} embedded, {failed} failed")
        return 0 if failed == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

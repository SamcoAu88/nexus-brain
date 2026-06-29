"""Add search_vector column and GIN index for full-text search

Revision ID: a1b2c3d4e5f6
Revises: a98554c378c2
Create Date: 2026-06-29 18:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "a98554c378c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add search_vector column and GIN index for FTS."""

    # 1. Add search_vector tsvector column
    op.add_column(
        "memory_chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            nullable=True,
        ),
    )

    # 2. Create GIN index on search_vector
    op.create_index(
        "idx_memory_chunks_search_vector",
        "memory_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )

    # 3. Create trigger function to auto-update tsvector on content change
    op.execute(
        """
        CREATE OR REPLACE FUNCTION memory_chunks_tsvector_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    # 4. Create trigger on memory_chunks
    op.execute(
        """
        CREATE TRIGGER trg_memory_chunks_tsvector
        BEFORE INSERT OR UPDATE OF content
        ON memory_chunks
        FOR EACH ROW
        EXECUTE FUNCTION memory_chunks_tsvector_update()
        """
    )

    # 5. Backfill existing rows
    op.execute(
        """
        UPDATE memory_chunks
        SET search_vector = to_tsvector('english', COALESCE(content, ''))
        WHERE search_vector IS NULL
        """
    )


def downgrade() -> None:
    """Remove search_vector column and trigger."""

    op.execute("DROP TRIGGER IF EXISTS trg_memory_chunks_tsvector ON memory_chunks")
    op.execute("DROP FUNCTION IF EXISTS memory_chunks_tsvector_update()")
    op.drop_index("idx_memory_chunks_search_vector", table_name="memory_chunks")
    op.drop_column("memory_chunks", "search_vector")

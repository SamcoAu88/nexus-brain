"""
Agent Tool Definitions
Tools that the LangGraph agent can invoke during reasoning.
"""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone

from src.core.database import SessionLocal
from src.models.memory import MemoryChunk, Source, Entity, Conversation, Message
from src.security.pii import process_pii

logger = logging.getLogger(__name__)

# ─── Memory Tools ───────────────────────────────────────


def search_memory(
    query: str,
    user_id: UUID,
    limit: int = 5,
    min_importance: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Search memory chunks by content similarity (basic keyword fallback until
    Sprint 5 implements full hybrid search).

    Args:
        query: Search query text
        user_id: User to scope results to
        limit: Max results to return
        min_importance: Minimum importance threshold (0.0-1.0)

    Returns:
        List of matching chunk dicts
    """
    db = None
    try:
        db = SessionLocal()
        # Keyword-based search via user's sources → chunks
        from src.models.memory import Collection

        results = (
            db.query(MemoryChunk)
            .join(Source, MemoryChunk.source_id == Source.source_id)
            .join(Collection, Source.collection_id == Collection.collection_id)
            .filter(
                Collection.user_id == user_id,
                MemoryChunk.content.ilike(f"%{query}%"),
                MemoryChunk.importance >= min_importance,
                MemoryChunk.is_deleted == False,
            )
            .limit(limit)
            .all()
        )

        return [
            {
                "chunk_id": str(c.chunk_id),
                "content": c.content,
                "importance": c.importance,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in results
        ]
    except Exception as e:
        logger.error(f"Memory search error: {e}")
        return []
    finally:
        if db is not None:
            db.close()


def get_conversation_history(
    conversation_id: UUID,
    limit: int = 10,
) -> List[Dict[str, str]]:
    """
    Retrieve recent messages from a conversation.

    Args:
        conversation_id: Conversation to fetch
        limit: Number of most recent messages

    Returns:
        List of message dicts with role and content
    """
    db = None
    try:
        db = SessionLocal()
        messages = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                Message.content_masked.isnot(None),  # Use masked for safety
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )

        # Return in chronological order
        messages.reverse()

        return [
            {
                "role": m.role,
                "content": m.content_masked or m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    except Exception as e:
        logger.error(f"Conversation history error: {e}")
        return []
    finally:
        if db is not None:
            db.close()


def store_memory(
    content: str,
    user_id: UUID,
    collection_name: str = "Agent Memory",
    source_type: str = "agent",
    title: Optional[str] = None,
    importance: float = 0.5,
) -> Optional[str]:
    """
    Store content as a new memory source with chunks.

    Args:
        content: Text content to store
        user_id: Owner user
        collection_name: Collection to store under
        source_type: Type of source
        title: Optional title
        importance: Importance score (0.0-1.0)

    Returns:
        Source ID if successful, None otherwise
    """
    from src.models.memory import Collection

    db = None
    try:
        db = SessionLocal()
        # Find or create collection
        collection = (
            db.query(Collection)
            .filter(
                Collection.user_id == user_id,
                Collection.name == collection_name,
            )
            .first()
        )

        if not collection:
            collection = Collection(
                user_id=user_id,
                name=collection_name,
                description="Auto-created by agent memory writer",
            )
            db.add(collection)
            db.flush()

        # Create source
        source = Source(
            collection_id=collection.collection_id,
            source_type=source_type,
            title=title or f"Agent Memory - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            raw_content=content,
            meta_data={
                "created_by": "agent",
                "importance": importance,
            },
        )
        db.add(source)
        db.flush()

        # Create chunk
        chunk = MemoryChunk(
            source_id=source.source_id,
            content=content,
            chunk_index=0,
            importance=importance,
        )
        db.add(chunk)
        db.commit()

        logger.info(f"✅ Memory stored: source={source.source_id}")
        return str(source.source_id)

    except Exception as e:
        if db is not None:
            db.rollback()
        logger.error(f"Memory storage error: {e}")
        return None
    finally:
        if db is not None:
            db.close()


def get_entity_context(
    user_id: UUID,
    entity_types: Optional[List[str]] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Retrieve known entities for context enrichment.

    Args:
        user_id: User to scope results to
        entity_types: Filter by entity types (e.g., ['person', 'place'])
        limit: Max entities

    Returns:
        List of entity dicts
    """
    db = None
    try:
        db = SessionLocal()
        query = db.query(Entity).filter(Entity.user_id == user_id)

        if entity_types:
            query = query.filter(Entity.entity_type.in_(entity_types))

        entities = query.order_by(Entity.updated_at.desc()).limit(limit).all()

        return [
            {
                "entity_id": str(e.entity_id),
                "name": e.name,
                "entity_type": e.entity_type,
                "description": e.description,
            }
            for e in entities
        ]
    except Exception as e:
        logger.error(f"Entity context error: {e}")
        return []
    finally:
        if db is not None:
            db.close()


def detect_pii(text: str) -> Dict[str, Any]:
    """
    Detect and mask PII in text using Presidio.

    Args:
        text: Text to analyze

    Returns:
        Dict with masked text and PII info
    """
    result = process_pii(text, mask=True)
    return {
        "masked_text": result.get("masked", text),
        "has_pii": result.get("has_pii", False),
        "pii_types": result.get("pii_types", []),
        "pii_count": result.get("pii_count", 0),
    }


# ─── Tool Registry ──────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "search_memory",
        "description": "Search the user's stored memories for relevant information. Use this when the user asks a question that might be answered by their past notes, messages, or stored content.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant memories",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "store_memory",
        "description": "Store important information from the conversation as a new memory. Use this when the user shares something worth remembering (preferences, facts, plans).",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to remember",
                },
                "title": {
                    "type": "string",
                    "description": "A short title for this memory",
                },
                "importance": {
                    "type": "number",
                    "description": "Importance score 0.0-1.0 (default: 0.5)",
                },
            },
            "required": ["content", "title"],
        },
    },
    {
        "name": "get_entity_context",
        "description": "Retrieve known entities (people, places, concepts) related to the user to enrich the agent's understanding.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by entity types like person, place, concept",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum entities to return (default: 10)",
                },
            },
        },
    },
]

"""
Memory Management Router
CRUD operations for collections, sources, chunks, conversations, and messages
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
import logging
from src.core.database import SessionLocal
from src.models.memory import Collection, Source, MemoryChunk, Conversation, Message
from src.schemas.memory import (
    CollectionCreate,
    CollectionResponse,
    SourceCreate,
    SourceResponse,
    MemoryChunkCreate,
    MemoryChunkResponse,
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# TODO: Add authentication dependency
# from src.auth import get_current_user


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# COLLECTION ENDPOINTS
# ============================================================


@router.post("/collections", response_model=CollectionResponse, tags=["collections"])
async def create_collection(
    collection: CollectionCreate,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """Create a new collection"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db_collection = Collection(
        user_id=user_id, name=collection.name, description=collection.description
    )
    db.add(db_collection)
    db.commit()
    db.refresh(db_collection)
    logger.info(f"Created collection {db_collection.collection_id} for user {user_id}")
    return db_collection


@router.get(
    "/collections", response_model=list[CollectionResponse], tags=["collections"]
)
async def list_collections(
    db: Session = Depends(get_db), user_id: UUID = None  # TODO: From auth
):
    """List all collections for user"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    collections = db.query(Collection).filter(Collection.user_id == user_id).all()
    return collections


@router.get(
    "/collections/{collection_id}",
    response_model=CollectionResponse,
    tags=["collections"],
)
async def get_collection(
    collection_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """Get a specific collection"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    collection = (
        db.query(Collection)
        .filter(
            Collection.collection_id == collection_id, Collection.user_id == user_id
        )
        .first()
    )

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    return collection


@router.delete("/collections/{collection_id}", status_code=204, tags=["collections"])
async def delete_collection(
    collection_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """Delete a collection"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    collection = (
        db.query(Collection)
        .filter(
            Collection.collection_id == collection_id, Collection.user_id == user_id
        )
        .first()
    )

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    db.delete(collection)
    db.commit()
    logger.info(f"Deleted collection {collection_id}")
    return None


# ============================================================
# SOURCE ENDPOINTS
# ============================================================


@router.post(
    "/collections/{collection_id}/sources",
    response_model=SourceResponse,
    tags=["sources"],
)
async def create_source(
    collection_id: UUID,
    source: SourceCreate,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """Create a new source in a collection"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Verify collection belongs to user
    collection = (
        db.query(Collection)
        .filter(
            Collection.collection_id == collection_id, Collection.user_id == user_id
        )
        .first()
    )

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    db_source = Source(
        collection_id=collection_id,
        source_type=source.source_type,
        title=source.title,
        url=source.url,
        raw_content=source.raw_content,
        meta_data=source.meta_data or {},
    )
    db.add(db_source)
    db.commit()
    db.refresh(db_source)
    logger.info(f"Created source {db_source.source_id}")
    return db_source


@router.get(
    "/collections/{collection_id}/sources",
    response_model=list[SourceResponse],
    tags=["sources"],
)
async def list_sources(
    collection_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """List all sources in a collection"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Verify collection
    collection = (
        db.query(Collection)
        .filter(
            Collection.collection_id == collection_id, Collection.user_id == user_id
        )
        .first()
    )

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    sources = (
        db.query(Source)
        .filter(Source.collection_id == collection_id, ~Source.is_deleted)
        .all()
    )
    return sources


# ============================================================
# MEMORY CHUNK ENDPOINTS
# ============================================================


@router.post(
    "/sources/{source_id}/chunks", response_model=MemoryChunkResponse, tags=["chunks"]
)
async def create_chunk(
    source_id: UUID,
    chunk: MemoryChunkCreate,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """Create a memory chunk"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Verify source exists and belongs to user's collection
    source = (
        db.query(Source)
        .join(Collection)
        .filter(Source.source_id == source_id, Collection.user_id == user_id)
        .first()
    )

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    db_chunk = MemoryChunk(
        source_id=source_id,
        content=chunk.content,
        chunk_index=chunk.chunk_index,
        importance=chunk.importance,
    )
    db.add(db_chunk)
    db.commit()
    db.refresh(db_chunk)
    logger.info(f"Created chunk {db_chunk.chunk_id}")
    return db_chunk


@router.get(
    "/sources/{source_id}/chunks",
    response_model=list[MemoryChunkResponse],
    tags=["chunks"],
)
async def list_chunks(
    source_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """List all chunks for a source"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Verify source
    source = (
        db.query(Source)
        .join(Collection)
        .filter(Source.source_id == source_id, Collection.user_id == user_id)
        .first()
    )

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    chunks = (
        db.query(MemoryChunk)
        .filter(MemoryChunk.source_id == source_id, ~MemoryChunk.is_deleted)
        .order_by(MemoryChunk.chunk_index)
        .all()
    )
    return chunks


# ============================================================
# CONVERSATION ENDPOINTS
# ============================================================


@router.post(
    "/conversations", response_model=ConversationResponse, tags=["conversations"]
)
async def create_conversation(
    conversation: ConversationCreate,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """Create a new conversation"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db_conversation = Conversation(user_id=user_id, title=conversation.title)
    db.add(db_conversation)
    db.commit()
    db.refresh(db_conversation)
    logger.info(f"Created conversation {db_conversation.conversation_id}")
    return db_conversation


@router.get(
    "/conversations", response_model=list[ConversationResponse], tags=["conversations"]
)
async def list_conversations(
    db: Session = Depends(get_db), user_id: UUID = None  # TODO: From auth
):
    """List all conversations for user"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, ~Conversation.is_archived)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return conversations


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    tags=["conversations"],
)
async def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """Get a specific conversation"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.conversation_id == conversation_id,
            Conversation.user_id == user_id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


# ============================================================
# MESSAGE ENDPOINTS
# ============================================================


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    tags=["messages"],
)
async def create_message(
    conversation_id: UUID,
    message: MessageCreate,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """Add a message to a conversation"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Verify conversation
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.conversation_id == conversation_id,
            Conversation.user_id == user_id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db_message = Message(
        conversation_id=conversation_id,
        role=message.role,
        content=message.content,
        tokens_used=message.tokens_used,
        model_used=message.model_used,
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    logger.info(f"Created message {db_message.message_id}")
    return db_message


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
    tags=["messages"],
)
async def list_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = None,  # TODO: From auth
):
    """List all messages in a conversation"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Verify conversation
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.conversation_id == conversation_id,
            Conversation.user_id == user_id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    return messages

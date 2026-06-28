"""Pydantic schemas for memory operations"""

from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional

# ============ Collection Schemas ============


class CollectionCreate(BaseModel):
    """Create a new collection"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class CollectionResponse(BaseModel):
    """Collection response"""

    collection_id: UUID
    user_id: UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Source Schemas ============


class SourceCreate(BaseModel):
    """Create a new source (document, link, etc)"""

    source_type: str = Field(
        ..., min_length=1, max_length=50
    )  # 'document', 'link', 'voice'
    title: Optional[str] = Field(None, max_length=255)
    url: Optional[str] = Field(None, max_length=2048)
    raw_content: Optional[str] = None
    meta_data: Optional[dict] = None


class SourceResponse(BaseModel):
    """Source response"""

    source_id: UUID
    collection_id: UUID
    source_type: str
    title: Optional[str]
    url: Optional[str]
    created_at: datetime
    is_deleted: bool

    class Config:
        from_attributes = True


# ============ Memory Chunk Schemas ============


class MemoryChunkCreate(BaseModel):
    """Create a memory chunk"""

    source_id: UUID
    content: str = Field(..., min_length=1)
    chunk_index: int = Field(..., ge=0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryChunkResponse(BaseModel):
    """Memory chunk response"""

    chunk_id: UUID
    source_id: UUID
    content: str
    chunk_index: int
    importance: float
    created_at: datetime
    last_accessed: Optional[datetime]
    is_deleted: bool

    class Config:
        from_attributes = True


class MemoryChunkSearch(BaseModel):
    """Search response for memory chunks"""

    chunk_id: UUID
    content: str
    importance: float
    relevance_score: Optional[float] = None  # For future hybrid search
    source_title: Optional[str]
    created_at: datetime


# ============ Conversation Schemas ============


class ConversationCreate(BaseModel):
    """Create a new conversation"""

    title: Optional[str] = Field(None, max_length=255)


class ConversationResponse(BaseModel):
    """Conversation response"""

    conversation_id: UUID
    user_id: UUID
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_archived: bool

    class Config:
        from_attributes = True


# ============ Message Schemas ============


class MessageCreate(BaseModel):
    """Create a message in conversation"""

    role: str = Field(..., min_length=1, max_length=20)  # 'user', 'assistant'
    content: str = Field(..., min_length=1)
    tokens_used: Optional[int] = None
    model_used: Optional[str] = None


class MessageResponse(BaseModel):
    """Message response"""

    message_id: UUID
    conversation_id: UUID
    role: str
    content: str
    content_masked: Optional[str]
    created_at: datetime
    tokens_used: Optional[int]

    class Config:
        from_attributes = True

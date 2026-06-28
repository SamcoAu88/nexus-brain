"""
SQLAlchemy Models for Memory Management
"""

from datetime import datetime
from sqlalchemy import BigInteger
from uuid import uuid4
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    DateTime,
    Boolean,
    UUID,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship

from src.models.base import Base


class UserProfile(Base):
    """User profile and settings"""

    __tablename__ = "user_profiles"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    telegram_id = Column(String(255), unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    collections = relationship("Collection", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")
    cost_tracking = relationship("CostTracking", back_populates="user")


class Collection(Base):
    """Memory collections/projects"""

    __tablename__ = "collections"

    collection_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("user_profiles.user_id"), nullable=False
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("UserProfile", back_populates="collections")
    sources = relationship("Source", back_populates="collection")

    __table_args__ = (Index("idx_user_collection", "user_id"),)


class Source(Base):
    """Data sources (documents, links, etc)"""

    __tablename__ = "sources"

    source_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    collection_id = Column(
        UUID(as_uuid=True), ForeignKey("collections.collection_id"), nullable=False
    )
    source_type = Column(
        String(50), nullable=False
    )  # 'document', 'link', 'voice', 'message'
    title = Column(String(255), nullable=True)
    url = Column(String(2048), nullable=True)
    raw_content = Column(Text, nullable=True)
    meta_data = Column(JSONB, nullable=True, default={})
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)

    # Relationships
    collection = relationship("Collection", back_populates="sources")
    chunks = relationship("MemoryChunk", back_populates="source")

    __table_args__ = (Index("idx_collection_source", "collection_id"),)


class MemoryChunk(Base):
    """Text chunks for embedding and search"""

    __tablename__ = "memory_chunks"

    chunk_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id = Column(
        UUID(as_uuid=True), ForeignKey("sources.source_id"), nullable=False
    )
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)  # Position in source
    embedding: list[float] | None = Column(
        ARRAY(Float), nullable=True
    )  # 1536 dimensions
    importance = Column(Float, default=0.5, nullable=False)  # 0.0 to 1.0
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_accessed = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)

    # Relationships
    source = relationship("Source", back_populates="chunks")
    entity_relations = relationship("ChunkEntity", back_populates="chunk")

    __table_args__ = (
        Index("idx_source_chunk", "source_id"),
        Index("idx_embedding_chunk", "embedding", postgresql_using="gin"),
    )


class Entity(Base):
    """Named entities and concepts"""

    __tablename__ = "entities"

    entity_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("user_profiles.user_id"), nullable=False
    )
    name = Column(String(255), nullable=False)
    entity_type = Column(String(50), nullable=False)  # 'person', 'place', 'concept'
    description = Column(Text, nullable=True)
    meta_data = Column(JSONB, nullable=True, default={})
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    relations = relationship(
        "EntityRelation",
        back_populates="entity_a",
        foreign_keys="EntityRelation.entity_a_id",
    )

    __table_args__ = (Index("idx_user_entity", "user_id"),)


class EntityRelation(Base):
    """Relationships between entities (graph)"""

    __tablename__ = "entity_relations"

    relation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_a_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.entity_id"), nullable=False
    )
    entity_b_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.entity_id"), nullable=False
    )
    relation_type = Column(String(100), nullable=False)  # 'knows', 'located_in', etc
    weight = Column(Float, default=1.0)  # Strength of relation
    meta_data = Column(JSONB, nullable=True, default={})
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    entity_a = relationship(
        "Entity", back_populates="relations", foreign_keys=[entity_a_id]
    )

    __table_args__ = (Index("idx_entity_relation", "entity_a_id", "entity_b_id"),)


class ChunkEntity(Base):
    """Junction table: chunks mention entities"""

    __tablename__ = "chunk_entities"

    chunk_entity_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    chunk_id = Column(
        UUID(as_uuid=True), ForeignKey("memory_chunks.chunk_id"), nullable=False
    )
    entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.entity_id"), nullable=False
    )
    mention_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    chunk = relationship("MemoryChunk", back_populates="entity_relations")

    __table_args__ = (Index("idx_chunk_entity", "chunk_id", "entity_id"),)


class Conversation(Base):
    """Chat conversations"""

    __tablename__ = "conversations"

    conversation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("user_profiles.user_id"), nullable=False
    )
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_archived = Column(Boolean, default=False)

    # Relationships
    user = relationship("UserProfile", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")

    __table_args__ = (Index("idx_user_conversation", "user_id"),)


class Message(Base):
    """Messages in conversations"""

    __tablename__ = "messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.conversation_id"), nullable=False
    )
    role = Column(String(20), nullable=False)  # 'user', 'assistant'
    content = Column(Text, nullable=False)
    content_masked = Column(Text, nullable=True)  # Masked version (PII removed)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tokens_used = Column(Integer, nullable=True)
    model_used = Column(String(100), nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (Index("idx_conversation_message", "conversation_id"),)


class CostTracking(Base):
    """Track API costs per user per day"""

    __tablename__ = "cost_tracking"

    cost_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("user_profiles.user_id"), nullable=False
    )
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    total_cost = Column(Float, default=0.0)
    requests_count = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("UserProfile", back_populates="cost_tracking")

    __table_args__ = (Index("idx_user_date_cost", "user_id", "date"),)


class AuditLog(Base):
    """Immutable audit log"""

    __tablename__ = "audit_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(100), nullable=False)
    table_name = Column(String(100), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=True)
    changes = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_user_audit", "user_id"),
        Index("idx_action_audit", "action"),
    )
    # ← NO TelegramUpdateLog here!


class TelegramUpdateLog(Base):  # ← Only THIS one, at root level
    """Track processed Telegram updates to prevent duplicates."""

    __tablename__ = "telegram_update_log"

    id = Column(Integer, primary_key=True)
    update_id = Column(BigInteger, nullable=False, unique=True, index=True)
    user_id = Column(UUID, nullable=True)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (Index("idx_update_id_expires", "update_id", "expires_at"),)

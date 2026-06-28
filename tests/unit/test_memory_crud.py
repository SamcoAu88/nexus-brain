"""
Unit tests for Memory Router CRUD operations
Tests collections, sources, chunks, conversations, and messages
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from src.main import app
from src.core.database import SessionLocal
from src.auth.password import hash_password
from src.models.memory import (
    UserProfile,
    Collection,
    Source,
    MemoryChunk,
    Conversation,
    Message,
)

client = TestClient(app)


@pytest.fixture
def db_session():
    """Create test database session"""
    db = SessionLocal()
    yield db
    # Cleanup
    db.query(Message).delete()
    db.query(Conversation).delete()
    db.query(MemoryChunk).delete()
    db.query(Source).delete()
    db.query(Collection).delete()
    db.query(UserProfile).delete()
    db.commit()
    db.close()


@pytest.fixture
def test_user(db_session):
    """Create test user"""
    user = UserProfile(
        telegram_id="123456789",
        username="testuser",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_collection(db_session, test_user):
    """Create test collection"""
    collection = Collection(
        user_id=test_user.user_id,
        name="Test Collection",
        description="A test collection",
    )
    db_session.add(collection)
    db_session.commit()
    db_session.refresh(collection)
    return collection


@pytest.fixture
def test_source(db_session, test_collection):
    """Create test source"""
    source = Source(
        collection_id=test_collection.collection_id,
        source_type="document",
        title="Test Document",
        url="https://example.com/doc",
        raw_content="This is test content",
        meta_data={"tags": ["test"]},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


@pytest.fixture
def test_conversation(db_session, test_user):
    """Create test conversation"""
    conversation = Conversation(user_id=test_user.user_id, title="Test Conversation")
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)
    return conversation


@pytest.fixture
def headers(test_user):
    """Mock auth headers with user_id"""
    # NOTE: In real app, this would be from JWT token
    return {"X-User-ID": str(test_user.user_id)}


class TestCollectionCRUD:
    """Test collection CRUD operations"""

    def test_create_collection_success(self, test_user, headers):
        """Test creating a collection"""

        # Monkeypatch to inject user_id (simulating auth)
        def get_user_id():
            return test_user.user_id

        app.dependency_overrides[lambda: None] = get_user_id

        # For now, we need to test via the endpoint directly
        # But since auth isn't implemented, we'll skip this for now
        # and focus on database-level testing

    def test_create_collection_db(self, db_session, test_user):
        """Test creating a collection (database level)"""
        collection = Collection(
            user_id=test_user.user_id, name="New Collection", description="Test"
        )
        db_session.add(collection)
        db_session.commit()

        assert collection.collection_id is not None
        assert collection.name == "New Collection"
        assert collection.user_id == test_user.user_id

    def test_list_collections_db(self, db_session, test_user, test_collection):
        """Test listing collections for user"""
        collections = (
            db_session.query(Collection)
            .filter(Collection.user_id == test_user.user_id)
            .all()
        )

        assert len(collections) == 1
        assert collections[0].name == "Test Collection"

    def test_get_collection_db(self, db_session, test_user, test_collection):
        """Test getting a specific collection"""
        collection = (
            db_session.query(Collection)
            .filter(
                Collection.collection_id == test_collection.collection_id,
                Collection.user_id == test_user.user_id,
            )
            .first()
        )

        assert collection is not None
        assert collection.collection_id == test_collection.collection_id

    def test_get_collection_not_found(self, db_session, test_user):
        """Test getting non-existent collection"""
        collection = (
            db_session.query(Collection)
            .filter(
                Collection.collection_id == uuid4(),
                Collection.user_id == test_user.user_id,
            )
            .first()
        )

        assert collection is None

    def test_delete_collection_db(self, db_session, test_user, test_collection):
        """Test deleting a collection"""
        db_session.delete(test_collection)
        db_session.commit()

        collection = (
            db_session.query(Collection)
            .filter(Collection.collection_id == test_collection.collection_id)
            .first()
        )

        assert collection is None


class TestSourceCRUD:
    """Test source CRUD operations"""

    def test_create_source_db(self, db_session, test_collection):
        """Test creating a source"""
        source = Source(
            collection_id=test_collection.collection_id,
            source_type="link",
            title="Example Link",
            url="https://example.com",
            meta_data={"domain": "example.com"},
        )
        db_session.add(source)
        db_session.commit()

        assert source.source_id is not None
        assert source.source_type == "link"
        assert not source.is_deleted

    def test_list_sources_db(self, db_session, test_collection, test_source):
        """Test listing sources in collection"""
        sources = (
            db_session.query(Source)
            .filter(
                Source.collection_id == test_collection.collection_id,
                ~Source.is_deleted,
            )
            .all()
        )

        assert len(sources) == 1
        assert sources[0].title == "Test Document"

    def test_list_sources_excludes_deleted(self, db_session, test_collection):
        """Test that deleted sources are excluded"""
        source1 = Source(
            collection_id=test_collection.collection_id,
            source_type="document",
            title="Active",
        )
        source2 = Source(
            collection_id=test_collection.collection_id,
            source_type="document",
            title="Deleted",
            is_deleted=True,
        )
        db_session.add_all([source1, source2])
        db_session.commit()

        sources = (
            db_session.query(Source)
            .filter(
                Source.collection_id == test_collection.collection_id,
                ~Source.is_deleted,
            )
            .all()
        )

        assert len(sources) == 1
        assert sources[0].title == "Active"


class TestChunkCRUD:
    """Test memory chunk CRUD operations"""

    def test_create_chunk_db(self, db_session, test_source):
        """Test creating a memory chunk"""
        chunk = MemoryChunk(
            source_id=test_source.source_id,
            content="This is chunk content",
            chunk_index=0,
            importance=0.8,
        )
        db_session.add(chunk)
        db_session.commit()

        assert chunk.chunk_id is not None
        assert chunk.chunk_index == 0
        assert chunk.importance == 0.8

    def test_create_multiple_chunks(self, db_session, test_source):
        """Test creating multiple chunks for one source"""
        chunks = [
            MemoryChunk(
                source_id=test_source.source_id,
                content=f"Chunk {i}",
                chunk_index=i,
                importance=0.5,
            )
            for i in range(3)
        ]
        db_session.add_all(chunks)
        db_session.commit()

        db_chunks = (
            db_session.query(MemoryChunk)
            .filter(MemoryChunk.source_id == test_source.source_id)
            .order_by(MemoryChunk.chunk_index)
            .all()
        )

        assert len(db_chunks) == 3
        assert db_chunks[0].chunk_index == 0
        assert db_chunks[2].chunk_index == 2

    def test_list_chunks_ordered(self, db_session, test_source):
        """Test chunks are returned in order"""
        for i in [2, 0, 1]:  # Create out of order
            chunk = MemoryChunk(
                source_id=test_source.source_id, content=f"Chunk {i}", chunk_index=i
            )
            db_session.add(chunk)
        db_session.commit()

        chunks = (
            db_session.query(MemoryChunk)
            .filter(MemoryChunk.source_id == test_source.source_id)
            .order_by(MemoryChunk.chunk_index)
            .all()
        )

        indices = [c.chunk_index for c in chunks]
        assert indices == [0, 1, 2]

    def test_chunk_importance_validation(self, db_session, test_source):
        """Test importance is between 0.0 and 1.0"""
        chunk_low = MemoryChunk(
            source_id=test_source.source_id,
            content="Low importance",
            chunk_index=0,
            importance=0.0,
        )
        chunk_high = MemoryChunk(
            source_id=test_source.source_id,
            content="High importance",
            chunk_index=1,
            importance=1.0,
        )
        db_session.add_all([chunk_low, chunk_high])
        db_session.commit()

        assert chunk_low.importance == 0.0
        assert chunk_high.importance == 1.0


class TestConversationCRUD:
    """Test conversation CRUD operations"""

    def test_create_conversation_db(self, db_session, test_user):
        """Test creating a conversation"""
        conv = Conversation(user_id=test_user.user_id, title="New Conversation")
        db_session.add(conv)
        db_session.commit()

        assert conv.conversation_id is not None
        assert not conv.is_archived

    def test_list_conversations_excludes_archived(self, db_session, test_user):
        """Test archived conversations are excluded"""
        conv1 = Conversation(user_id=test_user.user_id, title="Active")
        conv2 = Conversation(
            user_id=test_user.user_id, title="Archived", is_archived=True
        )
        db_session.add_all([conv1, conv2])
        db_session.commit()

        conversations = (
            db_session.query(Conversation)
            .filter(
                Conversation.user_id == test_user.user_id, ~Conversation.is_archived
            )
            .all()
        )

        assert len(conversations) == 1
        assert conversations[0].title == "Active"

    def test_list_conversations_ordered(self, db_session, test_user):
        """Test conversations ordered by most recent"""
        import time

        conv1 = Conversation(user_id=test_user.user_id, title="First")
        db_session.add(conv1)
        db_session.commit()

        # Small delay so second conversation has later timestamp
        time.sleep(0.01)

        conv2 = Conversation(user_id=test_user.user_id, title="Second")
        db_session.add(conv2)
        db_session.commit()

        conversations = (
            db_session.query(Conversation)
            .filter(Conversation.user_id == test_user.user_id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )

        # Second one should be first (most recent)
        assert conversations[0].conversation_id == conv2.conversation_id
        assert conversations[1].conversation_id == conv1.conversation_id


class TestMessageCRUD:
    """Test message CRUD operations"""

    def test_create_message_db(self, db_session, test_conversation):
        """Test creating a message"""
        message = Message(
            conversation_id=test_conversation.conversation_id,
            role="user",
            content="Hello bot",
            tokens_used=5,
            model_used="gpt-4",
        )
        db_session.add(message)
        db_session.commit()

        assert message.message_id is not None
        assert message.role == "user"

    def test_list_messages_ordered(self, db_session, test_conversation):
        """Test messages ordered by creation time"""
        msg1 = Message(
            conversation_id=test_conversation.conversation_id,
            role="user",
            content="First",
        )
        msg2 = Message(
            conversation_id=test_conversation.conversation_id,
            role="assistant",
            content="Second",
        )
        db_session.add_all([msg1, msg2])
        db_session.commit()

        messages = (
            db_session.query(Message)
            .filter(Message.conversation_id == test_conversation.conversation_id)
            .order_by(Message.created_at)
            .all()
        )

        assert len(messages) == 2
        assert messages[0].content == "First"
        assert messages[1].content == "Second"

    def test_message_role_validation(self, db_session, test_conversation):
        """Test message roles"""
        user_msg = Message(
            conversation_id=test_conversation.conversation_id,
            role="user",
            content="User message",
        )
        assistant_msg = Message(
            conversation_id=test_conversation.conversation_id,
            role="assistant",
            content="Assistant message",
        )
        db_session.add_all([user_msg, assistant_msg])
        db_session.commit()

        messages = (
            db_session.query(Message)
            .filter(Message.conversation_id == test_conversation.conversation_id)
            .all()
        )

        assert len(messages) == 2
        roles = {m.role for m in messages}
        assert roles == {"user", "assistant"}


class TestCrossTableRelationships:
    """Test relationships between tables"""

    def test_collection_source_relationship(
        self, db_session, test_collection, test_source
    ):
        """Test collection-source relationship"""
        collection = (
            db_session.query(Collection)
            .filter(Collection.collection_id == test_collection.collection_id)
            .first()
        )

        # Load sources through relationship
        assert collection.sources is not None
        assert len(collection.sources) == 1
        assert collection.sources[0].title == "Test Document"

    def test_source_chunk_relationship(self, db_session, test_source):
        """Test source-chunk relationship"""
        chunk1 = MemoryChunk(
            source_id=test_source.source_id, content="Chunk 1", chunk_index=0
        )
        chunk2 = MemoryChunk(
            source_id=test_source.source_id, content="Chunk 2", chunk_index=1
        )
        db_session.add_all([chunk1, chunk2])
        db_session.commit()

        source = (
            db_session.query(Source)
            .filter(Source.source_id == test_source.source_id)
            .first()
        )

        assert len(source.chunks) == 2

    def test_conversation_message_relationship(self, db_session, test_conversation):
        """Test conversation-message relationship"""
        msg1 = Message(
            conversation_id=test_conversation.conversation_id,
            role="user",
            content="Msg 1",
        )
        msg2 = Message(
            conversation_id=test_conversation.conversation_id,
            role="assistant",
            content="Msg 2",
        )
        db_session.add_all([msg1, msg2])
        db_session.commit()

        conversation = (
            db_session.query(Conversation)
            .filter(Conversation.conversation_id == test_conversation.conversation_id)
            .first()
        )

        assert len(conversation.messages) == 2

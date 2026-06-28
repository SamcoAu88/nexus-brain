"""
Unit tests for JWT Authentication
Tests token generation, verification, and endpoint protection
"""

import pytest
from uuid import uuid4
from datetime import timedelta
from fastapi.testclient import TestClient
from jose import jwt

from src.main import app
from src.auth.tokens import (
    create_access_token,
    create_refresh_token,
    verify_token,
    refresh_access_token,
)
from src.core.config import settings
from src.core.database import SessionLocal
from src.models.memory import UserProfile, Collection

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_db():
    """Cleanup database before and after each test"""
    # Cleanup before
    db = SessionLocal()
    db.query(Collection).delete()
    db.query(UserProfile).delete()
    db.commit()
    db.close()

    yield

    # Cleanup after
    db = SessionLocal()
    db.query(Collection).delete()
    db.query(UserProfile).delete()
    db.commit()
    db.close()


@pytest.fixture
def db_session():
    """Create test database session"""
    db = SessionLocal()
    yield db
    # Cleanup
    db.query(Collection).delete()
    db.query(UserProfile).delete()
    db.commit()
    db.close()


@pytest.fixture
def test_user(db_session):
    """Create test user with proper password hash"""
    from src.auth.password import hash_password

    user = UserProfile(username="testuser", password_hash=hash_password("password123"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestTokenGeneration:
    """Test JWT token creation"""

    def test_create_access_token(self):
        """Test creating access token"""
        user_id = uuid4()
        token = create_access_token(user_id)

        assert token is not None
        assert isinstance(token, str)

        # Decode and verify
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        assert str(user_id) == payload["user_id"]
        assert payload["type"] == "access"

    def test_access_token_expires_in_one_hour(self):
        """Test that access tokens expire after 1 hour"""
        user_id = uuid4()
        token = create_access_token(user_id)

        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        # Token should expire ~1 hour from now (allow 5 min margin)
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).timestamp()
        exp = payload["exp"]

        assert 3300 < (exp - now) < 3700  # Between 55 and 65 minutes

    def test_create_refresh_token(self):
        """Test creating refresh token"""
        user_id = uuid4()
        token = create_refresh_token(user_id)

        assert token is not None
        assert isinstance(token, str)

        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        assert str(user_id) == payload["user_id"]
        assert payload["type"] == "refresh"

    def test_refresh_token_expires_in_seven_days(self):
        """Test that refresh tokens expire after 7 days"""
        user_id = uuid4()
        token = create_refresh_token(user_id)

        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).timestamp()
        exp = payload["exp"]

        # Token should expire ~7 days from now (allow 1 hour margin)
        assert (7 * 24 * 3600 - 3600) < (exp - now) < (7 * 24 * 3600 + 3600)

    def test_custom_expiration(self):
        """Test access token with custom expiration"""
        user_id = uuid4()
        custom_expires = timedelta(hours=2)
        token = create_access_token(user_id, expires_delta=custom_expires)

        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).timestamp()
        exp = payload["exp"]

        # Token should expire ~2 hours from now
        assert 6900 < (exp - now) < 7300  # Between 115 and 125 minutes


class TestTokenVerification:
    """Test JWT token verification"""

    def test_verify_valid_token(self):
        """Test verifying a valid token"""
        user_id = uuid4()
        token = create_access_token(user_id)

        token_data = verify_token(token)

        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.type == "access"

    def test_verify_invalid_token(self):
        """Test verifying an invalid token"""
        token = "invalid.token.here"

        token_data = verify_token(token)

        assert token_data is None

    def test_verify_tampered_token(self):
        """Test verifying a tampered token"""
        user_id = uuid4()
        token = create_access_token(user_id)

        # Tamper with the token
        tampered = token[:-10] + "tampered00"

        token_data = verify_token(tampered)

        assert token_data is None

    def test_verify_token_wrong_secret(self):
        """Test that token from wrong secret fails"""
        user_id = uuid4()

        # Create token with wrong secret
        token = jwt.encode(
            {
                "user_id": str(user_id),
                "type": "access",
            },
            "wrong-secret-key",
            algorithm=settings.JWT_ALGORITHM,
        )

        token_data = verify_token(token)

        assert token_data is None


class TestTokenRefresh:
    """Test token refresh flow"""

    def test_refresh_valid_refresh_token(self):
        """Test refreshing with valid refresh token"""
        user_id = uuid4()
        refresh_token = create_refresh_token(user_id)

        new_access_token = refresh_access_token(refresh_token)

        assert new_access_token is not None

        # Verify new token
        token_data = verify_token(new_access_token)
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.type == "access"

    def test_refresh_with_access_token_fails(self):
        """Test that refreshing with access token fails"""
        user_id = uuid4()
        access_token = create_access_token(user_id)

        new_access_token = refresh_access_token(access_token)

        assert new_access_token is None

    def test_refresh_invalid_token(self):
        """Test refreshing with invalid token"""
        new_access_token = refresh_access_token("invalid.token")

        assert new_access_token is None


class TestSignup:
    """Test user signup"""

    def test_signup_creates_user(self):
        """Test signup endpoint creates user"""
        response = client.post(
            "/api/auth/signup",
            json={"username": "newuser", "password": "password123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newuser"
        assert "user_id" in data
        assert data["is_active"] is True

    def test_signup_requires_8_char_password(self):
        """Test signup requires strong password (8+ chars)"""
        response = client.post(
            "/api/auth/signup",
            json={"username": "user", "password": "short"},
        )

        assert response.status_code == 422  # Validation error

    def test_signup_duplicate_username_fails(self):
        """Test signup fails with duplicate username"""
        # First signup
        client.post(
            "/api/auth/signup",
            json={"username": "alice", "password": "password123"},
        )

        # Second signup with same username
        response = client.post(
            "/api/auth/signup",
            json={"username": "alice", "password": "otherpass123"},
        )

        assert response.status_code == 400
        assert "already taken" in response.json()["detail"]


class TestAuthEndpoints:
    """Test authentication endpoints"""

    def test_login_endpoint_exists(self):
        """Test login endpoint responds"""
        # First signup
        client.post(
            "/api/auth/signup",
            json={"username": "testuser", "password": "password123"},
        )

        # Now login
        response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "password123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_returns_valid_tokens(self):
        """Test login returns valid tokens"""
        # First signup
        client.post(
            "/api/auth/signup",
            json={"username": "tokenuser", "password": "password123"},
        )

        # Now login
        response = client.post(
            "/api/auth/login",
            json={"username": "tokenuser", "password": "password123"},
        )

        data = response.json()
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]

        # Verify access token
        access_data = verify_token(access_token)
        assert access_data is not None
        assert access_data.type == "access"

        # Verify refresh token
        refresh_data = verify_token(refresh_token)
        assert refresh_data is not None
        assert refresh_data.type == "refresh"

        # Should be same user
        assert access_data.user_id == refresh_data.user_id

    def test_login_invalid_password(self):
        """Test login fails with wrong password"""
        # First signup
        client.post(
            "/api/auth/signup",
            json={"username": "secure_user", "password": "correct_password123"},
        )

        # Try login with wrong password
        response = client.post(
            "/api/auth/login",
            json={"username": "secure_user", "password": "wrong_password"},
        )

        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]

    def test_login_nonexistent_user(self):
        """Test login fails for nonexistent user"""
        response = client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "password123"},
        )

        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]

    def test_refresh_endpoint(self):
        """Test token refresh endpoint"""
        # First signup
        client.post(
            "/api/auth/signup",
            json={"username": "user1", "password": "password123"},
        )

        # Then login
        login_response = client.post(
            "/api/auth/login",
            json={"username": "user1", "password": "password123"},
        )
        refresh_token = login_response.json()["refresh_token"]

        # Now refresh
        refresh_response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert refresh_response.status_code == 200
        data = refresh_response.json()
        assert "access_token" in data
        assert data["refresh_token"] == refresh_token  # Same refresh token returned

    def test_refresh_with_invalid_token(self):
        """Test refresh with invalid token fails"""
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid.token"},
        )

        assert response.status_code == 401
        assert "Invalid or expired" in response.json()["detail"]


class TestEndpointProtection:
    """Test that endpoints are protected with auth"""

    def test_collection_create_requires_auth(self):
        """Test that creating collection requires token"""
        response = client.post(
            "/api/collections",
            json={"name": "Test", "description": "Test collection"},
        )

        assert response.status_code == 401  # Unauthorized (no credentials)

    def test_collection_create_with_valid_token(self):
        """Test creating collection with valid token"""
        # Signup
        client.post(
            "/api/auth/signup",
            json={"username": "coluser", "password": "password123"},
        )

        # Login
        login_response = client.post(
            "/api/auth/login",
            json={"username": "coluser", "password": "password123"},
        )
        token = login_response.json()["access_token"]

        # Create collection with token
        response = client.post(
            "/api/collections",
            json={"name": "Test Collection", "description": "Test"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Collection"

    def test_list_collections_requires_auth(self):
        """Test that listing collections requires token"""
        response = client.get("/api/collections")

        assert response.status_code == 401

    def test_list_collections_with_valid_token(self):
        """Test listing collections with valid token"""
        # Signup
        client.post(
            "/api/auth/signup",
            json={"username": "listuser", "password": "password123"},
        )

        # Login
        login_response = client.post(
            "/api/auth/login",
            json={"username": "listuser", "password": "password123"},
        )
        token = login_response.json()["access_token"]

        # Create a collection first
        client.post(
            "/api/collections",
            json={"name": "Collection", "description": "Test"},
            headers={"Authorization": f"Bearer {token}"},
        )

        # List collections
        response = client.get(
            "/api/collections",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

"""
Unit tests for Telegram webhook idempotency
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.main import app
from src.core.database import SessionLocal
from src.models.memory import TelegramUpdateLog
from src.core.config import settings

client = TestClient(app)


@pytest.fixture
def db_session():
    """Create test database session"""
    db = SessionLocal()
    yield db
    # Cleanup: delete all test records
    db.query(TelegramUpdateLog).delete()
    db.commit()
    db.close()


@pytest.fixture
def mock_telegram_request():
    """Sample Telegram webhook payload"""
    return {
        "update_id": 123456789,
        "message": {
            "message_id": 1,
            "chat": {"id": 987654},
            "text": "Hello bot",
            "from": {"id": 111, "is_bot": False, "first_name": "Test"}
        }
    }


@pytest.fixture
def valid_headers():
    """Valid Telegram headers"""
    return {
        "X-Telegram-Bot-Api-Secret-Token": settings.TELEGRAM_WEBHOOK_SECRET
    }


def mock_validate_telegram_ip(client_ip: str) -> bool:
    """Mock IP validation to always pass in tests"""
    return True


class TestTelegramIdempotency:
    """Test suite for Telegram webhook idempotency"""
    
    @patch("src.api.telegram_router.validate_telegram_ip")
    def test_first_update_stored(self, mock_ip, db_session, mock_telegram_request, valid_headers):
        """Test: First webhook call stores update in database"""
        mock_ip.side_effect = mock_validate_telegram_ip
        
        response = client.post(
            "/api/telegram/webhook",
            json=mock_telegram_request,
            headers=valid_headers
        )
        
        assert response.status_code == 200
        assert response.json()["ok"] is True
        
        # Verify stored in database
        stored = db_session.query(TelegramUpdateLog).filter(
            TelegramUpdateLog.update_id == 123456789
        ).first()
        
        assert stored is not None
        assert stored.update_id == 123456789
        assert stored.processed_at is not None
        assert stored.expires_at is not None
    
    
    @patch("src.api.telegram_router.validate_telegram_ip")
    def test_duplicate_update_cached(self, mock_ip, db_session, mock_telegram_request, valid_headers):
        """Test: Duplicate update_id returns 200 OK (idempotent) without re-processing"""
        mock_ip.side_effect = mock_validate_telegram_ip
        
        # First call
        response1 = client.post(
            "/api/telegram/webhook",
            json=mock_telegram_request,
            headers=valid_headers
        )
        assert response1.status_code == 200
        
        # Verify one record in DB
        count_after_first = db_session.query(TelegramUpdateLog).filter(
            TelegramUpdateLog.update_id == 123456789
        ).count()
        assert count_after_first == 1
        
        # Second call (duplicate)
        response2 = client.post(
            "/api/telegram/webhook",
            json=mock_telegram_request,
            headers=valid_headers
        )
        assert response2.status_code == 200
        assert response2.json()["ok"] is True
        
        # Verify still only ONE record in DB (not duplicated)
        count_after_second = db_session.query(TelegramUpdateLog).filter(
            TelegramUpdateLog.update_id == 123456789
        ).count()
        assert count_after_second == 1  # Should NOT be 2
    
    
    @patch("src.api.telegram_router.validate_telegram_ip")
    def test_different_update_ids_processed(self, mock_ip, db_session, mock_telegram_request, valid_headers):
        """Test: Different update_ids are stored separately"""
        mock_ip.side_effect = mock_validate_telegram_ip
        
        # First update
        update1 = mock_telegram_request.copy()
        update1["update_id"] = 111111111
        response1 = client.post(
            "/api/telegram/webhook",
            json=update1,
            headers=valid_headers
        )
        assert response1.status_code == 200
        
        # Second update (different ID)
        update2 = mock_telegram_request.copy()
        update2["update_id"] = 222222222
        response2 = client.post(
            "/api/telegram/webhook",
            json=update2,
            headers=valid_headers
        )
        assert response2.status_code == 200
        
        # Verify both stored
        stored_ids = db_session.query(TelegramUpdateLog.update_id).all()
        assert len(stored_ids) == 2
        assert (111111111,) in stored_ids
        assert (222222222,) in stored_ids
    
    
    @patch("src.api.telegram_router.validate_telegram_ip")
    def test_missing_update_id_rejected(self, mock_ip, valid_headers):
        """Test: Request without update_id is rejected"""
        mock_ip.side_effect = mock_validate_telegram_ip
        
        invalid_update = {
            "message": {"text": "Hello"}  # Missing update_id
        }
        
        response = client.post(
            "/api/telegram/webhook",
            json=invalid_update,
            headers=valid_headers
        )
        
        assert response.status_code == 400
        assert "update_id" in response.json()["error"]
    
    
    @patch("src.api.telegram_router.validate_telegram_ip")
    def test_invalid_secret_rejected(self, mock_ip, mock_telegram_request):
        """Test: Invalid secret token is rejected"""
        mock_ip.side_effect = mock_validate_telegram_ip
        
        invalid_headers = {
            "X-Telegram-Bot-Api-Secret-Token": "wrong_secret"
        }
        
        response = client.post(
            "/api/telegram/webhook",
            json=mock_telegram_request,
            headers=invalid_headers
        )
        
        assert response.status_code == 403
        assert "secret token" in response.json()["error"].lower()
    
    
    @patch("src.api.telegram_router.validate_telegram_ip")
    def test_expires_at_set_to_24h(self, mock_ip, db_session, mock_telegram_request, valid_headers):
        """Test: expires_at is set to 24 hours from now"""
        mock_ip.side_effect = mock_validate_telegram_ip
        
        before_time = datetime.utcnow()
        
        response = client.post(
            "/api/telegram/webhook",
            json=mock_telegram_request,
            headers=valid_headers
        )
        assert response.status_code == 200
        
        after_time = datetime.utcnow()
        
        stored = db_session.query(TelegramUpdateLog).filter(
            TelegramUpdateLog.update_id == 123456789
        ).first()
        
        # expires_at should be ~24h from now
        expected_min = before_time + timedelta(hours=23, minutes=59)
        expected_max = after_time + timedelta(hours=24, minutes=1)
        
        assert expected_min <= stored.expires_at <= expected_max
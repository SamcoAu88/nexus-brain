"""
Unit Tests for Health Endpoints
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root_endpoint(client):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Nexus-Brain"
    assert data["version"] == "5.0.0"


def test_health_endpoint(client):
    """Test health check"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_readiness_endpoint(client):
    """Test readiness probe"""
    response = client.get("/api/health/ready")
    # May fail if services not running, but endpoint should exist
    assert response.status_code in [200, 503]


def test_liveness_endpoint(client):
    """Test liveness probe"""
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_docs_available(client):
    """Test that Swagger docs are available"""
    response = client.get("/docs")
    assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

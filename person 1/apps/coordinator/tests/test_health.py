"""
Tests for the coordinator health endpoint.
"""

from fastapi.testclient import TestClient

from coordinator.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    """GET /health should return HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_ok_status() -> None:
    """GET /health body should contain status: ok."""
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"


def test_health_returns_version() -> None:
    """GET /health body should contain a non-empty version string."""
    response = client.get("/health")
    data = response.json()
    assert "version" in data
    assert data["version"]

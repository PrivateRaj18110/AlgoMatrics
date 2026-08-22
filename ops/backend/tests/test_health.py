"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert "time" in body
    assert body["environment"]


def test_root_points_to_health() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["health"] == "/api/health"

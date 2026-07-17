"""Unit tests for health check endpoints. These do not require a live database."""

from fastapi.testclient import TestClient


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "CivicAI"


def test_health_check_response_shape(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    body = response.json()
    assert set(body.keys()) == {"status", "service", "environment"}


def test_openapi_schema_is_available_in_debug(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "CivicAI"
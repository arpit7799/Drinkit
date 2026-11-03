import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import app

pytestmark = pytest.mark.integration


async def test_readiness_reports_postgresql_as_ready(integration_engine: AsyncEngine):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["postgres"] == "up"
    assert data["checks"]["redis"] in ("up", "down")

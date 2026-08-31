from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory, get_db
from app.main import app
from app.models.address import CustomerAddress, FulfillmentCoverage
from app.models.auth import User
from app.models.catalog import Product, ProductVariant
from app.models.inventory import FulfillmentLocation
from app.models.outbox_event import OutboxEvent

pytestmark = pytest.mark.integration


@pytest.fixture
async def address_api_client(integration_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSessionFactory(bind=integration_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        async with AsyncSessionFactory(bind=integration_engine) as session:
            await session.execute(delete(CustomerAddress))
            await session.execute(delete(FulfillmentCoverage))
            await session.execute(delete(FulfillmentLocation))
            await session.execute(delete(ProductVariant))
            await session.execute(delete(Product))
            await session.execute(delete(User))
            await session.commit()


async def _register(client: AsyncClient, email: str) -> tuple[dict, UUID]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 201
    payload = response.json()
    return payload, UUID(payload["user"]["id"])


async def _create_location_and_coverage(
    integration_engine: AsyncEngine,
    postal_code: str,
) -> FulfillmentLocation:
    location = FulfillmentLocation(
        id=uuid4(),
        code=f"API-{uuid4()}",
        name="API Fulfillment Hub",
    )
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(location)
        await session.flush()
        session.add(FulfillmentCoverage(location_id=location.id, postal_code=postal_code))
        await session.commit()
    return location


async def test_authenticated_address_crud_and_default_replacement(
    address_api_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    first_tokens, _ = await _register(address_api_client, "address-api@example.com")
    headers = {"Authorization": f"Bearer {first_tokens['access_token']}"}
    first_payload = {
        "label": "  Home ",
        "recipient_name": " Alice Example ",
        "line1": " 1 Main Street ",
        "city": " Bengaluru ",
        "state": " Karnataka ",
        "postal_code": "560 001",
        "country_code": "in",
        "is_default": True,
    }

    first = await address_api_client.post("/api/v1/addresses", json=first_payload, headers=headers)
    assert first.status_code == 201
    first_address = first.json()
    assert first_address["postal_code"] == "560001"
    assert first_address["country_code"] == "IN"
    assert first_address["is_default"] is True

    second = await address_api_client.post(
        "/api/v1/addresses",
        json={
            **first_payload,
            "label": "Office",
            "line1": "2 Work Street",
            "is_default": True,
        },
        headers=headers,
    )
    assert second.status_code == 201
    second_address = second.json()
    assert second_address["is_default"] is True

    listed = await address_api_client.get("/api/v1/addresses", headers=headers)
    assert listed.status_code == 200
    assert [address["id"] for address in listed.json()] == [
        second_address["id"],
        first_address["id"],
    ]
    assert listed.json()[1]["is_default"] is False

    updated = await address_api_client.patch(
        f"/api/v1/addresses/{first_address['id']}",
        json={"city": "Mysuru", "is_default": True},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["city"] == "Mysuru"
    assert updated.json()["is_default"] is True

    invalid = await address_api_client.post(
        "/api/v1/addresses",
        json={**first_payload, "country_code": "USA"},
        headers=headers,
    )
    assert invalid.status_code == 422

    empty_update = await address_api_client.patch(
        f"/api/v1/addresses/{first_address['id']}",
        json={},
        headers=headers,
    )
    assert empty_update.status_code == 400
    assert empty_update.json()["error"]["code"] == "invalid_address_request"

    deleted = await address_api_client.delete(
        f"/api/v1/addresses/{first_address['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204

    remaining = await address_api_client.get("/api/v1/addresses", headers=headers)
    assert [address["id"] for address in remaining.json()] == [second_address["id"]]

    async with AsyncSessionFactory(bind=integration_engine) as session:
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.aggregate_id == UUID(first_address["id"]))
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
            )
        )

    assert [event.event_type for event in events] == [
        "customer.address.created",
        "customer.address.updated",
        "customer.address.deactivated",
    ]
    assert all("Main Street" not in str(event.payload) for event in events)
    assert all("Alice Example" not in str(event.payload) for event in events)


async def test_address_ownership_and_serviceability_are_protected(
    address_api_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    first_tokens, _ = await _register(address_api_client, "owner-api@example.com")
    second_tokens, _ = await _register(address_api_client, "other-api@example.com")
    first_headers = {"Authorization": f"Bearer {first_tokens['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second_tokens['access_token']}"}
    await _create_location_and_coverage(integration_engine, "560001")

    created = await address_api_client.post(
        "/api/v1/addresses",
        json={
            "label": "Home",
            "recipient_name": "Owner",
            "line1": "1 Main Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country_code": "IN",
            "is_default": True,
        },
        headers=first_headers,
    )
    assert created.status_code == 201
    address_id = created.json()["id"]

    forbidden_read = await address_api_client.get(
        f"/api/v1/addresses/{address_id}",
        headers=second_headers,
    )
    assert forbidden_read.status_code == 404
    assert forbidden_read.json()["error"]["code"] == "address_not_found"

    serviceability = await address_api_client.get(
        f"/api/v1/addresses/{address_id}/serviceability",
        headers=first_headers,
    )
    assert serviceability.status_code == 200
    assert serviceability.json()["serviceable"] is True
    assert serviceability.json()["fulfillment_location"]["name"] == "API Fulfillment Hub"

    uncovered = await address_api_client.post(
        "/api/v1/addresses",
        json={
            "label": "Other",
            "recipient_name": "Owner",
            "line1": "2 Other Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "999999",
            "country_code": "IN",
        },
        headers=first_headers,
    )
    assert uncovered.status_code == 201
    uncovered_serviceability = await address_api_client.get(
        f"/api/v1/addresses/{uncovered.json()['id']}/serviceability",
        headers=first_headers,
    )
    assert uncovered_serviceability.status_code == 200
    assert uncovered_serviceability.json() == {
        "serviceable": False,
        "fulfillment_location": None,
    }

    unauthenticated = await address_api_client.get("/api/v1/addresses")
    assert unauthenticated.status_code == 401

from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory, get_db
from app.main import app
from app.models.auth import User
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Product, ProductVariant
from app.models.pricing import VariantPrice
from app.modules.pricing.service import set_variant_price

pytestmark = pytest.mark.integration


@pytest.fixture
async def cart_client(integration_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
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
            await session.execute(delete(CartItem))
            await session.execute(delete(ShoppingCart))
            await session.execute(delete(VariantPrice))
            await session.execute(delete(ProductVariant))
            await session.execute(delete(Product))
            await session.execute(delete(User))
            await session.commit()


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "strong-password-123"},
    )
    assert response.status_code == 201
    return response.json()


async def _seed_variant_and_price(integration_engine: AsyncEngine) -> UUID:
    product_id = uuid4()
    variant_id = uuid4()
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            Product(
                id=product_id,
                name="Cart API Product",
                slug=f"cart-api-{product_id}",
                is_alcoholic=False,
            )
        )
        session.add(
            ProductVariant(
                id=variant_id,
                product_id=product_id,
                sku=f"CART-API-{variant_id}",
                name="One unit",
                quantity_value=Decimal("1"),
                quantity_unit="unit",
            )
        )
        await session.commit()
        await set_variant_price(
            session,
            variant_id=variant_id,
            currency_code="INR",
            amount_minor=1999,
        )
    return variant_id


async def test_authenticated_cart_crud_returns_price_snapshots_and_subtotal(
    cart_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    tokens = await _register(cart_client, "cart-api@example.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    variant_id = await _seed_variant_and_price(integration_engine)

    empty = await cart_client.get("/api/v1/cart", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["currency_code"] == "INR"
    assert empty.json()["items"] == []
    assert empty.json()["subtotal_minor"] == 0

    added = await cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": str(variant_id), "quantity": 2, "currency_code": "inr"},
        headers=headers,
    )
    assert added.status_code == 200
    added_payload = added.json()
    assert len(added_payload["items"]) == 1
    assert added_payload["items"][0]["quantity"] == 2
    assert added_payload["items"][0]["unit_price_minor"] == 1999
    assert added_payload["items"][0]["line_total_minor"] == 3998
    assert added_payload["subtotal_minor"] == 3998

    item_id = added_payload["items"][0]["id"]
    updated = await cart_client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 3},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["subtotal_minor"] == 5997

    removed = await cart_client.delete(
        f"/api/v1/cart/items/{item_id}",
        headers=headers,
    )
    assert removed.status_code == 204
    final = await cart_client.get("/api/v1/cart", headers=headers)
    assert final.json()["items"] == []
    assert final.json()["subtotal_minor"] == 0


async def test_cart_requires_authentication_and_enforces_item_ownership(
    cart_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    unauthenticated = await cart_client.get("/api/v1/cart")
    assert unauthenticated.status_code == 401

    first_tokens = await _register(cart_client, "cart-owner@example.com")
    second_tokens = await _register(cart_client, "cart-other@example.com")
    variant_id = await _seed_variant_and_price(integration_engine)
    first_headers = {"Authorization": f"Bearer {first_tokens['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second_tokens['access_token']}"}

    added = await cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": str(variant_id), "quantity": 1},
        headers=first_headers,
    )
    item_id = added.json()["items"][0]["id"]

    forbidden_update = await cart_client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 2},
        headers=second_headers,
    )
    forbidden_delete = await cart_client.delete(
        f"/api/v1/cart/items/{item_id}",
        headers=second_headers,
    )

    assert forbidden_update.status_code == 404
    assert forbidden_update.json()["error"]["code"] == "cart_item_not_found"
    assert forbidden_delete.status_code == 404
    assert forbidden_delete.json()["error"]["code"] == "cart_item_not_found"

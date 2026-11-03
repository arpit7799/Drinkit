"""Integration tests for Search and Discovery API endpoints."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory, get_db
from app.main import app
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Category, Product, ProductVariant, product_categories
from app.models.inventory import FulfillmentLocation, InventoryBalance
from app.models.orders import Order, OrderLine
from app.models.pricing import VariantPrice

pytestmark = pytest.mark.integration


@pytest.fixture
async def search_api_client(
    integration_engine: AsyncEngine,
) -> AsyncIterator[tuple[AsyncClient, dict[str, str]]]:
    """Provide AsyncClient with populated catalog and cleanup."""

    seed_ids: dict[str, str] = {}
    async with AsyncSessionFactory(bind=integration_engine) as session:
        # Pre-clean
        await session.execute(delete(OrderLine))
        await session.execute(delete(Order))
        await session.execute(delete(CartItem))
        await session.execute(delete(ShoppingCart))
        await session.execute(delete(InventoryBalance))
        await session.execute(delete(VariantPrice))
        await session.execute(delete(FulfillmentLocation))
        await session.execute(delete(product_categories))
        await session.execute(delete(ProductVariant))
        await session.execute(delete(Product))
        await session.execute(delete(Category))
        await session.commit()

        # Seed categories
        whiskey_cat = Category(name="Whiskey", slug="whiskey", sort_order=1)
        mixers_cat = Category(name="Mixers", slug="mixers", sort_order=2)
        session.add_all([whiskey_cat, mixers_cat])
        await session.flush()

        # Seed dark store location
        loc = FulfillmentLocation(
            id=uuid4(),
            code="DEL-GK-01",
            name="Greater Kailash Dark Store",
            is_active=True,
        )
        session.add(loc)
        await session.flush()
        seed_ids["location_id"] = str(loc.id)

        # Seed Product 1: Jameson Irish Whiskey
        jameson = Product(
            name="Jameson Irish Whiskey",
            slug="jameson-irish-whiskey",
            brand="Jameson",
            description="Smooth triple-distilled blended Irish whiskey",
            is_alcoholic=True,
            abv_percent=Decimal("40.0"),
        )
        jameson.categories.append(whiskey_cat)
        session.add(jameson)
        await session.flush()
        seed_ids["jameson_id"] = str(jameson.id)

        jameson_var = ProductVariant(
            product_id=jameson.id,
            sku="JMS-750",
            name="750ml Bottle",
            quantity_value=Decimal("750"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(jameson_var)
        await session.flush()

        jameson_price = VariantPrice(
            variant_id=jameson_var.id,
            currency_code="INR",
            amount_minor=220000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        jameson_inv = InventoryBalance(
            location_id=loc.id,
            variant_id=jameson_var.id,
            on_hand_quantity=Decimal("30"),
            reserved_quantity=Decimal("0"),
        )
        session.add_all([jameson_price, jameson_inv])

        # Seed Product 2: Kinley Soda Water (Mixer)
        soda = Product(
            name="Kinley Club Soda",
            slug="kinley-club-soda",
            brand="Kinley",
            description="Crisp sparkling club soda mixer for drinks",
            is_alcoholic=False,
            abv_percent=None,
        )
        soda.categories.append(mixers_cat)
        session.add(soda)
        await session.flush()
        seed_ids["soda_id"] = str(soda.id)

        soda_var = ProductVariant(
            product_id=soda.id,
            sku="KINLEY-750",
            name="750ml PET",
            quantity_value=Decimal("750"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(soda_var)
        await session.flush()

        soda_price = VariantPrice(
            variant_id=soda_var.id,
            currency_code="INR",
            amount_minor=2000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        soda_inv = InventoryBalance(
            location_id=loc.id,
            variant_id=soda_var.id,
            on_hand_quantity=Decimal("80"),
            reserved_quantity=Decimal("0"),
        )
        session.add_all([soda_price, soda_inv])

        await session.commit()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSessionFactory(bind=integration_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, seed_ids
    finally:
        app.dependency_overrides.clear()
        async with AsyncSessionFactory(bind=integration_engine) as session:
            await session.execute(delete(InventoryBalance))
            await session.execute(delete(VariantPrice))
            await session.execute(delete(FulfillmentLocation))
            await session.execute(delete(product_categories))
            await session.execute(delete(ProductVariant))
            await session.execute(delete(Product))
            await session.execute(delete(Category))
            await session.commit()


async def test_search_api_basic_and_filters(
    search_api_client: tuple[AsyncClient, dict[str, str]],
) -> None:
    client, _ = search_api_client

    # 1. Broad query
    resp = await client.get("/api/v1/search?q=whiskey")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Jameson Irish Whiskey"
    assert data["items"][0]["starting_price_minor"] == 220000
    assert data["items"][0]["in_stock"] is True

    # 2. Filter by category
    resp_cat = await client.get("/api/v1/search?category=mixers")
    assert resp_cat.status_code == 200
    cat_data = resp_cat.json()
    assert cat_data["total"] == 1
    assert cat_data["items"][0]["slug"] == "kinley-club-soda"

    # 3. Filter by alcohol flag
    resp_alc = await client.get("/api/v1/search?is_alcoholic=false")
    assert resp_alc.status_code == 200
    alc_data = resp_alc.json()
    assert alc_data["total"] == 1
    assert alc_data["items"][0]["name"] == "Kinley Club Soda"


async def test_search_api_facets_and_autocomplete(
    search_api_client: tuple[AsyncClient, dict[str, str]],
) -> None:
    client, _ = search_api_client

    # 1. Facets endpoint
    resp_facets = await client.get("/api/v1/search/facets")
    assert resp_facets.status_code == 200
    facets_data = resp_facets.json()
    assert len(facets_data["categories"]) >= 2
    assert len(facets_data["brands"]) >= 2
    assert facets_data["min_price_minor"] == 2000
    assert facets_data["max_price_minor"] == 220000

    # 2. Autocomplete endpoint
    resp_auto = await client.get("/api/v1/search/autocomplete?q=jam")
    assert resp_auto.status_code == 200
    auto_data = resp_auto.json()
    assert auto_data["query"] == "jam"
    assert len(auto_data["suggestions"]) >= 1
    assert any("Jameson" in s["title"] for s in auto_data["suggestions"])


async def test_search_api_recommendations(
    search_api_client: tuple[AsyncClient, dict[str, str]],
) -> None:
    client, seed_ids = search_api_client
    jameson_id = seed_ids["jameson_id"]

    resp = await client.get(f"/api/v1/search/recommendations?product_id={jameson_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["product_id"] == jameson_id
    assert data["headline"] == "Pairs Well With"
    # Whiskey pairs with soda
    rec_names = [item["name"] for item in data["items"]]
    assert any("Soda" in name for name in rec_names)

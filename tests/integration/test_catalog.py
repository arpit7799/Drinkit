from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory, get_db
from app.main import app
from app.models.catalog import Category, Product, ProductVariant, product_categories

pytestmark = pytest.mark.integration


@pytest.fixture
async def catalog_client(integration_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
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
            await session.execute(delete(product_categories))
            await session.execute(delete(Product))
            await session.execute(delete(Category))
            await session.commit()


async def _seed_catalog(integration_engine: AsyncEngine) -> UUID:
    async with AsyncSessionFactory(bind=integration_engine) as session:
        spirits = Category(name="Spirits", slug="spirits", sort_order=1)
        gin = Category(name="Gin", slug="gin", parent_id=None, sort_order=1)
        product = Product(
            name="Juniper Gin",
            slug="juniper-gin",
            brand="Drinkit House",
            description="A crisp botanical gin.",
            is_alcoholic=True,
            abv_percent=Decimal("42.00"),
        )
        product.categories.append(spirits)
        product.variants.extend(
            [
                ProductVariant(
                    sku="GIN-700",
                    name="700 ml",
                    quantity_value=Decimal("700"),
                    quantity_unit="ml",
                ),
                ProductVariant(
                    sku="GIN-INACTIVE",
                    name="Inactive pack",
                    quantity_value=Decimal("1000"),
                    quantity_unit="ml",
                    is_active=False,
                ),
            ]
        )
        hidden = Product(
            name="Hidden Gin",
            slug="hidden-gin",
            is_alcoholic=True,
            abv_percent=Decimal("40.00"),
            is_active=False,
        )
        hidden.categories.append(spirits)
        hidden.variants.append(
            ProductVariant(
                sku="HIDDEN-700",
                name="700 ml",
                quantity_value=Decimal("700"),
                quantity_unit="ml",
            )
        )
        session.add_all([spirits, gin, product, hidden])
        await session.commit()
        return product.id


async def test_catalog_lists_only_active_products_and_variants(
    catalog_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    await _seed_catalog(integration_engine)

    categories = await catalog_client.get("/api/v1/catalog/categories")
    assert categories.status_code == 200
    assert [item["slug"] for item in categories.json()] == ["gin", "spirits"]

    products = await catalog_client.get(
        "/api/v1/catalog/products",
        params={"category_slug": "spirits", "limit": 10, "offset": 0},
    )
    assert products.status_code == 200
    payload = products.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["slug"] == "juniper-gin"
    assert [variant["sku"] for variant in payload["items"][0]["variants"]] == ["GIN-700"]
    assert "price" not in payload["items"][0]
    assert "inventory" not in payload["items"][0]


async def test_catalog_detail_uses_slug_and_hides_inactive_product(
    catalog_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    await _seed_catalog(integration_engine)

    detail = await catalog_client.get("/api/v1/catalog/products/juniper-gin")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Juniper Gin"

    case_insensitive_detail = await catalog_client.get("/api/v1/catalog/products/JUNIPER-GIN")
    assert case_insensitive_detail.status_code == 200

    hidden = await catalog_client.get("/api/v1/catalog/products/hidden-gin")
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "Product not found"


async def test_catalog_rejects_invalid_pagination(catalog_client: AsyncClient):
    response = await catalog_client.get(
        "/api/v1/catalog/products",
        params={"limit": 101, "offset": -1},
    )

    assert response.status_code == 422


async def test_category_parent_deletion_preserves_child_as_a_root(
    catalog_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    async with AsyncSessionFactory(bind=integration_engine) as session:
        parent = Category(id=uuid4(), name="Party", slug="party")
        child = Category(name="Mixers", slug="mixers", parent_id=parent.id)
        session.add_all([parent, child])
        await session.commit()

        await session.delete(parent)
        await session.commit()

    async with AsyncSessionFactory(bind=integration_engine) as session:
        surviving_child = await session.scalar(select(Category).where(Category.id == child.id))

    assert surviving_child is not None
    assert surviving_child.parent_id is None


async def test_database_rejects_case_insensitive_duplicate_skus(
    catalog_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    async with AsyncSessionFactory(bind=integration_engine) as session:
        product = Product(name="Vodka", slug="vodka", is_alcoholic=True, abv_percent=Decimal("40"))
        product.variants.extend(
            [
                ProductVariant(
                    sku="VODKA-700",
                    name="700 ml",
                    quantity_value=Decimal("700"),
                    quantity_unit="ml",
                ),
                ProductVariant(
                    sku="vodka-700",
                    name="Duplicate",
                    quantity_value=Decimal("700"),
                    quantity_unit="ml",
                ),
            ]
        )
        session.add(product)

        with pytest.raises(SQLAlchemyError):
            await session.commit()

        await session.rollback()


async def test_database_rejects_inconsistent_alcohol_attributes(
    catalog_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            Product(
                name="Soda",
                slug="soda",
                is_alcoholic=False,
                abv_percent=Decimal("1.00"),
            )
        )

        with pytest.raises(SQLAlchemyError):
            await session.commit()

        await session.rollback()

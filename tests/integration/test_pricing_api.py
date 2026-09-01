from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory, get_db
from app.main import app
from app.models.catalog import Product, ProductVariant
from app.models.pricing import VariantPrice
from app.modules.pricing.service import set_variant_price

pytestmark = pytest.mark.integration


@pytest.fixture
async def pricing_client(integration_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
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
            await session.execute(delete(VariantPrice))
            await session.execute(delete(ProductVariant))
            await session.execute(delete(Product))
            await session.commit()


async def _seed_priced_variants(integration_engine: AsyncEngine) -> tuple[UUID, UUID]:
    product_id = uuid4()
    priced_variant_id = uuid4()
    unpriced_variant_id = uuid4()
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            Product(
                id=product_id,
                name="API Pricing Product",
                slug=f"api-pricing-{product_id}",
                is_alcoholic=False,
            )
        )
        session.add_all(
            [
                ProductVariant(
                    id=priced_variant_id,
                    product_id=product_id,
                    sku=f"API-PRICE-{priced_variant_id}",
                    name="Priced unit",
                    quantity_value=Decimal("1"),
                    quantity_unit="unit",
                ),
                ProductVariant(
                    id=unpriced_variant_id,
                    product_id=product_id,
                    sku=f"API-NO-PRICE-{unpriced_variant_id}",
                    name="Unpriced unit",
                    quantity_value=Decimal("1"),
                    quantity_unit="unit",
                ),
            ]
        )
        await session.commit()
        await set_variant_price(
            session,
            variant_id=priced_variant_id,
            currency_code="INR",
            amount_minor=2599,
        )
    return priced_variant_id, unpriced_variant_id


async def test_catalog_price_endpoint_returns_current_variant_price(
    pricing_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    priced_variant_id, _ = await _seed_priced_variants(integration_engine)

    response = await pricing_client.get(
        f"/api/v1/catalog/variants/{priced_variant_id}/price",
        params={"currency_code": "inr"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "variant_id": str(priced_variant_id),
        "currency_code": "INR",
        "amount_minor": 2599,
    }


async def test_catalog_price_endpoint_hides_missing_price_and_rejects_invalid_currency(
    pricing_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    _, unpriced_variant_id = await _seed_priced_variants(integration_engine)

    missing = await pricing_client.get(f"/api/v1/catalog/variants/{unpriced_variant_id}/price")
    invalid = await pricing_client.get(
        f"/api/v1/catalog/variants/{unpriced_variant_id}/price",
        params={"currency_code": "US"},
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "price_not_found"
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_pricing_request"

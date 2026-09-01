from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import AsyncSessionFactory
from app.core.exceptions import (
    InvalidPricingRequest,
    PriceNotFound,
    VariantNotFound,
)
from app.models.catalog import Product, ProductVariant
from app.models.outbox_event import OutboxEvent
from app.models.pricing import VariantPrice
from app.modules.pricing.service import (
    deactivate_variant_price,
    get_current_variant_price,
    set_variant_price,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def pricing_scope(integration_engine: AsyncEngine):
    yield
    async with AsyncSessionFactory(bind=integration_engine) as session:
        await session.execute(delete(VariantPrice))
        await session.execute(delete(ProductVariant))
        await session.execute(delete(Product))
        await session.commit()


async def _seed_variant(integration_engine: AsyncEngine) -> UUID:
    product_id = uuid4()
    variant_id = uuid4()
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            Product(
                id=product_id,
                name="Pricing Test Soda",
                slug=f"pricing-test-{product_id}",
                is_alcoholic=False,
            )
        )
        session.add(
            ProductVariant(
                id=variant_id,
                product_id=product_id,
                sku=f"PRICE-{variant_id}",
                name="One bottle",
                quantity_value=Decimal("1"),
                quantity_unit="unit",
            )
        )
        await session.commit()
    return variant_id


async def test_pricing_selects_current_and_future_effective_price(
    integration_engine: AsyncEngine,
    pricing_scope: None,
):
    variant_id = await _seed_variant(integration_engine)
    now = datetime.now(UTC).replace(microsecond=0)
    future = now + timedelta(hours=1)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        current = await set_variant_price(
            session,
            variant_id=variant_id,
            currency_code="inr",
            amount_minor=1299,
            starts_at=now - timedelta(hours=1),
            ends_at=future,
        )
        scheduled = await set_variant_price(
            session,
            variant_id=variant_id,
            currency_code="INR",
            amount_minor=1499,
            starts_at=future,
        )
        selected_now = await get_current_variant_price(
            session,
            variant_id=variant_id,
            currency_code="INR",
            as_of=now,
        )
        selected_future = await get_current_variant_price(
            session,
            variant_id=variant_id,
            currency_code="INR",
            as_of=future + timedelta(seconds=1),
        )

    assert current.currency_code == "INR"
    assert current.amount_minor == 1299
    assert scheduled.amount_minor == 1499
    assert selected_now is not None
    assert selected_now.id == current.id
    assert selected_future is not None
    assert selected_future.id == scheduled.id


async def test_pricing_upsert_and_deactivation_are_idempotent_and_evented(
    integration_engine: AsyncEngine,
    pricing_scope: None,
):
    variant_id = await _seed_variant(integration_engine)
    starts_at = datetime.now(UTC).replace(microsecond=0)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        first = await set_variant_price(
            session,
            variant_id=variant_id,
            currency_code="INR",
            amount_minor=1000,
            starts_at=starts_at,
        )
        second = await set_variant_price(
            session,
            variant_id=variant_id,
            currency_code="inr",
            amount_minor=1100,
            starts_at=starts_at,
        )
        deactivated = await deactivate_variant_price(session, price_id=first.id)
        repeated = await deactivate_variant_price(session, price_id=first.id)
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.aggregate_id == first.id)
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
            )
        )

    assert second.id == first.id
    assert second.amount_minor == 1100
    assert deactivated.is_active is False
    assert repeated.is_active is False
    assert [event.event_type for event in events] == [
        "pricing.variant_price.set",
        "pricing.variant_price.set",
        "pricing.variant_price.deactivated",
    ]


async def test_pricing_rejects_invalid_requests_and_unknown_resources(
    integration_engine: AsyncEngine,
    pricing_scope: None,
):
    variant_id = await _seed_variant(integration_engine)
    starts_at = datetime.now(UTC).replace(microsecond=0)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        with pytest.raises(InvalidPricingRequest):
            await set_variant_price(
                session,
                variant_id=variant_id,
                currency_code="INR",
                amount_minor=-1,
                starts_at=starts_at,
            )
        with pytest.raises(InvalidPricingRequest):
            await set_variant_price(
                session,
                variant_id=variant_id,
                currency_code="US",
                amount_minor=100,
                starts_at=starts_at,
            )
        with pytest.raises(InvalidPricingRequest):
            await set_variant_price(
                session,
                variant_id=variant_id,
                currency_code="ÅBC",
                amount_minor=100,
                starts_at=starts_at,
            )
        with pytest.raises(InvalidPricingRequest):
            await set_variant_price(
                session,
                variant_id=variant_id,
                currency_code="INR",
                amount_minor=100,
                starts_at=starts_at,
                ends_at=starts_at,
            )
        with pytest.raises(VariantNotFound):
            await set_variant_price(
                session,
                variant_id=uuid4(),
                currency_code="INR",
                amount_minor=100,
                starts_at=starts_at,
            )
        with pytest.raises(PriceNotFound):
            await deactivate_variant_price(session, price_id=uuid4())

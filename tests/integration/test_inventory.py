import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import AsyncSessionFactory
from app.models.catalog import Product, ProductVariant, product_categories
from app.models.inventory import (
    FulfillmentLocation,
    InventoryBalance,
    InventoryReservation,
    StockAdjustment,
)
from app.modules.inventory.service import (
    InsufficientInventory,
    InventoryIdempotencyConflict,
    adjust_stock,
    release_reservation,
    reserve_stock,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def inventory_scope(integration_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with AsyncSessionFactory(bind=integration_engine) as session:
        await session.execute(delete(InventoryReservation))
        await session.execute(delete(StockAdjustment))
        await session.execute(delete(InventoryBalance))
        await session.execute(delete(FulfillmentLocation))
        await session.execute(delete(product_categories))
        await session.execute(delete(ProductVariant))
        await session.execute(delete(Product))
        await session.commit()


async def _seed_inventory(integration_engine: AsyncEngine) -> tuple[UUID, UUID]:
    product_id = uuid4()
    variant_id = uuid4()
    location_id = uuid4()
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            Product(
                id=product_id,
                name="Sparkling Water",
                slug=f"sparkling-water-{product_id}",
                is_alcoholic=False,
            )
        )
        session.add(
            ProductVariant(
                id=variant_id,
                product_id=product_id,
                sku=f"WATER-{variant_id}",
                name="750 ml",
                quantity_value=Decimal("750"),
                quantity_unit="ml",
            )
        )
        session.add(
            FulfillmentLocation(
                id=location_id,
                code=f"DS-{location_id}",
                name="Central Dark Store",
            )
        )
        await session.commit()
    return location_id, variant_id


async def test_stock_adjustment_is_idempotent_and_release_restores_reserved_quantity(
    integration_engine: AsyncEngine,
    inventory_scope: None,
):
    location_id, variant_id = await _seed_inventory(integration_engine)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        first = await adjust_stock(
            session,
            location_id=location_id,
            variant_id=variant_id,
            quantity_delta=Decimal("10"),
            reason="initial_receipt",
            idempotency_key="receipt-1",
        )
        first_id = first.id

    async with AsyncSessionFactory(bind=integration_engine) as session:
        second = await adjust_stock(
            session,
            location_id=location_id,
            variant_id=variant_id,
            quantity_delta=Decimal("10"),
            reason="initial_receipt",
            idempotency_key="receipt-1",
        )
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.location_id == location_id,
                InventoryBalance.variant_id == variant_id,
            )
        )
        adjustment_count = await session.scalar(select(func.count(StockAdjustment.id)))
        balance_on_hand = balance.on_hand_quantity if balance is not None else None
        second_id = second.id
        await session.commit()

        with pytest.raises(InventoryIdempotencyConflict):
            await adjust_stock(
                session,
                location_id=location_id,
                variant_id=variant_id,
                quantity_delta=Decimal("9"),
                reason="different_receipt",
                idempotency_key="receipt-1",
            )

    assert first_id == second_id
    assert balance_on_hand == Decimal("10.000")
    assert adjustment_count == 1

    async with AsyncSessionFactory(bind=integration_engine) as session:
        reservation = await reserve_stock(
            session,
            location_id=location_id,
            variant_id=variant_id,
            quantity=Decimal("6"),
            reservation_key="cart-1-line-1",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        retry = await reserve_stock(
            session,
            location_id=location_id,
            variant_id=variant_id,
            quantity=Decimal("6"),
            reservation_key="cart-1-line-1",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        assert reservation.id == retry.id
        reservation_id = reservation.id

        with pytest.raises(InsufficientInventory):
            await adjust_stock(
                session,
                location_id=location_id,
                variant_id=variant_id,
                quantity_delta=Decimal("-5"),
                reason="damaged_stock",
                idempotency_key="damage-1",
            )

        released = await release_reservation(session, reservation_id)
        released_retry = await release_reservation(session, reservation_id)
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.location_id == location_id,
                InventoryBalance.variant_id == variant_id,
            )
        )

    assert released.status == "released"
    assert released_retry.id == released.id
    assert balance is not None
    assert balance.reserved_quantity == Decimal("0.000")


async def test_expired_reservation_returns_stock_before_new_reservation(
    integration_engine: AsyncEngine,
    inventory_scope: None,
):
    location_id, variant_id = await _seed_inventory(integration_engine)
    async with AsyncSessionFactory(bind=integration_engine) as session:
        await adjust_stock(
            session,
            location_id=location_id,
            variant_id=variant_id,
            quantity_delta=Decimal("5"),
            reason="receipt",
            idempotency_key="receipt-expiry",
        )
        old_reservation = await reserve_stock(
            session,
            location_id=location_id,
            variant_id=variant_id,
            quantity=Decimal("4"),
            reservation_key="expired-cart",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.id == old_reservation.id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()

        new_reservation = await reserve_stock(
            session,
            location_id=location_id,
            variant_id=variant_id,
            quantity=Decimal("5"),
            reservation_key="new-cart",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    assert new_reservation.quantity == Decimal("5.000")


async def test_concurrent_reservations_cannot_oversubscribe_one_balance(
    integration_engine: AsyncEngine,
    inventory_scope: None,
):
    location_id, variant_id = await _seed_inventory(integration_engine)
    async with AsyncSessionFactory(bind=integration_engine) as session:
        await adjust_stock(
            session,
            location_id=location_id,
            variant_id=variant_id,
            quantity_delta=Decimal("5"),
            reason="receipt-concurrency",
            idempotency_key="receipt-concurrency",
        )

    async def attempt(key: str) -> str:
        async with AsyncSessionFactory(bind=integration_engine) as session:
            try:
                await reserve_stock(
                    session,
                    location_id=location_id,
                    variant_id=variant_id,
                    quantity=Decimal("4"),
                    reservation_key=key,
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                )
            except InsufficientInventory:
                return "insufficient"
            return "reserved"

    outcomes = await asyncio.gather(attempt("concurrent-a"), attempt("concurrent-b"))

    assert sorted(outcomes) == ["insufficient", "reserved"]

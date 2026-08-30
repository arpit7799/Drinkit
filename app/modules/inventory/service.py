"""Transactional inventory adjustment and reservation workflows."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import transaction
from app.core.exceptions import (
    InsufficientInventory,
    InvalidInventoryRequest,
    InventoryIdempotencyConflict,
    InventoryNotFound,
    ReservationConflict,
)
from app.models.catalog import ProductVariant
from app.models.inventory import (
    FulfillmentLocation,
    InventoryBalance,
    InventoryReservation,
    StockAdjustment,
)


async def adjust_stock(
    session: AsyncSession,
    *,
    location_id: UUID,
    variant_id: UUID,
    quantity_delta: Decimal,
    reason: str,
    idempotency_key: str,
) -> InventoryBalance:
    """Apply one idempotent stock delta while holding the inventory row lock."""

    if quantity_delta == 0 or not reason.strip() or not idempotency_key.strip():
        raise InvalidInventoryRequest

    async with transaction(session):
        await _require_active_inventory_subjects(session, location_id, variant_id)
        balance = await _lock_or_create_balance(session, location_id, variant_id)
        existing = await session.scalar(
            select(StockAdjustment)
            .where(
                StockAdjustment.location_id == location_id,
                StockAdjustment.variant_id == variant_id,
                StockAdjustment.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.quantity_delta != quantity_delta or existing.reason != reason:
                raise InventoryIdempotencyConflict
            return balance

        new_on_hand = balance.on_hand_quantity + quantity_delta
        if new_on_hand < balance.reserved_quantity:
            raise InsufficientInventory

        balance.on_hand_quantity = new_on_hand
        session.add(
            StockAdjustment(
                location_id=location_id,
                variant_id=variant_id,
                quantity_delta=quantity_delta,
                reason=reason,
                idempotency_key=idempotency_key,
            )
        )
        await session.flush()
        return balance


async def reserve_stock(
    session: AsyncSession,
    *,
    location_id: UUID,
    variant_id: UUID,
    quantity: Decimal,
    reservation_key: str,
    expires_at: datetime,
) -> InventoryReservation:
    """Reserve available stock atomically and make retries idempotent."""

    now = datetime.now(UTC)
    if quantity <= 0 or not reservation_key.strip() or expires_at <= now:
        raise InvalidInventoryRequest

    async with transaction(session):
        await _require_active_inventory_subjects(session, location_id, variant_id)
        balance = await session.scalar(
            select(InventoryBalance)
            .where(
                InventoryBalance.location_id == location_id,
                InventoryBalance.variant_id == variant_id,
            )
            .with_for_update()
        )
        if balance is None:
            raise InsufficientInventory

        await _expire_reservations(session, balance, now)
        existing = await session.scalar(
            select(InventoryReservation)
            .where(
                InventoryReservation.location_id == location_id,
                InventoryReservation.variant_id == variant_id,
                InventoryReservation.reservation_key == reservation_key,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.status == "active" and existing.quantity == quantity:
                return existing
            raise ReservationConflict

        available = balance.on_hand_quantity - balance.reserved_quantity
        if available < quantity:
            raise InsufficientInventory

        reservation = InventoryReservation(
            location_id=location_id,
            variant_id=variant_id,
            reservation_key=reservation_key,
            quantity=quantity,
            status="active",
            expires_at=expires_at,
        )
        balance.reserved_quantity += quantity
        session.add(reservation)
        await session.flush()
        return reservation


async def release_reservation(
    session: AsyncSession,
    reservation_id: UUID,
) -> InventoryReservation:
    """Release an active reservation and return its quantity to availability."""

    async with transaction(session):
        reservation = await session.scalar(
            select(InventoryReservation).where(InventoryReservation.id == reservation_id)
        )
        if reservation is None:
            raise InventoryNotFound

        balance = await session.scalar(
            select(InventoryBalance)
            .where(
                InventoryBalance.location_id == reservation.location_id,
                InventoryBalance.variant_id == reservation.variant_id,
            )
            .with_for_update()
        )
        if balance is None:
            raise InventoryNotFound

        locked_reservation = await session.scalar(
            select(InventoryReservation)
            .where(InventoryReservation.id == reservation_id)
            .with_for_update()
        )
        if locked_reservation is None:
            raise InventoryNotFound

        if locked_reservation.status == "active":
            now = datetime.now(UTC)
            locked_reservation.status = (
                "expired" if locked_reservation.expires_at <= now else "released"
            )
            balance.reserved_quantity -= locked_reservation.quantity
            if balance.reserved_quantity < 0:
                raise InvalidInventoryRequest
            await session.flush()
        return locked_reservation


async def _require_active_inventory_subjects(
    session: AsyncSession,
    location_id: UUID,
    variant_id: UUID,
) -> None:
    location = await session.scalar(
        select(FulfillmentLocation).where(FulfillmentLocation.id == location_id)
    )
    variant = await session.scalar(select(ProductVariant).where(ProductVariant.id == variant_id))
    if location is None or not location.is_active or variant is None or not variant.is_active:
        raise InventoryNotFound


async def _lock_or_create_balance(
    session: AsyncSession,
    location_id: UUID,
    variant_id: UUID,
) -> InventoryBalance:
    await session.execute(
        pg_insert(InventoryBalance)
        .values(
            location_id=location_id,
            variant_id=variant_id,
            on_hand_quantity=Decimal("0"),
            reserved_quantity=Decimal("0"),
        )
        .on_conflict_do_nothing(index_elements=["location_id", "variant_id"])
    )
    balance = await session.scalar(
        select(InventoryBalance)
        .where(
            InventoryBalance.location_id == location_id,
            InventoryBalance.variant_id == variant_id,
        )
        .with_for_update()
    )
    if balance is None:
        raise InventoryNotFound
    return balance


async def _expire_reservations(
    session: AsyncSession,
    balance: InventoryBalance,
    now: datetime,
) -> None:
    expired = await session.scalars(
        select(InventoryReservation)
        .where(
            InventoryReservation.location_id == balance.location_id,
            InventoryReservation.variant_id == balance.variant_id,
            InventoryReservation.status == "active",
            InventoryReservation.expires_at <= now,
        )
        .with_for_update()
    )
    for reservation in expired:
        reservation.status = "expired"
        balance.reserved_quantity -= reservation.quantity
    if balance.reserved_quantity < 0:
        raise InvalidInventoryRequest

"""Transactional delivery scheduling and courier assignment workflows."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import transaction
from app.core.exceptions import (
    CourierNotFound,
    DeliveryNotFound,
    DeliverySlotNotFound,
    InvalidDeliveryRequest,
    OrderNotFound,
    OrderStatusConflict,
)
from app.models.delivery import Courier, Delivery, DeliverySlot
from app.models.orders import Order
from app.models.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)


async def schedule_delivery(
    session: AsyncSession,
    *,
    order_id: UUID,
    slot_id: UUID,
) -> Delivery:
    """Schedule a delivery for a confirmed order in a specific time slot."""

    async with transaction(session):
        order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None:
            raise OrderNotFound

        if order.status not in ("confirmed", "fulfilled"):
            raise OrderStatusConflict

        # Check if delivery already exists
        existing = await session.scalar(select(Delivery).where(Delivery.order_id == order_id))
        if existing is not None:
            raise InvalidDeliveryRequest

        # Validate and lock slot
        slot = await session.scalar(
            select(DeliverySlot).where(DeliverySlot.id == slot_id).with_for_update()
        )
        if slot is None:
            raise DeliverySlotNotFound

        if not slot.is_active:
            raise InvalidDeliveryRequest

        # Check capacity - count existing scheduled deliveries in this slot
        delivery_count = await session.scalar(
            select(func.count(Delivery.id)).where(
                Delivery.slot_id == slot_id, Delivery.status != "cancelled"
            )
        )
        if (delivery_count or 0) >= slot.capacity:
            raise InvalidDeliveryRequest

        # Create delivery
        delivery = Delivery(
            order_id=order_id,
            slot_id=slot_id,
            status="scheduled",
        )
        session.add(delivery)

        # Update order status if needed
        if order.status == "confirmed":
            order.status = "fulfilled"

        await session.flush()

        # Emit outbox event
        session.add(
            OutboxEvent(
                aggregate_type="delivery",
                aggregate_id=delivery.id,
                event_type="delivery.scheduled",
                payload={
                    "order_id": str(order_id),
                    "slot_id": str(slot_id),
                    "status": "scheduled",
                },
            )
        )

        logger.info(
            "delivery_scheduled",
            extra={
                "delivery_id": str(delivery.id),
                "order_id": str(order_id),
                "slot_id": str(slot_id),
            },
        )

        return await _require_loaded_delivery(session, delivery.id)


async def assign_courier(
    session: AsyncSession,
    *,
    delivery_id: UUID,
    courier_id: UUID,
) -> Delivery:
    """Assign a courier to a scheduled delivery."""

    async with transaction(session):
        delivery = await _load_delivery_for_update(session, delivery_id)
        if delivery is None:
            raise DeliveryNotFound

        if delivery.status not in ("scheduled", "assigned"):
            raise InvalidDeliveryRequest

        courier = await session.scalar(
            select(Courier)
            .where(Courier.id == courier_id, Courier.is_active.is_(True))
            .with_for_update()
        )
        if courier is None:
            raise CourierNotFound

        delivery.courier_id = courier_id
        delivery.status = "assigned"

        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="delivery",
                aggregate_id=delivery.id,
                event_type="delivery.assigned",
                payload={
                    "courier_id": str(courier_id),
                    "status": "assigned",
                },
            )
        )

        logger.info(
            "courier_assigned",
            extra={
                "delivery_id": str(delivery_id),
                "courier_id": str(courier_id),
            },
        )

        return await _require_loaded_delivery(session, delivery.id)


async def mark_picked_up(
    session: AsyncSession,
    *,
    delivery_id: UUID,
) -> Delivery:
    """Mark a delivery as picked up by the courier."""

    async with transaction(session):
        delivery = await _load_delivery_for_update(session, delivery_id)
        if delivery is None:
            raise DeliveryNotFound

        if delivery.status != "assigned":
            raise InvalidDeliveryRequest

        delivery.status = "picked_up"

        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="delivery",
                aggregate_id=delivery.id,
                event_type="delivery.picked_up",
                payload={},
            )
        )

        logger.info(
            "delivery_picked_up",
            extra={"delivery_id": str(delivery_id)},
        )

        return await _require_loaded_delivery(session, delivery.id)


async def mark_in_transit(
    session: AsyncSession,
    *,
    delivery_id: UUID,
) -> Delivery:
    """Mark a delivery as in transit."""

    async with transaction(session):
        delivery = await _load_delivery_for_update(session, delivery_id)
        if delivery is None:
            raise DeliveryNotFound

        if delivery.status != "picked_up":
            raise InvalidDeliveryRequest

        delivery.status = "in_transit"

        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="delivery",
                aggregate_id=delivery.id,
                event_type="delivery.in_transit",
                payload={},
            )
        )

        logger.info(
            "delivery_in_transit",
            extra={"delivery_id": str(delivery_id)},
        )

        return await _require_loaded_delivery(session, delivery.id)


async def mark_delivered(
    session: AsyncSession,
    *,
    delivery_id: UUID,
    tracking_number: str | None = None,
) -> Delivery:
    """Mark a delivery as completed."""

    async with transaction(session):
        delivery = await _load_delivery_for_update(session, delivery_id)
        if delivery is None:
            raise DeliveryNotFound

        if delivery.status != "in_transit":
            raise InvalidDeliveryRequest

        delivery.status = "delivered"
        delivery.actual_delivery_at = datetime.now(UTC)
        if tracking_number:
            delivery.tracking_number = tracking_number

        await session.flush()

        # Update order status
        order = await session.scalar(
            select(Order).where(Order.id == delivery.order_id).with_for_update()
        )
        if order is not None:
            order.status = "fulfilled"

        session.add(
            OutboxEvent(
                aggregate_type="delivery",
                aggregate_id=delivery.id,
                event_type="delivery.delivered",
                payload={
                    "tracking_number": tracking_number,
                    "actual_delivery_at": (
                        delivery.actual_delivery_at.isoformat()
                        if delivery.actual_delivery_at
                        else None
                    ),
                },
            )
        )

        logger.info(
            "delivery_completed",
            extra={
                "delivery_id": str(delivery.id),
                "tracking_number": tracking_number,
            },
        )

        return await _require_loaded_delivery(session, delivery.id)


async def _load_delivery_for_update(session: AsyncSession, delivery_id: UUID) -> Delivery | None:
    """Load delivery with row lock for updates."""
    return await session.scalar(
        select(Delivery).where(Delivery.id == delivery_id).with_for_update()
    )


async def _load_delivery(session: AsyncSession, delivery_id: UUID) -> Delivery | None:
    """Load delivery with relationships eagerly."""
    statement = (
        select(Delivery)
        .options(
            selectinload(Delivery.courier),
            selectinload(Delivery.slot),
        )
        .where(Delivery.id == delivery_id)
    )
    return await session.scalar(statement)


async def _require_loaded_delivery(session: AsyncSession, delivery_id: UUID) -> Delivery:
    """Load delivery with relationships eagerly, raising if not found."""
    delivery = await _load_delivery(session, delivery_id)
    if delivery is None:
        raise DeliveryNotFound
    return delivery

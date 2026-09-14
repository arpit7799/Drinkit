"""Delivery and courier admin service."""

import logging
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import transaction
from app.core.exceptions import (
    DeliverySlotNotFound,
    InvalidDeliveryRequest,
)
from app.models.delivery import Courier, DeliverySlot
from app.models.inventory import FulfillmentLocation
from app.models.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)


async def list_slots(
    session: AsyncSession,
    *,
    location_id: UUID,
    active_only: bool = True,
) -> Sequence[DeliverySlot]:
    """List delivery slots for a fulfillment location."""

    statement = select(DeliverySlot).where(DeliverySlot.fulfillment_location_id == location_id)
    if active_only:
        statement = statement.where(DeliverySlot.is_active.is_(True))
    statement = statement.order_by(DeliverySlot.start_at)
    result = await session.scalars(statement)
    return result.all()


async def create_slot(
    session: AsyncSession,
    *,
    location_id: UUID,
    start_at: datetime,
    end_at: datetime,
    capacity: int,
) -> DeliverySlot:
    """Create a delivery slot for a fulfillment location."""

    if capacity < 1:
        raise InvalidDeliveryRequest

    async with transaction(session):
        location = await session.scalar(
            select(FulfillmentLocation)
            .where(FulfillmentLocation.id == location_id)
            .with_for_update()
        )
        if location is None:
            raise DeliverySlotNotFound

        slot = DeliverySlot(
            fulfillment_location_id=location_id,
            start_at=start_at,
            end_at=end_at,
            capacity=capacity,
        )
        session.add(slot)
        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="delivery_slot",
                aggregate_id=slot.id,
                event_type="delivery_slot.created",
                payload={
                    "location_id": str(location_id),
                    "start_at": slot.start_at.isoformat(),
                    "end_at": slot.end_at.isoformat(),
                    "capacity": capacity,
                },
            )
        )

        logger.info(
            "delivery_slot_created",
            extra={
                "slot_id": str(slot.id),
                "location_id": str(location_id),
                "capacity": capacity,
            },
        )

        return slot


async def list_couriers(
    session: AsyncSession,
    *,
    active_only: bool = False,
) -> Sequence[Courier]:
    """List couriers."""

    statement = select(Courier)
    if active_only:
        statement = statement.where(Courier.is_active.is_(True))
    statement = statement.order_by(Courier.name)
    result = await session.scalars(statement)
    return result.all()


async def create_courier(
    session: AsyncSession,
    *,
    name: str,
    phone: str,
    vehicle_type: str,
) -> Courier:
    """Create a courier."""

    if vehicle_type not in ("bike", "scooter", "van", "truck"):
        raise InvalidDeliveryRequest

    async with transaction(session):
        courier = Courier(
            name=name,
            phone=phone,
            vehicle_type=vehicle_type,
        )
        session.add(courier)
        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="courier",
                aggregate_id=courier.id,
                event_type="courier.created",
                payload={
                    "name": name,
                    "vehicle_type": vehicle_type,
                },
            )
        )

        logger.info(
            "courier_created",
            extra={
                "courier_id": str(courier.id),
                "name": name,
                "vehicle_type": vehicle_type,
            },
        )

        return courier

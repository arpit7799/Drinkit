"""Dark store warehouse picking, packing, staging, and inventory workflows."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import transaction
from app.core.exceptions import (
    InvalidWarehouseRequest,
    OrderNotFound,
    WarehouseItemNotFound,
    WarehouseTaskConflict,
    WarehouseTaskNotFound,
)
from app.models.catalog import ProductVariant
from app.models.delivery import Delivery
from app.models.inventory import FulfillmentLocation
from app.models.orders import Order
from app.models.outbox_event import OutboxEvent
from app.models.warehouse import FulfillmentTaskItem, OrderFulfillmentTask, WarehouseBin
from app.modules.inventory.service import adjust_stock
from app.modules.warehouse.schemas import (
    BinZoneType,
    FulfillmentTaskStatus,
    WarehouseMetricsResponse,
)

logger = logging.getLogger(__name__)


async def create_fulfillment_task_for_order(
    session: AsyncSession,
    *,
    order_id: UUID,
    location_id: UUID,
) -> OrderFulfillmentTask:
    """Create a new dark-store fulfillment picking task for a confirmed order."""

    async with transaction(session):
        order = await session.scalar(
            select(Order)
            .options(selectinload(Order.lines))
            .where(Order.id == order_id)
            .with_for_update()
        )
        if order is None:
            raise OrderNotFound

        existing_task = await session.scalar(
            select(OrderFulfillmentTask)
            .options(selectinload(OrderFulfillmentTask.items))
            .where(OrderFulfillmentTask.order_id == order_id)
        )
        if existing_task is not None:
            return existing_task

        task = OrderFulfillmentTask(
            order_id=order_id,
            fulfillment_location_id=location_id,
            status=FulfillmentTaskStatus.PENDING,
        )
        session.add(task)
        await session.flush()

        for line in order.lines:
            variant = await session.scalar(
                select(ProductVariant).where(ProductVariant.id == line.variant_id)
            )
            sku = variant.sku if variant else "UNKNOWN"

            # Determine bin location if bin exists
            bin_entry = await session.scalar(
                select(WarehouseBin).where(
                    WarehouseBin.fulfillment_location_id == location_id,
                    WarehouseBin.is_active.is_(True),
                )
            )
            bin_location = bin_entry.bin_code if bin_entry else None

            item = FulfillmentTaskItem(
                task_id=task.id,
                variant_id=line.variant_id,
                sku=sku,
                expected_quantity=line.quantity,
                picked_quantity=0,
                is_shortage=False,
                is_damaged=False,
                bin_location=bin_location,
            )
            session.add(item)

        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="order_fulfillment",
                aggregate_id=task.id,
                event_type="warehouse.task.created",
                payload={
                    "order_id": str(order_id),
                    "location_id": str(location_id),
                    "items_count": len(order.lines),
                },
            )
        )
        logger.info(
            "fulfillment_task_created",
            extra={"task_id": str(task.id), "order_id": str(order_id)},
        )
        loaded = await session.scalar(
            select(OrderFulfillmentTask)
            .options(selectinload(OrderFulfillmentTask.items))
            .where(OrderFulfillmentTask.id == task.id)
        )
        return loaded or task


async def create_warehouse_bin(
    session: AsyncSession,
    *,
    location_id: UUID,
    bin_code: str,
    zone_type: BinZoneType = BinZoneType.AMBIENT,
) -> WarehouseBin:
    """Register a new shelf, cooler, or dispatch staging bay in a dark store."""

    clean_code = bin_code.strip()
    if not clean_code:
        raise InvalidWarehouseRequest

    async with transaction(session):
        location = await session.scalar(
            select(FulfillmentLocation).where(FulfillmentLocation.id == location_id)
        )
        if location is None:
            raise InvalidWarehouseRequest

        existing = await session.scalar(
            select(WarehouseBin).where(
                WarehouseBin.fulfillment_location_id == location_id,
                func.lower(WarehouseBin.bin_code) == clean_code.lower(),
            )
        )
        if existing is not None:
            raise InvalidWarehouseRequest

        bin_obj = WarehouseBin(
            fulfillment_location_id=location_id,
            bin_code=clean_code,
            zone_type=zone_type.value,
            is_active=True,
        )
        session.add(bin_obj)
        await session.flush()
        return bin_obj


async def list_warehouse_bins(
    session: AsyncSession,
    *,
    location_id: UUID,
    zone_type: BinZoneType | None = None,
) -> Sequence[WarehouseBin]:
    """Retrieve all configured bins for a fulfillment dark store."""

    stmt = select(WarehouseBin).where(
        WarehouseBin.fulfillment_location_id == location_id,
        WarehouseBin.is_active.is_(True),
    )
    if zone_type is not None:
        stmt = stmt.where(WarehouseBin.zone_type == zone_type.value)

    stmt = stmt.order_by(WarehouseBin.bin_code)
    return (await session.scalars(stmt)).all()


async def list_fulfillment_tasks(
    session: AsyncSession,
    *,
    location_id: UUID,
    status: FulfillmentTaskStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[OrderFulfillmentTask], int]:
    """List fulfillment tasks ordered by oldest created first (FIFO)."""

    stmt = (
        select(OrderFulfillmentTask)
        .options(selectinload(OrderFulfillmentTask.items))
        .where(OrderFulfillmentTask.fulfillment_location_id == location_id)
    )
    if status is not None:
        stmt = stmt.where(OrderFulfillmentTask.status == status.value)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = await session.scalar(count_stmt) or 0

    stmt = stmt.order_by(OrderFulfillmentTask.created_at.asc()).offset(offset).limit(limit)
    rows = (await session.scalars(stmt)).all()
    return rows, total


async def get_fulfillment_task(
    session: AsyncSession,
    *,
    task_id: UUID,
) -> OrderFulfillmentTask:
    """Retrieve fulfillment task with items loaded."""

    task = await session.scalar(
        select(OrderFulfillmentTask)
        .options(selectinload(OrderFulfillmentTask.items))
        .where(OrderFulfillmentTask.id == task_id)
    )
    if task is None:
        raise WarehouseTaskNotFound
    return task


async def start_picking_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    picker_id: UUID,
) -> OrderFulfillmentTask:
    """Assign picker to task and begin order picking."""

    async with transaction(session):
        task = await session.scalar(
            select(OrderFulfillmentTask)
            .options(selectinload(OrderFulfillmentTask.items))
            .where(OrderFulfillmentTask.id == task_id)
            .with_for_update()
        )
        if task is None:
            raise WarehouseTaskNotFound

        if task.status != FulfillmentTaskStatus.PENDING:
            raise WarehouseTaskConflict

        task.status = FulfillmentTaskStatus.PICKING
        task.picker_id = picker_id
        task.started_at = datetime.now(UTC)
        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="order_fulfillment",
                aggregate_id=task.id,
                event_type="warehouse.picking.started",
                payload={"order_id": str(task.order_id), "picker_id": str(picker_id)},
            )
        )
        return task


async def scan_and_pick_item(
    session: AsyncSession,
    *,
    task_id: UUID,
    variant_id: UUID,
    quantity: int,
    is_damaged: bool = False,
) -> FulfillmentTaskItem:
    """Record verified barcode scan and picked quantity for a line item."""

    if quantity <= 0:
        raise InvalidWarehouseRequest

    async with transaction(session):
        task = await session.scalar(
            select(OrderFulfillmentTask).where(OrderFulfillmentTask.id == task_id).with_for_update()
        )
        if task is None:
            raise WarehouseTaskNotFound

        if task.status != FulfillmentTaskStatus.PICKING:
            raise WarehouseTaskConflict

        item = await session.scalar(
            select(FulfillmentTaskItem)
            .where(
                FulfillmentTaskItem.task_id == task_id,
                FulfillmentTaskItem.variant_id == variant_id,
            )
            .with_for_update()
        )
        if item is None:
            raise WarehouseItemNotFound

        if is_damaged:
            item.is_damaged = True
            item.is_shortage = True
        else:
            item.picked_quantity += quantity
            if item.picked_quantity < item.expected_quantity:
                item.is_shortage = True
            else:
                item.is_shortage = False

        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="order_fulfillment",
                aggregate_id=task.id,
                event_type="warehouse.item.scanned",
                payload={
                    "task_id": str(task_id),
                    "variant_id": str(variant_id),
                    "picked_quantity": item.picked_quantity,
                    "is_damaged": is_damaged,
                },
            )
        )
        return item


async def complete_picking(
    session: AsyncSession,
    *,
    task_id: UUID,
) -> OrderFulfillmentTask:
    """Mark all items picked and transition task to picked."""

    async with transaction(session):
        task = await session.scalar(
            select(OrderFulfillmentTask)
            .options(selectinload(OrderFulfillmentTask.items))
            .where(OrderFulfillmentTask.id == task_id)
            .with_for_update()
        )
        if task is None:
            raise WarehouseTaskNotFound

        if task.status != FulfillmentTaskStatus.PICKING:
            raise WarehouseTaskConflict

        task.status = FulfillmentTaskStatus.PICKED
        task.picked_at = datetime.now(UTC)
        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="order_fulfillment",
                aggregate_id=task.id,
                event_type="warehouse.picking.completed",
                payload={"order_id": str(task.order_id)},
            )
        )
        return task


async def pack_and_stage_order(
    session: AsyncSession,
    *,
    task_id: UUID,
    packer_id: UUID,
    staging_bay: str,
    bag_seal_number: str,
) -> OrderFulfillmentTask:
    """Pack items into tamper-evident delivery bag and place in dispatch staging bay."""

    if not staging_bay.strip() or not bag_seal_number.strip():
        raise InvalidWarehouseRequest

    async with transaction(session):
        task = await session.scalar(
            select(OrderFulfillmentTask)
            .options(selectinload(OrderFulfillmentTask.items))
            .where(OrderFulfillmentTask.id == task_id)
            .with_for_update()
        )
        if task is None:
            raise WarehouseTaskNotFound

        if task.status not in (FulfillmentTaskStatus.PICKED, FulfillmentTaskStatus.PICKING):
            raise WarehouseTaskConflict

        now = datetime.now(UTC)
        task.status = FulfillmentTaskStatus.STAGED
        task.packer_id = packer_id
        task.staging_bay = staging_bay.strip().upper()
        task.bag_seal_number = bag_seal_number.strip()
        task.packed_at = now
        task.staged_at = now
        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="order_fulfillment",
                aggregate_id=task.id,
                event_type="warehouse.order.staged",
                payload={
                    "order_id": str(task.order_id),
                    "staging_bay": task.staging_bay,
                    "bag_seal_number": task.bag_seal_number,
                },
            )
        )
        return task


async def dispatch_order_to_courier(
    session: AsyncSession,
    *,
    task_id: UUID,
    courier_id: UUID,
) -> OrderFulfillmentTask:
    """Handover staged bag from staging bay to delivery partner."""

    async with transaction(session):
        task = await session.scalar(
            select(OrderFulfillmentTask)
            .options(selectinload(OrderFulfillmentTask.items))
            .where(OrderFulfillmentTask.id == task_id)
            .with_for_update()
        )
        if task is None:
            raise WarehouseTaskNotFound

        if task.status != FulfillmentTaskStatus.STAGED:
            raise WarehouseTaskConflict

        now = datetime.now(UTC)
        task.status = FulfillmentTaskStatus.DISPATCHED
        task.dispatched_at = now

        # Update order status to fulfilled if still confirmed
        order = await session.scalar(
            select(Order).where(Order.id == task.order_id).with_for_update()
        )
        if order is not None and order.status == "confirmed":
            order.status = "fulfilled"

        # Update delivery status to picked_up / in_transit if assigned
        delivery = await session.scalar(
            select(Delivery).where(Delivery.order_id == task.order_id).with_for_update()
        )
        if delivery is not None:
            delivery.courier_id = courier_id
            delivery.status = "picked_up"

        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="order_fulfillment",
                aggregate_id=task.id,
                event_type="warehouse.order.dispatched",
                payload={
                    "order_id": str(task.order_id),
                    "courier_id": str(courier_id),
                },
            )
        )
        return task


async def inward_stock_grn(
    session: AsyncSession,
    *,
    location_id: UUID,
    variant_id: UUID,
    quantity: Decimal,
    invoice_ref: str,
    idempotency_key: str,
) -> None:
    """Goods Receipt Note (GRN) dark-store stock inwarding."""

    reason = f"GRN: Inwarded invoice {invoice_ref.strip()}"
    await adjust_stock(
        session,
        location_id=location_id,
        variant_id=variant_id,
        quantity_delta=quantity,
        reason=reason,
        idempotency_key=idempotency_key,
    )


async def write_off_breakage_waste(
    session: AsyncSession,
    *,
    location_id: UUID,
    variant_id: UUID,
    quantity: Decimal,
    reason: str,
    reported_by: str,
    idempotency_key: str,
) -> None:
    """Record broken, leaking, or damaged liquid/glass stock write-off."""

    delta = -abs(quantity)
    waste_reason = f"Breakage/Waste: {reason.strip()} (reported by {reported_by.strip()})"
    await adjust_stock(
        session,
        location_id=location_id,
        variant_id=variant_id,
        quantity_delta=delta,
        reason=waste_reason,
        idempotency_key=idempotency_key,
    )


async def get_warehouse_metrics(
    session: AsyncSession,
    *,
    location_id: UUID,
) -> WarehouseMetricsResponse:
    """Calculate operational KPIs for a dark store."""

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    pending_count = (
        await session.scalar(
            select(func.count(OrderFulfillmentTask.id)).where(
                OrderFulfillmentTask.fulfillment_location_id == location_id,
                OrderFulfillmentTask.status == FulfillmentTaskStatus.PENDING,
            )
        )
        or 0
    )

    picking_count = (
        await session.scalar(
            select(func.count(OrderFulfillmentTask.id)).where(
                OrderFulfillmentTask.fulfillment_location_id == location_id,
                OrderFulfillmentTask.status == FulfillmentTaskStatus.PICKING,
            )
        )
        or 0
    )

    staged_count = (
        await session.scalar(
            select(func.count(OrderFulfillmentTask.id)).where(
                OrderFulfillmentTask.fulfillment_location_id == location_id,
                OrderFulfillmentTask.status == FulfillmentTaskStatus.STAGED,
            )
        )
        or 0
    )

    dispatched_today_count = (
        await session.scalar(
            select(func.count(OrderFulfillmentTask.id)).where(
                OrderFulfillmentTask.fulfillment_location_id == location_id,
                OrderFulfillmentTask.status == FulfillmentTaskStatus.DISPATCHED,
                OrderFulfillmentTask.dispatched_at >= today_start,
            )
        )
        or 0
    )

    bins_count = (
        await session.scalar(
            select(func.count(WarehouseBin.id)).where(
                WarehouseBin.fulfillment_location_id == location_id,
                WarehouseBin.is_active.is_(True),
            )
        )
        or 0
    )

    return WarehouseMetricsResponse(
        location_id=location_id,
        pending_orders=pending_count,
        active_picking=picking_count,
        staged_orders=staged_count,
        dispatched_today=dispatched_today_count,
        active_bins=bins_count,
    )

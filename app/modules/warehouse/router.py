"""Dark store warehouse operations API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.warehouse.schemas import (
    BinZoneType,
    DispatchOrderRequest,
    FulfillmentItemResponse,
    FulfillmentTaskResponse,
    FulfillmentTaskStatus,
    InwardStockRequest,
    PackAndStageRequest,
    PickItemRequest,
    RecordBreakageRequest,
    StartPickingRequest,
    WarehouseBinCreate,
    WarehouseBinResponse,
    WarehouseMetricsResponse,
)
from app.modules.warehouse.service import (
    complete_picking,
    create_warehouse_bin,
    dispatch_order_to_courier,
    get_fulfillment_task,
    get_warehouse_metrics,
    inward_stock_grn,
    list_fulfillment_tasks,
    list_warehouse_bins,
    pack_and_stage_order,
    scan_and_pick_item,
    start_picking_task,
    write_off_breakage_waste,
)

router = APIRouter(prefix="/warehouse", tags=["warehouse"])


@router.get("/tasks", response_model=list[FulfillmentTaskResponse])
async def list_tasks(
    location_id: UUID = Query(..., description="Fulfillment dark store location ID"),
    task_status: FulfillmentTaskStatus | None = Query(
        default=None, description="Filter by task status"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[FulfillmentTaskResponse]:
    """List fulfillment tasks for a dark store ordered FIFO."""

    tasks, _ = await list_fulfillment_tasks(
        session,
        location_id=location_id,
        status=task_status,
        limit=limit,
        offset=offset,
    )
    return [FulfillmentTaskResponse.model_validate(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=FulfillmentTaskResponse)
async def get_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> FulfillmentTaskResponse:
    """Get single fulfillment task with items."""

    task = await get_fulfillment_task(session, task_id=task_id)
    return FulfillmentTaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/start", response_model=FulfillmentTaskResponse)
async def start_picking(
    task_id: UUID,
    req: StartPickingRequest,
    session: AsyncSession = Depends(get_db),
) -> FulfillmentTaskResponse:
    """Assign picker and begin picking items."""

    task = await start_picking_task(session, task_id=task_id, picker_id=req.picker_id)
    return FulfillmentTaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/pick-item", response_model=FulfillmentItemResponse)
async def pick_item(
    task_id: UUID,
    req: PickItemRequest,
    session: AsyncSession = Depends(get_db),
) -> FulfillmentItemResponse:
    """Scan and verify picked quantity for a variant item."""

    item = await scan_and_pick_item(
        session,
        task_id=task_id,
        variant_id=req.variant_id,
        quantity=req.quantity,
        is_damaged=req.is_damaged,
    )
    return FulfillmentItemResponse.model_validate(item)


@router.post("/tasks/{task_id}/complete-picking", response_model=FulfillmentTaskResponse)
async def finish_picking(
    task_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> FulfillmentTaskResponse:
    """Complete order picking."""

    task = await complete_picking(session, task_id=task_id)
    return FulfillmentTaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/pack-and-stage", response_model=FulfillmentTaskResponse)
async def pack_order(
    task_id: UUID,
    req: PackAndStageRequest,
    session: AsyncSession = Depends(get_db),
) -> FulfillmentTaskResponse:
    """Pack items into tamper-evident sealed bag and assign staging bay."""

    task = await pack_and_stage_order(
        session,
        task_id=task_id,
        packer_id=req.packer_id,
        staging_bay=req.staging_bay,
        bag_seal_number=req.bag_seal_number,
    )
    return FulfillmentTaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/dispatch", response_model=FulfillmentTaskResponse)
async def dispatch_order(
    task_id: UUID,
    req: DispatchOrderRequest,
    session: AsyncSession = Depends(get_db),
) -> FulfillmentTaskResponse:
    """Handover staged delivery bag to delivery courier."""

    task = await dispatch_order_to_courier(
        session,
        task_id=task_id,
        courier_id=req.courier_id,
    )
    return FulfillmentTaskResponse.model_validate(task)


@router.post("/bins", response_model=WarehouseBinResponse, status_code=status.HTTP_201_CREATED)
async def create_bin(
    req: WarehouseBinCreate,
    session: AsyncSession = Depends(get_db),
) -> WarehouseBinResponse:
    """Register a new storage shelf, cooler, or dispatch staging bay."""

    bin_obj = await create_warehouse_bin(
        session,
        location_id=req.fulfillment_location_id,
        bin_code=req.bin_code,
        zone_type=req.zone_type,
    )
    return WarehouseBinResponse.model_validate(bin_obj)


@router.get("/bins", response_model=list[WarehouseBinResponse])
async def list_bins(
    location_id: UUID = Query(..., description="Fulfillment dark store location ID"),
    zone_type: BinZoneType | None = Query(default=None, description="Optional zone type filter"),
    session: AsyncSession = Depends(get_db),
) -> list[WarehouseBinResponse]:
    """List bins for a fulfillment dark store."""

    bins = await list_warehouse_bins(session, location_id=location_id, zone_type=zone_type)
    return [WarehouseBinResponse.model_validate(b) for b in bins]


@router.post("/inventory/inward", status_code=status.HTTP_200_OK)
async def inward_inventory(
    req: InwardStockRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Inward stock via Goods Receipt Note (GRN)."""

    await inward_stock_grn(
        session,
        location_id=req.location_id,
        variant_id=req.variant_id,
        quantity=req.quantity,
        invoice_ref=req.invoice_ref,
        idempotency_key=req.idempotency_key,
    )
    return {"status": "inwarded", "invoice_ref": req.invoice_ref}


@router.post("/inventory/breakage", status_code=status.HTTP_200_OK)
async def record_breakage(
    req: RecordBreakageRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Record bottle breakage or liquid damage write-off."""

    await write_off_breakage_waste(
        session,
        location_id=req.location_id,
        variant_id=req.variant_id,
        quantity=req.quantity,
        reason=req.reason,
        reported_by=req.reported_by,
        idempotency_key=req.idempotency_key,
    )
    return {"status": "breakage_recorded", "reported_by": req.reported_by}


@router.get("/metrics", response_model=WarehouseMetricsResponse)
async def metrics(
    location_id: UUID = Query(..., description="Fulfillment location ID"),
    session: AsyncSession = Depends(get_db),
) -> WarehouseMetricsResponse:
    """Retrieve operational KPIs for a dark store."""

    return await get_warehouse_metrics(session, location_id=location_id)

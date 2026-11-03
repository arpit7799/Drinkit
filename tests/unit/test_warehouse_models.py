"""Unit tests for warehouse and dark store fulfillment models and schemas."""

from decimal import Decimal
from uuid import uuid4

from app.models.warehouse import FulfillmentTaskItem, OrderFulfillmentTask, WarehouseBin
from app.modules.warehouse.schemas import (
    BinZoneType,
    FulfillmentTaskStatus,
    InwardStockRequest,
    PackAndStageRequest,
    PickItemRequest,
    RecordBreakageRequest,
    WarehouseBinCreate,
    WarehouseMetricsResponse,
)


def test_warehouse_enums() -> None:
    assert FulfillmentTaskStatus.PENDING == "pending"
    assert FulfillmentTaskStatus.PICKING == "picking"
    assert FulfillmentTaskStatus.PICKED == "picked"
    assert FulfillmentTaskStatus.PACKED == "packed"
    assert FulfillmentTaskStatus.STAGED == "staged"
    assert FulfillmentTaskStatus.DISPATCHED == "dispatched"

    assert BinZoneType.AMBIENT == "ambient"
    assert BinZoneType.CHILLED == "chilled"
    assert BinZoneType.COOLER == "cooler"
    assert BinZoneType.DISPATCH_STAGING == "dispatch_staging"


def test_warehouse_bin_model_instantiation() -> None:
    loc_id = uuid4()
    bin_obj = WarehouseBin(
        fulfillment_location_id=loc_id,
        bin_code="AISLE-A1-RACK-02",
        zone_type=BinZoneType.COOLER.value,
        is_active=True,
    )
    assert bin_obj.fulfillment_location_id == loc_id
    assert bin_obj.bin_code == "AISLE-A1-RACK-02"
    assert bin_obj.zone_type == "cooler"
    assert bin_obj.is_active is True

    constraints = [c.name for c in WarehouseBin.__table__.constraints]
    assert any("zone_type_valid" in (c or "") for c in constraints)
    assert any("bin_code_not_blank" in (c or "") for c in constraints)


def test_order_fulfillment_task_and_item_model() -> None:
    order_id = uuid4()
    loc_id = uuid4()
    task = OrderFulfillmentTask(
        order_id=order_id,
        fulfillment_location_id=loc_id,
        status="pending",
    )
    assert task.order_id == order_id
    assert task.fulfillment_location_id == loc_id
    assert task.status == "pending"

    task_constraints = [c.name for c in OrderFulfillmentTask.__table__.constraints]
    assert any("status_valid" in (c or "") for c in task_constraints)

    item = FulfillmentTaskItem(
        task_id=task.id,
        variant_id=uuid4(),
        sku="BIRA-WHITE-330",
        expected_quantity=6,
        picked_quantity=0,
        is_shortage=False,
        is_damaged=False,
    )
    assert item.expected_quantity == 6
    assert item.picked_quantity == 0
    assert item.is_shortage is False
    assert item.is_damaged is False

    item_constraints = [c.name for c in FulfillmentTaskItem.__table__.constraints]
    assert any("expected_quantity_positive" in (c or "") for c in item_constraints)


def test_warehouse_schema_validations() -> None:
    loc_id = uuid4()
    create_bin = WarehouseBinCreate(
        fulfillment_location_id=loc_id,
        bin_code="BAY-01",
        zone_type=BinZoneType.DISPATCH_STAGING,
    )
    assert create_bin.bin_code == "BAY-01"

    pick_req = PickItemRequest(variant_id=uuid4(), quantity=2, is_damaged=False)
    assert pick_req.quantity == 2

    pack_req = PackAndStageRequest(
        packer_id=uuid4(),
        staging_bay="BAY-04",
        bag_seal_number="SEAL-98721",
    )
    assert pack_req.staging_bay == "BAY-04"

    inward_req = InwardStockRequest(
        location_id=loc_id,
        variant_id=uuid4(),
        quantity=Decimal("120"),
        invoice_ref="INV-2026-001",
        idempotency_key="grn-001",
    )
    assert inward_req.quantity == Decimal("120")

    breakage_req = RecordBreakageRequest(
        location_id=loc_id,
        variant_id=uuid4(),
        quantity=Decimal("2"),
        reason="Bottles fell off delivery trolley",
        reported_by="Ramesh Picker",
        idempotency_key="break-001",
    )
    assert breakage_req.quantity == Decimal("2")

    metrics = WarehouseMetricsResponse(
        location_id=loc_id,
        pending_orders=5,
        active_picking=3,
        staged_orders=2,
        dispatched_today=45,
        active_bins=20,
    )
    assert metrics.dispatched_today == 45

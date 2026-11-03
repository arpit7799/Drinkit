"""Dark store warehouse operations and order fulfillment schemas."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FulfillmentTaskStatus(StrEnum):
    """Lifecycle statuses for order fulfillment within dark stores."""

    PENDING = "pending"
    PICKING = "picking"
    PICKED = "picked"
    PACKED = "packed"
    STAGED = "staged"
    DISPATCHED = "dispatched"
    CANCELLED = "cancelled"


class BinZoneType(StrEnum):
    """Storage zone classification."""

    AMBIENT = "ambient"
    CHILLED = "chilled"
    COOLER = "cooler"
    DISPATCH_STAGING = "dispatch_staging"


class WarehouseBinCreate(BaseModel):
    """Request to create a new storage or staging bin."""

    fulfillment_location_id: UUID
    bin_code: str = Field(min_length=1, max_length=64)
    zone_type: BinZoneType = BinZoneType.AMBIENT


class WarehouseBinResponse(BaseModel):
    """Storage or staging bin details."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fulfillment_location_id: UUID
    bin_code: str
    zone_type: str
    is_active: bool


class FulfillmentItemResponse(BaseModel):
    """Item detail within a picking/packing task."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    sku: str
    expected_quantity: int
    picked_quantity: int
    is_shortage: bool
    is_damaged: bool
    bin_location: str | None = None


class FulfillmentTaskResponse(BaseModel):
    """Physical order fulfillment task lifecycle representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    fulfillment_location_id: UUID
    status: str
    picker_id: UUID | None = None
    packer_id: UUID | None = None
    staging_bay: str | None = None
    bag_seal_number: str | None = None
    started_at: datetime | None = None
    picked_at: datetime | None = None
    packed_at: datetime | None = None
    staged_at: datetime | None = None
    dispatched_at: datetime | None = None
    items: list[FulfillmentItemResponse] = Field(default_factory=list)


class StartPickingRequest(BaseModel):
    """Request to assign picker and begin picking order items."""

    picker_id: UUID


class PickItemRequest(BaseModel):
    """Request to scan/pick a specific variant in a task."""

    variant_id: UUID
    quantity: int = Field(gt=0)
    is_damaged: bool = False


class PackAndStageRequest(BaseModel):
    """Request to pack items in tamper-evident bag and assign staging bay."""

    packer_id: UUID
    staging_bay: str = Field(min_length=1, max_length=64)
    bag_seal_number: str = Field(min_length=1, max_length=64)


class DispatchOrderRequest(BaseModel):
    """Request to handover staged order to assigned courier."""

    courier_id: UUID


class InwardStockRequest(BaseModel):
    """Request for Goods Receipt Note (GRN) inventory inwarding."""

    location_id: UUID
    variant_id: UUID
    quantity: Decimal = Field(gt=0)
    invoice_ref: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=120)


class RecordBreakageRequest(BaseModel):
    """Request to write off broken bottles or damaged inventory."""

    location_id: UUID
    variant_id: UUID
    quantity: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=255)
    reported_by: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=120)


class WarehouseMetricsResponse(BaseModel):
    """Operational KPI metrics for a dark store."""

    location_id: UUID
    pending_orders: int
    active_picking: int
    staged_orders: int
    dispatched_today: int
    active_bins: int

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DeliverySlotCreateRequest(BaseModel):
    fulfillment_location_id: UUID
    start_at: datetime
    end_at: datetime
    capacity: int = Field(ge=1)


class DeliverySlotResponse(BaseModel):
    id: UUID
    fulfillment_location_id: UUID
    start_at: datetime
    end_at: datetime
    capacity: int
    is_active: bool


class CourierCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=30)
    vehicle_type: str = Field(pattern="^(bike|scooter|van|truck)$")


class CourierResponse(BaseModel):
    id: UUID
    name: str
    phone: str
    vehicle_type: str
    is_active: bool
    current_lat: float | None
    current_lng: float | None


class ScheduleDeliveryRequest(BaseModel):
    slot_id: UUID


class AssignCourierRequest(BaseModel):
    courier_id: UUID


class MarkDeliveredRequest(BaseModel):
    tracking_number: str | None = None


class DeliveryResponse(BaseModel):
    id: UUID
    order_id: UUID
    courier_id: UUID | None
    slot_id: UUID | None
    status: str
    tracking_number: str | None
    tracking_url: str | None
    estimated_delivery_at: datetime | None
    actual_delivery_at: datetime | None
    courier: CourierResponse | None

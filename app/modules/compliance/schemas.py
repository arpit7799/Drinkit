"""Pydantic schemas for alcohol compliance, KYC, and regulatory enforcement."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.compliance import GovtIdType, KYCStatus


class KYCSubmissionRequest(BaseModel):
    """Customer submission of government identity for age verification."""

    id_type: GovtIdType
    id_number: str = Field(..., min_length=4, max_length=50, examples=["987654321012"])
    date_of_birth: date = Field(..., examples=["1998-05-15"])


class KYCResponse(BaseModel):
    """Verified customer KYC and legal drinking age status."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    id_type: GovtIdType
    id_number_last4: str
    date_of_birth: date
    verified_age: int
    status: KYCStatus
    rejection_reason: str | None
    verified_at: datetime | None


class StateAlcoholRegulationResponse(BaseModel):
    """State-level alcohol distribution parameters."""

    model_config = ConfigDict(from_attributes=True)

    state_code: str
    state_name: str
    minimum_legal_drinking_age: int
    operating_hours_start: time
    operating_hours_end: time
    max_spirits_litres_per_order: Decimal
    delivery_handover_otp_required: bool


class DryDayScheduleResponse(BaseModel):
    """Designated dry day prohibiting alcohol sale."""

    model_config = ConfigDict(from_attributes=True)

    state_code: str
    dry_date: date
    reason: str
    is_full_day: bool
    start_time: time | None
    end_time: time | None


class DeliveryHandoverVerifyRequest(BaseModel):
    """Courier verification at customer doorstep."""

    order_id: UUID
    handover_otp: str = Field(..., min_length=6, max_length=6, examples=["123456"])
    recipient_age_confirmed: bool = Field(default=True)


class DeliveryComplianceResponse(BaseModel):
    """Audit outcome of order handover verification."""

    model_config = ConfigDict(from_attributes=True)

    order_id: UUID
    recipient_age_verified: bool
    handover_otp_verified: bool
    verified_at: datetime | None

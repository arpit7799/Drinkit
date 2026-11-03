"""Pydantic request and response schemas for Drinkit VIP memberships."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MembershipPlanResponse(BaseModel):
    """Public details of a VIP membership plan."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    duration_days: int
    price_minor: int
    currency_code: str
    free_delivery_min_order_minor: int
    points_multiplier: Decimal
    priority_fulfillment: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MembershipPlanCreateRequest(BaseModel):
    """Admin request payload to launch or configure a VIP membership plan."""

    code: str = Field(
        min_length=2, max_length=64, description="Unique uppercase plan code, e.g. VIP_MONTHLY"
    )
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    duration_days: int = Field(gt=0, description="Duration in calendar days (e.g. 30, 90, 365)")
    price_minor: int = Field(
        ge=0, description="Price in currency minor units (e.g. 19900 for ₹199)"
    )
    currency_code: str = Field(default="INR", min_length=3, max_length=3)
    free_delivery_min_order_minor: int = Field(
        default=19900,
        ge=0,
        description="Minimum order subtotal minor units to waive delivery fees",
    )
    points_multiplier: Decimal = Field(
        default=Decimal("2.0"),
        ge=Decimal("1.0"),
        description="Liver points multiplier for members",
    )
    priority_fulfillment: bool = Field(default=True)
    is_active: bool = Field(default=True)


class CustomerMembershipResponse(BaseModel):
    """Customer subscription state and active plan details."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    plan_id: UUID
    status: str
    starts_at: datetime
    expires_at: datetime
    auto_renew: bool
    payment_reference: str | None
    cancellation_reason: str | None
    plan: MembershipPlanResponse | None = None
    created_at: datetime
    updated_at: datetime


class SubscribeMembershipRequest(BaseModel):
    """Request payload to subscribe or renew a VIP membership."""

    plan_id: UUID
    auto_renew: bool = False
    payment_reference: str | None = Field(default=None, max_length=128)


class CancelMembershipRequest(BaseModel):
    """Request payload to cancel an active VIP membership."""

    reason: str | None = Field(default=None, max_length=255)


class MembershipBenefitLogResponse(BaseModel):
    """Audit log item representing a specific VIP saving or perk claimed."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    membership_id: UUID
    order_id: UUID | None
    benefit_type: str
    amount_saved_minor: int
    bonus_points_awarded: int
    created_at: datetime


class MembershipSavingsSummaryResponse(BaseModel):
    """Aggregate calculation of all benefits and savings enjoyed by a customer."""

    customer_id: UUID
    is_vip: bool
    active_plan_code: str | None
    expires_at: datetime | None
    total_delivery_fees_saved_minor: int
    total_bonus_points_earned: int
    total_perks_claimed: int
    recent_benefits: list[MembershipBenefitLogResponse] = Field(default_factory=list)

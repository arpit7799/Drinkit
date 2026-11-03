"""Pydantic schemas for promotions, loyalty, and tax calculation."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.promotions_tax import (
    CouponStatus,
    DiscountType,
    LoyaltyTransactionType,
    TaxCategory,
)


class CouponCreateRequest(BaseModel):
    """Payload to create a new promotional coupon."""

    code: str = Field(..., min_length=2, max_length=50, examples=["PARTY20"])
    name: str = Field(..., min_length=1, max_length=200, examples=["Party Starter 20% Off"])
    description: str | None = Field(default=None, max_length=1000)
    discount_type: DiscountType = Field(default=DiscountType.PERCENTAGE)
    discount_value: Decimal = Field(..., gt=0, examples=[Decimal("20.00")])
    currency_code: str = Field(default="INR", min_length=3, max_length=3)
    min_order_amount_minor: int | None = Field(default=None, ge=0)
    max_discount_minor: int | None = Field(default=None, gt=0)
    max_uses: int | None = Field(default=None, gt=0)
    max_uses_per_customer: int | None = Field(default=None, gt=0)
    valid_from: datetime
    valid_until: datetime
    first_order_only: bool = False
    new_customers_only: bool = False


class CouponResponse(BaseModel):
    """Representation of an active or managed coupon."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    discount_type: DiscountType
    discount_value: Decimal
    currency_code: str
    min_order_amount_minor: int | None
    max_discount_minor: int | None
    max_uses: int | None
    max_uses_per_customer: int | None
    uses_count: int
    valid_from: datetime
    valid_until: datetime
    status: CouponStatus
    first_order_only: bool
    new_customers_only: bool


class CouponValidateRequest(BaseModel):
    """Payload for validating coupon application on a cart."""

    code: str = Field(..., min_length=1, max_length=50)
    cart_subtotal_minor: int = Field(..., ge=0)


class CouponValidateResponse(BaseModel):
    """Result of coupon validation against an order or cart."""

    valid: bool
    code: str
    discount_type: DiscountType
    discount_applied_minor: int
    subtotal_minor: int
    discounted_subtotal_minor: int
    message: str


class LoyaltyAccountResponse(BaseModel):
    """Current Liver Points balance and tier status."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    points_balance: int
    lifetime_earned: int
    lifetime_redeemed: int
    tier: str
    point_value_minor: int = 100  # 1 point = ₹1.00


class LoyaltyTransactionResponse(BaseModel):
    """Audit log entry for loyalty points balance changes."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_type: LoyaltyTransactionType
    points_delta: int
    balance_after: int
    order_id: UUID | None
    description: str | None
    created_at: datetime


class LoyaltyEstimateRequest(BaseModel):
    """Request to estimate discount value for point redemption."""

    points: int = Field(..., gt=0)


class LoyaltyEstimateResponse(BaseModel):
    """Estimated monetary value of loyalty points."""

    points: int
    discount_value_minor: int
    available_balance: int


class TaxLineBreakdown(BaseModel):
    """Itemized tax components for an order line."""

    variant_id: UUID
    tax_category: TaxCategory
    rate_bps: int
    cgst_minor: int
    sgst_minor: int
    igst_minor: int
    cess_minor: int
    total_tax_minor: int


class TaxCalculationResponse(BaseModel):
    """Overall tax computation breakdown for a destination postal code."""

    state_code: str
    state_name: str
    lines: list[TaxLineBreakdown]
    total_tax_minor: int

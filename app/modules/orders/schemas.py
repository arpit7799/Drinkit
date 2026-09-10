from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OrderLineResponse(BaseModel):
    id: UUID
    variant_id: UUID
    quantity: int
    currency_code: str
    unit_price_minor: int
    line_total_minor: int


class OrderResponse(BaseModel):
    id: UUID
    status: str
    currency_code: str
    subtotal_minor: int
    tax_minor: int
    delivery_fee_minor: int
    total_minor: int
    payment_status: str
    payment_provider: str | None
    payment_reference: str | None
    created_at: datetime
    lines: list[OrderLineResponse]


class CreateOrderRequest(BaseModel):
    address_id: UUID


class PaymentInitiationRequest(BaseModel):
    provider: str = Field(pattern="^(razorpay|stripe|phonepe)$")
    return_url: str | None = None


class PaymentInitiationResponse(BaseModel):
    order_id: UUID
    payment_url: str | None
    provider_reference: str
    status: str

from uuid import UUID

from pydantic import BaseModel, Field


class CartItemCreateRequest(BaseModel):
    variant_id: UUID
    quantity: int = Field(ge=1, le=999)
    currency_code: str = Field(default="INR", min_length=1, max_length=3)


class CartItemUpdateRequest(BaseModel):
    quantity: int = Field(ge=1, le=999)


class CartItemResponse(BaseModel):
    id: UUID
    variant_id: UUID
    quantity: int
    currency_code: str
    unit_price_minor: int
    line_total_minor: int


class CartResponse(BaseModel):
    id: UUID
    currency_code: str
    status: str
    items: list[CartItemResponse]
    subtotal_minor: int

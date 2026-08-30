"""Pydantic contracts for public catalog reads."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    parent_id: UUID | None
    is_active: bool
    sort_order: int


class ProductVariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    quantity_value: Decimal
    quantity_unit: str
    barcode: str | None
    is_active: bool
    sort_order: int


class ProductResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    brand: str | None
    description: str | None
    is_alcoholic: bool
    abv_percent: Decimal | None
    is_active: bool
    categories: list[CategoryResponse]
    variants: list[ProductVariantResponse]


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

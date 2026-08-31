"""Pydantic contracts for customer addresses and serviceability."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AddressCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    recipient_name: str = Field(min_length=1, max_length=160)
    line1: str = Field(min_length=1, max_length=240)
    line2: str | None = Field(default=None, max_length=240)
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=1, max_length=120)
    postal_code: str = Field(min_length=1, max_length=20)
    country_code: str = Field(min_length=2, max_length=2)
    delivery_instructions: str | None = Field(default=None, max_length=500)
    is_default: bool = False


class AddressUpdateRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=40)
    recipient_name: str | None = Field(default=None, min_length=1, max_length=160)
    line1: str | None = Field(default=None, min_length=1, max_length=240)
    line2: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    state: str | None = Field(default=None, min_length=1, max_length=120)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    delivery_instructions: str | None = Field(default=None, max_length=500)
    is_default: bool | None = None


class AddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    label: str
    recipient_name: str
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str
    country_code: str
    delivery_instructions: str | None
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FulfillmentLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    is_active: bool


class ServiceabilityResponse(BaseModel):
    serviceable: bool
    fulfillment_location: FulfillmentLocationResponse | None = None

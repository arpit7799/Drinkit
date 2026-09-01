from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VariantPriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variant_id: UUID
    currency_code: str = Field(min_length=3, max_length=3)
    amount_minor: int = Field(ge=0)

"""Read-only public pricing routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import PriceNotFound
from app.modules.pricing.schemas import VariantPriceResponse
from app.modules.pricing.service import get_current_variant_price

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/variants/{variant_id}/price", response_model=VariantPriceResponse)
async def variant_price(
    variant_id: UUID,
    currency_code: str = Query(default="INR", min_length=1, max_length=3),
    session: AsyncSession = Depends(get_db),
) -> VariantPriceResponse:
    """Return the current active price for one published sellable variant."""

    price = await get_current_variant_price(
        session,
        variant_id=variant_id,
        currency_code=currency_code,
    )
    if price is None:
        raise PriceNotFound
    return VariantPriceResponse(
        variant_id=price.variant_id,
        currency_code=price.currency_code,
        amount_minor=price.amount_minor,
    )

"""GST and jurisdiction-aware tax calculation engine."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.promotions_tax import TaxCategory, TaxJurisdiction, TaxRate
from app.modules.promotions.schemas import TaxCalculationResponse, TaxLineBreakdown

logger = logging.getLogger(__name__)

# Fallback GST rates in basis points if state-specific rates are not explicitly configured
DEFAULT_CATEGORY_RATES_BPS: dict[TaxCategory, int] = {
    TaxCategory.ALCOHOL: 2000,  # 20% State Excise / VAT
    TaxCategory.BEVERAGE_NON_ALCOHOLIC: 1800,  # 18% GST (CGST 9% + SGST 9%)
    TaxCategory.MIXER: 1800,  # 18% GST
    TaxCategory.SNACK: 1200,  # 12% GST
    TaxCategory.ICE: 500,  # 5% GST
    TaxCategory.PARTY_SUPPLY: 1800,  # 18% GST
    TaxCategory.RECOVERY: 1200,  # 12% GST
}


async def calculate_order_taxes(
    session: AsyncSession,
    *,
    postal_code: str,
    items: list[dict],
) -> TaxCalculationResponse:
    """Compute itemized line-by-line GST taxes for items destined for a postal code.

    Each item dict is expected to have:
    - ``variant_id``: UUID
    - ``category``: TaxCategory | str
    - ``line_subtotal_minor``: int
    """
    # 1. Resolve State Jurisdiction from Postal Code
    jurisdiction = await session.scalar(
        select(TaxJurisdiction).where(
            TaxJurisdiction.postal_code == postal_code,
            TaxJurisdiction.is_active.is_(True),
        )
    )

    state_code = jurisdiction.state_code if jurisdiction else "MH"
    state_name = jurisdiction.state_name if jurisdiction else "Maharashtra"

    # 2. Fetch all active tax rates for the resolved state
    tax_rates_res = await session.scalars(
        select(TaxRate).where(
            TaxRate.state_code == state_code,
            TaxRate.is_active.is_(True),
        )
    )
    rates_by_category = {rate.category: rate for rate in tax_rates_res.all()}

    lines: list[TaxLineBreakdown] = []
    total_tax_minor = 0

    for item in items:
        variant_id: UUID = item["variant_id"]
        raw_cat = item.get("category", TaxCategory.BEVERAGE_NON_ALCOHOLIC)
        category = TaxCategory(raw_cat) if isinstance(raw_cat, str) else raw_cat
        line_subtotal_minor: int = item["line_subtotal_minor"]

        rate_obj = rates_by_category.get(category)
        if rate_obj is not None:
            rate_bps = rate_obj.rate_bps
            cgst = (line_subtotal_minor * rate_obj.cgst_rate_bps) // 10000
            sgst = (line_subtotal_minor * rate_obj.sgst_rate_bps) // 10000
            igst = (line_subtotal_minor * rate_obj.igst_rate_bps) // 10000
            cess = (line_subtotal_minor * rate_obj.cess_rate_bps) // 10000
            line_tax = cgst + sgst + igst + cess
            if line_tax == 0 and rate_bps > 0:
                line_tax = (line_subtotal_minor * rate_bps) // 10000
        else:
            rate_bps = DEFAULT_CATEGORY_RATES_BPS.get(category, 1800)
            line_tax = (line_subtotal_minor * rate_bps) // 10000
            cgst = line_tax // 2
            sgst = line_tax - cgst
            igst = 0
            cess = 0

        total_tax_minor += line_tax
        lines.append(
            TaxLineBreakdown(
                variant_id=variant_id,
                tax_category=category,
                rate_bps=rate_bps,
                cgst_minor=cgst,
                sgst_minor=sgst,
                igst_minor=igst,
                cess_minor=cess,
                total_tax_minor=line_tax,
            )
        )

    return TaxCalculationResponse(
        state_code=state_code,
        state_name=state_name,
        lines=lines,
        total_tax_minor=total_tax_minor,
    )

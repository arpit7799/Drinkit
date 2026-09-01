"""Transactional variant pricing workflows."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import transaction
from app.core.exceptions import (
    InvalidPricingRequest,
    PriceNotFound,
    VariantNotFound,
)
from app.models.catalog import Product, ProductVariant
from app.models.outbox_event import OutboxEvent
from app.models.pricing import VariantPrice

logger = logging.getLogger(__name__)


async def set_variant_price(
    session: AsyncSession,
    *,
    variant_id: UUID,
    currency_code: str,
    amount_minor: int,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_active: bool = True,
) -> VariantPrice:
    """Create or update one effective price for an active sellable variant."""

    normalized_currency = normalize_currency_code(currency_code)
    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool) or amount_minor < 0:
        raise InvalidPricingRequest
    effective_start = starts_at or datetime.now(UTC)
    _validate_datetime(effective_start)
    if ends_at is not None:
        _validate_datetime(ends_at)
        if effective_start >= ends_at:
            raise InvalidPricingRequest

    async with transaction(session):
        variant = await session.scalar(
            select(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProductVariant.id == variant_id,
                ProductVariant.is_active.is_(True),
                Product.is_active.is_(True),
            )
            .with_for_update()
        )
        if variant is None:
            raise VariantNotFound
        price = await session.scalar(
            select(VariantPrice)
            .where(
                VariantPrice.variant_id == variant_id,
                VariantPrice.currency_code == normalized_currency,
                VariantPrice.starts_at == effective_start,
            )
            .with_for_update()
        )
        if price is None:
            price = VariantPrice(
                variant_id=variant_id,
                currency_code=normalized_currency,
                amount_minor=amount_minor,
                starts_at=effective_start,
                ends_at=ends_at,
                is_active=is_active,
            )
            session.add(price)
        else:
            price.amount_minor = amount_minor
            price.ends_at = ends_at
            price.is_active = is_active
        await session.flush()
        _record_event(
            session,
            event_type="pricing.variant_price.set",
            aggregate_id=price.id,
            payload={
                "variant_id": str(variant_id),
                "currency_code": price.currency_code,
                "amount_minor": price.amount_minor,
                "starts_at": price.starts_at.isoformat(),
                "ends_at": price.ends_at.isoformat() if price.ends_at else None,
                "is_active": price.is_active,
            },
        )
        logger.info(
            "variant_price_set",
            extra={
                "price_id": str(price.id),
                "variant_id": str(variant_id),
                "currency_code": price.currency_code,
                "amount_minor": price.amount_minor,
                "is_active": price.is_active,
            },
        )
        return price


async def get_current_variant_price(
    session: AsyncSession,
    *,
    variant_id: UUID,
    currency_code: str,
    as_of: datetime | None = None,
) -> VariantPrice | None:
    """Return the latest active price effective for an active variant."""

    normalized_currency = normalize_currency_code(currency_code)
    effective_at = as_of or datetime.now(UTC)
    _validate_datetime(effective_at)
    return await session.scalar(
        select(VariantPrice)
        .join(ProductVariant, ProductVariant.id == VariantPrice.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            VariantPrice.variant_id == variant_id,
            VariantPrice.currency_code == normalized_currency,
            VariantPrice.is_active.is_(True),
            VariantPrice.starts_at <= effective_at,
            (VariantPrice.ends_at.is_(None) | (VariantPrice.ends_at > effective_at)),
            ProductVariant.is_active.is_(True),
            Product.is_active.is_(True),
        )
        .order_by(VariantPrice.starts_at.desc(), VariantPrice.id)
    )


async def deactivate_variant_price(
    session: AsyncSession,
    *,
    price_id: UUID,
) -> VariantPrice:
    """Deactivate one price idempotently."""

    async with transaction(session):
        price = await session.scalar(
            select(VariantPrice).where(VariantPrice.id == price_id).with_for_update()
        )
        if price is None:
            raise PriceNotFound
        if price.is_active:
            price.is_active = False
            await session.flush()
            _record_event(
                session,
                event_type="pricing.variant_price.deactivated",
                aggregate_id=price.id,
                payload={"variant_id": str(price.variant_id)},
            )
            logger.info(
                "variant_price_deactivated",
                extra={"price_id": str(price.id), "variant_id": str(price.variant_id)},
            )
        return price


def normalize_currency_code(currency_code: str) -> str:
    """Return an uppercase three-letter currency code."""

    normalized = currency_code.strip().upper()
    if len(normalized) != 3 or not all("A" <= character <= "Z" for character in normalized):
        raise InvalidPricingRequest
    return normalized


def _validate_datetime(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidPricingRequest


def _record_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: UUID,
    payload: dict[str, object],
) -> None:
    session.add(
        OutboxEvent(
            aggregate_type="variant_price",
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )
    )

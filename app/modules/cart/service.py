"""Transactional customer shopping-cart workflows."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.database import transaction
from app.core.exceptions import (
    CartCurrencyConflict,
    CartItemNotFound,
    CartNotFound,
    InvalidCartRequest,
    InvalidPricingRequest,
    PriceNotFound,
    VariantNotFound,
)
from app.models.auth import User
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Product, ProductVariant
from app.models.outbox_event import OutboxEvent
from app.models.pricing import VariantPrice
from app.modules.pricing.service import get_current_variant_price, normalize_currency_code

logger = logging.getLogger(__name__)
MAX_CART_ITEM_QUANTITY = 999


async def get_cart(session: AsyncSession, *, user_id: UUID) -> ShoppingCart | None:
    """Return the customer's active cart with its current line snapshots."""

    return await _load_cart(session, user_id=user_id)


async def get_or_create_cart(
    session: AsyncSession,
    *,
    user_id: UUID,
    currency_code: str = "INR",
) -> ShoppingCart:
    """Return the active cart, creating an empty default-currency cart when needed."""

    normalized_currency = _normalize_cart_currency(currency_code)
    async with transaction(session):
        cart = await _lock_or_create_cart(
            session,
            user_id=user_id,
            currency_code=normalized_currency,
        )
        return _require_loaded_cart(await _load_cart(session, cart_id=cart.id))


async def add_cart_item(
    session: AsyncSession,
    *,
    user_id: UUID,
    variant_id: UUID,
    quantity: int,
    currency_code: str,
) -> ShoppingCart:
    """Add quantity to a variant line and snapshot its current price."""

    _validate_quantity(quantity)
    normalized_currency = _normalize_cart_currency(currency_code)
    async with transaction(session):
        cart = await _lock_or_create_cart(
            session,
            user_id=user_id,
            currency_code=normalized_currency,
        )
        _ensure_currency(cart, normalized_currency)
        price = await _current_price_or_raise(
            session,
            variant_id=variant_id,
            currency_code=cart.currency_code,
        )
        item = await session.scalar(
            select(CartItem)
            .where(CartItem.cart_id == cart.id, CartItem.variant_id == variant_id)
            .with_for_update()
        )
        if item is None:
            item = CartItem(
                cart_id=cart.id,
                variant_id=variant_id,
                price_id=price.id,
                quantity=quantity,
                currency_code=price.currency_code,
                unit_price_minor=price.amount_minor,
            )
            session.add(item)
        else:
            _validate_quantity(item.quantity + quantity)
            item.quantity += quantity
            _snapshot_price(item, price)
        await session.flush()
        _record_event(
            session,
            event_type="cart.item.upserted",
            aggregate_id=cart.id,
            payload={
                "item_id": str(item.id),
                "variant_id": str(variant_id),
                "quantity": item.quantity,
                "currency_code": item.currency_code,
                "unit_price_minor": item.unit_price_minor,
            },
        )
        logger.info(
            "cart_item_upserted",
            extra={
                "cart_id": str(cart.id),
                "item_id": str(item.id),
                "variant_id": str(variant_id),
                "quantity": item.quantity,
            },
        )
        return _require_loaded_cart(await _load_cart(session, cart_id=cart.id))


async def update_cart_item(
    session: AsyncSession,
    *,
    user_id: UUID,
    item_id: UUID,
    quantity: int,
) -> ShoppingCart:
    """Replace a customer's line quantity and refresh its price snapshot."""

    _validate_quantity(quantity)
    async with transaction(session):
        cart, item = await _lock_owned_item(session, user_id=user_id, item_id=item_id)
        price = await _current_price_or_raise(
            session,
            variant_id=item.variant_id,
            currency_code=cart.currency_code,
        )
        item.quantity = quantity
        _snapshot_price(item, price)
        await session.flush()
        _record_event(
            session,
            event_type="cart.item.upserted",
            aggregate_id=cart.id,
            payload={
                "item_id": str(item.id),
                "variant_id": str(item.variant_id),
                "quantity": item.quantity,
                "currency_code": item.currency_code,
                "unit_price_minor": item.unit_price_minor,
            },
        )
        logger.info(
            "cart_item_updated",
            extra={
                "cart_id": str(cart.id),
                "item_id": str(item.id),
                "quantity": item.quantity,
            },
        )
        return _require_loaded_cart(await _load_cart(session, cart_id=cart.id))


async def remove_cart_item(
    session: AsyncSession,
    *,
    user_id: UUID,
    item_id: UUID,
) -> ShoppingCart:
    """Remove one owned line from the active cart."""

    async with transaction(session):
        cart, item = await _lock_owned_item(session, user_id=user_id, item_id=item_id)
        await session.delete(item)
        await session.flush()
        _record_event(
            session,
            event_type="cart.item.removed",
            aggregate_id=cart.id,
            payload={"item_id": str(item_id), "variant_id": str(item.variant_id)},
        )
        logger.info(
            "cart_item_removed",
            extra={"cart_id": str(cart.id), "item_id": str(item_id)},
        )
        return _require_loaded_cart(await _load_cart(session, cart_id=cart.id))


async def _lock_or_create_cart(
    session: AsyncSession,
    *,
    user_id: UUID,
    currency_code: str,
) -> ShoppingCart:
    user = await session.scalar(
        select(User).where(User.id == user_id, User.is_active.is_(True)).with_for_update()
    )
    if user is None:
        raise CartNotFound
    cart = await session.scalar(
        select(ShoppingCart)
        .where(ShoppingCart.user_id == user_id, ShoppingCart.status == "active")
        .with_for_update()
    )
    if cart is not None:
        return cart
    cart = ShoppingCart(user_id=user_id, currency_code=currency_code, status="active")
    session.add(cart)
    await session.flush()
    _record_event(
        session,
        event_type="cart.created",
        aggregate_id=cart.id,
        payload={"user_id": str(user_id), "currency_code": currency_code},
    )
    logger.info(
        "cart_created",
        extra={"cart_id": str(cart.id), "user_id": str(user_id)},
    )
    return cart


async def _lock_owned_item(
    session: AsyncSession,
    *,
    user_id: UUID,
    item_id: UUID,
) -> tuple[ShoppingCart, CartItem]:
    cart = await session.scalar(
        select(ShoppingCart)
        .where(ShoppingCart.user_id == user_id, ShoppingCart.status == "active")
        .with_for_update()
    )
    if cart is None:
        raise CartItemNotFound
    item = await session.scalar(
        select(CartItem)
        .where(CartItem.id == item_id, CartItem.cart_id == cart.id)
        .with_for_update()
    )
    if item is None:
        raise CartItemNotFound
    return cart, item


async def _load_cart(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    cart_id: UUID | None = None,
) -> ShoppingCart | None:
    statement = select(ShoppingCart)
    if user_id is not None:
        statement = statement.where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.status == "active",
        )
    if cart_id is not None:
        statement = statement.where(ShoppingCart.id == cart_id)
    cart = await session.scalar(statement)
    if cart is not None:
        items = list(
            await session.scalars(
                select(CartItem)
                .where(CartItem.cart_id == cart.id)
                .order_by(CartItem.created_at, CartItem.id)
            )
        )
        set_committed_value(cart, "items", items)
    return cart


async def _current_price_or_raise(
    session: AsyncSession,
    *,
    variant_id: UUID,
    currency_code: str,
) -> VariantPrice:
    price = await get_current_variant_price(
        session,
        variant_id=variant_id,
        currency_code=currency_code,
    )
    if price is not None:
        return price
    variant = await session.scalar(
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProductVariant.id == variant_id,
            ProductVariant.is_active.is_(True),
            Product.is_active.is_(True),
        )
    )
    if variant is None:
        raise VariantNotFound
    raise PriceNotFound


def _validate_quantity(quantity: int) -> None:
    if not isinstance(quantity, int) or isinstance(quantity, bool):
        raise InvalidCartRequest
    if quantity < 1 or quantity > MAX_CART_ITEM_QUANTITY:
        raise InvalidCartRequest


def _require_loaded_cart(cart: ShoppingCart | None) -> ShoppingCart:
    if cart is None:
        raise CartNotFound
    return cart


def _normalize_cart_currency(currency_code: str) -> str:
    try:
        return normalize_currency_code(currency_code)
    except InvalidPricingRequest:
        raise InvalidCartRequest from None


def _ensure_currency(cart: ShoppingCart, currency_code: str) -> None:
    if cart.currency_code != currency_code:
        raise CartCurrencyConflict


def _snapshot_price(item: CartItem, price: VariantPrice) -> None:
    item.price_id = price.id
    item.currency_code = price.currency_code
    item.unit_price_minor = price.amount_minor


def _record_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: UUID,
    payload: dict[str, object],
) -> None:
    session.add(
        OutboxEvent(
            aggregate_type="shopping_cart",
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )
    )

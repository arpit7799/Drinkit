"""Transactional order creation and checkout workflows."""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import transaction
from app.core.exceptions import (
    AddressOwnershipError,
    CartNotFound,
    EmptyCartError,
    InsufficientInventoryForOrder,
    InvalidOrderRequest,
    VariantNotFound,
)
from app.models.address import CustomerAddress
from app.models.cart import ShoppingCart
from app.models.catalog import ProductVariant
from app.models.inventory import (
    FulfillmentLocation,
    InventoryBalance,
    InventoryReservation,
)
from app.models.orders import Order, OrderLine
from app.models.outbox_event import OutboxEvent
from app.modules.addresses.service import resolve_fulfillment_location
from app.modules.cart.service import (
    _load_cart,
)
from app.modules.pricing.service import get_current_variant_price

logger = logging.getLogger(__name__)

TAX_RATE_BPS = 1800  # 18% GST in basis points
DELIVERY_FEE_MINOR = 2900  # ₹29.00 flat fee in minor units
RESERVATION_TTL_MINUTES = 15


async def create_order_from_cart(
    session: AsyncSession,
    *,
    user_id: UUID,
    address_id: UUID,
) -> Order:
    """Create an immutable order from the customer's active cart.

    Locks the cart, validates address ownership, revalidates serviceability,
    reserves inventory at the serviceable location, freezes line prices,
    computes totals, and emits outbox events.
    """

    async with transaction(session):
        # Load and lock the active cart
        cart = await _lock_active_cart(session, user_id)
        if cart is None:
            raise CartNotFound

        # Validate cart has items
        if not cart.items:
            raise EmptyCartError

        # Validate address ownership and load address
        await _validate_address_ownership(session, user_id, address_id)

        # Revalidate serviceability and pick fulfillment location
        location = await resolve_fulfillment_location(
            session,
            user_id=user_id,
            address_id=address_id,
        )
        if location is None:
            raise InvalidOrderRequest

        # Lock inventory rows and validate availability, create reservations
        reservations = await _reserve_cart_inventory(session, cart, location)

        # Freeze line prices and build order lines
        order_lines = await _build_order_lines(session, cart, location)

        # Compute totals
        subtotal_minor = sum(line.line_total_minor for line in order_lines)
        tax_minor = (subtotal_minor * TAX_RATE_BPS) // 10000
        delivery_fee_minor = DELIVERY_FEE_MINOR
        total_minor = subtotal_minor + tax_minor + delivery_fee_minor

        # Create order
        order = Order(
            user_id=user_id,
            address_id=address_id,
            status="confirmed",
            currency_code=cart.currency_code,
            subtotal_minor=subtotal_minor,
            tax_minor=tax_minor,
            delivery_fee_minor=delivery_fee_minor,
            total_minor=total_minor,
            payment_status="pending",
        )
        session.add(order)
        await session.flush()

        # Persist order lines
        for line in order_lines:
            line.order_id = order.id
            session.add(line)

        await session.flush()

        # Mark reservations as consumed and link to order
        for res in reservations:
            res.status = "consumed"
            res.order_id = order.id

        # Clear the cart (lines will cascade delete)
        for item in cart.items:
            await session.delete(item)

        # Emit outbox events
        _record_order_event(
            session,
            event_type="order.created",
            aggregate_id=order.id,
            payload={
                "user_id": str(user_id),
                "address_id": str(address_id),
                "currency_code": cart.currency_code,
                "subtotal_minor": subtotal_minor,
                "tax_minor": tax_minor,
                "delivery_fee_minor": delivery_fee_minor,
                "total_minor": total_minor,
            },
        )

        logger.info(
            "order_created",
            extra={
                "order_id": str(order.id),
                "user_id": str(user_id),
                "line_count": len(order_lines),
                "total_minor": total_minor,
            },
        )

        # Load order with lines eagerly before transaction commits
        result = await session.execute(
            select(Order).options(selectinload(Order.lines)).where(Order.id == order.id)
        )
        return result.scalar_one()


async def _lock_active_cart(session: AsyncSession, user_id: UUID) -> ShoppingCart | None:
    """Load and lock the customer's active cart with its items."""
    return await _load_cart(session, user_id=user_id)


async def _validate_address_ownership(
    session: AsyncSession,
    user_id: UUID,
    address_id: UUID,
) -> CustomerAddress:
    """Validate the address exists and belongs to the customer."""
    address = await session.scalar(
        select(CustomerAddress).where(
            CustomerAddress.id == address_id,
            CustomerAddress.user_id == user_id,
            CustomerAddress.is_active.is_(True),
        )
    )
    if address is None:
        raise AddressOwnershipError
    return address


async def _reserve_cart_inventory(
    session: AsyncSession,
    cart: ShoppingCart,
    location: FulfillmentLocation,
) -> list[InventoryReservation]:
    """Reserve inventory for all cart lines at the fulfillment location."""
    reservations = []
    now = datetime.now(UTC)
    expires_at = datetime.fromtimestamp(now.timestamp() + RESERVATION_TTL_MINUTES * 60, tz=UTC)

    for item in cart.items:
        # Lock inventory balance
        balance = await session.scalar(
            select(InventoryBalance)
            .where(
                InventoryBalance.location_id == location.id,
                InventoryBalance.variant_id == item.variant_id,
            )
            .with_for_update()
        )
        if balance is None:
            raise InsufficientInventoryForOrder

        available = balance.on_hand_quantity - balance.reserved_quantity
        if available < item.quantity:
            raise InsufficientInventoryForOrder

        # Create reservation
        reservation_key = f"order-{location.id}-{item.variant_id}-{now.timestamp()}"
        reservation = InventoryReservation(
            location_id=location.id,
            variant_id=item.variant_id,
            reservation_key=reservation_key,
            quantity=Decimal(str(item.quantity)),
            status="active",
            expires_at=expires_at,
        )
        balance.reserved_quantity += Decimal(str(item.quantity))
        session.add(reservation)
        reservations.append(reservation)

    await session.flush()
    return reservations


async def _build_order_lines(
    session: AsyncSession,
    cart: ShoppingCart,
    location: FulfillmentLocation,
) -> list[OrderLine]:
    """Build immutable order lines with frozen price snapshots."""
    order_lines = []

    for item in cart.items:
        # Verify the variant is still active and price is still current
        price = await get_current_variant_price(
            session,
            variant_id=item.variant_id,
            currency_code=item.currency_code,
        )
        if price is None:
            variant = await session.scalar(
                select(ProductVariant).where(
                    ProductVariant.id == item.variant_id,
                    ProductVariant.is_active.is_(True),
                )
            )
            if variant is None:
                raise VariantNotFound
            raise Exception("Price no longer available")

        line = OrderLine(
            variant_id=item.variant_id,
            price_id=price.id,
            quantity=item.quantity,
            currency_code=item.currency_code,
            unit_price_minor=item.unit_price_minor,
            line_total_minor=item.quantity * item.unit_price_minor,
        )
        order_lines.append(line)

    return order_lines


async def _load_order(session: AsyncSession, order_id: UUID) -> Order:
    """Load order with lines eagerly."""
    statement = select(Order).options(selectinload(Order.lines)).where(Order.id == order_id)
    result = await session.execute(statement)
    return result.scalar_one()


async def get_order(session: AsyncSession, *, order_id: UUID, user_id: UUID) -> Order | None:
    """Load order with lines eagerly, verifying ownership."""
    statement = (
        select(Order)
        .options(selectinload(Order.lines))
        .where(Order.id == order_id, Order.user_id == user_id)
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


def _record_order_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: UUID,
    payload: dict[str, object],
) -> None:
    session.add(
        OutboxEvent(
            aggregate_type="order",
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )
    )

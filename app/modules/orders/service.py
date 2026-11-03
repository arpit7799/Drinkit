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
from app.modules.compliance.service import (
    create_delivery_compliance_log,
    verify_alcohol_compliance,
)
from app.modules.pricing.service import get_current_variant_price
from app.modules.promotions.service import (
    apply_coupon_to_order,
    award_loyalty_points,
    redeem_loyalty_points,
    validate_coupon,
)
from app.modules.promotions.tax import calculate_order_taxes

logger = logging.getLogger(__name__)

TAX_RATE_BPS = 1800  # Fallback 18% GST in basis points
DELIVERY_FEE_MINOR = 2900  # ₹29.00 flat fee in minor units
RESERVATION_TTL_MINUTES = 15


async def create_order_from_cart(
    session: AsyncSession,
    *,
    user_id: UUID,
    address_id: UUID,
    coupon_code: str | None = None,
    redeem_points: int = 0,
) -> Order:
    """Create an immutable order from the customer's active cart.

    Locks the cart, validates address ownership, revalidates serviceability,
    reserves inventory at the serviceable location, freezes line prices,
    computes taxes and promotional discounts, and emits outbox events.
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
        address = await _validate_address_ownership(session, user_id, address_id)

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

        # Check alcohol compliance (KYC, legal drinking age, operating hours, dry days)
        variant_ids = [line.variant_id for line in order_lines]
        variants_res = await session.scalars(
            select(ProductVariant)
            .options(selectinload(ProductVariant.product))
            .where(ProductVariant.id.in_(variant_ids))
        )
        has_alcohol = any(v.product.is_alcoholic for v in variants_res.all())
        if has_alcohol:
            state_code = address.state[:2].upper() if address.state else "MH"
            await verify_alcohol_compliance(
                session,
                customer_id=user_id,
                state_code=state_code,
                has_alcohol=True,
            )

        # Compute subtotal
        subtotal_minor = sum(line.line_total_minor for line in order_lines)

        # Validate and apply promotional coupon if provided
        coupon = None
        coupon_discount_minor = 0
        if coupon_code:
            coupon, coupon_discount_minor = await validate_coupon(
                session,
                code=coupon_code,
                cart_subtotal_minor=subtotal_minor,
                customer_id=user_id,
            )

        # Compute dynamic itemized GST taxes based on delivery address postal code
        tax_items = [
            {
                "variant_id": line.variant_id,
                "line_subtotal_minor": line.line_total_minor,
            }
            for line in order_lines
        ]
        tax_res = await calculate_order_taxes(
            session,
            postal_code=address.postal_code,
            items=tax_items,
        )
        tax_minor = tax_res.total_tax_minor

        delivery_fee_minor = DELIVERY_FEE_MINOR

        # Temporary total to determine max allowable points redemption
        discounted_subtotal = max(0, subtotal_minor - coupon_discount_minor)
        raw_total_minor = discounted_subtotal + tax_minor + delivery_fee_minor

        # Calculate and check loyalty points redemption
        loyalty_discount_minor = 0
        if redeem_points > 0:
            # Max discount cannot exceed raw total
            max_points_redeemable = raw_total_minor // 100
            actual_points = min(redeem_points, max_points_redeemable)
            loyalty_discount_minor = actual_points * 100

        total_discount_minor = coupon_discount_minor + loyalty_discount_minor
        total_minor = max(0, subtotal_minor - total_discount_minor) + tax_minor + delivery_fee_minor

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

        # Initialize delivery compliance log for alcohol orders
        if has_alcohol:
            await create_delivery_compliance_log(
                session,
                order_id=order.id,
                customer_id=user_id,
            )

        # Persist coupon usage if coupon was applied
        if coupon is not None and coupon_discount_minor > 0:
            await apply_coupon_to_order(
                session,
                coupon=coupon,
                customer_id=user_id,
                order_id=order.id,
                discount_applied_minor=coupon_discount_minor,
            )

        # Persist loyalty points redemption if points were used
        if redeem_points > 0 and actual_points > 0:
            await redeem_loyalty_points(
                session,
                customer_id=user_id,
                order_id=order.id,
                points_to_redeem=actual_points,
            )

        # Award loyalty points for confirmed order (1 point per ₹100 spent)
        await award_loyalty_points(
            session,
            customer_id=user_id,
            order_id=order.id,
            order_total_minor=total_minor,
        )

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
                "coupon_code": coupon.code if coupon else None,
                "discount_minor": total_discount_minor,
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

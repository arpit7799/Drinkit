"""Promotions and Liver Points loyalty service."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    CouponCustomerLimitReached,
    CouponExpired,
    CouponInactive,
    CouponMinOrderNotMet,
    CouponNotFound,
    CouponUsageLimitReached,
    InsufficientLoyaltyPoints,
)
from app.models.promotions_tax import (
    Coupon,
    CouponStatus,
    CouponUsage,
    DiscountType,
    LoyaltyAccount,
    LoyaltyTransaction,
    LoyaltyTransactionType,
)
from app.modules.promotions.schemas import CouponCreateRequest

logger = logging.getLogger(__name__)

# Point value conversion: 1 Liver Point = ₹1.00 (100 minor units)
POINT_VALUE_MINOR = 100


async def create_coupon(session: AsyncSession, request: CouponCreateRequest) -> Coupon:
    """Register a new promotional coupon code."""
    coupon = Coupon(
        code=request.code.strip().upper(),
        name=request.name.strip(),
        description=request.description,
        discount_type=request.discount_type,
        discount_value=request.discount_value,
        currency_code=request.currency_code,
        min_order_amount_minor=request.min_order_amount_minor,
        max_discount_minor=request.max_discount_minor,
        max_uses=request.max_uses,
        max_uses_per_customer=request.max_uses_per_customer,
        uses_count=0,
        valid_from=request.valid_from,
        valid_until=request.valid_until,
        status=CouponStatus.ACTIVE,
        first_order_only=request.first_order_only,
        new_customers_only=request.new_customers_only,
    )
    session.add(coupon)
    await session.flush()
    return coupon


async def get_coupon_by_code(session: AsyncSession, code: str) -> Coupon | None:
    """Retrieve coupon by unique alphanumeric code."""
    return await session.scalar(select(Coupon).where(Coupon.code == code.strip().upper()))


async def validate_coupon(
    session: AsyncSession,
    *,
    code: str,
    cart_subtotal_minor: int,
    customer_id: UUID | None = None,
) -> tuple[Coupon, int]:
    """Validate coupon rules and calculate the minor-unit discount amount.

    Returns:
        tuple[Coupon, int]: The verified coupon instance and the computed discount.
    """
    coupon = await get_coupon_by_code(session, code)
    if coupon is None:
        raise CouponNotFound()

    now = datetime.now(UTC)

    # 1. Status and global exhaustion check
    if coupon.status == CouponStatus.EXHAUSTED or (
        coupon.max_uses is not None and coupon.uses_count >= coupon.max_uses
    ):
        raise CouponUsageLimitReached()

    if coupon.status != CouponStatus.ACTIVE:
        raise CouponInactive()

    # 2. Time validity window
    if now < coupon.valid_from or now > coupon.valid_until:
        raise CouponExpired()

    # 3. Minimum order subtotal check
    if coupon.min_order_amount_minor and cart_subtotal_minor < coupon.min_order_amount_minor:
        raise CouponMinOrderNotMet()

    # 5. Customer usage count check
    if customer_id is not None and coupon.max_uses_per_customer is not None:
        customer_uses = await session.scalar(
            select(func.count(CouponUsage.id)).where(
                CouponUsage.coupon_id == coupon.id,
                CouponUsage.customer_id == customer_id,
            )
        )
        if customer_uses is not None and customer_uses >= coupon.max_uses_per_customer:
            raise CouponCustomerLimitReached()

    # 6. Calculate discount in minor units
    if coupon.discount_type == DiscountType.PERCENTAGE:
        # discount_value is e.g. 20.00 (%)
        calculated = (cart_subtotal_minor * int(coupon.discount_value * 100)) // 10000
        if coupon.max_discount_minor is not None:
            calculated = min(calculated, coupon.max_discount_minor)
        discount_applied = min(calculated, cart_subtotal_minor)
    elif coupon.discount_type == DiscountType.FIXED_AMOUNT:
        # discount_value is e.g. 100.00 (₹) -> 10000 minor units
        fixed_minor = int(coupon.discount_value * 100)
        discount_applied = min(fixed_minor, cart_subtotal_minor)
    else:
        discount_applied = 0

    return coupon, discount_applied


async def apply_coupon_to_order(
    session: AsyncSession,
    *,
    coupon: Coupon,
    customer_id: UUID,
    order_id: UUID,
    discount_applied_minor: int,
) -> CouponUsage:
    """Record coupon redemption for an order and increment the usage counter."""
    coupon.uses_count += 1
    if coupon.max_uses is not None and coupon.uses_count >= coupon.max_uses:
        coupon.status = CouponStatus.EXHAUSTED

    usage = CouponUsage(
        coupon_id=coupon.id,
        customer_id=customer_id,
        order_id=order_id,
        discount_applied_minor=discount_applied_minor,
    )
    session.add(usage)
    return usage


async def get_or_create_loyalty_account(session: AsyncSession, customer_id: UUID) -> LoyaltyAccount:
    """Fetch or lazily initialize the customer's Liver Points loyalty account."""
    account = await session.scalar(
        select(LoyaltyAccount).where(LoyaltyAccount.customer_id == customer_id)
    )
    if account is None:
        account = LoyaltyAccount(
            customer_id=customer_id,
            points_balance=0,
            lifetime_earned=0,
            lifetime_redeemed=0,
            tier="bronze",
        )
        session.add(account)
        await session.flush()
    return account


async def award_loyalty_points(
    session: AsyncSession,
    *,
    customer_id: UUID,
    order_id: UUID | None = None,
    order_total_minor: int,
) -> int:
    """Award Liver Points on order completion (1 point per ₹100 spent)."""
    # Award 1 point per 10,000 minor units (₹100)
    points_to_award = order_total_minor // 10000
    if points_to_award <= 0:
        return 0

    account = await get_or_create_loyalty_account(session, customer_id)

    # Pessimistic update
    account.points_balance += points_to_award
    account.lifetime_earned += points_to_award

    # Tier update
    if account.lifetime_earned >= 1000:
        account.tier = "gold"
    elif account.lifetime_earned >= 250:
        account.tier = "silver"
    else:
        account.tier = "bronze"
    account.tier_updated_at = datetime.now(UTC)

    txn = LoyaltyTransaction(
        account_id=account.id,
        transaction_type=LoyaltyTransactionType.EARN,
        points_delta=points_to_award,
        balance_after=account.points_balance,
        order_id=order_id,
        description=f"Points earned on order {order_id}" if order_id else "Points earned on order",
    )
    session.add(txn)
    return points_to_award


async def redeem_loyalty_points(
    session: AsyncSession,
    *,
    customer_id: UUID,
    order_id: UUID | None = None,
    points_to_redeem: int,
) -> int:
    """Redeem Liver Points for an order discount."""
    if points_to_redeem <= 0:
        return 0

    account = await session.scalar(
        select(LoyaltyAccount).where(LoyaltyAccount.customer_id == customer_id).with_for_update()
    )
    if account is None or account.points_balance < points_to_redeem:
        raise InsufficientLoyaltyPoints()

    account.points_balance -= points_to_redeem
    account.lifetime_redeemed += points_to_redeem

    discount_minor = points_to_redeem * POINT_VALUE_MINOR

    txn = LoyaltyTransaction(
        account_id=account.id,
        transaction_type=LoyaltyTransactionType.REDEEM,
        points_delta=-points_to_redeem,
        balance_after=account.points_balance,
        order_id=order_id,
        description=(
            f"Points redeemed on order {order_id}" if order_id else "Points redeemed on order"
        ),
    )
    session.add(txn)
    return discount_minor


async def get_loyalty_transactions(
    session: AsyncSession, account_id: UUID, limit: int = 20
) -> list[LoyaltyTransaction]:
    """Fetch recent loyalty points audit transactions."""
    result = await session.scalars(
        select(LoyaltyTransaction)
        .where(LoyaltyTransaction.account_id == account_id)
        .order_by(LoyaltyTransaction.created_at.desc())
        .limit(limit)
    )
    return list(result.all())

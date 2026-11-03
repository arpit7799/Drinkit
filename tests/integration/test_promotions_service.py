"""Integration tests for promotions, coupons, Liver Points, and tax calculation services."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.database import AsyncSessionFactory
from app.core.exceptions import (
    CouponExpired,
    CouponMinOrderNotMet,
    CouponNotFound,
    CouponUsageLimitReached,
    InsufficientLoyaltyPoints,
)
from app.models.address import CustomerAddress
from app.models.auth import User
from app.models.orders import Order
from app.models.promotions_tax import (
    Coupon,
    CouponStatus,
    DiscountType,
    TaxCategory,
    TaxJurisdiction,
    TaxRate,
)
from app.modules.promotions.schemas import CouponCreateRequest
from app.modules.promotions.service import (
    apply_coupon_to_order,
    award_loyalty_points,
    create_coupon,
    get_or_create_loyalty_account,
    redeem_loyalty_points,
    validate_coupon,
)
from app.modules.promotions.tax import calculate_order_taxes

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_coupon_creation_and_validation(integration_engine):
    code = f"SAVE20_{uuid4().hex[:6].upper()}"
    async with AsyncSessionFactory(bind=integration_engine) as session:
        now = datetime.now(UTC)
        request = CouponCreateRequest(
            code=code,
            name="Save 20%",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("20.00"),
            min_order_amount_minor=1000,
            max_discount_minor=2000,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=7),
            max_uses=10,
            max_uses_per_customer=2,
        )
        coupon = await create_coupon(session, request)
        await session.commit()

        # 1. Normal validation: ₹50.00 order subtotal (5000 minor)
        # 20% of 5000 is 1000, capped at max_discount_minor (2000) -> 1000
        verified, discount = await validate_coupon(
            session,
            code=code,
            cart_subtotal_minor=5000,
        )
        assert verified.id == coupon.id
        assert discount == 1000

        # 2. Large order hitting cap: ₹200.00 (20000 minor)
        # 20% of 20000 is 4000, but capped at 2000
        _, discount_capped = await validate_coupon(
            session,
            code=code,
            cart_subtotal_minor=20000,
        )
        assert discount_capped == 2000

        # 3. Minimum order not met
        with pytest.raises(CouponMinOrderNotMet):
            await validate_coupon(
                session,
                code=code,
                cart_subtotal_minor=500,
            )


@pytest.mark.asyncio
async def test_coupon_expiration_and_limits(integration_engine):
    user_id = uuid4()
    exp_code = f"EXP_{uuid4().hex[:6].upper()}"
    once_code = f"ONCE_{uuid4().hex[:6].upper()}"

    async with AsyncSessionFactory(bind=integration_engine) as session:
        now = datetime.now(UTC)
        expired_coupon = Coupon(
            code=exp_code,
            name="Old Coupon",
            discount_type=DiscountType.FIXED_AMOUNT,
            discount_value=Decimal("10.00"),
            valid_from=now - timedelta(days=10),
            valid_until=now - timedelta(days=2),
            status=CouponStatus.ACTIVE,
        )
        session.add(expired_coupon)

        limited_coupon = Coupon(
            code=once_code,
            name="Single Use",
            discount_type=DiscountType.FIXED_AMOUNT,
            discount_value=Decimal("50.00"),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
            max_uses=1,
            max_uses_per_customer=1,
            uses_count=0,
            status=CouponStatus.ACTIVE,
        )
        session.add(limited_coupon)
        await session.commit()

        # Expired coupon raises CouponExpired
        with pytest.raises(CouponExpired):
            await validate_coupon(session, code=exp_code, cart_subtotal_minor=5000)

        # Non-existent coupon raises CouponNotFound
        with pytest.raises(CouponNotFound):
            await validate_coupon(session, code="DOESNOTEXIST", cart_subtotal_minor=5000)

        # Test single usage and exhaustion
        order_id = uuid4()
        address_id = uuid4()
        user = User(
            id=user_id,
            email=f"lim-{user_id}@example.com",
            password_hash="$argon2id$test",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        address = CustomerAddress(
            id=address_id,
            user_id=user_id,
            label="home",
            recipient_name="Tester",
            line1="123",
            city="Mumbai",
            state="MH",
            postal_code="400001",
            country_code="IN",
            is_active=True,
        )
        session.add(address)
        await session.flush()

        order = Order(
            id=order_id,
            user_id=user_id,
            address_id=address_id,
            status="confirmed",
            currency_code="INR",
            subtotal_minor=5000,
            tax_minor=900,
            delivery_fee_minor=2900,
            total_minor=8800,
        )
        session.add(order)
        await session.flush()

        await apply_coupon_to_order(
            session,
            coupon=limited_coupon,
            customer_id=user_id,
            order_id=order_id,
            discount_applied_minor=5000,
        )
        await session.commit()

        assert limited_coupon.uses_count == 1
        assert limited_coupon.status == CouponStatus.EXHAUSTED

        # Second customer trying to use it hits global limit
        with pytest.raises(CouponUsageLimitReached):
            await validate_coupon(
                session,
                code=once_code,
                cart_subtotal_minor=5000,
                customer_id=uuid4(),
            )


@pytest.mark.asyncio
async def test_loyalty_earning_redemption_and_tier_upgrade(integration_engine):
    user_id = uuid4()
    async with AsyncSessionFactory(bind=integration_engine) as session:
        user = User(
            id=user_id,
            email=f"loyalty-flow-{user_id}@example.com",
            password_hash="$argon2id$test",
            is_active=True,
        )
        session.add(user)
        await session.commit()

        account = await get_or_create_loyalty_account(session, user_id)
        assert account.points_balance == 0
        assert account.tier == "bronze"

        # 1. Earn points on an order of ₹300.00 (30,000 minor) -> 3 points
        earned = await award_loyalty_points(
            session,
            customer_id=user_id,
            order_id=None,
            order_total_minor=30000,
        )
        await session.commit()
        assert earned == 3
        assert account.points_balance == 3

        # 2. Earn points on a large order of ₹25,000.00 (2,500,000 minor) -> 250 points
        # Should upgrade tier to 'silver' (>= 250)
        await award_loyalty_points(
            session,
            customer_id=user_id,
            order_id=None,
            order_total_minor=2500000,
        )
        await session.commit()
        assert account.points_balance == 253
        assert account.tier == "silver"

        # 3. Redeem 50 points -> ₹50.00 discount (5000 minor units)
        discount_minor = await redeem_loyalty_points(
            session,
            customer_id=user_id,
            order_id=None,
            points_to_redeem=50,
        )
        await session.commit()
        assert discount_minor == 5000
        assert account.points_balance == 203
        assert account.lifetime_redeemed == 50

        # 4. Attempting to redeem more than available balance raises InsufficientLoyaltyPoints
        with pytest.raises(InsufficientLoyaltyPoints):
            await redeem_loyalty_points(
                session,
                customer_id=user_id,
                order_id=None,
                points_to_redeem=500,
            )


@pytest.mark.asyncio
async def test_dynamic_tax_calculation_engine(integration_engine):
    state_code = "T1"
    postal_code = f"9{uuid4().int % 90000 + 10000}"

    async with AsyncSessionFactory(bind=integration_engine) as session:
        # Pre-clean any leftover from previous runs
        await session.execute(delete(TaxRate).where(TaxRate.state_code == state_code))
        await session.execute(
            delete(TaxJurisdiction).where(TaxJurisdiction.postal_code == postal_code)
        )
        await session.commit()

        now = datetime.now(UTC)
        # Seed jurisdiction and state tax rates
        jurisdiction = TaxJurisdiction(
            postal_code=postal_code,
            state_code=state_code,
            state_name="TestState",
            is_active=True,
        )
        session.add(jurisdiction)

        rate_alcohol = TaxRate(
            state_code=state_code,
            state_name="TestState",
            category=TaxCategory.ALCOHOL,
            rate_bps=2000,  # 20%
            cgst_rate_bps=0,
            sgst_rate_bps=0,
            igst_rate_bps=0,
            cess_rate_bps=0,
            effective_from=now,
            is_active=True,
        )
        rate_mixer = TaxRate(
            state_code=state_code,
            state_name="TestState",
            category=TaxCategory.MIXER,
            rate_bps=1800,  # 18% (9% CGST + 9% SGST)
            cgst_rate_bps=900,
            sgst_rate_bps=900,
            igst_rate_bps=0,
            cess_rate_bps=0,
            effective_from=now,
            is_active=True,
        )
        session.add_all([rate_alcohol, rate_mixer])
        await session.commit()

        try:
            items = [
                {
                    "variant_id": uuid4(),
                    "category": TaxCategory.ALCOHOL,
                    "line_subtotal_minor": 10000,  # ₹100 -> ₹20 tax (2000 minor)
                },
                {
                    "variant_id": uuid4(),
                    "category": TaxCategory.MIXER,
                    "line_subtotal_minor": 5000,  # ₹50 -> ₹9 tax (900 minor: 450 CGST + 450 SGST)
                },
            ]

            tax_res = await calculate_order_taxes(
                session,
                postal_code=postal_code,
                items=items,
            )

            assert tax_res.state_code == state_code
            assert tax_res.total_tax_minor == 2900  # 2000 + 900
            assert len(tax_res.lines) == 2
            assert tax_res.lines[0].total_tax_minor == 2000
            assert tax_res.lines[1].cgst_minor == 450
            assert tax_res.lines[1].sgst_minor == 450
        finally:
            await session.execute(delete(TaxRate).where(TaxRate.state_code == state_code))
            await session.execute(
                delete(TaxJurisdiction).where(TaxJurisdiction.postal_code == postal_code)
            )
            await session.commit()

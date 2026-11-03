"""Integration tests for Drinkit VIP membership service functions."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import AsyncSessionFactory
from app.models.auth import User
from app.modules.memberships.schemas import MembershipPlanCreateRequest
from app.modules.memberships.service import (
    cancel_membership,
    create_membership_plan,
    evaluate_membership_order_benefits,
    get_customer_active_membership,
    get_customer_savings_summary,
    list_active_plans,
    log_membership_order_benefits,
    subscribe_to_plan,
)


@pytest.mark.asyncio
async def test_membership_lifecycle_and_benefits(
    integration_engine: AsyncEngine,
) -> None:
    async with AsyncSessionFactory(bind=integration_engine) as session:
        # Create test customer
        user = User(
            id=uuid4(),
            email=f"vip-test-{uuid4().hex[:8]}@example.com",
            password_hash="$argon2id$v=19$m=1,t=1,p=1$test$test",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # 1. Create a membership plan
        plan_code = f"VIP_{uuid4().hex[:6].upper()}"
        plan_req = MembershipPlanCreateRequest(
            code=plan_code,
            name="Drinkit VIP Gold",
            description="Unlimited free deliveries above ₹199 and 2x Liver points",
            duration_days=30,
            price_minor=19900,
            currency_code="INR",
            free_delivery_min_order_minor=19900,
            points_multiplier=Decimal("2.0"),
            priority_fulfillment=True,
            is_active=True,
        )
        plan = await create_membership_plan(session, plan_req)
        await session.commit()
        assert plan.id is not None
        assert plan.code == plan_code

        # 2. Duplicate plan creation should raise 409 Conflict
        with pytest.raises(HTTPException) as exc_info:
            await create_membership_plan(session, plan_req)
        assert exc_info.value.status_code == 409

        # 3. List active plans
        plans = await list_active_plans(session)
        assert any(p.code == plan_code for p in plans)

        # 4. Check active membership before subscribing (should be None)
        active_before = await get_customer_active_membership(session, user.id)
        assert active_before is None

        # Non-VIP benefit evaluation: delivery fee not waived, multiplier is 1.0
        fee, saved, mult, mem = await evaluate_membership_order_benefits(
            session,
            customer_id=user.id,
            order_subtotal_minor=50000,
            proposed_delivery_fee_minor=2900,
        )
        assert fee == 2900
        assert saved == 0
        assert mult == Decimal("1.0")
        assert mem is None

        # 5. Subscribe customer to plan
        subscription = await subscribe_to_plan(
            session,
            customer_id=user.id,
            plan_id=plan.id,
            auto_renew=True,
            payment_reference="pay_razor_test123",
        )
        await session.commit()
        assert subscription.status == "active"
        assert subscription.auto_renew is True
        initial_expiry = subscription.expires_at

        # 6. Verify active membership found
        active = await get_customer_active_membership(session, user.id)
        assert active is not None
        assert active.plan.code == plan_code

        # 7. Extend subscription (subscribe again to same plan)
        extended = await subscribe_to_plan(
            session,
            customer_id=user.id,
            plan_id=plan.id,
        )
        await session.commit()
        assert extended.expires_at > initial_expiry

        # 8. Evaluate VIP benefits:
        # a) Order below min order (₹100 < ₹199 threshold)
        fee_low, saved_low, mult_low, mem_low = await evaluate_membership_order_benefits(
            session,
            customer_id=user.id,
            order_subtotal_minor=10000,
            proposed_delivery_fee_minor=2900,
        )
        assert fee_low == 2900
        assert saved_low == 0
        assert mult_low == Decimal("2.0")

        # b) Order above min order (₹500 >= ₹199 threshold)
        fee_high, saved_high, mult_high, mem_high = await evaluate_membership_order_benefits(
            session,
            customer_id=user.id,
            order_subtotal_minor=50000,
            proposed_delivery_fee_minor=2900,
        )
        assert fee_high == 0
        assert saved_high == 2900
        assert mult_high == Decimal("2.0")
        assert mem_high is not None

        # 9. Log VIP benefits and verify savings summary
        await log_membership_order_benefits(
            session,
            customer_id=user.id,
            membership_id=subscription.id,
            order_id=None,
            delivery_fee_saved_minor=2900,
            bonus_points_awarded=5,
        )
        await session.commit()

        savings = await get_customer_savings_summary(session, user.id)
        assert savings.is_vip is True
        assert savings.active_plan_code == plan_code
        assert savings.total_delivery_fees_saved_minor == 2900
        assert savings.total_bonus_points_earned == 5
        assert savings.total_perks_claimed == 2

        # 10. Cancel membership
        cancelled = await cancel_membership(
            session,
            customer_id=user.id,
            reason="Testing cancellation",
        )
        await session.commit()
        assert cancelled.status == "cancelled"
        assert cancelled.cancellation_reason == "Testing cancellation"

        # After cancellation, customer is no longer VIP
        active_after = await get_customer_active_membership(session, user.id)
        assert active_after is None


@pytest.mark.asyncio
async def test_vip_checkout_free_delivery_and_multiplied_points(
    integration_engine: AsyncEngine,
) -> None:
    from app.modules.cart.service import add_cart_item, get_or_create_cart
    from app.modules.orders.service import create_order_from_cart
    from app.modules.pricing.service import set_variant_price
    from tests.integration.test_orders import _seed_user_address_variant_and_price

    user_id, address_id, variant_id, _ = await _seed_user_address_variant_and_price(
        integration_engine
    )

    async with AsyncSessionFactory(bind=integration_engine) as session:
        # Set item price above VIP threshold (₹300.00 = 30000 minor)
        await set_variant_price(
            session,
            variant_id=variant_id,
            currency_code="INR",
            amount_minor=30000,
        )
        # Create VIP plan
        plan = await create_membership_plan(
            session,
            MembershipPlanCreateRequest(
                code=f"VIP_CART_{uuid4().hex[:6].upper()}",
                name="VIP Express Club",
                duration_days=30,
                price_minor=19900,
                free_delivery_min_order_minor=19900,
                points_multiplier=Decimal("2.0"),
            ),
        )
        # Subscribe customer
        await subscribe_to_plan(
            session,
            customer_id=user_id,
            plan_id=plan.id,
        )
        await session.commit()

        # Build cart
        await get_or_create_cart(session, user_id=user_id)
        await add_cart_item(
            session, user_id=user_id, variant_id=variant_id, quantity=1, currency_code="INR"
        )
        await session.commit()

        # Checkout order as VIP
        order = await create_order_from_cart(
            session,
            user_id=user_id,
            address_id=address_id,
        )

        assert order.status == "confirmed"
        assert order.subtotal_minor == 30000
        # Delivery fee is waived (0) for VIP above ₹199 threshold
        assert order.delivery_fee_minor == 0
        assert order.total_minor == order.subtotal_minor + order.tax_minor

        # Verify savings summary reflects ₹29.00 delivery fee saved
        savings = await get_customer_savings_summary(session, user_id)
        assert savings.is_vip is True
        assert savings.total_delivery_fees_saved_minor == 2900
        assert savings.total_perks_claimed >= 1

"""Unit tests for Drinkit VIP membership models and schemas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.membership import (
    CustomerMembership,
    MembershipBenefitLog,
    MembershipPlan,
)
from app.modules.memberships.schemas import (
    CancelMembershipRequest,
    CustomerMembershipResponse,
    MembershipBenefitLogResponse,
    MembershipPlanCreateRequest,
    MembershipPlanResponse,
    MembershipSavingsSummaryResponse,
    SubscribeMembershipRequest,
)


def test_membership_plan_model_instantiation() -> None:
    plan = MembershipPlan(
        code="VIP_MONTHLY",
        name="Drinkit VIP Monthly",
        description="Free delivery above ₹199 and 2x Liver points",
        duration_days=30,
        price_minor=19900,
        currency_code="INR",
        free_delivery_min_order_minor=19900,
        points_multiplier=Decimal("2.0"),
        priority_fulfillment=True,
        is_active=True,
    )
    assert plan.code == "VIP_MONTHLY"
    assert plan.duration_days == 30
    assert plan.price_minor == 19900
    assert plan.free_delivery_min_order_minor == 19900
    assert plan.points_multiplier == Decimal("2.0")
    assert plan.priority_fulfillment is True


def test_customer_membership_model_instantiation() -> None:
    cust_id = uuid4()
    plan_id = uuid4()
    now = datetime.now(UTC)
    membership = CustomerMembership(
        customer_id=cust_id,
        plan_id=plan_id,
        status="active",
        starts_at=now,
        expires_at=now + timedelta(days=30),
        auto_renew=True,
        payment_reference="pay_vip_12345",
    )
    assert membership.customer_id == cust_id
    assert membership.status == "active"
    assert membership.auto_renew is True
    assert membership.payment_reference == "pay_vip_12345"


def test_membership_benefit_log_model_instantiation() -> None:
    cust_id = uuid4()
    mem_id = uuid4()
    order_id = uuid4()
    log = MembershipBenefitLog(
        customer_id=cust_id,
        membership_id=mem_id,
        order_id=order_id,
        benefit_type="free_delivery",
        amount_saved_minor=2900,
        bonus_points_awarded=0,
    )
    assert log.benefit_type == "free_delivery"
    assert log.amount_saved_minor == 2900


def test_membership_plan_create_request_validation() -> None:
    # Valid payload
    req = MembershipPlanCreateRequest(
        code="VIP_ANNUAL",
        name="Drinkit VIP Annual Club",
        duration_days=365,
        price_minor=149900,
        free_delivery_min_order_minor=9900,
        points_multiplier=Decimal("3.0"),
    )
    assert req.code == "VIP_ANNUAL"
    assert req.duration_days == 365

    # Negative duration should fail
    with pytest.raises(ValidationError):
        MembershipPlanCreateRequest(
            code="VIP_INVALID",
            name="Invalid Plan",
            duration_days=0,
            price_minor=19900,
        )

    # Multiplier < 1.0 should fail
    with pytest.raises(ValidationError):
        MembershipPlanCreateRequest(
            code="VIP_INVALID",
            name="Invalid Plan",
            duration_days=30,
            price_minor=19900,
            points_multiplier=Decimal("0.5"),
        )


def test_membership_schemas_serialization() -> None:
    plan_id = uuid4()
    cust_id = uuid4()
    now = datetime.now(UTC)

    plan_resp = MembershipPlanResponse(
        id=plan_id,
        code="VIP_MONTHLY",
        name="VIP Monthly",
        description="Perks included",
        duration_days=30,
        price_minor=19900,
        currency_code="INR",
        free_delivery_min_order_minor=19900,
        points_multiplier=Decimal("2.0"),
        priority_fulfillment=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    assert plan_resp.code == "VIP_MONTHLY"

    mem_resp = CustomerMembershipResponse(
        id=uuid4(),
        customer_id=cust_id,
        plan_id=plan_id,
        status="active",
        starts_at=now,
        expires_at=now + timedelta(days=30),
        auto_renew=False,
        payment_reference=None,
        cancellation_reason=None,
        plan=plan_resp,
        created_at=now,
        updated_at=now,
    )
    assert mem_resp.plan is not None
    assert mem_resp.plan.code == "VIP_MONTHLY"

    sub_req = SubscribeMembershipRequest(plan_id=plan_id, auto_renew=True)
    assert sub_req.auto_renew is True

    cancel_req = CancelMembershipRequest(reason="Moving away")
    assert cancel_req.reason == "Moving away"

    savings_resp = MembershipSavingsSummaryResponse(
        customer_id=cust_id,
        is_vip=True,
        active_plan_code="VIP_MONTHLY",
        expires_at=now + timedelta(days=30),
        total_delivery_fees_saved_minor=5800,
        total_bonus_points_earned=40,
        total_perks_claimed=4,
        recent_benefits=[
            MembershipBenefitLogResponse(
                id=uuid4(),
                customer_id=cust_id,
                membership_id=mem_resp.id,
                order_id=uuid4(),
                benefit_type="free_delivery",
                amount_saved_minor=2900,
                bonus_points_awarded=0,
                created_at=now,
            )
        ],
    )
    assert savings_resp.is_vip is True
    assert savings_resp.total_delivery_fees_saved_minor == 5800
    assert len(savings_resp.recent_benefits) == 1

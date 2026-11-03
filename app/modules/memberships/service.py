"""Drinkit VIP membership business logic, subscription lifecycle, and perks evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.membership import (
    CustomerMembership,
    MembershipBenefitLog,
    MembershipPlan,
)
from app.modules.memberships.schemas import (
    MembershipBenefitLogResponse,
    MembershipPlanCreateRequest,
    MembershipSavingsSummaryResponse,
)


async def list_active_plans(session: AsyncSession) -> Sequence[MembershipPlan]:
    """Retrieve all publicly available, active VIP membership plans."""
    result = await session.scalars(
        select(MembershipPlan)
        .where(MembershipPlan.is_active.is_(True))
        .order_by(MembershipPlan.price_minor.asc())
    )
    return result.all()


async def get_plan_by_id(session: AsyncSession, plan_id: UUID) -> MembershipPlan | None:
    """Fetch a membership plan by its unique UUID."""
    return await session.get(MembershipPlan, plan_id)


async def get_plan_by_code(session: AsyncSession, code: str) -> MembershipPlan | None:
    """Fetch a membership plan by unique plan code."""
    result = await session.scalars(
        select(MembershipPlan).where(MembershipPlan.code == code.strip().upper())
    )
    return result.first()


async def create_membership_plan(
    session: AsyncSession, payload: MembershipPlanCreateRequest
) -> MembershipPlan:
    """Register a new VIP subscription tier in the platform."""
    existing = await get_plan_by_code(session, payload.code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Membership plan with code '{payload.code.upper()}' already exists",
        )

    plan = MembershipPlan(
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        duration_days=payload.duration_days,
        price_minor=payload.price_minor,
        currency_code=payload.currency_code.upper(),
        free_delivery_min_order_minor=payload.free_delivery_min_order_minor,
        points_multiplier=payload.points_multiplier,
        priority_fulfillment=payload.priority_fulfillment,
        is_active=payload.is_active,
    )
    session.add(plan)
    await session.flush()
    return plan


async def get_customer_active_membership(
    session: AsyncSession, customer_id: UUID, now: datetime | None = None
) -> CustomerMembership | None:
    """Retrieve the currently active VIP membership for a customer, lazily expiring stale ones."""
    current_time = now or datetime.now(UTC)

    result = await session.scalars(
        select(CustomerMembership)
        .options(selectinload(CustomerMembership.plan))
        .where(
            CustomerMembership.customer_id == customer_id,
            CustomerMembership.status == "active",
        )
        .order_by(desc(CustomerMembership.expires_at))
    )
    membership = result.first()
    if not membership:
        return None

    if membership.expires_at <= current_time:
        membership.status = "expired"
        await session.flush()
        return None

    return membership


async def subscribe_to_plan(
    session: AsyncSession,
    *,
    customer_id: UUID,
    plan_id: UUID,
    auto_renew: bool = False,
    payment_reference: str | None = None,
) -> CustomerMembership:
    """Subscribe a customer to a VIP plan or extend existing active membership."""
    plan = await get_plan_by_id(session, plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VIP membership plan not found or inactive",
        )

    now = datetime.now(UTC)
    active_membership = await get_customer_active_membership(session, customer_id, now=now)

    if active_membership and active_membership.plan_id == plan.id:
        # Extend current subscription window
        active_membership.expires_at = active_membership.expires_at + timedelta(
            days=plan.duration_days
        )
        active_membership.auto_renew = auto_renew
        if payment_reference:
            active_membership.payment_reference = payment_reference
        await session.flush()
        return active_membership

    if active_membership and active_membership.plan_id != plan.id:
        # Upgrade or switch plan: supersede previous plan
        active_membership.status = "expired"
        await session.flush()

    new_membership = CustomerMembership(
        customer_id=customer_id,
        plan_id=plan.id,
        status="active",
        starts_at=now,
        expires_at=now + timedelta(days=plan.duration_days),
        auto_renew=auto_renew,
        payment_reference=payment_reference,
    )
    session.add(new_membership)
    await session.flush()

    # Eagerly load plan relationship
    result = await session.scalars(
        select(CustomerMembership)
        .options(selectinload(CustomerMembership.plan))
        .where(CustomerMembership.id == new_membership.id)
    )
    return result.one()


async def cancel_membership(
    session: AsyncSession, *, customer_id: UUID, reason: str | None = None
) -> CustomerMembership:
    """Cancel an ongoing VIP membership."""
    membership = await get_customer_active_membership(session, customer_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active VIP membership found to cancel",
        )

    membership.status = "cancelled"
    membership.cancellation_reason = reason
    membership.auto_renew = False
    await session.flush()
    return membership


async def get_customer_savings_summary(
    session: AsyncSession, customer_id: UUID
) -> MembershipSavingsSummaryResponse:
    """Calculate cumulative delivery fee savings and bonus points accrued by VIP customer."""
    membership = await get_customer_active_membership(session, customer_id)
    is_vip = membership is not None
    active_plan_code = membership.plan.code if membership and membership.plan else None
    expires_at = membership.expires_at if membership else None

    logs_result = await session.scalars(
        select(MembershipBenefitLog)
        .where(MembershipBenefitLog.customer_id == customer_id)
        .order_by(desc(MembershipBenefitLog.created_at))
        .limit(20)
    )
    recent_logs = list(logs_result.all())

    # Aggregate total savings and points
    delivery_saved_res = await session.scalar(
        select(func.coalesce(func.sum(MembershipBenefitLog.amount_saved_minor), 0)).where(
            MembershipBenefitLog.customer_id == customer_id,
            MembershipBenefitLog.benefit_type == "free_delivery",
        )
    )
    bonus_points_res = await session.scalar(
        select(func.coalesce(func.sum(MembershipBenefitLog.bonus_points_awarded), 0)).where(
            MembershipBenefitLog.customer_id == customer_id,
        )
    )
    total_perks_res = await session.scalar(
        select(func.count(MembershipBenefitLog.id)).where(
            MembershipBenefitLog.customer_id == customer_id
        )
    )

    return MembershipSavingsSummaryResponse(
        customer_id=customer_id,
        is_vip=is_vip,
        active_plan_code=active_plan_code,
        expires_at=expires_at,
        total_delivery_fees_saved_minor=int(delivery_saved_res or 0),
        total_bonus_points_earned=int(bonus_points_res or 0),
        total_perks_claimed=int(total_perks_res or 0),
        recent_benefits=[MembershipBenefitLogResponse.model_validate(log) for log in recent_logs],
    )


async def evaluate_membership_order_benefits(
    session: AsyncSession,
    *,
    customer_id: UUID,
    order_subtotal_minor: int,
    proposed_delivery_fee_minor: int,
) -> tuple[int, int, Decimal, CustomerMembership | None]:
    """Evaluate VIP benefits for an order checkout.

    Returns:
        (fee_minor, saved_minor, points_multiplier, active_membership)
    """
    membership = await get_customer_active_membership(session, customer_id)
    if not membership:
        return (proposed_delivery_fee_minor, 0, Decimal("1.0"), None)

    plan = membership.plan
    if order_subtotal_minor >= plan.free_delivery_min_order_minor:
        effective_delivery_fee_minor = 0
        delivery_fee_saved_minor = proposed_delivery_fee_minor
    else:
        effective_delivery_fee_minor = proposed_delivery_fee_minor
        delivery_fee_saved_minor = 0

    return (
        effective_delivery_fee_minor,
        delivery_fee_saved_minor,
        plan.points_multiplier,
        membership,
    )


async def log_membership_order_benefits(
    session: AsyncSession,
    *,
    customer_id: UUID,
    membership_id: UUID,
    order_id: UUID,
    delivery_fee_saved_minor: int,
    bonus_points_awarded: int,
) -> None:
    """Record immutable audit logs for delivery fees saved and bonus loyalty points."""
    if delivery_fee_saved_minor > 0:
        delivery_log = MembershipBenefitLog(
            customer_id=customer_id,
            membership_id=membership_id,
            order_id=order_id,
            benefit_type="free_delivery",
            amount_saved_minor=delivery_fee_saved_minor,
            bonus_points_awarded=0,
        )
        session.add(delivery_log)

    if bonus_points_awarded > 0:
        points_log = MembershipBenefitLog(
            customer_id=customer_id,
            membership_id=membership_id,
            order_id=order_id,
            benefit_type="points_multiplier",
            amount_saved_minor=0,
            bonus_points_awarded=bonus_points_awarded,
        )
        session.add(points_log)

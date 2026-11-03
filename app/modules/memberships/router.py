"""FastAPI API router for Drinkit VIP memberships and subscriptions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User
from app.modules.auth.dependencies import get_current_user
from app.modules.memberships.schemas import (
    CancelMembershipRequest,
    CustomerMembershipResponse,
    MembershipPlanCreateRequest,
    MembershipPlanResponse,
    MembershipSavingsSummaryResponse,
    SubscribeMembershipRequest,
)
from app.modules.memberships.service import (
    cancel_membership,
    create_membership_plan,
    get_customer_active_membership,
    get_customer_savings_summary,
    list_active_plans,
    subscribe_to_plan,
)

router = APIRouter(prefix="/memberships", tags=["VIP Memberships"])


@router.get("/plans", response_model=list[MembershipPlanResponse])
async def list_membership_plans_endpoint(
    session: AsyncSession = Depends(get_db),
) -> list[MembershipPlanResponse]:
    """Retrieve all available VIP membership subscription plans."""
    plans = await list_active_plans(session)
    return [MembershipPlanResponse.model_validate(p) for p in plans]


@router.post(
    "/plans",
    response_model=MembershipPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_membership_plan_endpoint(
    payload: MembershipPlanCreateRequest,
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MembershipPlanResponse:
    """Create a new VIP membership plan."""
    plan = await create_membership_plan(session, payload)
    await session.commit()
    await session.refresh(plan)
    return MembershipPlanResponse.model_validate(plan)


@router.get("/me", response_model=CustomerMembershipResponse | None)
async def get_my_membership_endpoint(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomerMembershipResponse | None:
    """Retrieve the authenticated customer's current active VIP membership."""
    membership = await get_customer_active_membership(session, user.id)
    if not membership:
        return None
    return CustomerMembershipResponse.model_validate(membership)


@router.post(
    "/subscribe",
    response_model=CustomerMembershipResponse,
    status_code=status.HTTP_200_OK,
)
async def subscribe_membership_endpoint(
    payload: SubscribeMembershipRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomerMembershipResponse:
    """Subscribe authenticated user to a VIP membership plan or extend existing subscription."""
    membership = await subscribe_to_plan(
        session,
        customer_id=user.id,
        plan_id=payload.plan_id,
        auto_renew=payload.auto_renew,
        payment_reference=payload.payment_reference,
    )
    await session.commit()
    await session.refresh(membership)
    return CustomerMembershipResponse.model_validate(membership)


@router.post("/cancel", response_model=CustomerMembershipResponse)
async def cancel_membership_endpoint(
    payload: CancelMembershipRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomerMembershipResponse:
    """Cancel authenticated user's active VIP membership."""
    membership = await cancel_membership(
        session,
        customer_id=user.id,
        reason=payload.reason,
    )
    await session.commit()
    await session.refresh(membership)
    return CustomerMembershipResponse.model_validate(membership)


@router.get("/savings", response_model=MembershipSavingsSummaryResponse)
async def get_membership_savings_endpoint(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MembershipSavingsSummaryResponse:
    """Retrieve lifetime VIP delivery fee savings, bonus points, and claimed benefits."""
    return await get_customer_savings_summary(session, user.id)

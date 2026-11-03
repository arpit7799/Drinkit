"""REST API routes for compliance, customer KYC, and delivery verification."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import StateRegulationNotFound
from app.models.auth import User
from app.modules.auth.dependencies import get_current_user
from app.modules.compliance.schemas import (
    DeliveryComplianceResponse,
    DeliveryHandoverVerifyRequest,
    KYCResponse,
    KYCSubmissionRequest,
    StateAlcoholRegulationResponse,
)
from app.modules.compliance.service import (
    get_customer_kyc,
    get_state_regulation,
    submit_customer_kyc,
    verify_delivery_handover,
)

router = APIRouter(prefix="/compliance", tags=["compliance"])


@router.post(
    "/kyc",
    response_model=KYCResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_kyc_endpoint(
    request: KYCSubmissionRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KYCResponse:
    """Submit government ID document and date-of-birth for age verification."""
    kyc = await submit_customer_kyc(session, user.id, request)
    await session.commit()
    await session.refresh(kyc)
    return KYCResponse.model_validate(kyc)


@router.get(
    "/kyc",
    response_model=KYCResponse | None,
    status_code=status.HTTP_200_OK,
)
async def get_my_kyc_endpoint(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KYCResponse | None:
    """Retrieve verified customer KYC verification status."""
    kyc = await get_customer_kyc(session, user.id)
    if kyc is None:
        return None
    return KYCResponse.model_validate(kyc)


@router.get(
    "/regulations/{state_code}",
    response_model=StateAlcoholRegulationResponse,
    status_code=status.HTTP_200_OK,
)
async def get_state_regulation_endpoint(
    state_code: str,
    session: AsyncSession = Depends(get_db),
) -> StateAlcoholRegulationResponse:
    """Retrieve statutory legal drinking age, operating hours, and limits for a state."""
    reg = await get_state_regulation(session, state_code)
    if reg is None:
        raise StateRegulationNotFound()
    return StateAlcoholRegulationResponse.model_validate(reg)


@router.post(
    "/orders/{order_id}/verify-handover",
    response_model=DeliveryComplianceResponse,
    status_code=status.HTTP_200_OK,
)
async def verify_order_handover_endpoint(
    order_id: UUID,
    payload: DeliveryHandoverVerifyRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeliveryComplianceResponse:
    """Verify courier delivery handover at customer doorstep using secure OTP."""
    log = await verify_delivery_handover(
        session,
        order_id=order_id,
        courier_id=None,
        handover_otp=payload.handover_otp,
        recipient_age_confirmed=payload.recipient_age_confirmed,
    )
    await session.commit()
    return DeliveryComplianceResponse.model_validate(log)

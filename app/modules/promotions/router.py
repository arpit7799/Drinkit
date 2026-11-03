"""API endpoints for coupons, promotions, and Liver Points loyalty."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import CouponNotFound
from app.models.auth import User
from app.modules.auth.dependencies import get_current_user
from app.modules.promotions.schemas import (
    CouponCreateRequest,
    CouponResponse,
    CouponValidateRequest,
    CouponValidateResponse,
    LoyaltyAccountResponse,
    LoyaltyEstimateRequest,
    LoyaltyEstimateResponse,
    LoyaltyTransactionResponse,
)
from app.modules.promotions.service import (
    POINT_VALUE_MINOR,
    create_coupon,
    get_coupon_by_code,
    get_loyalty_transactions,
    get_or_create_loyalty_account,
    validate_coupon,
)

router = APIRouter(prefix="/promotions", tags=["promotions"])


@router.post(
    "/coupons/validate",
    response_model=CouponValidateResponse,
    status_code=status.HTTP_200_OK,
)
async def validate_coupon_endpoint(
    payload: CouponValidateRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CouponValidateResponse:
    """Validate a coupon code and calculate the discount against an active subtotal."""
    coupon, discount_applied = await validate_coupon(
        session,
        code=payload.code,
        cart_subtotal_minor=payload.cart_subtotal_minor,
        customer_id=user.id,
    )
    discounted_subtotal = max(0, payload.cart_subtotal_minor - discount_applied)

    return CouponValidateResponse(
        valid=True,
        code=coupon.code,
        discount_type=coupon.discount_type,
        discount_applied_minor=discount_applied,
        subtotal_minor=payload.cart_subtotal_minor,
        discounted_subtotal_minor=discounted_subtotal,
        message=f"Coupon {coupon.code} applied successfully.",
    )


@router.post(
    "/coupons",
    response_model=CouponResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_coupon_endpoint(
    payload: CouponCreateRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CouponResponse:
    """Create a new promotional coupon code."""
    coupon = await create_coupon(session, payload)
    await session.commit()
    await session.refresh(coupon)
    return CouponResponse.model_validate(coupon)


@router.get(
    "/coupons/{code}",
    response_model=CouponResponse,
    status_code=status.HTTP_200_OK,
)
async def get_coupon_endpoint(
    code: str,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CouponResponse:
    """Fetch promotional coupon details by code."""
    coupon = await get_coupon_by_code(session, code)
    if coupon is None:
        raise CouponNotFound()
    return CouponResponse.model_validate(coupon)


@router.get(
    "/loyalty",
    response_model=LoyaltyAccountResponse,
    status_code=status.HTTP_200_OK,
)
async def get_loyalty_account_endpoint(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LoyaltyAccountResponse:
    """Retrieve customer's Liver Points loyalty balance and tier."""
    account = await get_or_create_loyalty_account(session, user.id)
    return LoyaltyAccountResponse.model_validate(account)


@router.get(
    "/loyalty/transactions",
    response_model=list[LoyaltyTransactionResponse],
    status_code=status.HTTP_200_OK,
)
async def get_loyalty_transactions_endpoint(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LoyaltyTransactionResponse]:
    """Retrieve recent loyalty points history and audit logs."""
    account = await get_or_create_loyalty_account(session, user.id)
    transactions = await get_loyalty_transactions(session, account.id)
    return [LoyaltyTransactionResponse.model_validate(tx) for tx in transactions]


@router.post(
    "/loyalty/estimate",
    response_model=LoyaltyEstimateResponse,
    status_code=status.HTTP_200_OK,
)
async def estimate_loyalty_discount_endpoint(
    payload: LoyaltyEstimateRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LoyaltyEstimateResponse:
    """Estimate the monetary discount for a designated amount of points."""
    account = await get_or_create_loyalty_account(session, user.id)
    discount_minor = payload.points * POINT_VALUE_MINOR
    return LoyaltyEstimateResponse(
        points=payload.points,
        discount_value_minor=discount_minor,
        available_balance=account.points_balance,
    )

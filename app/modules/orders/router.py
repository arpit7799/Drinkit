"""Authenticated customer order routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User
from app.models.orders import Order
from app.modules.auth.dependencies import get_current_user
from app.modules.orders.schemas import (
    CreateOrderRequest,
    OrderLineResponse,
    OrderResponse,
    PaymentInitiationRequest,
    PaymentInitiationResponse,
)
from app.modules.orders.service import create_order_from_cart, get_order

router = APIRouter(prefix="/orders", tags=["orders"])


def _order_response(order: Order) -> OrderResponse:
    lines = [
        OrderLineResponse(
            id=line.id,
            variant_id=line.variant_id,
            quantity=line.quantity,
            currency_code=line.currency_code,
            unit_price_minor=line.unit_price_minor,
            line_total_minor=line.line_total_minor,
        )
        for line in order.lines
    ]
    return OrderResponse(
        id=order.id,
        status=order.status,
        currency_code=order.currency_code,
        subtotal_minor=order.subtotal_minor,
        tax_minor=order.tax_minor,
        delivery_fee_minor=order.delivery_fee_minor,
        total_minor=order.total_minor,
        payment_status=order.payment_status,
        payment_provider=order.payment_provider,
        payment_reference=order.payment_reference,
        created_at=order.created_at,
        lines=lines,
    )


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """Create an order from the customer's active cart."""

    order = await create_order_from_cart(
        session,
        user_id=current_user.id,
        address_id=request.address_id,
    )
    return _order_response(order)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order_detail(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """Return a specific order owned by the authenticated customer."""

    order = await get_order(session, order_id=order_id, user_id=current_user.id)
    if order is None:
        from app.core.exceptions import OrderNotFound

        raise OrderNotFound
    return _order_response(order)


@router.post("/{order_id}/payment", response_model=PaymentInitiationResponse)
async def initiate_payment(
    order_id: UUID,
    request: PaymentInitiationRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PaymentInitiationResponse:
    """Initiate payment for a confirmed order."""

    order = await get_order(session, order_id=order_id, user_id=current_user.id)
    if order is None:
        from app.core.exceptions import OrderNotFound

        raise OrderNotFound

    if order.status != "confirmed":
        from app.core.exceptions import OrderStatusConflict

        raise OrderStatusConflict

    if order.payment_status != "pending":
        from app.core.exceptions import InvalidOrderRequest

        raise InvalidOrderRequest

    # Delegate to payment provider
    from app.modules.payments.service import initiate_payment as do_initiate_payment

    result = await do_initiate_payment(
        session,
        order_id=order.id,
        provider=request.provider,
        return_url=request.return_url,
    )
    return PaymentInitiationResponse(
        order_id=result.order_id,
        payment_url=result.payment_url,
        provider_reference=result.provider_reference,
        status=result.status,
    )

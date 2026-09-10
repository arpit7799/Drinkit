"""Payment initiation and processing workflows."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import transaction
from app.core.exceptions import (
    InvalidOrderRequest,
    OrderNotFound,
    OrderStatusConflict,
    PaymentProviderError,
)
from app.models.orders import Order
from app.models.outbox_event import OutboxEvent
from app.modules.payments.providers import (
    PaymentInitiationResult,
    get_payment_provider,
)

logger = logging.getLogger(__name__)


async def initiate_payment(
    session: AsyncSession,
    *,
    order_id: UUID,
    provider: str,
    return_url: str | None = None,
) -> PaymentInitiationResult:
    """Initiate payment for a confirmed order."""

    async with transaction(session):
        order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None:
            raise OrderNotFound

        if order.status != "confirmed":
            raise OrderStatusConflict

        if order.payment_status != "pending":
            raise InvalidOrderRequest

        # Get customer info from user and address
        from app.models.address import CustomerAddress
        from app.models.auth import User

        user = await session.scalar(select(User).where(User.id == order.user_id))
        address = await session.scalar(
            select(CustomerAddress).where(CustomerAddress.id == order.address_id)
        )
        if user is None or address is None:
            raise InvalidOrderRequest

        # Delegate to provider
        payment_provider = get_payment_provider(provider)
        result = await payment_provider.initiate_payment(
            order_id=order.id,
            amount_minor=order.total_minor,
            currency_code=order.currency_code,
            return_url=return_url,
            customer_email=user.email,
            customer_phone=None,
        )

        # Update order with payment info
        order.payment_status = "authorized"
        order.payment_provider = provider
        order.payment_reference = result.provider_reference

        # Record outbox event
        session.add(
            OutboxEvent(
                aggregate_type="order",
                aggregate_id=order.id,
                event_type="order.payment.initiated",
                payload={
                    "provider": provider,
                    "provider_reference": result.provider_reference,
                    "amount_minor": order.total_minor,
                    "currency_code": order.currency_code,
                },
            )
        )

        logger.info(
            "payment_initiated",
            extra={
                "order_id": str(order.id),
                "provider": provider,
                "provider_reference": result.provider_reference,
                "amount_minor": order.total_minor,
            },
        )

        return result


async def confirm_payment(
    session: AsyncSession,
    *,
    provider_reference: str,
) -> Order:
    """Confirm payment via provider webhook/callback."""

    async with transaction(session):
        order = await session.scalar(
            select(Order).where(Order.payment_reference == provider_reference).with_for_update()
        )
        if order is None:
            raise OrderNotFound

        if order.payment_status != "authorized":
            raise InvalidOrderRequest

        if not order.payment_provider:
            raise InvalidOrderRequest

        provider = get_payment_provider(order.payment_provider)
        verified = await provider.verify_payment(provider_reference=provider_reference)
        if not verified:
            order.payment_status = "failed"
            session.add(
                OutboxEvent(
                    aggregate_type="order",
                    aggregate_id=order.id,
                    event_type="order.payment.failed",
                    payload={"provider_reference": provider_reference},
                )
            )
            raise PaymentProviderError

        order.payment_status = "captured"
        session.add(
            OutboxEvent(
                aggregate_type="order",
                aggregate_id=order.id,
                event_type="order.payment.captured",
                payload={"provider_reference": provider_reference},
            )
        )

        logger.info(
            "payment_captured",
            extra={
                "order_id": str(order.id),
                "provider_reference": provider_reference,
            },
        )

        return order


async def refund_order(
    session: AsyncSession,
    *,
    order_id: UUID,
    amount_minor: int | None = None,
) -> Order:
    """Process a refund for a captured order."""

    async with transaction(session):
        order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None:
            raise OrderNotFound

        if order.payment_status != "captured":
            raise InvalidOrderRequest

        if not order.payment_provider or not order.payment_reference:
            raise InvalidOrderRequest

        refund_amount = amount_minor or order.total_minor
        provider = get_payment_provider(order.payment_provider)
        success = await provider.refund_payment(
            provider_reference=order.payment_reference,
            amount_minor=refund_amount,
        )
        if not success:
            raise PaymentProviderError

        order.payment_status = "refunded"
        session.add(
            OutboxEvent(
                aggregate_type="order",
                aggregate_id=order.id,
                event_type="order.payment.refunded",
                payload={
                    "provider_reference": order.payment_reference,
                    "amount_minor": refund_amount,
                },
            )
        )

        logger.info(
            "payment_refunded",
            extra={
                "order_id": str(order.id),
                "amount_minor": refund_amount,
            },
        )

        return order

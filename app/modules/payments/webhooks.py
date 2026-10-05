"""Payment webhook endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.orders import Order
from app.modules.payments.providers import get_payment_provider
from app.modules.payments.service import confirm_payment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments/webhooks", tags=["payment-webhooks"])


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(..., alias="X-Razorpay-Signature"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Razorpay webhook events."""
    body = await request.body()

    # Verify signature
    provider = get_payment_provider("razorpay")
    webhook_secret = "your_razorpay_webhook_secret"  # Should come from config

    if not await provider.verify_webhook_signature(body, x_razorpay_signature, webhook_secret):
        logger.warning("razorpay_webhook_invalid_signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event")

    logger.info("razorpay_webhook_received", extra={"event": event})

    if event == "payment.captured":
        payment_entity = payload["payload"]["payment"]["entity"]
        order_id = payment_entity.get("notes", {}).get("order_id")
        provider_reference = payment_entity.get("order_id")

        if order_id:
            try:
                await confirm_payment(session, provider_reference=provider_reference)
                logger.info("payment_confirmed_via_webhook", extra={"order_id": order_id})
            except Exception as e:
                logger.error(
                    "webhook_confirm_failed",
                    extra={
                        "order_id": order_id,
                        "error": str(e),
                    },
                )

    elif event == "payment.failed":
        payment_entity = payload["payload"]["payment"]["entity"]
        order_id = payment_entity.get("notes", {}).get("order_id")
        provider_reference = payment_entity.get("order_id")

        if order_id:
            try:
                async with session.begin():
                    order = await session.scalar(
                        select(Order).where(Order.id == order_id).with_for_update()
                    )
                    if order and order.payment_status == "authorized":
                        order.payment_status = "failed"
            except Exception as e:
                logger.error("webhook_failed_failed", extra={"order_id": order_id, "error": str(e)})

    return {"status": "ok"}


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Stripe webhook events."""
    body = await request.body()

    # Verify signature
    provider = get_payment_provider("stripe")
    webhook_secret = "your_stripe_webhook_secret"  # Should come from config

    if not await provider.verify_webhook_signature(body, stripe_signature, webhook_secret):
        logger.warning("stripe_webhook_invalid_signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = json.loads(body)
    event_type = payload.get("type")

    logger.info("stripe_webhook_received", extra={"event_type": event_type})

    if event_type == "payment_intent.succeeded":
        payment_intent = payload["data"]["object"]
        provider_reference = payment_intent["id"]

        try:
            await confirm_payment(session, provider_reference=provider_reference)
        except Exception as e:
            logger.error("stripe_webhook_confirm_failed", extra={"error": str(e)})

    elif event_type == "payment_intent.payment_failed":
        payment_intent = payload["data"]["object"]
        provider_reference = payment_intent["id"]
        order_id = payment_intent.get("metadata", {}).get("order_id")

        if order_id:
            try:
                async with session.begin():
                    order = await session.scalar(
                        select(Order).where(Order.id == order_id).with_for_update()
                    )
                    if order and order.payment_status == "authorized":
                        order.payment_status = "failed"
            except Exception as e:
                logger.error("stripe_webhook_failed", extra={"error": str(e)})

    return {"status": "ok"}


@router.post("/phonepe")
async def phonepe_webhook(
    request: Request,
    x_verify: str = Header(..., alias="X-VERIFY"),
    x_merchant_id: str = Header(..., alias="X-MERCHANT-ID"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Handle PhonePe webhook events."""
    body = await request.body()

    # Verify signature
    provider = get_payment_provider("phonepe")
    webhook_secret = "your_phonepe_webhook_secret"  # Should come from config

    if not await provider.verify_webhook_signature(body, x_verify, webhook_secret):
        logger.warning("phonepe_webhook_invalid_signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = json.loads(body)
    event = payload.get("event")

    logger.info("phonepe_webhook_received", extra={"event": event})

    if event == "CHECKOUT_ORDER_COMPLETED":
        data = payload.get("data", {})
        provider_reference = data.get("merchantTransactionId")

        if provider_reference:
            try:
                await confirm_payment(session, provider_reference=provider_reference)
            except Exception as e:
                logger.error("phonepe_webhook_confirm_failed", extra={"error": str(e)})

    return {"status": "ok"}

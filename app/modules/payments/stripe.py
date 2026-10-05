"""Stripe payment provider with real API integration."""

import hashlib
import hmac
import logging
from uuid import UUID

import httpx

from app.modules.payments.providers import (
    PaymentInitiationResult,
)

logger = logging.getLogger(__name__)


class StripeProvider:
    """Stripe payment provider with real API integration."""

    def __init__(
        self,
        secret_key: str | None = None,
        publishable_key: str | None = None,
        test_mode: bool = True,
    ):
        self.secret_key = secret_key or "sk_test_dummy"
        self.publishable_key = publishable_key or "pk_test_dummy"
        self.test_mode = test_mode
        self.base_url = "https://api.stripe.com/v1"
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "stripe"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                auth=(self.secret_key, ""),
                timeout=30.0,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _to_form_data(self, data: dict) -> dict:
        """Convert dict to form data for Stripe (returns dict, httpx handles encoding)."""
        return {k: v for k, v in data.items() if v is not None}

    async def initiate_payment(
        self,
        *,
        order_id: UUID,
        amount_minor: int,
        currency_code: str,
        return_url: str | None,
        customer_email: str,
        customer_phone: str | None,
    ) -> "PaymentInitiationResult":
        """Create a Stripe PaymentIntent and return client secret."""
        client = await self._get_client()

        # Create or retrieve customer
        customer_data = {"email": customer_email}
        if customer_phone:
            customer_data["phone"] = customer_phone

        try:
            # Create PaymentIntent
            payload = {
                "amount": str(amount_minor),
                "currency": currency_code.lower(),
                "automatic_payment_methods[enabled]": "true",
                "customer_email": customer_email,
                "metadata[order_id]": str(order_id),
            }

            if return_url:
                payload["return_url"] = return_url

            response = await client.post(
                f"{self.base_url}/payment_intents",
                data=self._to_form_data(payload),
            )
            response.raise_for_status()
            data = response.json()

            payment_intent_id = data["id"]

            # Build payment URL (Stripe Checkout or custom)
            payment_url = None
            if return_url:
                # For Stripe Checkout Session (optional - using PaymentIntent directly)
                session_payload = {
                    "payment_intent_data[metadata][order_id]": str(order_id),
                    "mode": "payment",
                    "success_url": return_url,
                    "cancel_url": return_url,
                    "line_items[0][price_data][currency]": currency_code.lower(),
                    "line_items[0][price_data][product_data][name]": f"Order {order_id.hex[:8]}",
                    "line_items[0][price_data][unit_amount]": str(amount_minor),
                    "line_items[0][quantity]": "1",
                }

                session_response = await client.post(
                    f"{self.base_url}/checkout/sessions",
                    data=self._to_form_data(session_payload),
                )
                session_response.raise_for_status()
                session_data = session_response.json()
                payment_url = session_data["url"]

            logger.info(
                "stripe_payment_intent_created",
                extra={
                    "order_id": str(order_id),
                    "payment_intent_id": payment_intent_id,
                    "amount_minor": amount_minor,
                    "currency": currency_code,
                },
            )

            return PaymentInitiationResult(
                order_id=order_id,
                payment_url=payment_url,
                provider_reference=payment_intent_id,
                status="initiated",
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "stripe_payment_intent_failed",
                extra={
                    "order_id": str(order_id),
                    "status_code": e.response.status_code,
                    "response": e.response.text,
                },
            )
            return PaymentInitiationResult(
                order_id=order_id,
                payment_url=None,
                provider_reference="",
                status="failed",
            )

    async def verify_payment(self, *, provider_reference: str) -> bool:
        """Verify payment by retrieving PaymentIntent status."""
        client = await self._get_client()

        try:
            response = await client.get(f"{self.base_url}/payment_intents/{provider_reference}")
            response.raise_for_status()
            data = response.json()

            # Check if payment was captured/succeeded
            return data.get("status") == "succeeded"

        except httpx.HTTPStatusError as e:
            logger.error(
                "stripe_verify_failed",
                extra={
                    "provider_reference": provider_reference,
                    "status_code": e.response.status_code,
                    "response": e.response.text,
                },
            )
            return False

    async def verify_webhook_signature(
        self, payload: bytes, signature: str, webhook_secret: str
    ) -> bool:
        """Verify Stripe webhook signature."""
        # Stripe sends signature as 't=<timestamp>,v1=<signature>'
        try:
            timestamp_part, signature_part = signature.split(",")
            timestamp = timestamp_part.split("=")[1]
            received_signature = signature_part.split("=")[1]

            signed_payload = f"{timestamp}.{payload.decode()}"
            expected_signature = hmac.new(
                webhook_secret.encode(),
                signed_payload.encode(),
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(expected_signature, received_signature)
        except Exception:
            return False

    async def refund_payment(
        self,
        *,
        provider_reference: str,
        amount_minor: int | None = None,
    ) -> bool:
        """Process a refund for a captured payment."""
        client = await self._get_client()

        try:
            # Create refund for the PaymentIntent
            payload = {"payment_intent": provider_reference}
            if amount_minor is not None:
                payload["amount"] = str(amount_minor)

            response = await client.post(
                f"{self.base_url}/refunds",
                data=self._to_form_data(payload),
            )
            response.raise_for_status()

            logger.info(
                "stripe_refund_processed",
                extra={
                    "payment_intent_id": provider_reference,
                    "amount_minor": amount_minor,
                    "refund_id": response.json().get("id"),
                },
            )
            return True

        except httpx.HTTPStatusError as e:
            logger.error(
                "stripe_refund_failed",
                extra={
                    "provider_reference": provider_reference,
                    "status_code": e.response.status_code,
                    "response": e.response.text,
                },
            )
            return False

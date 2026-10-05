"""Razorpay payment provider with real API integration."""

import hashlib
import hmac
import logging
from uuid import UUID

import httpx

from app.modules.payments.providers import (
    PaymentInitiationResult,
)

logger = logging.getLogger(__name__)


class RazorpayProvider:
    """Razorpay payment provider with real API integration."""

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        test_mode: bool = True,
    ):
        self.key_id = key_id or "rzp_test_dummy"
        self.key_secret = key_secret or "dummy_secret"
        self.test_mode = test_mode
        self.base_url = "https://api.razorpay.com/v1"
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "razorpay"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                auth=(self.key_id, self.key_secret),
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

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
        """Create a Razorpay order and return payment details."""
        client = await self._get_client()

        # Create Razorpay order
        payload = {
            "amount": amount_minor,
            "currency": currency_code.upper(),
            "receipt": f"order_{order_id.hex[:12]}",
            "payment_capture": 1,  # Auto-capture
            "notes": {
                "order_id": str(order_id),
            },
        }

        try:
            response = await client.post(f"{self.base_url}/orders", json=payload)
            response.raise_for_status()
            data = response.json()

            razorpay_order_id = data["id"]

            # Build checkout URL
            payment_url = None
            if return_url:
                payment_url = (
                    f"https://checkout.razorpay.com/v1/checkout.js?"
                    f"rzp_order_id={razorpay_order_id}&"
                    f"rzp_key={self.key_id}&"
                    f"rzp_amount={amount_minor}&"
                    f"rzp_currency={currency_code.upper()}&"
                    f"rzp_email={customer_email}&"
                    f"rzp_phone={customer_phone or ''}&"
                    f"rzp_return_url={return_url}"
                )

            logger.info(
                "razorpay_order_created",
                extra={
                    "order_id": str(order_id),
                    "razorpay_order_id": razorpay_order_id,
                    "amount_minor": amount_minor,
                    "currency": currency_code,
                },
            )

            return PaymentInitiationResult(
                order_id=order_id,
                payment_url=payment_url,
                provider_reference=razorpay_order_id,
                status="initiated",
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "razorpay_order_failed",
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
        """Verify payment by fetching Razorpay order and checking payment status."""
        client = await self._get_client()

        try:
            # Fetch the order to get payment details
            response = await client.get(f"{self.base_url}/orders/{provider_reference}")
            response.raise_for_status()
            order_data = response.json()

            # If order has payments, verify the latest one
            if "payments" in order_data and order_data["payments"]:
                # Fetch payments for this order
                payments_response = await client.get(
                    f"{self.base_url}/orders/{provider_reference}/payments"
                )
                payments_response.raise_for_status()
                payments_data = payments_response.json()

                for payment in payments_data.get("items", []):
                    if payment.get("status") == "captured":
                        return True

            return False

        except httpx.HTTPStatusError as e:
            logger.error(
                "razorpay_verify_failed",
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
        """Verify Razorpay webhook signature."""
        expected_signature = hmac.new(
            webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    async def refund_payment(
        self,
        *,
        provider_reference: str,
        amount_minor: int | None = None,
    ) -> bool:
        """Process a refund for a captured payment."""
        client = await self._get_client()

        try:
            # First, find the payment ID from the order
            response = await client.get(f"{self.base_url}/orders/{provider_reference}/payments")
            response.raise_for_status()
            payments_data = response.json()

            payment_id = None
            for payment in payments_data.get("items", []):
                if payment.get("status") == "captured":
                    payment_id = payment["id"]
                    break

            if not payment_id:
                logger.error("no_captured_payment_found", extra={"order_id": provider_reference})
                return False

            # Process refund
            refund_payload = {}
            if amount_minor is not None:
                refund_payload["amount"] = amount_minor

            refund_response = await client.post(
                f"{self.base_url}/payments/{payment_id}/refund",
                json=refund_payload,
            )
            refund_response.raise_for_status()

            logger.info(
                "razorpay_refund_processed",
                extra={
                    "payment_id": payment_id,
                    "amount_minor": amount_minor,
                    "refund_id": refund_response.json().get("id"),
                },
            )
            return True

        except httpx.HTTPStatusError as e:
            logger.error(
                "razorpay_refund_failed",
                extra={
                    "provider_reference": provider_reference,
                    "status_code": e.response.status_code,
                    "response": e.response.text,
                },
            )
            return False

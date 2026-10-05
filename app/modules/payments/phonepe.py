"""PhonePe payment provider with real API integration."""

import base64
import hashlib
import hmac
import json
import logging
from uuid import UUID

import httpx

from app.modules.payments.providers import (
    PaymentInitiationResult,
)

logger = logging.getLogger(__name__)


class PhonePeProvider:
    """PhonePe payment provider with real API integration."""

    def __init__(
        self,
        merchant_id: str | None = None,
        salt_key: str | None = None,
        salt_index: int = 1,
        test_mode: bool = True,
    ):
        self.merchant_id = merchant_id or "MID_DUMMY"
        self.salt_key = salt_key or "dummy_salt_key"
        self.salt_index = salt_index
        self.test_mode = test_mode
        self.base_url = (
            "https://api-preprod.phonepe.com/apis/pg-sandbox"
            if test_mode
            else "https://api.phonepe.com/apis/pg"
        )
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "phonepe"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _generate_x_verify(self, payload: str, endpoint: str) -> str:
        """Generate X-VERIFY header for PhonePe API."""
        string_to_hash = payload + endpoint + self.salt_key
        hash_value = hashlib.sha256(string_to_hash.encode()).hexdigest()
        return f"{hash_value}###{self.salt_index}"

    def _encode_payload(self, data: dict) -> str:
        """Encode payload as base64."""
        json_str = json.dumps(data, separators=(",", ":"))
        return base64.b64encode(json_str.encode()).decode()

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
        """Initiate PhonePe payment and return redirect URL."""
        client = await self._get_client()

        merchant_transaction_id = f"TXN_{order_id.hex[:16].upper()}"

        payload = {
            "merchantId": self.merchant_id,
            "merchantTransactionId": merchant_transaction_id,
            "merchantUserId": str(order_id),
            "amount": amount_minor,
            "redirectUrl": return_url or "https://example.com/callback",
            "redirectMode": "POST",
            "callbackUrl": return_url or "https://example.com/callback",
            "paymentInstrument": {
                "type": "PAY_PAGE",
            },
        }

        if customer_phone:
            cleaned_phone = customer_phone.replace("+", "").replace("-", "").replace(" ", "")
            payload["mobileNumber"] = cleaned_phone

        endpoint = "/pg/v1/pay"
        encoded_payload = self._encode_payload(payload)
        x_verify = self._generate_x_verify(encoded_payload, endpoint)

        try:
            response = await client.post(
                f"{self.base_url}{endpoint}",
                json={"request": encoded_payload},
                headers={
                    "Content-Type": "application/json",
                    "X-VERIFY": x_verify,
                    "X-MERCHANT-ID": self.merchant_id,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("success") and "data" in data:
                instrument_response = data["data"]["instrumentResponse"]
                redirect_url = instrument_response.get("redirectInfo", {}).get("url")

                logger.info(
                    "phonepe_payment_initiated",
                    extra={
                        "order_id": str(order_id),
                        "merchant_transaction_id": merchant_transaction_id,
                        "amount_minor": amount_minor,
                        "currency": currency_code,
                    },
                )

                return PaymentInitiationResult(
                    order_id=order_id,
                    payment_url=redirect_url,
                    provider_reference=merchant_transaction_id,
                    status="initiated",
                )
            else:
                logger.error(
                    "phonepe_payment_failed",
                    extra={
                        "order_id": str(order_id),
                        "response": data,
                    },
                )
                return PaymentInitiationResult(
                    order_id=order_id,
                    payment_url=None,
                    provider_reference=merchant_transaction_id,
                    status="failed",
                )

        except httpx.HTTPStatusError as e:
            logger.error(
                "phonepe_payment_failed",
                extra={
                    "order_id": str(order_id),
                    "status_code": e.response.status_code,
                    "response": e.response.text,
                },
            )
            return PaymentInitiationResult(
                order_id=order_id,
                payment_url=None,
                provider_reference=merchant_transaction_id,
                status="failed",
            )

    async def verify_payment(self, *, provider_reference: str) -> bool:
        """Verify payment status by checking transaction status."""
        client = await self._get_client()

        endpoint = f"/pg/v1/status/{self.merchant_id}/{provider_reference}"
        x_verify = self._generate_x_verify("", endpoint)

        try:
            response = await client.get(
                f"{self.base_url}{endpoint}",
                headers={
                    "Content-Type": "application/json",
                    "X-VERIFY": x_verify,
                    "X-MERCHANT-ID": self.merchant_id,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("success") and "data" in data:
                payment_data = data["data"]
                state = payment_data.get("state")
                return state == "COMPLETED"

            return False

        except httpx.HTTPStatusError as e:
            logger.error(
                "phonepe_verify_failed",
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
        """Verify PhonePe webhook signature (X-VERIFY header)."""
        # PhonePe webhook verification uses the same logic
        expected = hmac.new(
            webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def refund_payment(
        self,
        *,
        provider_reference: str,
        amount_minor: int | None = None,
    ) -> bool:
        """Process a refund for a completed payment."""
        client = await self._get_client()

        refund_transaction_id = f"REFUND_{provider_reference}"

        payload = {
            "merchantId": self.merchant_id,
            "merchantTransactionId": provider_reference,
            "merchantRefundId": refund_transaction_id,
            "amount": amount_minor or 0,  # 0 means full refund
        }

        endpoint = "/pg/v1/refund"
        encoded_payload = self._encode_payload(payload)
        x_verify = self._generate_x_verify(encoded_payload, endpoint)

        try:
            response = await client.post(
                f"{self.base_url}{endpoint}",
                json={"request": encoded_payload},
                headers={
                    "Content-Type": "application/json",
                    "X-VERIFY": x_verify,
                    "X-MERCHANT-ID": self.merchant_id,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                logger.info(
                    "phonepe_refund_processed",
                    extra={
                        "provider_reference": provider_reference,
                        "amount_minor": amount_minor,
                        "refund_id": data.get("data", {}).get("merchantRefundId"),
                    },
                )
                return True

            logger.error(
                "phonepe_refund_failed",
                extra={
                    "provider_reference": provider_reference,
                    "response": data,
                },
            )
            return False

        except httpx.HTTPStatusError as e:
            logger.error(
                "phonepe_refund_failed",
                extra={
                    "provider_reference": provider_reference,
                    "status_code": e.response.status_code,
                    "response": e.response.text,
                },
            )
            return False

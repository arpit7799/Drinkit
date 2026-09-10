"""Payment provider abstraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass
class PaymentInitiationResult:
    order_id: UUID
    payment_url: str | None
    provider_reference: str
    status: str  # "initiated" | "requires_action" | "failed"


class PaymentProvider(ABC):
    """Abstract base class for payment providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'razorpay', 'stripe', 'phonepe')."""
        pass

    @abstractmethod
    async def initiate_payment(
        self,
        *,
        order_id: UUID,
        amount_minor: int,
        currency_code: str,
        return_url: str | None,
        customer_email: str,
        customer_phone: str | None,
    ) -> PaymentInitiationResult:
        """Initiate a payment for the given order."""
        pass

    @abstractmethod
    async def verify_payment(self, *, provider_reference: str) -> bool:
        """Verify payment status with the provider."""
        pass

    @abstractmethod
    async def refund_payment(
        self,
        *,
        provider_reference: str,
        amount_minor: int | None = None,
    ) -> bool:
        """Process a refund (full or partial)."""
        pass


def get_payment_provider(name: str) -> PaymentProvider:
    """Get a payment provider instance by name."""
    providers = {
        "razorpay": RazorpayProvider(),
        "stripe": StripeProvider(),
        "phonepe": PhonePeProvider(),
    }
    if name not in providers:
        raise ValueError(f"Unknown payment provider: {name}")
    return providers[name]


class RazorpayProvider(PaymentProvider):
    """Razorpay payment provider (stub implementation)."""

    @property
    def name(self) -> str:
        return "razorpay"

    async def initiate_payment(
        self,
        *,
        order_id: UUID,
        amount_minor: int,
        currency_code: str,
        return_url: str | None,
        customer_email: str,
        customer_phone: str | None,
    ) -> PaymentInitiationResult:
        # TODO: Implement real Razorpay integration
        # For now, return a mock result
        return PaymentInitiationResult(
            order_id=order_id,
            payment_url=None,
            provider_reference=f"rzp_test_{order_id.hex[:16]}",
            status="initiated",
        )

    async def verify_payment(self, *, provider_reference: str) -> bool:
        # TODO: Implement real verification
        return True

    async def refund_payment(
        self,
        *,
        provider_reference: str,
        amount_minor: int | None = None,
    ) -> bool:
        # TODO: Implement real refund
        return True


class StripeProvider(PaymentProvider):
    """Stripe payment provider (stub implementation)."""

    @property
    def name(self) -> str:
        return "stripe"

    async def initiate_payment(
        self,
        *,
        order_id: UUID,
        amount_minor: int,
        currency_code: str,
        return_url: str | None,
        customer_email: str,
        customer_phone: str | None,
    ) -> PaymentInitiationResult:
        # TODO: Implement real Stripe integration
        return PaymentInitiationResult(
            order_id=order_id,
            payment_url=None,
            provider_reference=f"stripe_test_{order_id.hex[:16]}",
            status="initiated",
        )

    async def verify_payment(self, *, provider_reference: str) -> bool:
        return True

    async def refund_payment(
        self,
        *,
        provider_reference: str,
        amount_minor: int | None = None,
    ) -> bool:
        return True


class PhonePeProvider(PaymentProvider):
    """PhonePe payment provider (stub implementation)."""

    @property
    def name(self) -> str:
        return "phonepe"

    async def initiate_payment(
        self,
        *,
        order_id: UUID,
        amount_minor: int,
        currency_code: str,
        return_url: str | None,
        customer_email: str,
        customer_phone: str | None,
    ) -> PaymentInitiationResult:
        # TODO: Implement real PhonePe integration
        return PaymentInitiationResult(
            order_id=order_id,
            payment_url=None,
            provider_reference=f"phonepe_test_{order_id.hex[:16]}",
            status="initiated",
        )

    async def verify_payment(self, *, provider_reference: str) -> bool:
        return True

    async def refund_payment(
        self,
        *,
        provider_reference: str,
        amount_minor: int | None = None,
    ) -> bool:
        return True

"""Payment provider abstraction and factory."""

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

    @abstractmethod
    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        webhook_secret: str,
    ) -> bool:
        """Verify webhook signature from the provider."""
        pass


def get_payment_provider(name: str) -> "PaymentProvider":
    """Get a payment provider instance by name.

    Uses lazy imports to avoid circular dependencies.
    """
    from app.modules.payments.phonepe import PhonePeProvider
    from app.modules.payments.razorpay import RazorpayProvider
    from app.modules.payments.stripe import StripeProvider

    providers = {
        "razorpay": lambda: RazorpayProvider(),
        "stripe": lambda: StripeProvider(),
        "phonepe": lambda: PhonePeProvider(),
    }
    if name not in providers:
        raise ValueError(f"Unknown payment provider: {name}")
    return providers[name]()  # type: ignore[return-value]

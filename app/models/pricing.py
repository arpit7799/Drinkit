"""Variant pricing persistence models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import BaseModel


class VariantPrice(BaseModel):
    """A time-effective price for one sellable product variant."""

    __tablename__ = "variant_prices"
    __table_args__ = (
        CheckConstraint(
            "amount_minor >= 0",
            name="amount_minor_non_negative",
        ),
        CheckConstraint(
            "currency_code ~ '^[A-Z]{3}$'",
            name="currency_code_valid",
        ),
        CheckConstraint(
            "ends_at IS NULL OR starts_at < ends_at",
            name="effective_window_valid",
        ),
        UniqueConstraint(
            "variant_id",
            "currency_code",
            "starts_at",
            name="uq_variant_prices_variant_currency_start",
        ),
        Index(
            "ix_variant_prices_variant_currency_effective",
            "variant_id",
            "currency_code",
            "is_active",
            "starts_at",
        ),
        Index(
            "ix_variant_prices_active_effective",
            "is_active",
            "starts_at",
            "ends_at",
        ),
    )

    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

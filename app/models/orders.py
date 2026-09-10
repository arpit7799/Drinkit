"""Order and checkout persistence models."""

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel


class Order(BaseModel):
    """An immutable customer order created from a cart at checkout."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal_minor >= 0", name="subtotal_non_negative"),
        CheckConstraint("tax_minor >= 0", name="tax_non_negative"),
        CheckConstraint("delivery_fee_minor >= 0", name="delivery_fee_non_negative"),
        CheckConstraint("total_minor >= 0", name="total_non_negative"),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_code_valid"),
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'fulfilled', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint(
            "payment_status IN ('pending', 'authorized', 'captured', 'failed', 'refunded')",
            name="payment_status_valid",
        ),
        Index("ix_orders_user_status_created", "user_id", "status", "created_at"),
        Index("ix_orders_payment_status", "payment_status"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    address_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customer_addresses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'draft'"),
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delivery_fee_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payment_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
    )
    payment_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OrderLine(BaseModel):
    """An immutable order line with a frozen price snapshot."""

    __tablename__ = "order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_code_valid"),
        CheckConstraint("unit_price_minor >= 0", name="unit_price_non_negative"),
        CheckConstraint("line_total_minor >= 0", name="line_total_non_negative"),
        UniqueConstraint(
            "order_id",
            "variant_id",
            name="uq_order_lines_order_variant",
        ),
        Index("ix_order_lines_order_variant", "order_id", "variant_id"),
    )

    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    price_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("variant_prices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)

    order: Mapped[Order] = relationship(back_populates="lines")

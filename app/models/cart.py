"""Customer shopping cart persistence models."""

from __future__ import annotations

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


class ShoppingCart(BaseModel):
    """A customer's currency-scoped cart and its lifecycle state."""

    __tablename__ = "shopping_carts"
    __table_args__ = (
        CheckConstraint(
            "currency_code ~ '^[A-Z]{3}$'",
            name="currency_code_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'checked_out', 'abandoned')",
            name="status_valid",
        ),
        Index(
            "uq_shopping_carts_one_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_shopping_carts_user_status_updated", "user_id", "status", "updated_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
    )
    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CartItem(BaseModel):
    """One variant line with a price snapshot captured at mutation time."""

    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price_minor >= 0", name="unit_price_minor_non_negative"),
        CheckConstraint(
            "currency_code ~ '^[A-Z]{3}$'",
            name="currency_code_valid",
        ),
        UniqueConstraint("cart_id", "variant_id", name="uq_cart_items_cart_variant"),
        Index("ix_cart_items_cart_updated", "cart_id", "updated_at"),
    )

    cart_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shopping_carts.id", ondelete="CASCADE"),
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
    cart: Mapped[ShoppingCart] = relationship(back_populates="items")

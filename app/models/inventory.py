"""Inventory, fulfillment-location, and reservation persistence models."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import BaseModel


class FulfillmentLocation(BaseModel):
    """A dark store or other location that holds sellable inventory."""

    __tablename__ = "fulfillment_locations"
    __table_args__ = (
        CheckConstraint("length(btrim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        Index("uq_fulfillment_locations_code_ci", text("lower(code)"), unique=True),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class InventoryBalance(BaseModel):
    """Authoritative on-hand and reserved quantity for one location and variant."""

    __tablename__ = "inventory_balances"
    __table_args__ = (
        CheckConstraint("on_hand_quantity >= 0", name="on_hand_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="reserved_non_negative"),
        CheckConstraint(
            "reserved_quantity <= on_hand_quantity",
            name="reserved_lte_on_hand",
        ),
        UniqueConstraint(
            "location_id", "variant_id", name="uq_inventory_balances_location_variant"
        ),
        Index("ix_inventory_balances_variant_location", "variant_id", "location_id"),
    )

    location_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fulfillment_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
    )
    on_hand_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default=text("0")
    )


class StockAdjustment(BaseModel):
    """Immutable stock delta recorded with an idempotency key."""

    __tablename__ = "stock_adjustments"
    __table_args__ = (
        CheckConstraint("quantity_delta <> 0", name="quantity_delta_non_zero"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_not_blank"),
        UniqueConstraint(
            "location_id",
            "variant_id",
            "idempotency_key",
            name="uq_stock_adjustments_idempotency",
        ),
        Index("ix_stock_adjustments_inventory", "location_id", "variant_id", "created_at"),
    )

    location_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fulfillment_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)


class InventoryReservation(BaseModel):
    """A temporary hold that moves quantity from available to reserved."""

    __tablename__ = "inventory_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "status IN ('active', 'released', 'expired', 'consumed')",
            name="status_valid",
        ),
        UniqueConstraint(
            "location_id",
            "variant_id",
            "reservation_key",
            name="uq_inventory_reservations_request",
        ),
        Index("ix_inventory_reservations_expiring", "status", "expires_at"),
    )

    location_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fulfillment_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
    )
    reservation_key: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

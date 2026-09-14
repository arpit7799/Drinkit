"""Delivery, courier, and slot persistence models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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


class DeliverySlot(BaseModel):
    """A time window for deliveries from a fulfillment location."""

    __tablename__ = "delivery_slots"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="time_window_valid"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
        UniqueConstraint(
            "fulfillment_location_id",
            "start_at",
            name="uq_delivery_slots_location_start",
        ),
        Index(
            "ix_delivery_slots_location_active_window",
            "fulfillment_location_id",
            "is_active",
            "start_at",
        ),
    )

    fulfillment_location_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fulfillment_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )


class Courier(BaseModel):
    """A delivery partner/courier."""

    __tablename__ = "couriers"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(btrim(phone)) > 0", name="phone_not_blank"),
        CheckConstraint(
            "vehicle_type IN ('bike', 'scooter', 'van', 'truck')",
            name="vehicle_type_valid",
        ),
        Index("ix_couriers_active", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    current_lat: Mapped[float | None] = mapped_column(nullable=True)
    current_lng: Mapped[float | None] = mapped_column(nullable=True)


class Delivery(BaseModel):
    """A scheduled delivery for an order."""

    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'assigned', 'picked_up', "
            "'in_transit', 'delivered', 'failed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint(
            "tracking_number IS NULL OR length(btrim(tracking_number)) > 0",
            name="tracking_number_format",
        ),
        UniqueConstraint(
            "order_id",
            name="uq_deliveries_order",
        ),
        Index("ix_deliveries_courier_status", "courier_id", "status"),
        Index("ix_deliveries_slot_status", "slot_id", "status"),
    )

    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    courier_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("couriers.id", ondelete="SET NULL"),
        nullable=True,
    )
    slot_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("delivery_slots.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'scheduled'"),
    )
    tracking_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    actual_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    courier: Mapped["Courier | None"] = relationship(lazy="selectin")
    slot: Mapped["DeliverySlot | None"] = relationship(lazy="selectin")

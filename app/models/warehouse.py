"""Dark store warehouse bins, picking tasks, and packing persistence models."""

from __future__ import annotations

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


class WarehouseBin(BaseModel):
    """Storage shelf, rack, cooler, or dispatch bay within a dark store."""

    __tablename__ = "warehouse_bins"
    __table_args__ = (
        CheckConstraint("length(btrim(bin_code)) > 0", name="bin_code_not_blank"),
        CheckConstraint(
            "zone_type IN ('ambient', 'chilled', 'cooler', 'dispatch_staging')",
            name="zone_type_valid",
        ),
        UniqueConstraint(
            "fulfillment_location_id",
            "bin_code",
            name="uq_warehouse_bins_location_code",
        ),
        Index("ix_warehouse_bins_location_zone", "fulfillment_location_id", "zone_type"),
    )

    fulfillment_location_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fulfillment_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    bin_code: Mapped[str] = mapped_column(String(64), nullable=False)
    zone_type: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'ambient'")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class OrderFulfillmentTask(BaseModel):
    """Physical picking, packing, and dispatch lifecycle task for an order in a dark store."""

    __tablename__ = "order_fulfillment_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'picking', 'picked', 'packed', "
            "'staged', 'dispatched', 'cancelled')",
            name="status_valid",
        ),
        UniqueConstraint("order_id", name="uq_order_fulfillment_tasks_order"),
        Index("ix_order_fulfillment_tasks_location_status", "fulfillment_location_id", "status"),
        Index("ix_order_fulfillment_tasks_picker", "picker_id"),
    )

    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    fulfillment_location_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fulfillment_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    picker_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    packer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    staging_bay: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bag_seal_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    packed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    staged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list[FulfillmentTaskItem]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class FulfillmentTaskItem(BaseModel):
    """Line item to be picked, verified, and packed for an order."""

    __tablename__ = "fulfillment_task_items"
    __table_args__ = (
        CheckConstraint("expected_quantity > 0", name="expected_quantity_positive"),
        CheckConstraint("picked_quantity >= 0", name="picked_quantity_non_negative"),
        UniqueConstraint("task_id", "variant_id", name="uq_fulfillment_task_items_task_variant"),
        Index("ix_fulfillment_task_items_task", "task_id"),
    )

    task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("order_fulfillment_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    picked_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    is_shortage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_damaged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    bin_location: Mapped[str | None] = mapped_column(String(64), nullable=True)

    task: Mapped[OrderFulfillmentTask] = relationship(back_populates="items")

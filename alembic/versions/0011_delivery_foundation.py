"""Create delivery, courier, and delivery slot models.

Revision ID: 0011_delivery_foundation
Revises: 0010_inv_resv_order
Create Date: 2026-09-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011_delivery_foundation"
down_revision: str | None = "0010_inv_resv_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "couriers",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("vehicle_type", sa.String(20), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("current_lat", sa.Float(), nullable=True),
        sa.Column("current_lng", sa.Float(), nullable=True),
    )

    op.create_table(
        "delivery_slots",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "fulfillment_location_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("fulfillment_locations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    op.create_table(
        "deliveries",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "courier_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("couriers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "slot_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("delivery_slots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'scheduled'"),
        ),
        sa.Column("tracking_number", sa.String(64), nullable=True),
        sa.Column("tracking_url", sa.String(256), nullable=True),
        sa.Column("estimated_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_delivery_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_deliveries_courier_status",
        "deliveries",
        ["courier_id", "status"],
    )
    op.create_index(
        "ix_deliveries_slot_status",
        "deliveries",
        ["slot_id", "status"],
    )
    op.create_index(
        "ix_couriers_active",
        "couriers",
        ["is_active"],
    )
    op.create_index(
        "ix_delivery_slots_location_active_window",
        "delivery_slots",
        ["fulfillment_location_id", "is_active", "start_at"],
    )
    op.create_index(
        "uq_delivery_slots_location_start",
        "delivery_slots",
        ["fulfillment_location_id", "start_at"],
        unique=True,
    )

    op.create_check_constraint(
        "status_valid",
        "deliveries",
        "status IN ('scheduled', 'assigned', 'picked_up', 'in_transit', 'delivered', 'failed', 'cancelled')",
    )
    op.create_check_constraint(
        "tracking_number_format",
        "deliveries",
        "tracking_number IS NULL OR length(btrim(tracking_number)) > 0",
    )
    op.create_check_constraint(
        "time_window_valid",
        "delivery_slots",
        "start_at < end_at",
    )
    op.create_check_constraint(
        "capacity_positive",
        "delivery_slots",
        "capacity > 0",
    )
    op.create_check_constraint(
        "vehicle_type_valid",
        "couriers",
        "vehicle_type IN ('bike', 'scooter', 'van', 'truck')",
    )
    op.create_check_constraint(
        "name_not_blank",
        "couriers",
        "length(btrim(name)) > 0",
    )
    op.create_check_constraint(
        "phone_not_blank",
        "couriers",
        "length(btrim(phone)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint("phone_not_blank", "couriers", type_="check")
    op.drop_constraint("name_not_blank", "couriers", type_="check")
    op.drop_constraint("vehicle_type_valid", "couriers", type_="check")
    op.drop_constraint("capacity_positive", "delivery_slots", type_="check")
    op.drop_constraint("time_window_valid", "delivery_slots", type_="check")
    op.drop_constraint("tracking_number_format", "deliveries", type_="check")
    op.drop_constraint("status_valid", "deliveries", type_="check")
    op.drop_index("uq_delivery_slots_location_start", table_name="delivery_slots")
    op.drop_index("ix_delivery_slots_location_active_window", table_name="delivery_slots")
    op.drop_index("ix_couriers_active", table_name="couriers")
    op.drop_index("ix_deliveries_slot_status", table_name="deliveries")
    op.drop_index("ix_deliveries_courier_status", table_name="deliveries")
    op.drop_table("deliveries")
    op.drop_table("delivery_slots")
    op.drop_table("couriers")
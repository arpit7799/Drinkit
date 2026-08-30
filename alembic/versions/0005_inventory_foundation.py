"""Create fulfillment locations, inventory balances, adjustments, and reservations.

Revision ID: 0005_inventory_foundation
Revises: 0004_catalog_products
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_inventory_foundation"
down_revision: str | None = "0004_catalog_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fulfillment_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("length(btrim(code)) > 0", name="code_not_blank"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        sa.PrimaryKeyConstraint("id", name="pk_fulfillment_locations"),
    )
    op.create_index(
        "uq_fulfillment_locations_code_ci",
        "fulfillment_locations",
        [sa.text("lower(code)")],
        unique=True,
    )

    op.create_table(
        "inventory_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("on_hand_quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column(
            "reserved_quantity",
            sa.Numeric(precision=12, scale=3),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.CheckConstraint("on_hand_quantity >= 0", name="on_hand_non_negative"),
        sa.CheckConstraint("reserved_quantity >= 0", name="reserved_non_negative"),
        sa.CheckConstraint("reserved_quantity <= on_hand_quantity", name="reserved_lte_on_hand"),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["fulfillment_locations.id"],
            name="fk_inventory_balances_location_id_fulfillment_locations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name="fk_inventory_balances_variant_id_product_variants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_balances"),
        sa.UniqueConstraint(
            "location_id",
            "variant_id",
            name="uq_inventory_balances_location_variant",
        ),
    )
    op.create_index(
        "ix_inventory_balances_variant_location",
        "inventory_balances",
        ["variant_id", "location_id"],
    )

    op.create_table(
        "stock_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.CheckConstraint("quantity_delta <> 0", name="quantity_delta_non_zero"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_not_blank"),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["fulfillment_locations.id"],
            name="fk_stock_adjustments_location_id_fulfillment_locations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name="fk_stock_adjustments_variant_id_product_variants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stock_adjustments"),
        sa.UniqueConstraint(
            "location_id",
            "variant_id",
            "idempotency_key",
            name="uq_stock_adjustments_idempotency",
        ),
    )
    op.create_index(
        "ix_stock_adjustments_inventory",
        "stock_adjustments",
        ["location_id", "variant_id", "created_at"],
    )

    op.create_table(
        "inventory_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_key", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint(
            "status IN ('active', 'released', 'expired', 'consumed')",
            name="status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["fulfillment_locations.id"],
            name="fk_inventory_reservations_location_id_fulfillment_locations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name="fk_inventory_reservations_variant_id_product_variants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_reservations"),
        sa.UniqueConstraint(
            "location_id",
            "variant_id",
            "reservation_key",
            name="uq_inventory_reservations_request",
        ),
    )
    op.create_index(
        "ix_inventory_reservations_expiring",
        "inventory_reservations",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_reservations_expiring", table_name="inventory_reservations")
    op.drop_table("inventory_reservations")
    op.drop_index("ix_stock_adjustments_inventory", table_name="stock_adjustments")
    op.drop_table("stock_adjustments")
    op.drop_index("ix_inventory_balances_variant_location", table_name="inventory_balances")
    op.drop_table("inventory_balances")
    op.drop_index("uq_fulfillment_locations_code_ci", table_name="fulfillment_locations")
    op.drop_table("fulfillment_locations")

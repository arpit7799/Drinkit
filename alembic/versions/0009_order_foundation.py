"""Create customer orders and immutable order lines with frozen price snapshots.

Revision ID: 0009_order_foundation
Revises: 0008_cart_foundation
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_order_foundation"
down_revision: str | None = "0008_cart_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
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
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "address_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("customer_addresses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("subtotal_minor", sa.BigInteger(), nullable=False),
        sa.Column("tax_minor", sa.BigInteger(), nullable=False),
        sa.Column("delivery_fee_minor", sa.BigInteger(), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "payment_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("payment_provider", sa.String(64), nullable=True),
        sa.Column("payment_reference", sa.String(128), nullable=True),
    )

    op.create_table(
        "order_lines",
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
        ),
        sa.Column(
            "variant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "price_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("variant_prices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("line_total_minor", sa.BigInteger(), nullable=False),
    )

    op.create_index(
        "ix_orders_user_status_created",
        "orders",
        ["user_id", "status", "created_at"],
    )
    op.create_index("ix_orders_payment_status", "orders", ["payment_status"])
    op.create_index(
        "ix_order_lines_order_variant",
        "order_lines",
        ["order_id", "variant_id"],
    )

    op.create_check_constraint(
        "subtotal_non_negative",
        "orders",
        "subtotal_minor >= 0",
    )
    op.create_check_constraint(
        "tax_non_negative",
        "orders",
        "tax_minor >= 0",
    )
    op.create_check_constraint(
        "delivery_fee_non_negative",
        "orders",
        "delivery_fee_minor >= 0",
    )
    op.create_check_constraint(
        "total_non_negative",
        "orders",
        "total_minor >= 0",
    )
    op.create_check_constraint(
        "currency_code_valid",
        "orders",
        "currency_code ~ '^[A-Z]{3}$'",
    )
    op.create_check_constraint(
        "status_valid",
        "orders",
        "status IN ('draft', 'confirmed', 'fulfilled', 'cancelled')",
    )
    op.create_check_constraint(
        "payment_status_valid",
        "orders",
        "payment_status IN ('pending', 'authorized', 'captured', 'failed', 'refunded')",
    )

    op.create_check_constraint(
        "quantity_positive",
        "order_lines",
        "quantity > 0",
    )
    op.create_check_constraint(
        "currency_code_valid",
        "order_lines",
        "currency_code ~ '^[A-Z]{3}$'",
    )
    op.create_check_constraint(
        "unit_price_non_negative",
        "order_lines",
        "unit_price_minor >= 0",
    )
    op.create_check_constraint(
        "line_total_non_negative",
        "order_lines",
        "line_total_minor >= 0",
    )

    op.create_unique_constraint(
        "uq_order_lines_order_variant",
        "order_lines",
        ["order_id", "variant_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_order_lines_order_variant", "order_lines", type_="unique")
    op.drop_constraint("line_total_non_negative", "order_lines", type_="check")
    op.drop_constraint("unit_price_non_negative", "order_lines", type_="check")
    op.drop_constraint("currency_code_valid", "order_lines", type_="check")
    op.drop_constraint("quantity_positive", "order_lines", type_="check")
    op.drop_constraint("payment_status_valid", "orders", type_="check")
    op.drop_constraint("status_valid", "orders", type_="check")
    op.drop_constraint("currency_code_valid", "orders", type_="check")
    op.drop_constraint("total_non_negative", "orders", type_="check")
    op.drop_constraint("delivery_fee_non_negative", "orders", type_="check")
    op.drop_constraint("tax_non_negative", "orders", type_="check")
    op.drop_constraint("subtotal_non_negative", "orders", type_="check")
    op.drop_index("ix_order_lines_order_variant", table_name="order_lines")
    op.drop_index("ix_orders_payment_status", table_name="orders")
    op.drop_index("ix_orders_user_status_created", table_name="orders")
    op.drop_table("order_lines")
    op.drop_table("orders")
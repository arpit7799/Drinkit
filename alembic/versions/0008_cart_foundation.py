"""Create customer shopping carts and price-snapshotted cart items.

Revision ID: 0008_cart_foundation
Revises: 0007_pricing_foundation
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_cart_foundation"
down_revision: str | None = "0007_pricing_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shopping_carts",
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
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_code_valid"),
        sa.CheckConstraint(
            "status IN ('active', 'checked_out', 'abandoned')",
            name="status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_shopping_carts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_shopping_carts"),
    )
    op.create_index(
        "uq_shopping_carts_one_active_user",
        "shopping_carts",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_shopping_carts_user_status_updated",
        "shopping_carts",
        ["user_id", "status", "updated_at"],
    )
    op.create_index("ix_shopping_carts_user_id", "shopping_carts", ["user_id"])

    op.create_table(
        "cart_items",
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
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("price_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("unit_price_minor >= 0", name="unit_price_minor_non_negative"),
        sa.CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_code_valid"),
        sa.ForeignKeyConstraint(
            ["cart_id"],
            ["shopping_carts.id"],
            name="fk_cart_items_cart_id_shopping_carts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name="fk_cart_items_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["price_id"],
            ["variant_prices.id"],
            name="fk_cart_items_price_id_variant_prices",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cart_items"),
        sa.UniqueConstraint("cart_id", "variant_id", name="uq_cart_items_cart_variant"),
    )
    op.create_index("ix_cart_items_cart_updated", "cart_items", ["cart_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_cart_items_cart_updated", table_name="cart_items")
    op.drop_table("cart_items")
    op.drop_index("ix_shopping_carts_user_id", table_name="shopping_carts")
    op.drop_index("ix_shopping_carts_user_status_updated", table_name="shopping_carts")
    op.drop_index("uq_shopping_carts_one_active_user", table_name="shopping_carts")
    op.drop_table("shopping_carts")

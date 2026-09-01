"""Create time-effective variant pricing.

Revision ID: 0007_pricing_foundation
Revises: 0006_addresses_coverage
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_pricing_foundation"
down_revision: str | None = "0006_addresses_coverage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "variant_prices",
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
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("amount_minor >= 0", name="amount_minor_non_negative"),
        sa.CheckConstraint(
            "currency_code ~ '^[A-Z]{3}$'",
            name="currency_code_valid",
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR starts_at < ends_at",
            name="effective_window_valid",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name="fk_variant_prices_variant_id_product_variants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_variant_prices"),
        sa.UniqueConstraint(
            "variant_id",
            "currency_code",
            "starts_at",
            name="uq_variant_prices_variant_currency_start",
        ),
    )
    op.create_index(
        "ix_variant_prices_variant_currency_effective",
        "variant_prices",
        ["variant_id", "currency_code", "is_active", "starts_at"],
    )
    op.create_index(
        "ix_variant_prices_active_effective",
        "variant_prices",
        ["is_active", "starts_at", "ends_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_variant_prices_active_effective", table_name="variant_prices")
    op.drop_index("ix_variant_prices_variant_currency_effective", table_name="variant_prices")
    op.drop_table("variant_prices")

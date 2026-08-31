"""Create customer addresses and fulfillment postal-code coverage.

Revision ID: 0006_addresses_coverage
Revises: 0005_inventory_foundation
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_addresses_coverage"
down_revision: str | None = "0005_inventory_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_addresses",
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
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column("recipient_name", sa.String(length=160), nullable=False),
        sa.Column("line1", sa.String(length=240), nullable=False),
        sa.Column("line2", sa.String(length=240), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=120), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("delivery_instructions", sa.String(length=500), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("length(btrim(label)) > 0", name="label_not_blank"),
        sa.CheckConstraint(
            "length(btrim(recipient_name)) > 0", name="recipient_name_not_blank"
        ),
        sa.CheckConstraint("length(btrim(line1)) > 0", name="line1_not_blank"),
        sa.CheckConstraint("length(btrim(city)) > 0", name="city_not_blank"),
        sa.CheckConstraint("length(btrim(state)) > 0", name="state_not_blank"),
        sa.CheckConstraint("length(btrim(postal_code)) > 0", name="postal_code_not_blank"),
        sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_format"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_customer_addresses_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_customer_addresses"),
    )
    op.create_index(
        "uq_customer_addresses_one_default",
        "customer_addresses",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE AND is_active IS TRUE"),
    )
    op.create_index(
        "ix_customer_addresses_user_active",
        "customer_addresses",
        ["user_id", "is_active", "updated_at"],
    )

    op.create_table(
        "fulfillment_coverages",
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
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("length(btrim(postal_code)) > 0", name="postal_code_not_blank"),
        sa.CheckConstraint("priority >= 0", name="priority_non_negative"),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["fulfillment_locations.id"],
            name="fk_fulfillment_coverages_location_id_fulfillment_locations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fulfillment_coverages"),
        sa.UniqueConstraint(
            "location_id",
            "postal_code",
            name="uq_fulfillment_coverages_location_postal",
        ),
    )
    op.create_index(
        "ix_fulfillment_coverages_postal_active",
        "fulfillment_coverages",
        ["postal_code", "is_active", "priority", "location_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fulfillment_coverages_postal_active",
        table_name="fulfillment_coverages",
    )
    op.drop_table("fulfillment_coverages")
    op.drop_index("ix_customer_addresses_user_active", table_name="customer_addresses")
    op.drop_index("uq_customer_addresses_one_default", table_name="customer_addresses")
    op.drop_table("customer_addresses")

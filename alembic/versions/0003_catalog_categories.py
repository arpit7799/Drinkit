"""Create the hierarchical catalog category foundation.

Revision ID: 0003_catalog_categories
Revises: 0002_auth_identity
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_catalog_categories"
down_revision: str | None = "0002_auth_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
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
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        sa.CheckConstraint("length(btrim(slug)) > 0", name="slug_not_blank"),
        sa.CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name="fk_categories_parent_id_categories",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
    )
    op.create_index("uq_categories_slug_ci", "categories", [sa.text("lower(slug)")], unique=True)
    op.create_index(
        "ix_categories_parent_active_sort",
        "categories",
        ["parent_id", "is_active", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_categories_parent_active_sort", table_name="categories")
    op.drop_index("uq_categories_slug_ci", table_name="categories")
    op.drop_table("categories")

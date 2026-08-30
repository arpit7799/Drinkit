"""Create catalog products, category membership, and sellable variants.

Revision ID: 0004_catalog_products
Revises: 0003_catalog_categories
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_catalog_products"
down_revision: str | None = "0003_catalog_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
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
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("is_alcoholic", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("abv_percent", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        sa.CheckConstraint("length(btrim(slug)) > 0", name="slug_not_blank"),
        sa.CheckConstraint(
            "abv_percent IS NULL OR (abv_percent >= 0 AND abv_percent <= 100)",
            name="abv_percent_valid",
        ),
        sa.CheckConstraint(
            "(is_alcoholic = false AND abv_percent IS NULL) OR "
            "(is_alcoholic = true AND abv_percent IS NOT NULL)",
            name="alcohol_attributes_consistent",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
    )
    op.create_index("uq_products_slug_ci", "products", [sa.text("lower(slug)")], unique=True)

    op.create_table(
        "product_categories",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_product_categories_category_id_categories",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_categories_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", "category_id", name="pk_product_categories"),
    )

    op.create_table(
        "product_variants",
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
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("quantity_value", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("quantity_unit", sa.String(length=30), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        sa.CheckConstraint("quantity_value > 0", name="quantity_positive"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_variants_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_variants"),
    )
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])
    op.create_index(
        "uq_product_variants_sku_ci", "product_variants", [sa.text("lower(sku)")], unique=True
    )
    op.create_index(
        "uq_product_variants_barcode_ci",
        "product_variants",
        [sa.text("lower(barcode)")],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_product_variants_barcode_ci", table_name="product_variants")
    op.drop_index("uq_product_variants_sku_ci", table_name="product_variants")
    op.drop_index("ix_product_variants_product_id", table_name="product_variants")
    op.drop_table("product_variants")
    op.drop_table("product_categories")
    op.drop_index("uq_products_slug_ci", table_name="products")
    op.drop_table("products")

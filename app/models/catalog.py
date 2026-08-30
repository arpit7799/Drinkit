"""Catalog category and sellable product persistence models."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel

product_categories = Table(
    "product_categories",
    BaseModel.metadata,
    Column(
        "product_id",
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Category(BaseModel):
    """Hierarchical catalog category used to organize sellable products."""

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(btrim(slug)) > 0", name="slug_not_blank"),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        Index("uq_categories_slug_ci", text("lower(slug)"), unique=True),
        Index("ix_categories_parent_active_sort", "parent_id", "is_active", "sort_order"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class Product(BaseModel):
    """Customer-facing catalog identity, independent from price or stock."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(btrim(slug)) > 0", name="slug_not_blank"),
        CheckConstraint(
            "abv_percent IS NULL OR (abv_percent >= 0 AND abv_percent <= 100)",
            name="abv_percent_valid",
        ),
        CheckConstraint(
            "(is_alcoholic = false AND abv_percent IS NULL) OR "
            "(is_alcoholic = true AND abv_percent IS NOT NULL)",
            name="alcohol_attributes_consistent",
        ),
        Index("uq_products_slug_ci", text("lower(slug)"), unique=True),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    is_alcoholic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    abv_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    categories: Mapped[list[Category]] = relationship(
        secondary=product_categories,
        lazy="selectin",
    )
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProductVariant(BaseModel):
    """Sellable SKU and pack-size identity; inventory and pricing are separate domains."""

    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("quantity_value > 0", name="quantity_positive"),
        Index("uq_product_variants_sku_ci", text("lower(sku)"), unique=True),
        Index(
            "uq_product_variants_barcode_ci",
            text("lower(barcode)"),
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
        ),
    )

    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity_value: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    product: Mapped[Product] = relationship(back_populates="variants")

"""Catalog read workflows."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import Category, Product, ProductVariant, product_categories


async def list_active_categories(session: AsyncSession) -> Sequence[Category]:
    """Return published categories in deterministic merchandising order."""

    result = await session.scalars(
        select(Category)
        .where(Category.is_active)
        .order_by(Category.sort_order, Category.name, Category.id)
    )
    return result.all()


async def list_active_products(
    session: AsyncSession,
    *,
    category_slug: str | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[Product], int]:
    """Return published products with at least one published sellable variant."""

    conditions = [
        Product.is_active,
        select(ProductVariant.id)
        .where(ProductVariant.product_id == Product.id, ProductVariant.is_active)
        .exists(),
    ]
    if category_slug is not None:
        conditions.append(
            select(product_categories.c.product_id)
            .join(Category, Category.id == product_categories.c.category_id)
            .where(
                product_categories.c.product_id == Product.id,
                Category.is_active,
                func.lower(Category.slug) == category_slug.strip().lower(),
            )
            .exists()
        )

    statement = (
        select(Product)
        .where(*conditions)
        .options(selectinload(Product.categories), selectinload(Product.variants))
        .order_by(Product.name, Product.id)
    )
    total_query = select(func.count()).select_from(statement.order_by(None).subquery())
    total = await session.scalar(total_query)
    result = await session.scalars(statement.offset(offset).limit(limit))
    return result.all(), int(total or 0)


async def get_active_product_by_slug(session: AsyncSession, slug: str) -> Product | None:
    """Return one published product with at least one published variant."""

    result = await session.scalar(
        select(Product)
        .where(
            func.lower(Product.slug) == slug.strip().lower(),
            Product.is_active,
            select(ProductVariant.id)
            .where(ProductVariant.product_id == Product.id, ProductVariant.is_active)
            .exists(),
        )
        .options(selectinload(Product.categories), selectinload(Product.variants))
    )
    return result

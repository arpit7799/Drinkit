"""Read-only public catalog routes."""

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.catalog import Category, Product
from app.modules.catalog.schemas import (
    CategoryResponse,
    ProductListResponse,
    ProductResponse,
    ProductVariantResponse,
)
from app.modules.catalog.service import (
    get_active_product_by_slug,
    list_active_categories,
    list_active_products,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _category_response(category: Category) -> CategoryResponse:
    return CategoryResponse.model_validate(category)


def _product_response(product: Product) -> ProductResponse:
    categories = [category for category in product.categories if category.is_active]
    variants = [variant for variant in product.variants if variant.is_active]
    return ProductResponse(
        id=product.id,
        name=product.name,
        slug=product.slug,
        brand=product.brand,
        description=product.description,
        is_alcoholic=product.is_alcoholic,
        abv_percent=product.abv_percent,
        is_active=product.is_active,
        categories=[_category_response(category) for category in categories],
        variants=[ProductVariantResponse.model_validate(variant) for variant in variants],
    )


@router.get("/categories", response_model=list[CategoryResponse])
async def categories(session: AsyncSession = Depends(get_db)) -> Sequence[CategoryResponse]:
    """List published catalog categories."""

    return [_category_response(category) for category in await list_active_categories(session)]


@router.get("/products", response_model=ProductListResponse)
async def products(
    category_slug: str | None = Query(default=None, min_length=1, max_length=140),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> ProductListResponse:
    """List published products with active sellable variants."""

    results, total = await list_active_products(
        session,
        category_slug=category_slug,
        limit=limit,
        offset=offset,
    )
    return ProductListResponse(
        items=[_product_response(product) for product in results],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products/{slug}", response_model=ProductResponse)
async def product_detail(
    slug: str,
    session: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """Return one published product by its stable slug."""

    product = await get_active_product_by_slug(session, slug)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return _product_response(product)

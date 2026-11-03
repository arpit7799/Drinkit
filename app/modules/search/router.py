"""Search and discovery API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.search.schemas import (
    AutocompleteResponse,
    FacetResponse,
    RecommendationResponse,
    SearchResponse,
    SearchSortOrder,
)
from app.modules.search.service import (
    autocomplete_suggestions,
    get_product_recommendations,
    get_search_facets,
    search_products,
)

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str | None = Query(default=None, description="Free-text search keyword"),
    category: str | None = Query(default=None, description="Filter by category slug"),
    brand: str | None = Query(default=None, description="Filter by brand"),
    min_price: int | None = Query(default=None, ge=0, description="Minimum price in minor units"),
    max_price: int | None = Query(default=None, ge=0, description="Maximum price in minor units"),
    is_alcoholic: bool | None = Query(default=None, description="Filter alcoholic products"),
    in_stock: bool | None = Query(default=None, description="Filter in-stock products"),
    location_id: UUID | None = Query(default=None, description="Fulfillment dark store ID"),
    sort_by: SearchSortOrder = Query(default=SearchSortOrder.RELEVANCE, description="Sort order"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Search products with multi-faceted filtering, pricing, and stock status."""

    return await search_products(
        session,
        query=q,
        category_slug=category,
        brand=brand,
        min_price_minor=min_price,
        max_price_minor=max_price,
        is_alcoholic=is_alcoholic,
        in_stock=in_stock,
        location_id=location_id,
        sort_by=sort_by.value,
        limit=limit,
        offset=offset,
    )


@router.get("/autocomplete", response_model=AutocompleteResponse)
async def autocomplete(
    q: str = Query(..., min_length=1, max_length=100, description="Search prefix"),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> AutocompleteResponse:
    """Instant search suggestions for typeahead search bars."""

    return await autocomplete_suggestions(session, prefix=q, limit=limit)


@router.get("/facets", response_model=FacetResponse)
async def facets(
    category: str | None = Query(default=None, description="Filter facets by category slug"),
    is_alcoholic: bool | None = Query(default=None, description="Filter facets by alcohol flag"),
    session: AsyncSession = Depends(get_db),
) -> FacetResponse:
    """Retrieve catalog-wide or category-filtered facet breakdowns."""

    return await get_search_facets(session, category_slug=category, is_alcoholic=is_alcoholic)


@router.get("/recommendations", response_model=RecommendationResponse)
async def recommendations(
    product_id: UUID = Query(..., description="Reference product ID"),
    location_id: UUID | None = Query(default=None, description="Optional fulfillment location ID"),
    limit: int = Query(default=6, ge=1, le=20),
    session: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    """Get smart beverage pairings and cross-sell recommendations."""

    return await get_product_recommendations(
        session,
        product_id=product_id,
        location_id=location_id,
        limit=limit,
    )

"""Search, discovery, and recommendation schemas."""

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SearchSortOrder(StrEnum):
    """Supported sort orders for catalog search and discovery."""

    RELEVANCE = "relevance"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    NAME_ASC = "name_asc"


class SuggestionType(StrEnum):
    """Types of autocomplete suggestions."""

    PRODUCT = "product"
    BRAND = "brand"
    CATEGORY = "category"


class SearchCategoryRef(BaseModel):
    """Category reference in search results."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str


class SearchVariantItem(BaseModel):
    """Variant detail embedded in search results."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    quantity_value: Decimal
    quantity_unit: str
    price_minor: int | None = None
    currency_code: str = "INR"
    in_stock: bool = False
    available_quantity: Decimal = Decimal(0)


class SearchResultItem(BaseModel):
    """Product summary returned in search and recommendation lists."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    brand: str | None = None
    description: str | None = None
    is_alcoholic: bool = False
    abv_percent: Decimal | None = None
    starting_price_minor: int | None = None
    currency_code: str = "INR"
    in_stock: bool = False
    categories: list[SearchCategoryRef] = Field(default_factory=list)
    variants: list[SearchVariantItem] = Field(default_factory=list)


class FacetCategoryItem(BaseModel):
    """Category facet entry with item count."""

    name: str
    slug: str
    count: int


class FacetBrandItem(BaseModel):
    """Brand facet entry with item count."""

    brand: str
    count: int


class FacetResponse(BaseModel):
    """Aggregated facet metrics for search results."""

    categories: list[FacetCategoryItem] = Field(default_factory=list)
    brands: list[FacetBrandItem] = Field(default_factory=list)
    min_price_minor: int | None = None
    max_price_minor: int | None = None


class SearchResponse(BaseModel):
    """Paginated search response with facet metadata."""

    items: list[SearchResultItem]
    total: int
    facets: FacetResponse
    limit: int
    offset: int


class AutocompleteSuggestion(BaseModel):
    """Instant search suggestion item."""

    title: str
    type: SuggestionType
    slug: str | None = None
    brand: str | None = None
    category_slug: str | None = None


class AutocompleteResponse(BaseModel):
    """Response containing autocomplete suggestions."""

    query: str
    suggestions: list[AutocompleteSuggestion] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    """Smart beverage pairings and cross-sell recommendations."""

    product_id: UUID
    headline: str
    items: list[SearchResultItem] = Field(default_factory=list)

"""Unit tests for search and discovery schemas."""

from decimal import Decimal
from uuid import uuid4

from app.modules.search.schemas import (
    AutocompleteResponse,
    AutocompleteSuggestion,
    FacetBrandItem,
    FacetCategoryItem,
    FacetResponse,
    RecommendationResponse,
    SearchCategoryRef,
    SearchResponse,
    SearchResultItem,
    SearchSortOrder,
    SearchVariantItem,
    SuggestionType,
)


def test_search_sort_order_enums() -> None:
    assert SearchSortOrder.RELEVANCE == "relevance"
    assert SearchSortOrder.PRICE_ASC == "price_asc"
    assert SearchSortOrder.PRICE_DESC == "price_desc"
    assert SearchSortOrder.NAME_ASC == "name_asc"


def test_suggestion_type_enums() -> None:
    assert SuggestionType.PRODUCT == "product"
    assert SuggestionType.BRAND == "brand"
    assert SuggestionType.CATEGORY == "category"


def test_search_variant_and_result_item() -> None:
    var_id = uuid4()
    variant = SearchVariantItem(
        id=var_id,
        sku="BIRA-WHITE-330",
        name="Bira 91 White 330ml Can",
        quantity_value=Decimal("330"),
        quantity_unit="ml",
        price_minor=18000,
        currency_code="INR",
        in_stock=True,
        available_quantity=Decimal("24"),
    )
    assert variant.id == var_id
    assert variant.price_minor == 18000
    assert variant.in_stock is True

    cat_id = uuid4()
    category = SearchCategoryRef(id=cat_id, name="Beer", slug="beer")

    prod_id = uuid4()
    item = SearchResultItem(
        id=prod_id,
        name="Bira 91 White",
        slug="bira-91-white",
        brand="Bira 91",
        description="Refreshing wheat beer",
        is_alcoholic=True,
        abv_percent=Decimal("4.9"),
        starting_price_minor=18000,
        currency_code="INR",
        in_stock=True,
        categories=[category],
        variants=[variant],
    )
    assert item.name == "Bira 91 White"
    assert item.starting_price_minor == 18000
    assert len(item.variants) == 1
    assert item.categories[0].slug == "beer"


def test_facet_response_schema() -> None:
    facets = FacetResponse(
        categories=[FacetCategoryItem(name="Beer", slug="beer", count=5)],
        brands=[FacetBrandItem(brand="Bira 91", count=3)],
        min_price_minor=12000,
        max_price_minor=45000,
    )
    assert len(facets.categories) == 1
    assert facets.categories[0].count == 5
    assert facets.brands[0].brand == "Bira 91"
    assert facets.min_price_minor == 12000
    assert facets.max_price_minor == 45000


def test_search_response_schema() -> None:
    prod_id = uuid4()
    item = SearchResultItem(
        id=prod_id,
        name="Schweppes Tonic Water",
        slug="schweppes-tonic-water",
        brand="Schweppes",
        is_alcoholic=False,
        starting_price_minor=6000,
        currency_code="INR",
        in_stock=True,
    )
    response = SearchResponse(
        items=[item],
        total=1,
        facets=FacetResponse(),
        limit=20,
        offset=0,
    )
    assert response.total == 1
    assert response.items[0].brand == "Schweppes"
    assert response.limit == 20


def test_autocomplete_and_recommendation_schemas() -> None:
    auto = AutocompleteResponse(
        query="bir",
        suggestions=[
            AutocompleteSuggestion(
                title="Bira 91",
                type=SuggestionType.BRAND,
                brand="Bira 91",
            ),
            AutocompleteSuggestion(
                title="Bira 91 Blonde",
                type=SuggestionType.PRODUCT,
                slug="bira-91-blonde",
            ),
        ],
    )
    assert auto.query == "bir"
    assert len(auto.suggestions) == 2
    assert auto.suggestions[0].type == SuggestionType.BRAND

    rec_id = uuid4()
    rec = RecommendationResponse(
        product_id=rec_id,
        headline="Pairs Well With",
        items=[],
    )
    assert rec.product_id == rec_id
    assert rec.headline == "Pairs Well With"
    assert rec.items == []

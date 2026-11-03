"""Integration tests for search, discovery, and recommendation service."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Category, Product, ProductVariant, product_categories
from app.models.inventory import FulfillmentLocation, InventoryBalance
from app.models.orders import Order, OrderLine
from app.models.pricing import VariantPrice
from app.modules.search.schemas import SearchSortOrder, SuggestionType
from app.modules.search.service import (
    autocomplete_suggestions,
    get_product_recommendations,
    get_search_facets,
    search_products,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def search_db_session(
    integration_engine: AsyncEngine,
) -> AsyncIterator[AsyncSession]:
    """Yield clean test session with populated test catalog and teardown."""

    async with AsyncSessionFactory(bind=integration_engine) as session:
        # Pre-clean
        await session.execute(delete(OrderLine))
        await session.execute(delete(Order))
        await session.execute(delete(CartItem))
        await session.execute(delete(ShoppingCart))
        await session.execute(delete(InventoryBalance))
        await session.execute(delete(VariantPrice))
        await session.execute(delete(FulfillmentLocation))
        await session.execute(delete(product_categories))
        await session.execute(delete(ProductVariant))
        await session.execute(delete(Product))
        await session.execute(delete(Category))
        await session.commit()

        # Seed categories
        beer_cat = Category(name="Beer", slug="beer", sort_order=1)
        spirits_cat = Category(name="Spirits", slug="spirits", sort_order=2)
        mixers_cat = Category(name="Mixers", slug="mixers", sort_order=3)
        snacks_cat = Category(name="Snacks", slug="snacks", sort_order=4)
        session.add_all([beer_cat, spirits_cat, mixers_cat, snacks_cat])
        await session.flush()

        # Seed dark store location
        location = FulfillmentLocation(
            id=uuid4(),
            code="BLR-KOR-01",
            name="Koramangala Dark Store",
            is_active=True,
        )
        session.add(location)
        await session.flush()

        # Seed Product 1: Bira 91 White Beer (Alcoholic, in stock)
        bira_white = Product(
            name="Bira 91 White Beer",
            slug="bira-91-white-beer",
            brand="Bira 91",
            description="Crisp wheat beer with citrus notes",
            is_alcoholic=True,
            abv_percent=Decimal("4.9"),
        )
        bira_white.categories.append(beer_cat)
        session.add(bira_white)
        await session.flush()

        bira_var = ProductVariant(
            product_id=bira_white.id,
            sku="BIRA-WHITE-330",
            name="330ml Can",
            quantity_value=Decimal("330"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(bira_var)
        await session.flush()

        # Seed price and stock for Bira
        bira_price = VariantPrice(
            variant_id=bira_var.id,
            currency_code="INR",
            amount_minor=18000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        bira_inv = InventoryBalance(
            location_id=location.id,
            variant_id=bira_var.id,
            on_hand_quantity=Decimal("50"),
            reserved_quantity=Decimal("0"),
        )
        session.add_all([bira_price, bira_inv])

        # Seed Product 2: Bira 91 Blonde Beer (Alcoholic, lower price, out of stock)
        bira_blonde = Product(
            name="Bira 91 Blonde Beer",
            slug="bira-91-blonde-beer",
            brand="Bira 91",
            description="Refreshing extra punchy lager",
            is_alcoholic=True,
            abv_percent=Decimal("4.5"),
        )
        bira_blonde.categories.append(beer_cat)
        session.add(bira_blonde)
        await session.flush()

        bira_blonde_var = ProductVariant(
            product_id=bira_blonde.id,
            sku="BIRA-BLONDE-330",
            name="330ml Can",
            quantity_value=Decimal("330"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(bira_blonde_var)
        await session.flush()

        bira_blonde_price = VariantPrice(
            variant_id=bira_blonde_var.id,
            currency_code="INR",
            amount_minor=15000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        session.add(bira_blonde_price)

        # Seed Product 3: Tanqueray London Dry Gin (Alcoholic, expensive)
        tanqueray = Product(
            name="Tanqueray London Dry Gin",
            slug="tanqueray-london-dry-gin",
            brand="Tanqueray",
            description="Classic botanical gin with juniper and angelica",
            is_alcoholic=True,
            abv_percent=Decimal("43.1"),
        )
        tanqueray.categories.append(spirits_cat)
        session.add(tanqueray)
        await session.flush()

        tanqueray_var = ProductVariant(
            product_id=tanqueray.id,
            sku="TANQ-GIN-750",
            name="750ml Bottle",
            quantity_value=Decimal("750"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(tanqueray_var)
        await session.flush()

        tanqueray_price = VariantPrice(
            variant_id=tanqueray_var.id,
            currency_code="INR",
            amount_minor=280000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        tanqueray_inv = InventoryBalance(
            location_id=location.id,
            variant_id=tanqueray_var.id,
            on_hand_quantity=Decimal("15"),
            reserved_quantity=Decimal("0"),
        )
        session.add_all([tanqueray_price, tanqueray_inv])

        # Seed Product 4: Schweppes Tonic Water (Non-alcoholic mixer, in stock)
        schweppes = Product(
            name="Schweppes Tonic Water",
            slug="schweppes-tonic-water",
            brand="Schweppes",
            description="Sparkling tonic mixer with quinine",
            is_alcoholic=False,
            abv_percent=None,
        )
        schweppes.categories.append(mixers_cat)
        session.add(schweppes)
        await session.flush()

        schweppes_var = ProductVariant(
            product_id=schweppes.id,
            sku="SCHW-TONIC-300",
            name="300ml Can",
            quantity_value=Decimal("300"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(schweppes_var)
        await session.flush()

        schweppes_price = VariantPrice(
            variant_id=schweppes_var.id,
            currency_code="INR",
            amount_minor=6000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        schweppes_inv = InventoryBalance(
            location_id=location.id,
            variant_id=schweppes_var.id,
            on_hand_quantity=Decimal("100"),
            reserved_quantity=Decimal("0"),
        )
        session.add_all([schweppes_price, schweppes_inv])

        # Seed Product 5: Lays Classic Salted Potato Chips (Snack)
        lays = Product(
            name="Lays Classic Salted Chips",
            slug="lays-classic-salted-chips",
            brand="Lays",
            description="Crispy potato chips party snack",
            is_alcoholic=False,
            abv_percent=None,
        )
        lays.categories.append(snacks_cat)
        session.add(lays)
        await session.flush()

        lays_var = ProductVariant(
            product_id=lays.id,
            sku="LAYS-SALT-50",
            name="50g Pouch",
            quantity_value=Decimal("50"),
            quantity_unit="g",
            is_active=True,
        )
        session.add(lays_var)
        await session.flush()

        lays_price = VariantPrice(
            variant_id=lays_var.id,
            currency_code="INR",
            amount_minor=2000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        session.add(lays_price)

        await session.commit()

        yield session

        # Teardown
        await session.execute(delete(InventoryBalance))
        await session.execute(delete(VariantPrice))
        await session.execute(delete(FulfillmentLocation))
        await session.execute(delete(product_categories))
        await session.execute(delete(ProductVariant))
        await session.execute(delete(Product))
        await session.execute(delete(Category))
        await session.commit()


async def test_search_free_text_matches(search_db_session: AsyncSession) -> None:
    # 1. Search for "Bira" matches both Bira beers
    res = await search_products(search_db_session, query="Bira")
    assert res.total == 2
    assert all("Bira" in item.name for item in res.items)

    # 2. Search for "Tonic" matches Schweppes Tonic Water
    res_tonic = await search_products(search_db_session, query="Tonic")
    assert res_tonic.total == 1
    assert res_tonic.items[0].slug == "schweppes-tonic-water"

    # 3. Search for "juniper" in description matches Tanqueray Gin
    res_gin = await search_products(search_db_session, query="juniper")
    assert res_gin.total == 1
    assert res_gin.items[0].brand == "Tanqueray"


async def test_search_category_and_brand_filters(search_db_session: AsyncSession) -> None:
    # Category filter
    res = await search_products(search_db_session, category_slug="beer")
    assert res.total == 2
    assert all("Beer" in [c.name for c in item.categories] for item in res.items)

    # Brand filter
    res_brand = await search_products(search_db_session, brand="Schweppes")
    assert res_brand.total == 1
    assert res_brand.items[0].brand == "Schweppes"


async def test_search_alcohol_and_stock_filters(search_db_session: AsyncSession) -> None:
    # Non-alcoholic only
    res_na = await search_products(search_db_session, is_alcoholic=False)
    assert res_na.total == 2
    assert all(item.is_alcoholic is False for item in res_na.items)

    # In-stock only
    res_stock = await search_products(search_db_session, in_stock=True)
    # Bira White, Tanqueray, Schweppes are in stock; Bira Blonde & Lays are out of stock
    assert res_stock.total == 3
    assert all(item.in_stock is True for item in res_stock.items)


async def test_search_price_filtering_and_sorting(search_db_session: AsyncSession) -> None:
    # Price filtering
    res_price = await search_products(
        search_db_session,
        min_price_minor=10000,
        max_price_minor=20000,
    )
    # Bira Blonde (15000) and Bira White (18000)
    assert res_price.total == 2
    for item in res_price.items:
        assert 10000 <= item.starting_price_minor <= 20000

    # Sort price ascending
    res_asc = await search_products(search_db_session, sort_by=SearchSortOrder.PRICE_ASC)
    prices = [item.starting_price_minor for item in res_asc.items if item.starting_price_minor]
    assert prices == sorted(prices)
    assert prices[0] == 2000  # Lays chips

    # Sort price descending
    res_desc = await search_products(search_db_session, sort_by=SearchSortOrder.PRICE_DESC)
    prices_desc = [
        item.starting_price_minor for item in res_desc.items if item.starting_price_minor
    ]
    assert prices_desc == sorted(prices_desc, reverse=True)
    assert prices_desc[0] == 280000  # Tanqueray gin


async def test_search_facets_computation(search_db_session: AsyncSession) -> None:
    facets = await get_search_facets(search_db_session)
    assert len(facets.categories) >= 4
    cat_names = [c.name for c in facets.categories]
    assert "Beer" in cat_names
    assert "Spirits" in cat_names
    assert "Mixers" in cat_names

    brand_names = [b.brand for b in facets.brands]
    assert "Bira 91" in brand_names
    assert "Schweppes" in brand_names

    assert facets.min_price_minor == 2000
    assert facets.max_price_minor == 280000


async def test_autocomplete_service(search_db_session: AsyncSession) -> None:
    # Autocomplete for "bir" should find brand "Bira 91" and products
    res = await autocomplete_suggestions(search_db_session, prefix="bir", limit=5)
    assert res.query == "bir"
    assert len(res.suggestions) >= 2
    types = [s.type for s in res.suggestions]
    assert SuggestionType.BRAND in types or SuggestionType.PRODUCT in types

    # Autocomplete for category "bee"
    res_cat = await autocomplete_suggestions(search_db_session, prefix="bee", limit=5)
    cat_suggestions = [s for s in res_cat.suggestions if s.type == SuggestionType.CATEGORY]
    assert len(cat_suggestions) >= 1
    assert cat_suggestions[0].title == "Beer"


async def test_recommendations_smart_pairing(search_db_session: AsyncSession) -> None:
    # Tanqueray Gin should recommend Schweppes Tonic Water ("gin" -> "tonic")
    res_gin = await search_products(search_db_session, query="Tanqueray")
    gin_product = res_gin.items[0]

    rec = await get_product_recommendations(search_db_session, product_id=gin_product.id, limit=3)
    assert rec.product_id == gin_product.id
    assert rec.headline == "Pairs Well With"
    rec_names = [item.name for item in rec.items]
    assert any("Tonic" in name for name in rec_names)

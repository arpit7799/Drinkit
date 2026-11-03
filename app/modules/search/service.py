"""Product search, faceted discovery, autocomplete, and recommendation service."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import Category, Product, ProductVariant, product_categories
from app.models.inventory import InventoryBalance
from app.models.pricing import VariantPrice
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

PAIRING_RULES: dict[str, list[str]] = {
    "beer": ["snacks", "chips", "peanuts", "namkeen", "chakhna"],
    "gin": ["tonic", "tonic-water", "mixers", "soft-drinks", "ice"],
    "vodka": ["energy-drinks", "juices", "mixers", "soda", "ice"],
    "whiskey": ["soda", "water", "ice", "snacks", "glasses"],
    "whisky": ["soda", "water", "ice", "snacks", "glasses"],
    "rum": ["cola", "soft-drinks", "ice", "mixers"],
    "tequila": ["salt", "mixers", "tonic", "juices", "ice"],
    "wine": ["cheese", "crackers", "snacks", "nuts"],
}


async def enrich_products_with_pricing_and_inventory(
    session: AsyncSession,
    products: Sequence[Product],
    *,
    currency_code: str = "INR",
    location_id: UUID | None = None,
    now: datetime | None = None,
) -> list[SearchResultItem]:
    """Enrich a sequence of products with time-effective pricing and live inventory."""

    if not products:
        return []

    effective_now = now or datetime.now(UTC)
    normalized_currency = currency_code.strip().upper()

    # Collect all active variant IDs across all products
    variant_ids: list[UUID] = []
    variant_product_map: dict[UUID, UUID] = {}
    for product in products:
        for variant in product.variants:
            if variant.is_active:
                variant_ids.append(variant.id)
                variant_product_map[variant.id] = product.id

    prices_by_variant: dict[UUID, VariantPrice] = {}
    if variant_ids:
        price_stmt = (
            select(VariantPrice)
            .where(
                VariantPrice.variant_id.in_(variant_ids),
                VariantPrice.currency_code == normalized_currency,
                VariantPrice.is_active.is_(True),
                VariantPrice.starts_at <= effective_now,
                (VariantPrice.ends_at.is_(None) | (VariantPrice.ends_at > effective_now)),
            )
            .order_by(VariantPrice.variant_id, VariantPrice.starts_at.desc(), VariantPrice.id)
        )
        price_rows = (await session.scalars(price_stmt)).all()
        for p in price_rows:
            if p.variant_id not in prices_by_variant:
                prices_by_variant[p.variant_id] = p

    inventory_by_variant: dict[UUID, Decimal] = defaultdict(Decimal)
    if variant_ids:
        inv_stmt = select(InventoryBalance).where(InventoryBalance.variant_id.in_(variant_ids))
        if location_id is not None:
            inv_stmt = inv_stmt.where(InventoryBalance.location_id == location_id)

        inv_rows = (await session.scalars(inv_stmt)).all()
        for inv in inv_rows:
            available = inv.on_hand_quantity - inv.reserved_quantity
            if available > Decimal(0):
                inventory_by_variant[inv.variant_id] += available

    results: list[SearchResultItem] = []
    for product in products:
        active_categories = [
            SearchCategoryRef(id=c.id, name=c.name, slug=c.slug)
            for c in product.categories
            if c.is_active
        ]

        active_variants: list[SearchVariantItem] = []
        variant_prices: list[int] = []
        has_stock = False

        for variant in product.variants:
            if not variant.is_active:
                continue

            v_price = prices_by_variant.get(variant.id)
            price_minor = v_price.amount_minor if v_price is not None else None
            if price_minor is not None:
                variant_prices.append(price_minor)

            available_qty = inventory_by_variant.get(variant.id, Decimal(0))
            is_in_stock = available_qty > Decimal(0)
            if is_in_stock:
                has_stock = True

            active_variants.append(
                SearchVariantItem(
                    id=variant.id,
                    sku=variant.sku,
                    name=variant.name,
                    quantity_value=variant.quantity_value,
                    quantity_unit=variant.quantity_unit,
                    price_minor=price_minor,
                    currency_code=normalized_currency,
                    in_stock=is_in_stock,
                    available_quantity=available_qty,
                )
            )

        starting_price = min(variant_prices) if variant_prices else None

        results.append(
            SearchResultItem(
                id=product.id,
                name=product.name,
                slug=product.slug,
                brand=product.brand,
                description=product.description,
                is_alcoholic=product.is_alcoholic,
                abv_percent=product.abv_percent,
                starting_price_minor=starting_price,
                currency_code=normalized_currency,
                in_stock=has_stock,
                categories=active_categories,
                variants=active_variants,
            )
        )

    return results


async def search_products(
    session: AsyncSession,
    *,
    query: str | None = None,
    category_slug: str | None = None,
    brand: str | None = None,
    min_price_minor: int | None = None,
    max_price_minor: int | None = None,
    is_alcoholic: bool | None = None,
    in_stock: bool | None = None,
    location_id: UUID | None = None,
    sort_by: str = SearchSortOrder.RELEVANCE,
    currency_code: str = "INR",
    limit: int = 20,
    offset: int = 0,
) -> SearchResponse:
    """Execute quick-commerce product search with faceted filtering and ranking."""

    # 1. Base query for active products having at least one active variant
    stmt = (
        select(Product)
        .where(
            Product.is_active.is_(True),
            select(ProductVariant.id)
            .where(
                ProductVariant.product_id == Product.id,
                ProductVariant.is_active.is_(True),
            )
            .exists(),
        )
        .options(
            selectinload(Product.categories),
            selectinload(Product.variants),
        )
    )

    # 2. Filter category slug
    if category_slug is not None and category_slug.strip():
        norm_cat = category_slug.strip().lower()
        stmt = stmt.where(
            select(product_categories.c.product_id)
            .join(Category, Category.id == product_categories.c.category_id)
            .where(
                product_categories.c.product_id == Product.id,
                Category.is_active.is_(True),
                func.lower(Category.slug) == norm_cat,
            )
            .exists()
        )

    # 3. Filter brand
    if brand is not None and brand.strip():
        norm_brand = brand.strip().lower()
        stmt = stmt.where(func.lower(Product.brand) == norm_brand)

    # 4. Filter is_alcoholic
    if is_alcoholic is not None:
        stmt = stmt.where(Product.is_alcoholic.is_(is_alcoholic))

    # 5. Free-text search matching across name, brand, description, and categories
    clean_query = query.strip() if query else ""
    if clean_query:
        tokens = [t.lower() for t in clean_query.split() if t.strip()]
        token_clauses = []
        for t in tokens:
            pattern = f"%{t}%"
            token_clauses.append(
                or_(
                    Product.name.ilike(pattern),
                    Product.brand.ilike(pattern),
                    Product.description.ilike(pattern),
                    select(product_categories.c.product_id)
                    .join(Category, Category.id == product_categories.c.category_id)
                    .where(
                        product_categories.c.product_id == Product.id,
                        Category.is_active.is_(True),
                        Category.name.ilike(pattern),
                    )
                    .exists(),
                )
            )
        stmt = stmt.where(*token_clauses)

    # Fetch candidate products matching the database-level filters
    candidate_products = (await session.scalars(stmt)).all()

    # Enrich candidates with live prices & inventory
    enriched = await enrich_products_with_pricing_and_inventory(
        session,
        candidate_products,
        currency_code=currency_code,
        location_id=location_id,
    )

    # Compute unconstrained facets from all candidates before post-pricing/in_stock filters
    brand_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[tuple[str, str], int] = defaultdict(int)
    valid_prices: list[int] = []

    for item in enriched:
        if item.brand:
            brand_counts[item.brand] += 1
        for cat in item.categories:
            category_counts[(cat.name, cat.slug)] += 1
        if item.starting_price_minor is not None:
            valid_prices.append(item.starting_price_minor)

    facet_brands = [
        FacetBrandItem(brand=b, count=c)
        for b, c in sorted(brand_counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    facet_categories = [
        FacetCategoryItem(name=k[0], slug=k[1], count=c)
        for k, c in sorted(category_counts.items(), key=lambda x: (-x[1], x[0][0]))
    ]
    min_price_found = min(valid_prices) if valid_prices else None
    max_price_found = max(valid_prices) if valid_prices else None

    facets = FacetResponse(
        categories=facet_categories,
        brands=facet_brands,
        min_price_minor=min_price_found,
        max_price_minor=max_price_found,
    )

    # Apply pricing and in_stock post-filters
    filtered = enriched
    if min_price_minor is not None:
        filtered = [
            i
            for i in filtered
            if i.starting_price_minor is not None and i.starting_price_minor >= min_price_minor
        ]
    if max_price_minor is not None:
        filtered = [
            i
            for i in filtered
            if i.starting_price_minor is not None and i.starting_price_minor <= max_price_minor
        ]
    if in_stock is not None:
        filtered = [i for i in filtered if i.in_stock == in_stock]

    # Quick-commerce sorting logic
    q_lower = clean_query.lower()

    def relevance_key(item: SearchResultItem) -> tuple[int, int, str]:
        # Priority 1: Exact name match
        score = 0
        name_lower = item.name.lower()
        brand_lower = (item.brand or "").lower()

        if q_lower and name_lower == q_lower:
            score += 1000
        elif q_lower and name_lower.startswith(q_lower):
            score += 500
        elif q_lower and q_lower in name_lower:
            score += 200

        if q_lower and brand_lower == q_lower:
            score += 300
        elif q_lower and brand_lower.startswith(q_lower):
            score += 150

        # Stock bonus in quick-commerce
        if item.in_stock:
            score += 50

        return (-score, item.starting_price_minor or 999999999, item.name)

    if sort_by == SearchSortOrder.PRICE_ASC:
        filtered.sort(
            key=lambda x: (x.starting_price_minor is None, x.starting_price_minor, x.name)
        )
    elif sort_by == SearchSortOrder.PRICE_DESC:
        filtered.sort(
            key=lambda x: (
                x.starting_price_minor is None,
                -(x.starting_price_minor or 0),
                x.name,
            )
        )
    elif sort_by == SearchSortOrder.NAME_ASC:
        filtered.sort(key=lambda x: x.name)
    else:  # RELEVANCE (default)
        filtered.sort(key=relevance_key)

    total = len(filtered)
    paginated_items = filtered[offset : offset + limit]

    return SearchResponse(
        items=paginated_items,
        total=total,
        facets=facets,
        limit=limit,
        offset=offset,
    )


async def autocomplete_suggestions(
    session: AsyncSession,
    *,
    prefix: str,
    limit: int = 10,
) -> AutocompleteResponse:
    """Generate instant search suggestions for products, brands, and categories."""

    clean_prefix = prefix.strip()
    if not clean_prefix:
        return AutocompleteResponse(query=clean_prefix, suggestions=[])

    suggestions: list[AutocompleteSuggestion] = []
    seen_titles: set[str] = set()
    pattern = f"{clean_prefix}%"
    wildcard_pattern = f"%{clean_prefix}%"

    # 1. Matching categories
    cat_stmt = (
        select(Category)
        .where(
            Category.is_active.is_(True),
            or_(Category.name.ilike(pattern), Category.name.ilike(wildcard_pattern)),
        )
        .order_by(Category.name)
        .limit(limit)
    )
    categories = (await session.scalars(cat_stmt)).all()
    for cat in categories:
        if cat.name.lower() not in seen_titles:
            seen_titles.add(cat.name.lower())
            suggestions.append(
                AutocompleteSuggestion(
                    title=cat.name,
                    type=SuggestionType.CATEGORY,
                    slug=cat.slug,
                    category_slug=cat.slug,
                )
            )
            if len(suggestions) >= limit:
                return AutocompleteResponse(query=clean_prefix, suggestions=suggestions)

    # 2. Matching brands
    brand_stmt = (
        select(Product.brand)
        .where(
            Product.is_active.is_(True),
            Product.brand.is_not(None),
            or_(Product.brand.ilike(pattern), Product.brand.ilike(wildcard_pattern)),
        )
        .distinct()
        .order_by(Product.brand)
        .limit(limit)
    )
    brands = (await session.scalars(brand_stmt)).all()
    for brand in brands:
        if brand and brand.lower() not in seen_titles:
            seen_titles.add(brand.lower())
            suggestions.append(
                AutocompleteSuggestion(
                    title=brand,
                    type=SuggestionType.BRAND,
                    brand=brand,
                )
            )
            if len(suggestions) >= limit:
                return AutocompleteResponse(query=clean_prefix, suggestions=suggestions)

    # 3. Matching products
    prod_stmt = (
        select(Product)
        .where(
            Product.is_active.is_(True),
            or_(Product.name.ilike(pattern), Product.name.ilike(wildcard_pattern)),
            select(ProductVariant.id)
            .where(
                ProductVariant.product_id == Product.id,
                ProductVariant.is_active.is_(True),
            )
            .exists(),
        )
        .options(selectinload(Product.categories))
        .order_by(Product.name)
        .limit(limit)
    )
    products = (await session.scalars(prod_stmt)).all()
    for prod in products:
        if prod.name.lower() not in seen_titles:
            seen_titles.add(prod.name.lower())
            first_cat_slug = prod.categories[0].slug if prod.categories else None
            suggestions.append(
                AutocompleteSuggestion(
                    title=prod.name,
                    type=SuggestionType.PRODUCT,
                    slug=prod.slug,
                    brand=prod.brand,
                    category_slug=first_cat_slug,
                )
            )
            if len(suggestions) >= limit:
                break

    return AutocompleteResponse(query=clean_prefix, suggestions=suggestions)


async def get_search_facets(
    session: AsyncSession,
    *,
    category_slug: str | None = None,
    is_alcoholic: bool | None = None,
    currency_code: str = "INR",
) -> FacetResponse:
    """Retrieve catalog-wide or category-filtered facet breakdowns."""

    search_res = await search_products(
        session,
        category_slug=category_slug,
        is_alcoholic=is_alcoholic,
        currency_code=currency_code,
        limit=1000,
    )
    return search_res.facets


async def get_product_recommendations(
    session: AsyncSession,
    *,
    product_id: UUID,
    location_id: UUID | None = None,
    limit: int = 6,
) -> RecommendationResponse:
    """Recommend smart beverage pairings and cross-sell companions for quick commerce."""

    # Fetch reference product
    target_prod = await session.scalar(
        select(Product)
        .where(Product.id == product_id, Product.is_active.is_(True))
        .options(selectinload(Product.categories), selectinload(Product.variants))
    )
    if target_prod is None:
        return RecommendationResponse(
            product_id=product_id,
            headline="Popular Products",
            items=[],
        )

    # Identify pairing tags based on product name and categories
    target_text = f"{target_prod.name} {' '.join(c.slug for c in target_prod.categories)}".lower()
    paired_keywords: list[str] = []
    headline = "Pairs Well With"

    for key, pairs in PAIRING_RULES.items():
        if key in target_text:
            paired_keywords.extend(pairs)
            break

    candidate_products: list[Product] = []
    seen_ids: set[UUID] = {target_prod.id}

    if paired_keywords:
        # Search for products matching paired keywords
        kw_clauses = [
            or_(
                Product.name.ilike(f"%{kw}%"),
                select(product_categories.c.product_id)
                .join(Category, Category.id == product_categories.c.category_id)
                .where(
                    product_categories.c.product_id == Product.id,
                    Category.is_active.is_(True),
                    or_(Category.slug.ilike(f"%{kw}%"), Category.name.ilike(f"%{kw}%")),
                )
                .exists(),
            )
            for kw in paired_keywords
        ]
        paired_stmt = (
            select(Product)
            .where(
                Product.id != target_prod.id,
                Product.is_active.is_(True),
                or_(*kw_clauses),
                select(ProductVariant.id)
                .where(
                    ProductVariant.product_id == Product.id,
                    ProductVariant.is_active.is_(True),
                )
                .exists(),
            )
            .options(selectinload(Product.categories), selectinload(Product.variants))
            .limit(limit)
        )
        candidates = (await session.scalars(paired_stmt)).all()
        for c in candidates:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                candidate_products.append(c)

    # If we need more items, fallback to products in the same category or brand
    if len(candidate_products) < limit:
        category_ids = [c.id for c in target_prod.categories]
        fallback_stmt = (
            select(Product)
            .where(
                Product.id.notin_(list(seen_ids)),
                Product.is_active.is_(True),
                select(ProductVariant.id)
                .where(
                    ProductVariant.product_id == Product.id,
                    ProductVariant.is_active.is_(True),
                )
                .exists(),
            )
            .options(selectinload(Product.categories), selectinload(Product.variants))
        )
        conditions: list[Any] = []
        if category_ids:
            conditions.append(
                select(product_categories.c.product_id)
                .where(
                    product_categories.c.product_id == Product.id,
                    product_categories.c.category_id.in_(category_ids),
                )
                .exists()
            )
        if target_prod.brand:
            conditions.append(Product.brand == target_prod.brand)

        if conditions:
            fallback_stmt = fallback_stmt.where(or_(*conditions))

        fallback_stmt = fallback_stmt.limit(limit - len(candidate_products))
        fallbacks = (await session.scalars(fallback_stmt)).all()
        for f in fallbacks:
            if f.id not in seen_ids:
                seen_ids.add(f.id)
                candidate_products.append(f)

    if not paired_keywords and candidate_products:
        headline = "You Might Also Like"

    enriched_items = await enrich_products_with_pricing_and_inventory(
        session,
        candidate_products,
        location_id=location_id,
    )

    return RecommendationResponse(
        product_id=product_id,
        headline=headline,
        items=enriched_items,
    )

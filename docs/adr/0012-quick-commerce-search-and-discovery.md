# ADR 0012: Quick-Commerce Search, Faceted Discovery, and Beverage Pairing Recommendations

- Status: Accepted
- Date: 2026-11-03

## Context

Quick commerce platforms like Drinkit require search latencies under 50ms and immediate item discoverability. Traditional e-commerce search often suffers from disconnected pricing and inventory states (leading to out-of-stock dropoffs), rigid categorization, and poor beverage cross-selling. In beverage delivery, customers frequently search by brand ("Bira", "Tanqueray"), mixology intent ("tonic", "ice", "mixers"), or mood/snack pairings.

## Decision

Implement a dedicated high-throughput search and discovery engine (`app.modules.search`):

1. **Integrated Real-Time Catalog Enrichment**:
   - Products retrieved via database query clauses are enriched in bulk with current active variant prices and dark-store on-hand stock balances (`on_hand - reserved`).
   - Prevents stale pricing displays and eliminates N+1 query overhead.

2. **Multi-Token Free Text & Relevance Weighting**:
   - Matches keywords across product names, brands, descriptions, and category names.
   - Relevance ranking prioritizes exact title matches, prefix matches, and grants an in-stock boost to maximize fulfillment rates.

3. **Faceted Metadata Computation**:
   - Dynamic facet counts for matching categories, brands, and price boundaries (`min_price_minor`, `max_price_minor`) are generated alongside search results.

4. **Multi-Entity Autocomplete**:
   - Rapid prefix and substring search spanning categories, brand names, and active products with type indicators for rich frontend dropdowns.

5. **Quick-Commerce Beverage Pairing & Cross-Sell Matrix**:
   - Rule-based beverage pairing system (e.g., Gin -> Tonic, Beer -> Chips, Whiskey -> Soda) with automated fallbacks to same-category and same-brand merchandise.

## Consequences

- Delivers instant search and autocomplete responsiveness for web and mobile clients.
- Drastically increases average order value (AOV) through intelligent beverage companion pairings.
- Retains clean modular separation between search workflows and foundational catalog persistence.

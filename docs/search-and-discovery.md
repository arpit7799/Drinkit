# Product Search, Discovery & Recommendation Engine

## Overview

Drinkit's Search and Discovery engine (`app.modules.search`) provides sub-millisecond catalog retrieval, multi-attribute faceted filtering, instant typeahead autocomplete, and pairing-based beverage recommendations tailored for 10-minute quick commerce.

---

## 1. Key Capabilities

### A. Free-Text Multi-Token Search
- Tokenizes search queries across product names, brands, descriptions, and category taxonomy.
- Quick-commerce relevance scoring:
  - Exact title matches receive maximum weight.
  - Prefix matches receive secondary priority.
  - In-stock products receive priority boost to avoid customer out-of-stock bounce rates.

### B. Multi-Faceted Filtering
Supports combination filtering across:
- `category`: Category slug (e.g. `beer`, `mixers`, `spirits`).
- `brand`: Brand name (e.g. `Bira 91`, `Tanqueray`, `Schweppes`).
- `min_price` & `max_price`: Range bounds in minor currency units (paise).
- `is_alcoholic`: True/False filter for sober vs alcoholic shopping.
- `in_stock`: Filters items available in the specified dark store.
- `location_id`: Dark store fulfillment node ID.

### C. Live Pricing & Inventory Enrichment
- Results automatically attach current active prices (`starts_at <= now < ends_at`) and location-specific available inventory (`on_hand - reserved`).
- Eliminates stale pricing or out-of-stock disappointments before customer adds to cart.

### D. Dynamic Facet Aggregation
Returns real-time facets matching candidate products:
- `categories`: Array of `{ name, slug, count }`.
- `brands`: Array of `{ brand, count }`.
- `min_price_minor` & `max_price_minor`: Price span across current results.

### E. Instant Typeahead Autocomplete
- `GET /api/v1/search/autocomplete?q=...`
- Returns unified suggestions across matching categories, brands, and products.
- Deduplicates and ranks results for responsive mobile search bars.

### F. Smart Beverage Recommendations & Pairings
- `GET /api/v1/search/recommendations?product_id=...`
- Applies quick-commerce beverage pairing matrices:
  - **Gin** -> Tonic Water, Mixers, Ice.
  - **Beer** -> Chips, Peanuts, Savory snacks.
  - **Vodka** -> Cranberry juice, Energy drinks, Soda.
  - **Whiskey** -> Sparkling club soda, Ice, Glassware.
  - **Rum** -> Cola, Lime mixers.
- Gracefully falls back to cross-sell products in the same category or brand when specific pairing rules do not match.

---

## 2. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/search` | Search products with full-text tokens, facets, filters, and sort options |
| `GET` | `/api/v1/search/autocomplete` | Instant typeahead autocomplete suggestions |
| `GET` | `/api/v1/search/facets` | Catalog-wide or category-filtered facet breakdowns |
| `GET` | `/api/v1/search/recommendations` | Smart pairing and cross-sell recommendations |

---

## 3. Query Parameters for `/api/v1/search`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | `string` | `None` | Free-text search terms |
| `category` | `string` | `None` | Filter by category slug |
| `brand` | `string` | `None` | Filter by brand name |
| `min_price` | `integer` | `None` | Minimum starting price in minor currency |
| `max_price` | `integer` | `None` | Maximum starting price in minor currency |
| `is_alcoholic` | `boolean` | `None` | Filter alcoholic items |
| `in_stock` | `boolean` | `None` | Filter items in stock |
| `location_id` | `UUID` | `None` | Fulfillment dark store ID |
| `sort_by` | `string` | `relevance` | Sort order: `relevance`, `price_asc`, `price_desc`, `name_asc` |
| `limit` | `integer` | `20` | Page size (1 to 100) |
| `offset` | `integer` | `0` | Pagination offset |

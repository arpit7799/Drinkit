# Catalog foundation

## Scope

Phase 3 introduces the read-only product catalog boundary for Drinkit. It
provides hierarchical categories, customer-facing product identity, category
membership, and sellable product variants/SKUs. It intentionally does not
implement inventory, pricing, promotions, carts, search, recommendations,
admin mutations, or age/jurisdiction enforcement.

## Persistence model

- `categories` stores published merchandising categories with optional
  self-referential parents, stable slugs, and deterministic sort order.
- `products` stores customer-facing identity and descriptions independent from
  price and stock.
- `product_categories` allows a product to appear in multiple merchandising
  categories.
- `product_variants` stores sellable SKU and package quantity data. A variant
  is the future inventory and pricing join point, but those domains are not
  coupled into this phase.

PostgreSQL enforces:

- case-insensitive uniqueness for category and product slugs;
- case-insensitive uniqueness for SKU and optional barcode;
- positive variant quantities;
- non-empty names and slugs;
- ABV values between 0 and 100;
- consistency between `is_alcoholic` and `abv_percent`;
- foreign-key cascade behavior for product membership and variants;
- `ON DELETE SET NULL` for a deleted category parent.

The alcohol fields are catalog classification data only. They are not a legal
age-verification or delivery-eligibility decision.

## Public API

- `GET /api/v1/catalog/categories`
  - returns active categories ordered by `sort_order`, name, and ID;
  - response is a flat list with `parent_id` for client-side tree building.
- `GET /api/v1/catalog/products`
  - returns active products with at least one active variant;
  - supports optional case-insensitive `category_slug` filtering;
  - supports bounded `limit` (1–100) and non-negative `offset` pagination;
  - results are deterministic by product name and ID.
- `GET /api/v1/catalog/products/{slug}`
  - returns one active product with active categories and variants;
  - inactive products and products without an active variant return `404`.

Prices, stock, reservations, inventory availability, and delivery estimates are
not returned by these endpoints. They will be joined in later domain slices.

## Operational rules

Catalog writes are not exposed through the public API in this phase. A future
admin/catalog-management phase must add authorization, audit events, validation
workflow, and safe publication controls before mutations are enabled.

Read services explicitly eager-load categories and variants for async API
serialization. Services do not commit transactions; the existing request
session owns the database connection lifecycle.

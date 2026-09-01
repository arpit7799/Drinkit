# Variant pricing foundation

## Scope

Phase 6 adds the pricing boundary for sellable product variants:

- prices are attached to `product_variants`, not customer-facing products;
- money is stored as non-negative integer minor units, avoiding floating-point
  rounding in future cart and order calculations;
- each price has an ISO-style three-letter currency code and an effective time
  window;
- internal services can create, update, list through direct queries, and
  deactivate prices transactionally;
- the public API exposes the current price for a published variant.

This phase intentionally does not implement carts, promotions, tax, discounts,
checkout, orders, payments, refunds, or operator pricing APIs.

## API

- `GET /api/v1/catalog/variants/{variant_id}/price`
  - optional `currency_code` query parameter, defaulting to `INR`;
  - currency input is normalized to uppercase;
  - only active products, active variants, active prices, and currently
    effective windows are eligible;
  - missing prices return the stable `price_not_found` error envelope.

The response uses minor units. For example, `2599` in `INR` represents ₹25.99.
Clients must use the currency metadata rather than assuming a decimal scale in
application logic; the minor-unit scale is a currency concern for a later money
library boundary.

## Persistence

`variant_prices` stores:

- `variant_id` as a foreign key to the sellable SKU;
- `currency_code` as three uppercase alphabetic characters;
- `amount_minor` as a non-negative `BIGINT`;
- `starts_at` and optional `ends_at` as timezone-aware timestamps;
- `is_active` for operational retirement without deleting history.

The `(variant_id, currency_code, starts_at)` key makes price writes idempotent
for one effective start. Lookup indexes cover variant/currency/current-window
queries and active effective-time scans.

## Selection and transaction behavior

A current-price lookup selects active prices where `starts_at <= as_of` and
`ends_at` is null or after `as_of`. If multiple valid records overlap, the
latest `starts_at` wins and the price UUID provides a deterministic tie-breaker.

Internal price writes lock the active variant and the matching effective-start
record inside a service-owned PostgreSQL transaction. They emit pricing events
to the existing transactional outbox and structured logs containing IDs and
money metadata, but no customer address information.

## Deferred work

Operator authorization, price books, promotions, tax calculation, jurisdiction
rules, cart snapshots, and order-time price freezing must be designed before
pricing writes become public administration APIs. Cart and checkout workflows
must copy the selected price into their own immutable line snapshots rather
than recomputing historical totals from mutable catalog prices.

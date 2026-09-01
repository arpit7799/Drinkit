# Store price on variants, not products

- Status: Accepted
- Date: 2026-09-01
- Scope: Phase 6 pricing foundation

## Decision

Drinkit stores prices against `product_variants`, the same sellable SKU
boundary used by inventory. Prices use integer minor units and an explicit
three-letter currency code. Each record has an effective UTC time window and
can be retired without deleting its history.

Current-price resolution is deterministic: active records whose window contains
`as_of` are eligible; the latest `starts_at` wins, followed by the UUID as a
tie-breaker. Internal writes lock the active variant and use
`(variant_id, currency_code, starts_at)` as the idempotent write key.

## Reason

A product can have multiple package sizes, and each package can have different
prices. Keeping pricing on the variant avoids ambiguity and allows later carts
and orders to snapshot the exact sellable unit and price. Integer minor units
avoid binary floating-point errors in money arithmetic while preserving a
provider-independent persistence contract.

The time-effective record supports scheduled price changes and historical
inspection without overwriting prior prices. PostgreSQL remains authoritative;
Redis or a broker may later cache or publish price changes but cannot decide the
price used by a transaction.

## Alternatives considered

### Decimal floating-point API and database values

Rejected as the public persistence contract. Decimal columns can be correct,
but integer minor units make rounding explicit at the boundary and prevent
accidental binary-float conversions in future clients and services.

### Price directly on `products`

Rejected because package variants are independently sellable and inventory
addressed. Product-level pricing would not model different pack sizes safely.

### Public pricing administration

Deferred. Phase 2 authentication does not provide operator roles, approval,
audit actor identity, or reconciliation. Pricing mutation remains an internal
service boundary until those controls exist.

## Consequences

- Clients must carry currency metadata and treat `amount_minor` as an integer.
- Cart and order lines must snapshot the selected price rather than re-querying
  mutable catalog prices for historical totals.
- Overlapping effective windows are permitted for now but resolve
  deterministically; an operator pricing workflow should add validation and
  approval rules before exposing scheduled price administration.
- Promotions, taxes, refunds, and jurisdiction-specific alcohol pricing remain
  separate domains.

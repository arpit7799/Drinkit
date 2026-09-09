# ADR 0007: Cart lines own price snapshots

- Status: Accepted
- Date: 2026-09-02

## Context

Drinkit needs a customer cart after introducing variant-level pricing. A cart
must remain useful while catalog prices change, and later checkout must not
reconstruct a historical cart total from mutable pricing rows. Inventory is
also location-specific, so adding a cart line must not silently reserve stock
or choose a fulfillment location.

## Decision

Attach cart lines to `ProductVariant` and copy the effective price identity and
amount into each line:

- `price_id` records which variant price was selected;
- `currency_code` records the cart/line currency;
- `unit_price_minor` records the integer minor-unit amount at the mutation.

Allow exactly one active cart per customer and one line per variant per cart.
Use service-owned transactions with row locks for cart and line mutations.
Expose only authenticated, ownership-scoped cart APIs. Emit cart changes to the
transactional outbox.

A cart has a fixed currency after creation. Cart line addition and quantity
updates require a currently effective price in that currency. Quantity updates
refresh the line snapshot rather than multiplying an old price indefinitely.

## Consequences

- Cart and order totals avoid floating-point arithmetic.
- Later checkout has explicit data from which to create immutable order lines.
- Price changes do not mutate existing cart-line snapshots without a customer
  cart mutation.
- Cart code remains independent from inventory reservations, delivery routing,
  tax, promotions, payments, and legal eligibility checks.
- A future currency-switching feature must be a deliberate cart lifecycle
  operation rather than an implicit mutation.

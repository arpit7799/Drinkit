# Customer cart foundation

## Scope

Phase 7 adds the authenticated customer cart boundary that follows catalog,
inventory, serviceability, and variant pricing. It provides:

- one active cart per customer;
- cart lines keyed by sellable `ProductVariant` IDs;
- positive line quantities bounded to 999 units;
- a fixed cart currency selected at cart creation;
- immutable-in-operation price snapshots containing the selected price ID,
  currency, and integer minor-unit amount;
- deterministic integer-minor-unit subtotal calculation;
- transactional outbox events for cart creation, line upsert, and line removal.

Cart mutations do **not** reserve inventory, select a fulfillment location,
validate age or jurisdiction eligibility, apply promotions or tax, or create an
order. Those behaviors require later domain boundaries.

## API

All cart endpoints require the authenticated customer access token:

- `GET /api/v1/cart`
  - returns or creates the customer's default `INR` active cart;
  - includes line snapshots and `subtotal_minor`.
- `POST /api/v1/cart/items`
  - request: `variant_id`, `quantity`, and optional `currency_code` (default
    `INR`);
  - adds to an existing line when the variant is already present;
  - snapshots the current effective variant price.
- `PATCH /api/v1/cart/items/{item_id}`
  - request: replacement `quantity`;
  - refreshes the line's price snapshot from the current effective price.
- `DELETE /api/v1/cart/items/{item_id}`
  - removes only a line owned by the authenticated customer.

Unknown variants, inactive products/variants, and variants without a current
price are rejected. An item belonging to another customer is indistinguishable
from a missing item and returns `cart_item_not_found`.

## Persistence and invariants

`shopping_carts` stores the customer, currency, lifecycle status, and UTC
created/updated timestamps. PostgreSQL enforces one active cart per customer
with a partial unique index.

`cart_items` stores:

- the parent cart and sellable variant;
- the selected `variant_prices` record ID;
- the snapshotted currency and non-negative `unit_price_minor`;
- the positive quantity.

PostgreSQL enforces one line per variant in a cart, positive bounded quantity,
non-negative amount, valid currency format, and foreign-key integrity. Deleting
a cart cascades to its lines; price and variant records cannot be deleted while
a cart line references them.

Cart writes lock the customer/cart and matching line rows inside service-owned
transactions. This serializes concurrent quantity changes and prevents a
lost-update line merge. Services do not commit independently outside their
transaction context.

## Price behavior

The cart stores a price snapshot when a line is added or its quantity is
updated. Adding more quantity to an existing line refreshes that line to the
current effective price. The cart never calculates totals using floating-point
values. Each line total is:

```text
quantity * unit_price_minor
```

The subtotal is the sum of those integer line totals. Currency conversion,
minor-unit scale metadata, promotions, tax, and immutable order-time snapshots
remain outside this phase.

## Events

Cart mutations append events to the existing transactional outbox in the same
transaction as the cart change:

- `cart.created`
- `cart.item.upserted`
- `cart.item.removed`

Consumers must treat events as durable integration signals and design for
at-least-once delivery. No external event broker is required by this phase.

## Deferred work

The next order/checkout boundary must explicitly define inventory reservation
and expiry, serviceability revalidation, age/jurisdiction checks, promotion and
tax application, delivery fees, payment authorization, and the final immutable
order line price snapshot. None of those concerns are hidden inside cart
mutation code.

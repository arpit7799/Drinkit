# ADR 0008: Checkout converts cart to immutable order with frozen price snapshots

- Status: Accepted
- Date: 2026-09-10

## Context

After Phase 7 introduced authenticated customer carts with price snapshots, Drinkit needs a checkout boundary that converts the cart into an immutable order. The order must freeze prices, reserve inventory, and initiate payment without recalculating from mutable catalog prices. Inventory is location-specific, so checkout must select a fulfillment location and reserve stock atomically.

## Decision

Create an `orders` domain with:

- `Order` and `OrderLine` persistence models
- Single transactional checkout: lock cart → validate address → pick fulfillment location → reserve inventory → freeze line prices → compute totals → create order → consume reservations → clear cart
- Price snapshots copied from cart into order lines (variant, price_id, currency, unit_price_minor, line_total_minor)
- 15-minute inventory reservations at the serviceable fulfillment location, marked `consumed` and linked to order
- Payment provider abstraction with stub implementations (Razorpay, Stripe, PhonePe); order payment status transitions: `pending` → `authorized` → `captured` (or `failed`/`refunded`)
- Authenticated API: `POST /api/v1/orders`, `GET /api/v1/orders/{id}`, `POST /api/v1/orders/{id}/payment`
- All mutations emit durable outbox events in the same transaction

## Consequences

- Orders are immutable after creation; totals never recalculated from catalog
- Inventory reservations prevent overselling during checkout window
- Payment provider interface allows swapping implementations without order logic changes
- Checkout is independent of delivery scheduling, age verification, promotions, tax engine
- Real payment integrations need webhook endpoints, signature verification, refund flows
- Partial refunds, cancellations, age/jurisdiction checks deferred to next phases
# Order and Checkout Foundation

## Scope

Phase 8 adds the checkout boundary that converts a cart into an immutable order with frozen price snapshots, reserves inventory, initiates payment, and emits durable events. It builds on the cart (Phase 7), pricing (Phase 6), inventory (Phase 4), and serviceability (Phase 5) foundations.

This phase implements:

- **Order creation from cart**: atomic checkout that locks the cart, validates address ownership, revalidates serviceability, reserves inventory at the selected fulfillment location, freezes line prices, computes totals (18% GST + ₹29 flat delivery), clears the cart, and emits `order.created` outbox event
- **Immutable order lines**: each line stores the variant, selected price ID, quantity, currency, and integer minor-unit price snapshot — totals never recalculated from mutable catalog prices
- **Inventory reservation**: 15-minute TTL reservations at the serviceable fulfillment location, marked `consumed` on order creation
- **Payment initiation**: provider-agnostic abstraction with stub implementations for Razorpay, Stripe, PhonePe; order payment status transitions `pending` → `authorized` → `captured` (or `failed`/`refunded`)
- **Authenticated order API**: create order, get order detail, initiate payment
- **Durable outbox events**: `order.created`, `order.payment.initiated`, `order.payment.captured`, `order.payment.failed`, `order.payment.refunded`

Deferred (next phases): delivery scheduling, age/jurisdiction enforcement, promotions/tax engine, webhook handlers, operator admin, refunds via admin.

## API

All endpoints require `Authorization: Bearer <access_token>`.

### Create Order

```text
POST /api/v1/orders
Content-Type: application/json

{
  "address_id": "uuid"
}
```

Response (201):

```json
{
  "id": "uuid",
  "status": "confirmed",
  "currency_code": "INR",
  "subtotal_minor": 3998,
  "tax_minor": 719,
  "delivery_fee_minor": 2900,
  "total_minor": 7617,
  "payment_status": "pending",
  "payment_provider": null,
  "payment_reference": null,
  "created_at": "2026-09-10T...",
  "lines": [
    {
      "id": "uuid",
      "variant_id": "uuid",
      "quantity": 2,
      "currency_code": "INR",
      "unit_price_minor": 1999,
      "line_total_minor": 3998
    }
  ]
}
```

Errors:
- `404 cart_not_found` — no active cart or cart empty
- `409 address_ownership_error` — address not owned by customer
- `400 invalid_order_request` — serviceability not available, inventory insufficient, price no longer available
- `401` — unauthenticated

### Get Order Detail

```text
GET /api/v1/orders/{order_id}
```

Returns the same structure as create. Only returns orders owned by the authenticated customer.

### Initiate Payment

```text
POST /api/v1/orders/{order_id}/payment
Content-Type: application/json

{
  "provider": "razorpay",
  "return_url": "https://app.example.com/orders/..."
}
```

Response:

```json
{
  "order_id": "uuid",
  "payment_url": null,
  "provider_reference": "rzp_test_abc123",
  "status": "initiated"
}
```

Order payment status transitions to `authorized`. Provider stubs return `provider_reference` only; real implementations would return a hosted payment URL.

## Persistence and Invariants

### Orders table

- `user_id`, `address_id` — RESTRICT foreign keys
- `status` — `draft`, `confirmed`, `fulfilled`, `cancelled`
- `payment_status` — `pending`, `authorized`, `captured`, `failed`, `refunded`
- All money in non-negative integer minor units
- Currency code: 3 uppercase ASCII letters (CHECK constraint)
- Partial unique index on `payment_reference` (when not null)

### Order Lines table

- One line per variant per order (unique constraint on `order_id`, `variant_id`)
- `price_id` — FK to `variant_prices` (RESTRICT)
- `quantity > 0`, `unit_price_minor >= 0`, `line_total_minor >= 0`
- Currency code validated

### Inventory Reservations

- `order_id` FK (nullable, SET NULL) links reservation to consuming order
- Status: `active`, `released`, `expired`, `consumed`
- 15-minute TTL (`RESERVATION_TTL_MINUTES`)

## Transaction Behavior

Checkout uses a single service-owned transaction (`async with transaction(session)`):

1. Lock customer row and active cart
2. Lock cart items
3. Validate address ownership (SELECT FOR UPDATE)
4. Resolve fulfillment location via serviceability
5. Lock inventory balances and create reservations
6. Load current prices and build order lines
7. Compute totals
8. Insert order + lines
8. Mark reservations `consumed` + link `order_id`
9. Delete cart items (cascade from cart)
10. Emit `order.created` outbox event

Payment initiation uses its own transaction locking the order row. Webhook confirmation and refunds follow the same pattern.

## Events

All mutations emit to the transactional outbox in the same transaction:

| Event | Trigger | Payload |
|-------|---------|---------|
| `order.created` | Checkout | user_id, address_id, currency, subtotal, tax, delivery, total |
| `order.payment.initiated` | Payment initiation | provider, provider_reference, amount_minor, currency |
| `order.payment.captured` | Webhook verification | provider_reference |
| `order.payment.failed` | Webhook verification failure | provider_reference |
| `order.payment.refunded` | Refund | provider_reference, amount_minor |

## Deferred Work

- Real payment provider integrations (webhook endpoints, signature verification)
- Delivery scheduling and tracking
- Age/jurisdiction validation at checkout
- Promotions, coupons, loyalty, tax jurisdiction rules
- Partial refunds, cancellation workflows
- Operator admin for order management
- Webhook signature verification
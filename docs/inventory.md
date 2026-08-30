# Inventory and reservation foundation

## Scope

Phase 4 adds the first fulfillment and inventory boundary:

- fulfillment locations representing dark stores;
- per-location, per-variant inventory balances;
- idempotent stock-adjustment ledger entries;
- expiring inventory reservations;
- concurrency-safe reservation and release services.

This phase intentionally does not implement addresses, service-area selection,
pricing, carts, orders, payments, delivery dispatch, public inventory mutation
routes, or operator RBAC.

## Persistence model

- `fulfillment_locations` identifies active inventory-holding locations by a
  case-insensitive operational code.
- `inventory_balances` stores `on_hand_quantity` and `reserved_quantity` for
  each location/variant pair.
- `stock_adjustments` records immutable quantity deltas and a required
  location/variant/idempotency key tuple.
- `inventory_reservations` stores temporary holds with a request key, quantity,
  lifecycle status, and expiry timestamp.

PostgreSQL constraints enforce non-negative quantities, reserved quantity not
exceeding on-hand quantity, positive reservations, valid reservation statuses,
unique inventory balances, and foreign-key cleanup.

## Transaction behavior

`adjust_stock` and `reserve_stock` own their transactions through the existing
service transaction helper. The balance row is locked with `SELECT ... FOR
UPDATE`. A missing balance is initialized with PostgreSQL `INSERT ... ON
CONFLICT DO NOTHING` and then locked, so concurrent first receipts cannot create
two balances.

Stock adjustment idempotency is checked while holding the balance lock. Reusing
the same key with the same delta/reason is a no-op; reusing it with different
data returns an idempotency conflict. A negative adjustment cannot reduce
on-hand quantity below the currently reserved quantity.

Reservations expire active holds while holding the balance lock before checking
availability. The expiry transition decrements reserved quantity in the same
transaction as the new reservation. A repeated reservation request with the
same key and quantity returns the existing active reservation. Release is
idempotent and transitions active holds to `released` or `expired` as
appropriate.

## Concurrency contract

For one location/variant balance, all stock changes and reservation changes
serialize on the same PostgreSQL row. Two concurrent reservations cannot both
consume the same available quantity. PostgreSQL is the source of truth; Redis
is not required for correctness in this phase.

The service currently requires both the fulfillment location and product
variant to be active. There is no public mutation route because Phase 2
customer authentication does not provide operator authorization or audit
identity.

## Deferred work

Later phases must add operator/RBAC-protected stock intake and reconciliation,
warehouse/service-area mapping, reservation consumption during order creation,
expiry cleanup jobs, audit actors, inventory event publication, and read APIs
that select a location from a customer address. Pricing and order totals must
remain separate from this inventory authority.

# ADR 0004: PostgreSQL balance rows as inventory authority

- Status: Accepted
- Date: 2026-08-30
- Scope: Phase 4 inventory and reservation foundation

## Decision

Keep inventory authority in PostgreSQL using one `inventory_balances` row per
fulfillment location and product variant. Mutations are performed through
service-owned transactions and lock the balance row with `SELECT ... FOR
UPDATE`.

Record every stock change as an immutable `stock_adjustments` ledger entry
with a required idempotency key. Store temporary holds in
`inventory_reservations`; reservation, expiry, release, and balance updates are
atomic. Redis is not part of the correctness path.

## Reason

Drinkit needs to prevent overselling when multiple carts or order attempts
compete for the same dark-store stock. A single PostgreSQL row is a clear lock
boundary for available quantity, while the adjustment ledger preserves the
reason and retry identity of stock changes. Persisted reservation state makes
holds recoverable and auditable across API processes.

The service layer is internal for now. Customer authentication alone is not an
operator authorization model, so stock mutation endpoints would be unsafe until
RBAC, audit actors, and operational workflows exist.

## Alternatives considered

### Redis as the inventory authority

Rejected. Redis can later accelerate availability reads or coordinate ephemeral
work, but losing or partitioning Redis must not change durable stock truth.

### Reservation rows without a balance lock

Rejected. Checking available quantity and incrementing reserved quantity in
separate unlocked operations allows concurrent requests to oversubscribe stock.

### Only an aggregate balance without an adjustment ledger

Rejected. It loses the reason and idempotency evidence needed for receiving,
reconciliation, retry safety, and operational investigation.

### One balance row per reservation or order line

Rejected. It makes availability aggregation and locking more complex. The
location/variant balance is the natural contention boundary; reservations hold
the detail history separately.

## Trade-offs

- Contending reservations for one SKU/location serialize, which is required for
  correctness and can be optimized only after measured contention exists.
- Offset-free availability reads and multi-location selection are deferred until
  addresses and service areas exist.
- The initial status model includes `consumed` for the future order workflow,
  but this phase only creates, expires, and releases reservations.
- Expiry is performed opportunistically during reservation attempts. A later
  background cleanup job is required for quiet inventory locations.

# ADR 0005: Postal-code coverage for initial serviceability

- Status: Accepted
- Date: 2026-08-31
- Scope: Phase 5 customer addresses and fulfillment serviceability

## Decision

Store customer addresses independently from fulfillment locations. Represent
initial serviceability as explicit normalized postal-code coverage records linked
to fulfillment locations. Resolve an active address to an active covered
location by ascending coverage priority and deterministic location UUID.

Customer address mutations are ownership-scoped and use service-owned
transactions. Address default changes lock the owning user row before clearing
other defaults and setting the requested address. Addresses are deactivated
rather than hard-deleted through the public API.

## Reason

Inventory is location-scoped, so the application needs a durable customer
location boundary before carts or order reservations can select a stock node.
Postal-code coverage is explicit, auditable, cheap to query, and does not imply
that the system has accurate geocoding or delivery geometry.

Keeping coverage separate from addresses avoids embedding operational routing
rules in customer PII records. Keeping address ownership in the service layer
ensures one customer cannot read or mutate another customer's destination.

## Alternatives considered

### Geographic radius from latitude/longitude

Deferred. It requires geocoding, coordinate quality controls, distance rules,
and operational calibration that are not available in the current foundation.

### One hardcoded fulfillment location per user

Rejected. It cannot model multiple dark stores, expansion, failover, or
priority-based routing.

### Coverage embedded on the address

Rejected. Coverage is an operational property that changes independently of
customer data and can apply to many addresses.

### Hard-delete customer addresses

Rejected for the public API. Deactivation preserves historical destination
identity for future order and compliance workflows while excluding it from
active customer operations.

## Trade-offs

- Postal codes are a coarse serviceability rule and can over- or under-include
  physical addresses; later phases can add polygons and geocoding.
- Multiple locations can cover one postal code, so priority and a stable tie
  breaker are required.
- Coverage writes are internal in this phase because operator RBAC and audit
  identities are not implemented yet.
- A customer's default address is optional; clearing or deactivating it does
  not silently promote another address.

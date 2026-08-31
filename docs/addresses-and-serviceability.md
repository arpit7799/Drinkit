# Customer addresses and fulfillment serviceability

## Scope

Phase 5 adds the customer location boundary needed to select inventory from a
fulfillment location:

- authenticated customers can create, list, update, default, and deactivate
  their own addresses;
- postal codes are normalized once at the service boundary;
- fulfillment locations can have active postal-code coverage records;
- serviceability resolves an owned address to the active covered location with
  the lowest priority, then the lowest location UUID as a deterministic tie
  breaker.

This phase intentionally does not implement carts, pricing, orders, payments,
delivery dispatch, geographic distance, geocoding, operator coverage APIs,
service-area polygons, age verification, or jurisdiction rules.

## API

All address routes require the Phase 2 bearer access token:

- `POST /api/v1/addresses`
- `GET /api/v1/addresses`
- `GET /api/v1/addresses/{address_id}`
- `PATCH /api/v1/addresses/{address_id}`
- `POST /api/v1/addresses/{address_id}/default`
- `DELETE /api/v1/addresses/{address_id}`
- `GET /api/v1/addresses/{address_id}/serviceability`

Address records are ownership-scoped. An address belonging to another user is
reported as not found rather than disclosed. Delete is a soft deactivation so
future order and compliance workflows can retain the historical destination
record without exposing it in active address lists.

Serviceability returns HTTP 200 with `serviceable: false` when an address is
owned and active but no active coverage matches. It returns the selected
fulfillment location when coverage exists.

## Persistence

- `customer_addresses` belongs to `users` and stores recipient and delivery
  fields, normalized postal/country values, active state, and optional default
  state.
- A partial unique index permits at most one active default address per user.
- `fulfillment_coverages` maps a fulfillment location to a normalized postal
  code, active state, and non-negative priority.
- A location/postal-code pair is unique, preventing ambiguous duplicate
  coverage records at one location.

## Transaction behavior

Address creation, updates, default changes, and deactivation lock the active
user row before changing defaults. This serializes concurrent default changes
and protects the partial unique index. Services own their transactions; the
authentication dependency explicitly ends its read-only transaction before a
protected mutation service runs on the same request session.

## Normalization

Postal codes are trimmed of surrounding and internal whitespace and uppercased
before persistence and lookup. Country codes are trimmed, uppercased, and
validated as two alphabetic characters. The database retains lightweight
non-blank and country-format invariants; the service owns canonicalization.

## Deferred work

Coverage administration must later gain operator authorization, audit actors,
and reconciliation. Location selection can later incorporate service-area
polygons, geocoding, capacity, delivery ETA, and inventory availability. Those
rules should extend serviceability without moving inventory authority out of
PostgreSQL.

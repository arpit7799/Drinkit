# ADR 0009: Real-Time Order Tracking via WebSockets and Transactional Outbox Relay

- Status: Accepted
- Date: 2026-11-03

## Context

Drinkit operates as a 10-minute quick-commerce beverage delivery service. Customers expect immediate, millisecond-latency order status and rider tracking from the moment an order is confirmed until delivery completion. At the same time, microservices and external notification engines must receive guaranteed, ordered order lifecycle updates without dual-write inconsistencies. Direct database polling by connected mobile/web clients would create severe connection bottlenecks and lock contention under peak order bursts.

## Decision

Implement an event-driven real-time tracking architecture using:

1. **Transactional Outbox Table (`outbox_events`)**:
   - Order mutations, delivery state changes, and courier dispatch events write domain events into the PostgreSQL `outbox_events` table inside the exact same database transaction as the business entity changes.
   - Dual-write race conditions are eliminated by construction.

2. **Asynchronous Outbox Relay Worker (`app.workers.outbox_relay`)**:
   - Background worker processes un-relayed outbox records in bounded batches using `SELECT ... FOR UPDATE SKIP LOCKED` to allow horizontally scalable concurrent worker execution without lock contention or duplicate publishing.
   - Events are published to Redis channels (`orders:{order_id}` and `users:{user_id}:orders`) and marked `published_at = clock_timestamp()` upon successful publication.
   - Failed events increment `retry_count` and record `last_error` with exponential backoff capping.
   - Periodic execution supported via Celery beat task `outbox_relay.process_batch`.

3. **Customer WebSocket Gateway (`GET /api/v1/orders/{order_id}/live`)**:
   - Authenticated handshake via customer JWT access token.
   - Immediate verification of order existence and tenant/ownership boundaries (rejecting unowned orders with policy violation WS_1008).
   - Instant initial `order.snapshot` frame containing immutable order details, current status, payment status, and enriched delivery/courier coordinate data.
   - Subscribes to the isolated Redis pub/sub channel `orders:{order_id}` and forwards live broadcasts directly over the persistent WebSocket connection.
   - Bi-directional ping/pong heartbeat handling to maintain socket liveness across firewalls and cellular networks.
   - Clean connection cleanup on client disconnect, unsubscribing from Redis and releasing pool resources.

## Consequences

- Clients receive immediate snapshots upon connection followed by zero-polling live updates.
- Decouples client WebSocket connections from database transaction loops and pool contention.
- Transactional outbox guarantees at-least-once delivery semantics for all order and delivery lifecycle events.
- Redis pub/sub enables horizontal fan-out across multiple FastAPI application instances.

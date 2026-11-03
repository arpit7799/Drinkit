# Real-Time Order Tracking & Event-Driven Outbox Relay

## Overview

Drinkit provides Blinkit-grade sub-second order tracking for active customer orders. The architecture couples a **Transactional Outbox Pattern** with **Redis Pub/Sub** and a **FastAPI WebSocket Gateway** to achieve resilient, event-driven, zero-polling order updates.

```
+--------------------+        Database Tx        +-------------------------+
| Customer / Courier | ------------------------> | Orders & Delivery State |
| Action (REST API)  |                           +-------------------------+
+--------------------+                                        |
                                                              v
                                                 +-------------------------+
                                                 | PostgreSQL Outbox Table |
                                                 +-------------------------+
                                                              |
                                                              | SELECT FOR UPDATE SKIP LOCKED
                                                              v
                                                 +-------------------------+
                                                 | Outbox Relay Worker     |
                                                 +-------------------------+
                                                              |
                                                              | PUBLISH orders:{order_id}
                                                              v
                                                 +-------------------------+
                                                 | Redis Pub/Sub           |
                                                 +-------------------------+
                                                              |
                                                              | Subscribed
                                                              v
                                                 +-------------------------+
+--------------------+        WebSocket Stream   | FastAPI WebSocket       |
| Mobile / Web App   | <======================== | /api/v1/orders/{id}/live|
+--------------------+                           +-------------------------+
```

---

## 1. Transactional Outbox Relay

### Database Model (`OutboxEvent`)
- Located in `app.models.outbox_event.OutboxEvent`.
- Written in the same ACID transaction as the order creation, status update, or delivery dispatch.
- Fields:
  - `aggregate_type`: e.g. `"order"`, `"delivery"`
  - `aggregate_id`: UUID of the primary aggregate
  - `event_type`: e.g. `"order.created"`, `"delivery.status_updated"`
  - `payload`: JSON payload with event parameters
  - `published_at`: Timestamp when relayed to message broker; `NULL` while pending
  - `retry_count`: Incremented on delivery failure
  - `last_error`: Diagnostic message on publishing error

### Relay Engine (`app.workers.outbox_relay`)
- `process_outbox_batch(session, redis_client, batch_size=100)`:
  - Queries pending outbox records using `with_for_update(skip_locked=True)`.
  - Concurrently safe across any number of worker processes without duplicate publishing or row locking blocks.
  - Publishes events to Redis channel `orders:{aggregate_id}`.
  - Automatically updates `published_at` and commits the batch.
- Periodic execution scheduled via Celery beat (`app.workers.celery_app.outbox_relay_task`).

---

## 2. Customer WebSocket Gateway

### Endpoint
- `GET /api/v1/orders/{order_id}/live?token={jwt_access_token}`

### Authentication & Authorization
- Tokens are verified via query parameter during handshake (`_authenticate_ws`).
- Ownership is strictly enforced (`Order.user_id == current_user.id`).
- Unauthenticated or unauthorized connections are immediately rejected with close code `1008` (Policy Violation).

### Event Protocol

#### Initial Snapshot
Upon successful connection, the server immediately emits an initial `order.snapshot` message:
```json
{
  "type": "order.snapshot",
  "data": {
    "order_id": "a3b8417c-2d0a-42fc-8cf9-bdfbc92d1193",
    "status": "confirmed",
    "payment_status": "captured",
    "currency_code": "INR",
    "total_minor": 5260,
    "delivery": {
      "id": "e931481b-8526-4074-b5b6-79cfb7ef3f2b",
      "status": "in_transit",
      "tracking_number": "TRK-2026-9812",
      "tracking_url": null,
      "estimated_delivery_at": "2026-11-03T20:45:00+00:00",
      "courier": {
        "name": "Ramesh Kumar",
        "phone": "+919876543210",
        "vehicle_type": "bike",
        "current_lat": 18.9220,
        "current_lng": 72.8340
      }
    }
  }
}
```

#### Heartbeats
- Client sends plain text: `"ping"`
- Server replies: `{"type": "pong"}`

#### Real-Time Broadcasts
As courier locations update or order statuses change, events published to Redis channel `orders:{order_id}` are immediately streamed to connected WebSocket subscribers in real time.

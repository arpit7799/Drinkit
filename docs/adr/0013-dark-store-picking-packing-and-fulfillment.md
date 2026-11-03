# ADR 0013: Dark Store Picking, Packing, Staging, and Fulfillment Operations

- Status: Accepted
- Date: 2026-11-03

## Context

In quick-commerce delivery, the physical warehouse fulfillment SLA is 120-180 seconds from order confirmation to dispatch. Orders cannot jump straight from checkout to courier transit without operational dark store governance. Without item-level scanning, incorrect liquor variants or missing items are dispatched. In addition, beverages and glass alcohol bottles experience transit damage and breakage, requiring auditable write-offs.

## Decision

Implement a dedicated Dark Store Warehouse Operations domain (`app.modules.warehouse`):

1. **Automatic Fulfillment Task Generation (`order_fulfillment_tasks`)**:
   - On checkout confirmation, an `OrderFulfillmentTask` is automatically generated for the destination dark store.
   - Items are populated from `order_lines` with bin location guidance (`ambient`, `chilled`, `cooler`).

2. **State Machine (`pending` -> `picking` -> `picked` -> `staged` -> `dispatched`)**:
   - Picking assignment tracks employee picker ID and start timestamps.
   - Barcode scans ensure zero-defect SKU verification.
   - Packer seals items in tamper-evident bags (`bag_seal_number`) and stages them in designated dispatch bays (`staging_bay`).

3. **Event-Driven Outbox Auditing**:
   - Emits outbox events at each stage (`warehouse.task.created`, `warehouse.picking.started`, `warehouse.item.scanned`, `warehouse.order.staged`, `warehouse.order.dispatched`) to feed customer real-time tracking WebSockets.

4. **Goods Receipt Note (GRN) & Liquid/Glass Breakage Write-offs**:
   - Built-in stock inwarding and wastage/breakage write-off mechanisms maintaining PostgreSQL row-locked inventory balance integrity.

## Consequences

- Full operational visibility for dark store operators, pickers, and packers.
- Enforces tamper-evident packaging and bay staging before courier dispatch.
- Decouples warehouse physical operations cleanly from customer cart and checkout while maintaining transactional consistency.

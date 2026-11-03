# Dark Store Warehouse Operations & Order Fulfillment Hub

## Overview

Drinkit's Warehouse Operations subsystem (`app.modules.warehouse`) governs the physical execution of quick-commerce order fulfillment inside local dark stores. In a 10-minute delivery model, the operations hub orchestrates barcode-verified picking, order consolidation, tamper-evident bag sealing, dispatch staging, and inventory inwarding/breakage tracking.

---

## 1. Fulfillment Lifecycle State Machine

```
[Confirmed Order]
       │
       ▼
[PENDING]  ─── Picker Assigned ───►  [PICKING]
                                        │
                               Barcode Item Scans / Shortage
                                        │
                                        ▼
                                     [PICKED]
                                        │
                         Packer Consolidates & Bags
                         Assigns Tamper Seal & Staging Bay
                                        │
                                        ▼
                                     [STAGED]
                                        │
                         Courier Handover at Staging Bay
                                        │
                                        ▼
                                   [DISPATCHED]
                                        │
                               Order: FULFILLED
```

### State Descriptions:
1. **`pending`**: Order placed and confirmed. Task queued for dark-store pickers (FIFO).
2. **`picking`**: Picker assigned to order; routes through ambient, chilled, and cooler storage zones.
3. **`picked`**: All items physically retrieved and verified via barcode scanner.
4. **`packed` / `staged`**: Packer seals items into tamper-evident delivery bag (`SEAL-KOR-98214`) and stages bag in a designated bay (`BAY-04`).
5. **`dispatched`**: Delivery courier takes custody of sealed bag from staging bay. Order transitions to `fulfilled` and courier sets off for customer doorstep.

---

## 2. Dark Store Storage & Bins

Warehouse bins model physical storage addresses within dark stores:
- **`ambient`**: Dry snacks, party supplies, glassware, mixers.
- **`chilled`**: Wines, pre-mixed cocktails, soft drinks.
- **`cooler`**: Craft beers, draught kegs, bagged party ice cubes.
- **`dispatch_staging`**: Dispatch staging bays awaiting courier pickup.

---

## 3. Inventory Operations: GRN & Breakage Write-off

- **Goods Receipt Note (GRN) Inwarding**:
  `POST /api/v1/warehouse/inventory/inward`
  Increments dark-store on-hand balance upon supplier delivery with invoice audit reference.
- **Breakage & Damage Write-off**:
  `POST /api/v1/warehouse/inventory/breakage`
  Decrements on-hand inventory for glass bottle breakage, puncture, or leakage with supervisor identification and reason logging.

---

## 4. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/warehouse/tasks` | List active picking and fulfillment tasks (FIFO) |
| `GET` | `/api/v1/warehouse/tasks/{id}` | Retrieve task details with item pick list |
| `POST` | `/api/v1/warehouse/tasks/{id}/start` | Assign picker and begin picking order |
| `POST` | `/api/v1/warehouse/tasks/{id}/pick-item` | Scan item barcode and verify quantity |
| `POST` | `/api/v1/warehouse/tasks/{id}/complete-picking` | Mark order picking complete |
| `POST` | `/api/v1/warehouse/tasks/{id}/pack-and-stage` | Seal in bag and place in staging bay |
| `POST` | `/api/v1/warehouse/tasks/{id}/dispatch` | Handover bag to delivery courier |
| `POST` | `/api/v1/warehouse/bins` | Create dark store shelf, cooler, or bay |
| `GET` | `/api/v1/warehouse/bins` | List configured storage bins |
| `POST` | `/api/v1/warehouse/inventory/inward` | Inward stock via Goods Receipt Note (GRN) |
| `POST` | `/api/v1/warehouse/inventory/breakage` | Record bottle breakage / leakage write-off |
| `GET` | `/api/v1/warehouse/metrics` | Operational KPIs for dark store manager |

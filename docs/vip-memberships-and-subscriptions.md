# Drinkit VIP Membership & Subscription Club

## Overview
Drinkit VIP is the recurring membership subscription service that turns occasional weekend shoppers into high-LTV, loyal beverage connoisseurs. Modeled after premier quick-commerce clubs (Blinkit One / Instamart Super / Swiggy One), Drinkit VIP offers instant perks:
- **Free Instant Deliveries**: Waives the ₹29.00 flat delivery fee on all orders meeting the tier threshold (e.g., ₹199).
- **Points Acceleration**: Doubles (2.0x+) Liver Points earned per order, speeding up coupon and reward redemption.
- **Priority Dark-Store Picking**: Dark-store fulfillment queues prioritize VIP orders for expedited staging and dispatch.
- **Audit Savings Ledger**: Granular, immutable event logging records every rupee saved and bonus point earned, delivering transparency through the customer profile.

---

## Data Model Architecture

### 1. `membership_plans`
Defines the configurable membership tiers available for customer subscription:
- `code`: Unique identifier (e.g., `VIP_MONTHLY`, `VIP_QUARTERLY`, `VIP_ANNUAL`).
- `duration_days`: Subscription validity window (e.g., 30, 90, 365 days).
- `price_minor`: Price in minor currency units (e.g., 19900 for ₹199).
- `free_delivery_min_order_minor`: Minimum order subtotal required to qualify for delivery fee waiver (default: 19900 = ₹199).
- `points_multiplier`: Loyalty point multiplier (e.g., 2.0x).
- `priority_fulfillment`: Boolean flag signaling dark-store staging precedence.
- `is_active`: Toggles plan visibility in the catalog.

### 2. `customer_memberships`
Tracks each customer's subscription lifecycle:
- `customer_id`: Foreign key referencing `users.id`.
- `plan_id`: Foreign key referencing `membership_plans.id`.
- `status`: Lifecycle state (`active`, `cancelled`, `expired`).
- `starts_at` / `expires_at`: UTC timestamps bounding validity.
- `auto_renew`: Whether recurring renewals are scheduled.
- `payment_reference`: External transaction reference for billing audits.
- `cancellation_reason`: Optional feedback captured upon customer churn.

### 3. `membership_benefit_logs`
Immutable audit log recording every perk claimed:
- `benefit_type`: `free_delivery`, `points_multiplier`, `exclusive_drop`, or `priority_queue`.
- `amount_saved_minor`: Rupee equivalent saved (e.g., 2900 minor units for waived delivery).
- `bonus_points_awarded`: Bonus Liver Points credited on top of the standard earn rate.
- `order_id`: Optional link to the order where the benefit was consumed.

---

## API Surface

| Method | Endpoint | Description | Auth |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/memberships/plans` | List active, public VIP membership tiers | Public |
| `POST` | `/api/v1/memberships/plans` | Create or update a VIP membership plan | Admin |
| `GET` | `/api/v1/memberships/me` | Fetch customer's active membership | Authenticated |
| `POST` | `/api/v1/memberships/subscribe` | Subscribe to a plan or extend validity | Authenticated |
| `POST` | `/api/v1/memberships/cancel` | Cancel active membership subscription | Authenticated |
| `GET` | `/api/v1/memberships/savings` | Customer lifetime savings & bonus points audit | Authenticated |

---

## Checkout Integration

During both solo checkout (`/api/v1/orders`) and collaborative Party Mode checkout (`/api/v1/party/sessions/{id}/checkout`):
1. `evaluate_membership_order_benefits()` checks if the ordering customer has an active VIP membership.
2. If `order_subtotal >= plan.free_delivery_min_order_minor`, `delivery_fee_minor` is set to `0` and savings of `₹29.00` are tracked.
3. Order points are multiplied by `plan.points_multiplier` (e.g. 2.0x base earn).
4. `log_membership_order_benefits()` appends immutable rows to `membership_benefit_logs` linking the order to the customer's savings ledger.

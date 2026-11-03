# ADR 0015: Drinkit VIP Membership and Subscriptions Club

## Status
Accepted

## Context
Quick-commerce economics require high recurring purchase frequency and large average order values (AOV). Customers ordering alcoholic beverages, mixers, ice, and bar snacks often hesitate when faced with incremental delivery fees on small replenishment runs. 

To maximize customer retention, lifetime value (LTV), and brand loyalty, Drinkit requires a subscription membership tier ("Drinkit VIP") offering free instant deliveries above low order thresholds, multiplied loyalty rewards (Liver Points), dark-store fulfillment prioritization, and a transparent lifetime savings ledger.

## Decision
Implement a dedicated VIP Membership domain (`app.modules.memberships`):
1. **Configurable Plans (`membership_plans`)**: Store duration in days, pricing, minimum order thresholds for free delivery, and points multiplier.
2. **Subscription Management (`customer_memberships`)**: Track customer subscription lifecycle states (`active`, `cancelled`, `expired`) with lazy expiration and automated period extension.
3. **Seamless Checkout Hook**: Wire `evaluate_membership_order_benefits()` directly into `app.modules.orders.service` and `app.modules.party.service`. Orders qualifying for VIP perks automatically set `delivery_fee_minor = 0` and scale loyalty accruals by `points_multiplier`.
4. **Immutable Audit Ledger (`membership_benefit_logs`)**: Persist individual entries whenever delivery fees are waived or bonus points are awarded, allowing users to query cumulative savings via `GET /api/v1/memberships/savings`.

## Consequences
- Elevates customer retention and transforms sporadic purchasers into predictable monthly active subscribers.
- Seamless integration with both regular carts and collaborative Party Mode orders.
- Full auditability of promotional subsidies through database-level foreign key logging.

# Promotions, Liver Points Loyalty & Dynamic GST Taxation

## Overview

Drinkit's promotions, loyalty, and tax subsystem provides end-to-end promotional coupon governance, repeat-purchase incentives via "Liver Points", and Indian GST/state excise tax calculations.

---

## 1. Promotional Coupons

Coupons are managed in `app.modules.promotions.service` and backed by `coupons` and `coupon_usages` database tables.

### Rules & Capabilities
- **Discount Types**:
  - `percentage`: Discount is computed as `(subtotal * discount_value) / 100`, bounded by `max_discount_minor`.
  - `fixed_amount`: Fixed minor unit deduction capped at subtotal.
- **Constraints Enforced**:
  - `status == ACTIVE`
  - Current timestamp between `valid_from` and `valid_until`.
  - Subtotal satisfies `min_order_amount_minor`.
  - Global `uses_count < max_uses`. Once exhausted, status transitions to `EXHAUSTED`.
  - Customer lifetime redemptions in `coupon_usages` `< max_uses_per_customer`.

### API Endpoints
- `POST /api/v1/promotions/coupons`: Register a promotional coupon.
- `GET /api/v1/promotions/coupons/{code}`: Fetch coupon details and validity metadata.
- `POST /api/v1/promotions/coupons/validate`: Validate code against a given cart subtotal and preview discount.

---

## 2. Liver Points Loyalty Engine

Liver Points gamify customer engagement and incentivize repeat orders.

### Loyalty Rules
- **Earning**: Customers earn 1 point per ₹100 (10,000 minor units) of order total.
- **Redemption**: Customers can redeem available points at the rate of 1 point = ₹1.00 (100 minor units discount) during checkout.
- **Concurrency Protection**: Point redemption acquires a pessimistic lock (`with_for_update()`) on `loyalty_accounts` to prevent race conditions from concurrent checkouts.
- **Tiers**:
  - **Bronze**: Default (< 250 lifetime points).
  - **Silver**: >= 250 lifetime points.
  - **Gold**: >= 1,000 lifetime points.
- **Audit Logging**: Every point balance modification writes an immutable record to `loyalty_transactions` with `points_delta`, `balance_after`, `order_id`, and `transaction_type` (`EARN`, `REDEEM`, `EXPIRE`, `ADJUST`).

### API Endpoints
- `GET /api/v1/promotions/loyalty`: View current customer's point balance, tier, and lifetime stats.
- `GET /api/v1/promotions/loyalty/transactions`: Audit trail of recent points transactions.
- `POST /api/v1/promotions/loyalty/estimate`: Estimate monetary discount value for a specific number of points.

---

## 3. Dynamic GST & State Tax Engine

Located in `app.modules.promotions.tax`:
- **State Jurisdiction Resolution**: Resolves destination postal code to `TaxJurisdiction`.
- **Itemized Tax Breakdown**: Queries active `TaxRate`s for the destination state.
- **Category Rates**:
  - `alcohol`: State Excise / VAT (e.g. 20%).
  - `beverage_non_alcoholic`: 18% GST (CGST 9% + SGST 9% intrastate, or IGST 18% interstate).
  - `mixer`: 18% GST.
  - `snack`: 12% / 5% GST.
  - `ice`: 5% GST.
  - `party_supply`: 18% GST.
  - `recovery`: 12% GST.
- **Symmetric Splitting**: Eliminates truncation rounding errors by computing line-level tax and distributing across central and state buckets (`cgst = line_tax // 2`, `sgst = line_tax - cgst`).

---

## 4. Checkout Integration

During `create_order_from_cart(session, user_id, address_id, coupon_code, redeem_points)`:
1. Locks the active cart and validates inventory reservations.
2. Validates `coupon_code` (if provided) and calculates discount.
3. Computes line-by-line destination taxes using `calculate_order_taxes`.
4. Redeems `redeem_points` (if requested and available).
5. Calculates net `total_minor`:
   $$\text{total} = \max(0, \text{subtotal} - \text{discounts}) + \text{tax} + \text{delivery\_fee}$$
6. Creates immutable `Order` and links `CouponUsage` and `LoyaltyTransaction`.
7. Awards Liver Points for the placed order.
8. Emits `order.created` event via the transactional outbox table.

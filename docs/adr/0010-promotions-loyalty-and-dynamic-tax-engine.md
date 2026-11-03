# ADR 0010: Promotions, Liver Points Loyalty, and Dynamic GST Taxation Engine

- Status: Accepted
- Date: 2026-11-03

## Context

Drinkit operates as a quick-commerce beverage and party delivery platform across multiple states in India. High customer conversion and retention rely on flexible promotional campaigns (percentage discounts, flat amounts, minimum order requirements, usage caps, and per-customer limits) alongside gamified repeat engagement via "Liver Points" loyalty rewards. Furthermore, beverages in India are subject to complex multi-tiered taxation: alcoholic beverages fall under state excise duties / VAT (which vary widely between states such as Maharashtra and Delhi), whereas non-alcoholic mixers, soda, ice, snacks, and recovery kits fall under the central and state GST regime (with CGST, SGST, IGST, and potential compensation cess). Hardcoded tax rates cause financial inaccuracies and compliance liabilities.

## Decision

Implement a modular promotions, loyalty, and tax calculation domain:

1. **Promotional Coupon Engine (`app.modules.promotions.service`)**:
   - Validation against minimum cart subtotal (`min_order_amount_minor`), time validity windows (`valid_from` to `valid_until`), global coupon usage limits (`max_uses`), and per-customer lifetime caps (`max_uses_per_customer`).
   - Supports percentage discounts (with optional `max_discount_minor` caps) and fixed-amount discounts.
   - Atomic recording in `coupon_usages` and automatic transition to `status = EXHAUSTED` upon reaching `max_uses`.

2. **Liver Points Loyalty System (`app.modules.promotions.service`)**:
   - Customer loyalty balance tracked in `loyalty_accounts` with database check constraint `points_balance >= 0`.
   - Automatic point earning on order completion (1 point per ₹100 / 10,000 minor units spent).
   - Point redemption at 1 point = ₹1.00 (100 minor units) discount on checkout with pessimistic row locking (`with_for_update()`) to prevent concurrent redemption race conditions.
   - Dynamic tier progression (`bronze` -> `silver` at 250 lifetime points -> `gold` at 1000 lifetime points).
   - Complete audit trail of balance modifications in `loyalty_transactions`.

3. **Jurisdiction-Aware GST Tax Engine (`app.modules.promotions.tax`)**:
   - Resolves delivery address postal code to state jurisdiction via `tax_jurisdictions`.
   - Computes itemized line taxes based on product `TaxCategory` (Alcohol, Non-Alcoholic Beverage, Mixer, Snack, Ice, Party Supply, Recovery) and state `TaxRate` (CGST, SGST, IGST, cess).
   - Applies symmetric integer splitting (`cgst = line_tax // 2`, `sgst = line_tax - cgst`) to eliminate fractional penny discrepancies.
   - Replaces static tax assumptions in order checkout with dynamic line-by-line calculation.

4. **Unified Checkout Integration (`app.modules.orders.service`)**:
   - `create_order_from_cart` accepts optional `coupon_code` and `redeem_loyalty_points`.
   - Evaluates subtotal -> applies coupon discount -> applies loyalty points -> computes itemized taxes and delivery fee -> computes immutable `total_minor`.
   - Records coupon usages, loyalty point deductions, loyalty point earnings, and outbox events in the same ACID transaction.

## Consequences

- Full transactional integrity across discounts, loyalty balances, and order totals.
- Eliminates overselling of promotional budgets via database-enforced usage caps and pessimistic locking.
- Correct line-item GST reporting ready for invoice generation and regulatory compliance.

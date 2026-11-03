# ADR 0011: Alcohol Compliance, Customer KYC, and Regulatory Doorstep Governance

- Status: Accepted
- Date: 2026-11-03

## Context

Drinkit operates as a quick-commerce delivery platform handling alcoholic beverages across various Indian states and union territories. Alcohol retail is strictly regulated by state excise laws. Non-compliance (selling to minors, sales during dry days, deliveries outside statutory operating hours, or missing doorstep age verification) results in immediate legal revocation of fulfillment licenses and criminal liabilities. Quick-commerce platforms cannot rely on self-declaration checkboxes; they require verifiable customer KYC, dynamic state regulation enforcement, and doorstep delivery audits.

## Decision

Implement a dedicated compliance domain (`app.modules.compliance`):

1. **Customer Government ID / KYC Verification (`customer_kycs`)**:
   - Customer submits government-issued ID (Aadhaar, PAN, Driving License, Passport) and date of birth.
   - Chronological age is computed and stored alongside masked last 4 characters (`id_number_last4`).
   - Plaintext ID numbers are never stored in the database; a SHA-256 hash (`id_number_hash`) is indexed for deduplication and audit lookup.
   - Customers below 18 years of age are automatically rejected.

2. **State Alcohol Regulations & Statutory Parameters (`state_alcohol_regulations`)**:
   - Maintains state-by-state parameters:
     - Legal Drinking Age (LDA): 21 (Maharashtra, Karnataka), 25 (Delhi, Punjab, Haryana), 18 (Goa, Rajasthan).
     - Statutory delivery operating hours: e.g. 10:00 to 22:00.
     - Maximum permitted spirits volume per delivery: e.g. 9.0 Litres.
     - Compulsory handover OTP flag.

3. **Dry Day Schedule Calendar (`dry_days`)**:
   - Enforces state-specific dry days (national holidays such as Republic Day, Independence Day, Gandhi Jayanti, and election blackout windows).
   - Orders containing alcoholic products are blocked on active dry days.

4. **Doorstep Handover OTP & Courier Verification (`delivery_compliance_logs`)**:
   - On order placement containing alcoholic items, a secure cryptographic 6-digit OTP is generated.
   - Couriers must verify the recipient's physical presence, confirm visual legal age, and submit the customer's handover OTP at doorstep before marking the delivery as completed.

5. **Integrated Checkout Barrier (`app.modules.orders.service`)**:
   - `create_order_from_cart` inspects cart items: if any product has `is_alcoholic = True`, `verify_alcohol_compliance` is triggered before order confirmation.
   - Unverified customers or customers below the destination state's LDA are blocked with specific HTTP 403 policy errors (`KYCRequiredForAlcohol`, `UnderageAlcoholPurchase`, `DryDayRestriction`, `AlcoholHoursRestriction`).

## Consequences

- Full regulatory compliance for alcohol delivery with clear audit trails for state excise inspections.
- Protects minors and shields the platform and fulfillment dark stores from unlawful distribution.
- Separates compliance logic cleanly from catalog, pricing, and payment domains.

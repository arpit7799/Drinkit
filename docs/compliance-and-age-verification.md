# Alcohol Compliance & Regulatory Governance

## Overview

Drinkit's compliance subsystem ensures full adherence to state excise laws and legal drinking age (LDA) mandates across all serviceable jurisdictions in India.

---

## 1. Customer KYC & Age Verification

### Workflow
1. Customer submits a government ID (Aadhaar, PAN, Driving License, Passport) with date of birth via `POST /api/v1/compliance/kyc`.
2. Exact chronological age is calculated and verified:
   - If age < 18: status is set to `REJECTED`.
   - If age >= 18: status is set to `VERIFIED`.
3. Privacy & Security:
   - Plaintext ID numbers are never saved in the database.
   - An irreversible SHA-256 hash (`id_number_hash`) is indexed to prevent duplicate identity reuse.
   - Only masked last 4 characters (`id_number_last4`) are stored for display and courier verification.

---

## 2. State Legal Drinking Age & Regulatory Matrix

| State / UT | Code | Legal Drinking Age (LDA) | Operating Hours | Max Spirits (Litres) |
|---|---|---|---|---|
| Maharashtra | MH | 21 years | 10:00 - 22:30 | 10.0 L |
| Delhi | DL | 25 years | 10:00 - 22:00 | 9.0 L |
| Karnataka | KA | 21 years | 10:00 - 22:00 | 9.0 L |
| Goa | GA | 18 years | 09:00 - 23:00 | 12.0 L |

*Note: Regulations are maintained in the database table `state_alcohol_regulations` and dynamically resolved by destination address.*

---

## 3. Dry Day Prohibitions

- State-specific dry dates (e.g. Gandhi Jayanti, Republic Day, Independence Day, local elections) are cataloged in `dry_days`.
- Orders containing alcoholic products are blocked with HTTP 403 `DryDayRestriction`.

---

## 4. Doorstep Delivery Handover & Verification

- For all confirmed orders containing alcoholic items, the system generates a secure 6-digit handover OTP in `delivery_compliance_logs`.
- At the customer's delivery location:
  1. Courier checks recipient's physical identity.
  2. Courier asks customer for their 6-digit delivery handover OTP.
  3. Courier posts OTP and age confirmation to `POST /api/v1/compliance/orders/{order_id}/verify-handover`.
  4. The audit log updates with courier ID, verification timestamp, and geolocation metadata.

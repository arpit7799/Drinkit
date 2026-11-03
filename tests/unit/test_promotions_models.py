"""Unit tests for promotions, loyalty, and tax ORM models."""

from app.models.promotions_tax import (
    Coupon,
    CouponUsage,
    LoyaltyAccount,
    LoyaltyTransaction,
    TaxJurisdiction,
    TaxRate,
)


def test_coupon_model_columns_and_constraints():
    assert Coupon.__tablename__ == "coupons"
    columns = {col.name for col in Coupon.__table__.columns}
    assert "code" in columns
    assert "discount_type" in columns
    assert "discount_value" in columns
    assert "currency_code" in columns
    assert "min_order_amount_minor" in columns
    assert "max_discount_minor" in columns
    assert "max_uses" in columns
    assert "max_uses_per_customer" in columns
    assert "uses_count" in columns
    assert "status" in columns
    assert "valid_from" in columns
    assert "valid_until" in columns

    constraints = {c.name for c in Coupon.__table__.constraints if c.name}
    assert any("valid_window" in c for c in constraints)
    assert any("positive_discount" in c for c in constraints)
    assert any("percentage_max_100" in c for c in constraints)
    assert any("uq_coupons_code" in c for c in constraints)


def test_coupon_usage_model():
    assert CouponUsage.__tablename__ == "coupon_usages"
    columns = {col.name for col in CouponUsage.__table__.columns}
    assert "coupon_id" in columns
    assert "customer_id" in columns
    assert "order_id" in columns
    assert "discount_applied_minor" in columns

    constraints = {c.name for c in CouponUsage.__table__.constraints}
    assert "uq_coupon_usage" in constraints


def test_loyalty_models_columns_and_constraints():
    assert LoyaltyAccount.__tablename__ == "loyalty_accounts"
    account_cols = {col.name for col in LoyaltyAccount.__table__.columns}
    assert "customer_id" in account_cols
    assert "points_balance" in account_cols
    assert "lifetime_earned" in account_cols
    assert "lifetime_redeemed" in account_cols
    assert "tier" in account_cols

    account_constraints = {c.name for c in LoyaltyAccount.__table__.constraints if c.name}
    assert any("nonnegative_balance" in c for c in account_constraints)
    assert any("nonnegative_lifetime" in c for c in account_constraints)

    assert LoyaltyTransaction.__tablename__ == "loyalty_transactions"
    txn_cols = {col.name for col in LoyaltyTransaction.__table__.columns}
    assert "account_id" in txn_cols
    assert "transaction_type" in txn_cols
    assert "points_delta" in txn_cols
    assert "balance_after" in txn_cols
    assert "order_id" in txn_cols

    txn_constraints = {c.name for c in LoyaltyTransaction.__table__.constraints if c.name}
    assert any("nonzero_delta" in c for c in txn_constraints)


def test_tax_models_columns_and_constraints():
    assert TaxRate.__tablename__ == "tax_rates"
    rate_cols = {col.name for col in TaxRate.__table__.columns}
    assert "state_code" in rate_cols
    assert "category" in rate_cols
    assert "rate_bps" in rate_cols
    assert "cgst_rate_bps" in rate_cols
    assert "sgst_rate_bps" in rate_cols
    assert "igst_rate_bps" in rate_cols

    rate_constraints = {c.name for c in TaxRate.__table__.constraints if c.name}
    assert any("uq_tax_rates_state_category" in c for c in rate_constraints)
    assert any("rate_range" in c for c in rate_constraints)

    assert TaxJurisdiction.__tablename__ == "tax_jurisdictions"
    jur_cols = {col.name for col in TaxJurisdiction.__table__.columns}
    assert "postal_code" in jur_cols
    assert "state_code" in jur_cols
    assert "state_name" in jur_cols

    jur_constraints = {c.name for c in TaxJurisdiction.__table__.constraints if c.name}
    assert any("uq_tax_jurisdictions_postal" in c for c in jur_constraints)

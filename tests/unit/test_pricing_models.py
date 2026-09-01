from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models.pricing import VariantPrice


def test_variant_price_has_money_and_effective_window_fields():
    assert VariantPrice.__tablename__ == "variant_prices"
    columns = VariantPrice.__table__.c

    assert {
        "id",
        "variant_id",
        "currency_code",
        "amount_minor",
        "starts_at",
        "ends_at",
        "is_active",
    } <= set(columns.keys())
    assert any(
        constraint.name == "uq_variant_prices_variant_currency_start"
        for constraint in VariantPrice.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    assert any(
        constraint.name == "ck_variant_prices_amount_minor_non_negative"
        for constraint in VariantPrice.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )
    assert any(
        constraint.name == "ck_variant_prices_effective_window_valid"
        for constraint in VariantPrice.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )


def test_variant_price_indexes_support_current_price_lookup():
    index_names = {index.name for index in VariantPrice.__table__.indexes}

    assert "ix_variant_prices_variant_currency_effective" in index_names
    assert "ix_variant_prices_active_effective" in index_names

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models.cart import CartItem, ShoppingCart


def test_shopping_cart_has_one_active_currency_scoped_customer_cart():
    assert ShoppingCart.__tablename__ == "shopping_carts"
    columns = ShoppingCart.__table__.c

    assert {"id", "user_id", "currency_code", "status"} <= set(columns.keys())
    assert any(
        index.name == "uq_shopping_carts_one_active_user" and index.unique
        for index in ShoppingCart.__table__.indexes
    )
    assert any(
        constraint.name == "ck_shopping_carts_status_valid"
        for constraint in ShoppingCart.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )


def test_cart_item_has_price_snapshot_and_unique_variant_line():
    assert CartItem.__tablename__ == "cart_items"
    columns = CartItem.__table__.c

    assert {
        "id",
        "cart_id",
        "variant_id",
        "price_id",
        "quantity",
        "currency_code",
        "unit_price_minor",
    } <= set(columns.keys())
    assert any(
        constraint.name == "uq_cart_items_cart_variant"
        for constraint in CartItem.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    assert any(
        constraint.name == "ck_cart_items_quantity_positive"
        for constraint in CartItem.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )
    assert any(
        constraint.name == "ck_cart_items_unit_price_minor_non_negative"
        for constraint in CartItem.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )

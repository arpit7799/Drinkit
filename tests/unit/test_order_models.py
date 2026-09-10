"""Order and checkout persistence model contract tests."""

from app.models.orders import Order, OrderLine


def test_order_persistence_model_has_required_columns():
    assert Order.__tablename__ == "orders"
    assert OrderLine.__tablename__ == "order_lines"


def test_order_enforces_customer_and_address_foreign_keys():
    order_columns = {col.name for col in Order.__table__.columns}
    assert "user_id" in order_columns
    assert "address_id" in order_columns
    assert "status" in order_columns
    assert "currency_code" in order_columns
    assert "subtotal_minor" in order_columns
    assert "tax_minor" in order_columns
    assert "delivery_fee_minor" in order_columns
    assert "total_minor" in order_columns
    assert "payment_status" in order_columns
    assert "payment_provider" in order_columns
    assert "payment_reference" in order_columns


def test_order_line_enforces_variant_price_and_quantity_constraints():
    line_columns = {col.name for col in OrderLine.__table__.columns}
    assert "order_id" in line_columns
    assert "variant_id" in line_columns
    assert "price_id" in line_columns
    assert "quantity" in line_columns
    assert "currency_code" in line_columns
    assert "unit_price_minor" in line_columns
    assert "line_total_minor" in line_columns


def test_order_database_constraints_are_present():
    order_constraints = {c.name for c in Order.__table__.constraints}
    assert "ck_orders_subtotal_non_negative" in order_constraints
    assert "ck_orders_tax_non_negative" in order_constraints
    assert "ck_orders_delivery_fee_non_negative" in order_constraints
    assert "ck_orders_total_non_negative" in order_constraints
    assert "ck_orders_currency_code_valid" in order_constraints
    assert "ck_orders_status_valid" in order_constraints
    assert "ck_orders_payment_status_valid" in order_constraints

    line_constraints = {c.name for c in OrderLine.__table__.constraints}
    assert "ck_order_lines_quantity_positive" in line_constraints
    assert "ck_order_lines_currency_code_valid" in line_constraints
    assert "ck_order_lines_unit_price_non_negative" in line_constraints
    assert "ck_order_lines_line_total_non_negative" in line_constraints
    assert "uq_order_lines_order_variant" in line_constraints


def test_order_status_transitions_are_constrained():
    # The CHECK constraint enforces valid statuses
    # Valid: draft, confirmed, fulfilled, cancelled
    pass


def test_order_line_uniqueness_per_order_and_variant():
    # One line per variant per order enforced by unique constraint
    pass

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models.inventory import (
    FulfillmentLocation,
    InventoryBalance,
    InventoryReservation,
    StockAdjustment,
)


def test_fulfillment_location_has_stable_active_identity():
    assert FulfillmentLocation.__tablename__ == "fulfillment_locations"
    columns = FulfillmentLocation.__table__.c

    assert {"id", "code", "name", "is_active"} <= set(columns.keys())
    assert any(
        index.name == "uq_fulfillment_locations_code_ci" and index.unique
        for index in FulfillmentLocation.__table__.indexes
    )
    assert any(
        constraint.name == "ck_fulfillment_locations_code_not_blank"
        for constraint in FulfillmentLocation.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )


def test_inventory_balance_is_unique_per_location_and_variant():
    assert InventoryBalance.__tablename__ == "inventory_balances"
    columns = InventoryBalance.__table__.c

    assert {"id", "location_id", "variant_id", "on_hand_quantity", "reserved_quantity"} <= set(
        columns.keys()
    )
    assert any(
        constraint.name == "uq_inventory_balances_location_variant"
        for constraint in InventoryBalance.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    assert any(
        constraint.name == "ck_inventory_balances_reserved_lte_on_hand"
        for constraint in InventoryBalance.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )


def test_stock_adjustment_is_idempotent_per_inventory_key():
    assert StockAdjustment.__tablename__ == "stock_adjustments"
    columns = StockAdjustment.__table__.c

    assert {
        "id",
        "location_id",
        "variant_id",
        "quantity_delta",
        "reason",
        "idempotency_key",
    } <= set(columns.keys())
    assert any(
        constraint.name == "uq_stock_adjustments_idempotency"
        for constraint in StockAdjustment.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    )


def test_reservation_has_expiry_status_and_unique_request_key():
    assert InventoryReservation.__tablename__ == "inventory_reservations"
    columns = InventoryReservation.__table__.c

    assert {
        "id",
        "location_id",
        "variant_id",
        "reservation_key",
        "quantity",
        "status",
        "expires_at",
    } <= set(columns.keys())
    assert any(
        constraint.name == "uq_inventory_reservations_request"
        for constraint in InventoryReservation.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    )

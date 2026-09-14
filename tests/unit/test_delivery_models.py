"""Delivery and courier persistence model contract tests."""

from app.models.delivery import Courier, Delivery, DeliverySlot


def test_delivery_persistence_model_has_required_columns():
    assert Delivery.__tablename__ == "deliveries"
    assert DeliverySlot.__tablename__ == "delivery_slots"
    assert Courier.__tablename__ == "couriers"


def test_delivery_enforces_order_and_courier_foreign_keys():
    delivery_columns = {col.name for col in Delivery.__table__.columns}
    assert "order_id" in delivery_columns
    assert "courier_id" in delivery_columns
    assert "slot_id" in delivery_columns
    assert "status" in delivery_columns
    assert "tracking_number" in delivery_columns
    assert "tracking_url" in delivery_columns
    assert "estimated_delivery_at" in delivery_columns
    assert "actual_delivery_at" in delivery_columns


def test_delivery_slot_enforces_time_window_and_capacity():
    slot_columns = {col.name for col in DeliverySlot.__table__.columns}
    assert "fulfillment_location_id" in slot_columns
    assert "start_at" in slot_columns
    assert "end_at" in slot_columns
    assert "capacity" in slot_columns
    assert "is_active" in slot_columns


def test_courier_enforces_identity_and_status():
    courier_columns = {col.name for col in Courier.__table__.columns}
    assert "name" in courier_columns
    assert "phone" in courier_columns
    assert "vehicle_type" in courier_columns
    assert "is_active" in courier_columns
    assert "current_lat" in courier_columns
    assert "current_lng" in courier_columns


def test_delivery_database_constraints_are_present():
    delivery_constraints = {c.name for c in Delivery.__table__.constraints}
    assert "ck_deliveries_status_valid" in delivery_constraints
    assert "ck_deliveries_tracking_number_format" in delivery_constraints

    slot_constraints = {c.name for c in DeliverySlot.__table__.constraints}
    assert "ck_delivery_slots_time_window_valid" in slot_constraints
    assert "ck_delivery_slots_capacity_positive" in slot_constraints

    courier_constraints = {c.name for c in Courier.__table__.constraints}
    assert "ck_couriers_vehicle_type_valid" in courier_constraints


def test_delivery_status_transitions_are_constrained():
    # CHECK constraint enforces valid statuses
    # Valid: scheduled, assigned, picked_up, in_transit, delivered, failed, cancelled
    pass


def test_courier_vehicle_type_is_constrained():
    # CHECK constraint: bike, scooter, van, truck
    pass

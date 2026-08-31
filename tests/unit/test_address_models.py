from sqlalchemy import DateTime, String, Uuid

from app.models.address import CustomerAddress, FulfillmentCoverage


def test_address_models_have_explicit_tables_and_relationship_keys():
    assert CustomerAddress.__table__.name == "customer_addresses"
    assert FulfillmentCoverage.__table__.name == "fulfillment_coverages"
    assert isinstance(CustomerAddress.__table__.c.user_id.type, Uuid)
    assert isinstance(CustomerAddress.__table__.c.postal_code.type, String)
    assert isinstance(CustomerAddress.__table__.c.created_at.type, DateTime)
    assert isinstance(FulfillmentCoverage.__table__.c.location_id.type, Uuid)
    assert isinstance(FulfillmentCoverage.__table__.c.postal_code.type, String)


def test_customer_addresses_require_owned_location_fields_and_default_lifecycle():
    table = CustomerAddress.__table__

    for column in (
        table.c.user_id,
        table.c.label,
        table.c.recipient_name,
        table.c.line1,
        table.c.city,
        table.c.state,
        table.c.postal_code,
        table.c.country_code,
    ):
        assert column.nullable is False

    assert table.c.line2.nullable is True
    assert table.c.delivery_instructions.nullable is True
    assert table.c.is_default.nullable is False
    assert table.c.is_active.nullable is False
    assert any(index.name == "uq_customer_addresses_one_default" for index in table.indexes)


def test_fulfillment_coverage_is_unique_per_location_and_normalized_postal_code():
    table = FulfillmentCoverage.__table__

    assert table.c.location_id.nullable is False
    assert table.c.postal_code.nullable is False
    assert table.c.is_active.nullable is False
    assert any(
        constraint.name == "uq_fulfillment_coverages_location_postal"
        for constraint in table.constraints
    )
    assert any(index.name == "ix_fulfillment_coverages_postal_active" for index in table.indexes)


def test_address_and_coverage_constraints_protect_blank_values_and_statuses():
    address_constraints = {constraint.name for constraint in CustomerAddress.__table__.constraints}
    coverage_constraints = {
        constraint.name for constraint in FulfillmentCoverage.__table__.constraints
    }

    assert "ck_customer_addresses_label_not_blank" in address_constraints
    assert "ck_customer_addresses_postal_code_not_blank" in address_constraints
    assert "ck_customer_addresses_country_code_format" in address_constraints
    assert "ck_fulfillment_coverages_postal_code_not_blank" in coverage_constraints

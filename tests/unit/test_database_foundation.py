from datetime import datetime

from sqlalchemy import JSON, DateTime, Uuid

from app.core.database import Base
from app.models.outbox_event import OutboxEvent


def test_metadata_has_explicit_constraint_naming_convention():
    convention = Base.metadata.naming_convention

    assert convention["pk"] == "pk_%(table_name)s"
    assert convention["fk"] == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    assert convention["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert convention["ck"] == "ck_%(table_name)s_%(constraint_name)s"


def test_outbox_event_has_database_enforced_foundation_columns():
    table = OutboxEvent.__table__

    assert table.name == "outbox_events"
    assert isinstance(table.c.id.type, Uuid)
    assert isinstance(table.c.payload.type, JSON)
    assert isinstance(table.c.occurred_at.type, DateTime)
    assert table.c.aggregate_type.nullable is False
    assert table.c.event_type.nullable is False
    assert table.c.payload.nullable is False
    assert table.c.published_at.nullable is True
    assert any(
        constraint.name == "ck_outbox_events_attempts_non_negative"
        for constraint in table.constraints
    )


def test_base_model_annotations_use_uuid_and_aware_utc_timestamps():
    assert OutboxEvent.__table__.c.id.type.python_type is not None
    assert OutboxEvent.__table__.c.created_at.type.python_type is datetime
    assert OutboxEvent.__table__.c.updated_at.type.python_type is datetime
    assert OutboxEvent.__table__.c.created_at.type.timezone is True
    assert OutboxEvent.__table__.c.updated_at.type.timezone is True

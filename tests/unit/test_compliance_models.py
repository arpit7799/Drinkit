"""Unit tests for compliance and regulatory persistence models."""

from app.models.compliance import (
    CustomerKYC,
    DeliveryComplianceLog,
    DryDaySchedule,
    StateAlcoholRegulation,
)


def test_customer_kyc_columns_and_constraints():
    assert CustomerKYC.__tablename__ == "customer_kycs"
    columns = {col.name for col in CustomerKYC.__table__.columns}
    assert "customer_id" in columns
    assert "id_type" in columns
    assert "id_number_hash" in columns
    assert "id_number_last4" in columns
    assert "date_of_birth" in columns
    assert "verified_age" in columns
    assert "status" in columns
    assert "rejection_reason" in columns
    assert "verified_at" in columns

    constraints = {c.name for c in CustomerKYC.__table__.constraints if c.name}
    assert any("nonnegative_age" in c for c in constraints)
    assert any("uq_customer_kycs_customer_id" in c for c in constraints)


def test_state_alcohol_regulation_columns_and_constraints():
    assert StateAlcoholRegulation.__tablename__ == "state_alcohol_regulations"
    columns = {col.name for col in StateAlcoholRegulation.__table__.columns}
    assert "state_code" in columns
    assert "state_name" in columns
    assert "minimum_legal_drinking_age" in columns
    assert "operating_hours_start" in columns
    assert "operating_hours_end" in columns
    assert "max_spirits_litres_per_order" in columns
    assert "delivery_handover_otp_required" in columns

    constraints = {c.name for c in StateAlcoholRegulation.__table__.constraints if c.name}
    assert any("lda_range" in c for c in constraints)
    assert any("positive_max_litres" in c for c in constraints)
    assert any("uq_state_alcohol_regulations_state_code" in c for c in constraints)


def test_dry_day_schedule_columns_and_constraints():
    assert DryDaySchedule.__tablename__ == "dry_days"
    columns = {col.name for col in DryDaySchedule.__table__.columns}
    assert "state_code" in columns
    assert "dry_date" in columns
    assert "reason" in columns
    assert "is_full_day" in columns
    assert "start_time" in columns
    assert "end_time" in columns

    constraints = {c.name for c in DryDaySchedule.__table__.constraints if c.name}
    assert any("uq_dry_days_state_date" in c for c in constraints)


def test_delivery_compliance_log_columns_and_constraints():
    assert DeliveryComplianceLog.__tablename__ == "delivery_compliance_logs"
    columns = {col.name for col in DeliveryComplianceLog.__table__.columns}
    assert "order_id" in columns
    assert "customer_id" in columns
    assert "courier_id" in columns
    assert "recipient_age_verified" in columns
    assert "handover_otp_verified" in columns
    assert "handover_otp" in columns
    assert "verified_at" in columns
    assert "audit_metadata" in columns

    constraints = {c.name for c in DeliveryComplianceLog.__table__.constraints if c.name}
    assert any("uq_delivery_compliance_logs_order_id" in c for c in constraints)

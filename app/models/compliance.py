"""Alcohol compliance, KYC age verification, and regulatory governance models."""

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import BaseModel


class GovtIdType(StrEnum):
    """Supported government identity document types for KYC."""

    AADHAAR = "aadhaar"
    PAN = "pan"
    DRIVING_LICENSE = "driving_license"
    PASSPORT = "passport"


class KYCStatus(StrEnum):
    """Customer identity verification status."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CustomerKYC(BaseModel):
    """Customer government ID and date-of-birth verification record."""

    __tablename__ = "customer_kycs"
    __table_args__ = (
        UniqueConstraint("customer_id", name="uq_customer_kycs_customer_id"),
        CheckConstraint("verified_age >= 0", name="ck_customer_kycs_nonnegative_age"),
        Index("ix_customer_kycs_status", "status"),
        Index("ix_customer_kycs_id_hash", "id_number_hash"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    id_type: Mapped[GovtIdType] = mapped_column(
        Enum(GovtIdType, name="govt_id_type_enum"),
        nullable=False,
    )
    id_number_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    id_number_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    verified_age: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[KYCStatus] = mapped_column(
        Enum(KYCStatus, name="kyc_status_enum"),
        nullable=False,
        default=KYCStatus.PENDING,
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verifier_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class StateAlcoholRegulation(BaseModel):
    """Statutory state-level alcohol distribution parameters."""

    __tablename__ = "state_alcohol_regulations"
    __table_args__ = (
        UniqueConstraint("state_code", name="uq_state_alcohol_regulations_state_code"),
        CheckConstraint(
            "minimum_legal_drinking_age >= 18 AND minimum_legal_drinking_age <= 30",
            name="ck_state_regulations_lda_range",
        ),
        CheckConstraint(
            "max_spirits_litres_per_order > 0",
            name="ck_state_regulations_positive_max_litres",
        ),
    )

    state_code: Mapped[str] = mapped_column(String(2), nullable=False, unique=True)
    state_name: Mapped[str] = mapped_column(String(100), nullable=False)
    minimum_legal_drinking_age: Mapped[int] = mapped_column(Integer, nullable=False, default=21)
    operating_hours_start: Mapped[time] = mapped_column(Time, nullable=False)
    operating_hours_end: Mapped[time] = mapped_column(Time, nullable=False)
    max_spirits_litres_per_order: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, default=Decimal("9.00")
    )
    delivery_handover_otp_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )


class DryDaySchedule(BaseModel):
    """State dry days during which alcohol sale and delivery are prohibited."""

    __tablename__ = "dry_days"
    __table_args__ = (
        UniqueConstraint("state_code", "dry_date", name="uq_dry_days_state_date"),
        Index("ix_dry_days_lookup", "state_code", "dry_date"),
    )

    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    dry_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    is_full_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)


class DeliveryComplianceLog(BaseModel):
    """Audit log verifying recipient age check and handover verification at doorstep."""

    __tablename__ = "delivery_compliance_logs"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_delivery_compliance_logs_order_id"),
        Index("ix_delivery_compliance_customer", "customer_id"),
        Index("ix_delivery_compliance_courier", "courier_id"),
    )

    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    courier_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("couriers.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_age_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    handover_otp_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    handover_otp: Mapped[str] = mapped_column(String(6), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

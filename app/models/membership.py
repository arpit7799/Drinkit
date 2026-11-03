"""Drinkit VIP membership and subscription club persistence models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel


class MembershipPlan(BaseModel):
    """A purchasable VIP subscription tier granting free delivery, multipliers, and perks."""

    __tablename__ = "membership_plans"
    __table_args__ = (
        CheckConstraint("length(btrim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("duration_days > 0", name="duration_positive"),
        CheckConstraint("price_minor >= 0", name="price_non_negative"),
        CheckConstraint("free_delivery_min_order_minor >= 0", name="min_order_non_negative"),
        CheckConstraint("points_multiplier >= 1.0", name="multiplier_gte_one"),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_code_valid"),
        UniqueConstraint("code", name="uq_membership_plans_code"),
        Index("ix_membership_plans_active", "is_active"),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'INR'")
    )
    free_delivery_min_order_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("19900")
    )
    points_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(3, 1), nullable=False, server_default=text("2.0")
    )
    priority_fulfillment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class CustomerMembership(BaseModel):
    """An active, expired, or cancelled VIP membership instance for a customer."""

    __tablename__ = "customer_memberships"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'cancelled', 'expired')", name="status_valid"),
        CheckConstraint("starts_at < expires_at", name="valid_time_window"),
        Index("ix_customer_memberships_customer_status", "customer_id", "status"),
        Index("ix_customer_memberships_expires", "expires_at"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("membership_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    plan: Mapped[MembershipPlan] = relationship(lazy="selectin")


class MembershipBenefitLog(BaseModel):
    """Immutable audit trail of VIP perks enjoyed by customer (fees waived, bonus points)."""

    __tablename__ = "membership_benefit_logs"
    __table_args__ = (
        CheckConstraint(
            "benefit_type IN ("
            "'free_delivery', 'points_multiplier', 'exclusive_drop', 'priority_queue'"
            ")",
            name="benefit_type_valid",
        ),
        CheckConstraint("amount_saved_minor >= 0", name="amount_saved_non_negative"),
        Index("ix_membership_benefit_logs_customer", "customer_id"),
        Index("ix_membership_benefit_logs_order", "order_id"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    membership_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customer_memberships.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    benefit_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount_saved_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    bonus_points_awarded: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

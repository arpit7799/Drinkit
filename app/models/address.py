"""Customer addresses and fulfillment postal-code coverage models."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import BaseModel


class CustomerAddress(BaseModel):
    """A customer-managed delivery address."""

    __tablename__ = "customer_addresses"
    __table_args__ = (
        CheckConstraint("length(btrim(label)) > 0", name="label_not_blank"),
        CheckConstraint("length(btrim(recipient_name)) > 0", name="recipient_name_not_blank"),
        CheckConstraint("length(btrim(line1)) > 0", name="line1_not_blank"),
        CheckConstraint("length(btrim(city)) > 0", name="city_not_blank"),
        CheckConstraint("length(btrim(state)) > 0", name="state_not_blank"),
        CheckConstraint("length(btrim(postal_code)) > 0", name="postal_code_not_blank"),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_format"),
        Index(
            "uq_customer_addresses_one_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default IS TRUE AND is_active IS TRUE"),
        ),
        Index("ix_customer_addresses_user_active", "user_id", "is_active", "updated_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(160), nullable=False)
    line1: Mapped[str] = mapped_column(String(240), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(240), nullable=True)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(120), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    delivery_instructions: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class FulfillmentCoverage(BaseModel):
    """Postal-code coverage offered by one fulfillment location."""

    __tablename__ = "fulfillment_coverages"
    __table_args__ = (
        CheckConstraint("length(btrim(postal_code)) > 0", name="postal_code_not_blank"),
        CheckConstraint("priority >= 0", name="priority_non_negative"),
        UniqueConstraint(
            "location_id",
            "postal_code",
            name="uq_fulfillment_coverages_location_postal",
        ),
        Index(
            "ix_fulfillment_coverages_postal_active",
            "postal_code",
            "is_active",
            "priority",
            "location_id",
        ),
    )

    location_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fulfillment_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

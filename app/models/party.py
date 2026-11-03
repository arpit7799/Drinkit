"""Party Mode, collaborative group ordering, and curated packs persistence models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel


class PartySession(BaseModel):
    """A collaborative group ordering room hosted by a customer."""

    __tablename__ = "party_sessions"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint("length(btrim(invite_code)) = 6", name="invite_code_length"),
        CheckConstraint(
            "status IN ('active', 'locked', 'checkout_pending', 'ordered', 'closed')",
            name="status_valid",
        ),
        CheckConstraint(
            "spending_limit_minor IS NULL OR spending_limit_minor >= 0",
            name="spending_limit_non_negative",
        ),
        UniqueConstraint("invite_code", name="uq_party_sessions_invite_code"),
        Index("ix_party_sessions_host_status", "host_user_id", "status"),
        Index("ix_party_sessions_invite_code", "invite_code"),
    )

    host_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(6), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    spending_limit_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delivery_address_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customer_addresses.id", ondelete="SET NULL"),
        nullable=True,
    )
    fulfillment_location_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fulfillment_locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    participants: Mapped[list[PartyParticipant]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    items: Mapped[list[PartyCartItem]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PartyParticipant(BaseModel):
    """A member of a collaborative party ordering session."""

    __tablename__ = "party_participants"
    __table_args__ = (
        CheckConstraint("length(btrim(nickname)) > 0", name="nickname_not_blank"),
        CheckConstraint("role IN ('host', 'guest')", name="role_valid"),
        Index("ix_party_participants_session", "session_id"),
        Index("ix_party_participants_user", "user_id"),
    )

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("party_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    nickname: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'guest'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    session: Mapped[PartySession] = relationship(back_populates="participants")


class PartyCartItem(BaseModel):
    """An item contributed to the shared party cart by a participant."""

    __tablename__ = "party_cart_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price_minor >= 0", name="unit_price_non_negative"),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_code_valid"),
        Index("ix_party_cart_items_session", "session_id"),
        Index("ix_party_cart_items_variant", "variant_id"),
    )

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("party_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    added_by_participant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("party_participants.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    session: Mapped[PartySession] = relationship(back_populates="items")


class PartyPack(BaseModel):
    """Curated bundles such as cocktail stations, beer packs, or recovery kits."""

    __tablename__ = "party_packs"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(btrim(slug)) > 0", name="slug_not_blank"),
        CheckConstraint("bundle_price_minor >= 0", name="bundle_price_non_negative"),
        CheckConstraint(
            "theme IN ('party', 'cocktail', 'recovery', 'game_night', 'bbq')",
            name="theme_valid",
        ),
        UniqueConstraint("slug", name="uq_party_packs_slug"),
        Index("ix_party_packs_theme_active", "theme", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    theme: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'party'"))
    bundle_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    items: Mapped[list[PartyPackItem]] = relationship(
        back_populates="pack",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PartyPackItem(BaseModel):
    """Constituent SKU and quantity in a curated party pack."""

    __tablename__ = "party_pack_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("pack_id", "variant_id", name="uq_party_pack_items_pack_variant"),
        Index("ix_party_pack_items_pack", "pack_id"),
    )

    pack_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("party_packs.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    pack: Mapped[PartyPack] = relationship(back_populates="items")

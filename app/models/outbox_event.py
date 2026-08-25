"""Domain-neutral transactional outbox model.

The outbox is infrastructure, not a business domain. Future services can
write an event in the same PostgreSQL transaction as their state change and a
worker can publish it later without making Redis or a broker authoritative.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import BaseModel


class OutboxEvent(BaseModel):
    """Durable event awaiting publication to an external broker or projector."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_outbox_events_aggregate", "aggregate_type", "aggregate_id"),
        Index(
            "ix_outbox_events_unpublished",
            "occurred_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(150), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

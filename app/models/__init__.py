"""ORM model exports used by Alembic metadata discovery."""

from app.models.outbox_event import OutboxEvent

__all__ = ["OutboxEvent"]

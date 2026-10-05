"""Payments module."""

from app.modules.payments.webhooks import router as webhooks_router

__all__ = ["webhooks_router"]

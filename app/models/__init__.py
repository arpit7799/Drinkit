"""ORM model exports used by Alembic metadata discovery."""

from app.models.address import CustomerAddress, FulfillmentCoverage
from app.models.auth import AuthSession, Device, User
from app.models.catalog import Category, Product, ProductVariant
from app.models.inventory import (
    FulfillmentLocation,
    InventoryBalance,
    InventoryReservation,
    StockAdjustment,
)
from app.models.outbox_event import OutboxEvent

__all__ = [
    "AuthSession",
    "Category",
    "CustomerAddress",
    "Device",
    "FulfillmentCoverage",
    "FulfillmentLocation",
    "InventoryBalance",
    "InventoryReservation",
    "OutboxEvent",
    "Product",
    "ProductVariant",
    "StockAdjustment",
    "User",
]

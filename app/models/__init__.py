"""ORM model exports used by Alembic metadata discovery."""

from app.models.address import CustomerAddress, FulfillmentCoverage
from app.models.auth import AuthSession, Device, User
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Category, Product, ProductVariant
from app.models.inventory import (
    FulfillmentLocation,
    InventoryBalance,
    InventoryReservation,
    StockAdjustment,
)
from app.models.orders import Order, OrderLine
from app.models.outbox_event import OutboxEvent
from app.models.pricing import VariantPrice

__all__ = [
    "AuthSession",
    "CartItem",
    "Category",
    "CustomerAddress",
    "Device",
    "FulfillmentCoverage",
    "FulfillmentLocation",
    "InventoryBalance",
    "InventoryReservation",
    "Order",
    "OrderLine",
    "OutboxEvent",
    "Product",
    "ProductVariant",
    "StockAdjustment",
    "ShoppingCart",
    "User",
    "VariantPrice",
]

"""ORM model exports used by Alembic metadata discovery."""

from app.models.address import CustomerAddress, FulfillmentCoverage
from app.models.auth import AuthSession, Device, User
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Category, Product, ProductVariant
from app.models.delivery import Courier, Delivery, DeliverySlot
from app.models.inventory import (
    FulfillmentLocation,
    InventoryBalance,
    InventoryReservation,
    StockAdjustment,
)
from app.models.orders import Order, OrderLine
from app.models.outbox_event import OutboxEvent
from app.models.pricing import VariantPrice
from app.models.promotions_tax import (
    Coupon,
    CouponStatus,
    CouponUsage,
    DiscountType,
    LoyaltyAccount,
    LoyaltyTransaction,
    LoyaltyTransactionType,
    TaxCategory,
    TaxJurisdiction,
    TaxRate,
)

__all__ = [
    "AuthSession",
    "CartItem",
    "Category",
    "Coupon",
    "CouponStatus",
    "CouponUsage",
    "Courier",
    "CustomerAddress",
    "Device",
    "Delivery",
    "DeliverySlot",
    "DiscountType",
    "FulfillmentCoverage",
    "FulfillmentLocation",
    "InventoryBalance",
    "InventoryReservation",
    "LoyaltyAccount",
    "LoyaltyTransaction",
    "LoyaltyTransactionType",
    "Order",
    "OrderLine",
    "OutboxEvent",
    "Product",
    "ProductVariant",
    "StockAdjustment",
    "ShoppingCart",
    "TaxCategory",
    "TaxJurisdiction",
    "TaxRate",
    "User",
    "VariantPrice",
]

"""Versioned API router."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.modules.addresses.router import router as addresses_router
from app.modules.auth.router import router as auth_router
from app.modules.cart.router import router as cart_router
from app.modules.catalog.router import router as catalog_router
from app.modules.compliance.router import router as compliance_router
from app.modules.memberships.router import router as memberships_router
from app.modules.orders.router import router as orders_router
from app.modules.orders.websocket import router as tracking_router
from app.modules.party.router import router as party_router
from app.modules.payments import webhooks_router
from app.modules.pricing.router import router as pricing_router
from app.modules.promotions.router import router as promotions_router
from app.modules.search.router import router as search_router
from app.modules.warehouse.router import router as warehouse_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(addresses_router)
api_router.include_router(catalog_router)
api_router.include_router(search_router)
api_router.include_router(cart_router)
api_router.include_router(orders_router)
api_router.include_router(warehouse_router)
api_router.include_router(party_router)
api_router.include_router(memberships_router)
api_router.include_router(tracking_router)
api_router.include_router(promotions_router)
api_router.include_router(compliance_router)
api_router.include_router(webhooks_router)
api_router.include_router(pricing_router)
api_router.include_router(health_router)

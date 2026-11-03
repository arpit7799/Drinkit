"""Integration tests for Party Mode and collaborative group ordering API endpoints."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory, get_db
from app.main import app
from app.models.address import CustomerAddress, FulfillmentCoverage
from app.models.auth import User
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Category, Product, ProductVariant, product_categories
from app.models.delivery import Courier, Delivery
from app.models.inventory import FulfillmentLocation, InventoryBalance
from app.models.orders import Order, OrderLine
from app.models.party import (
    PartyCartItem,
    PartyPack,
    PartyPackItem,
    PartyParticipant,
    PartySession,
)
from app.models.pricing import VariantPrice
from app.models.warehouse import FulfillmentTaskItem, OrderFulfillmentTask, WarehouseBin
from app.modules.auth.dependencies import get_current_user
from app.modules.party.service import create_party_session

pytestmark = pytest.mark.integration


@pytest.fixture
async def party_api_client(
    integration_engine: AsyncEngine,
) -> AsyncIterator[tuple[AsyncClient, dict[str, str], User]]:
    seed_ids: dict[str, str] = {}
    async with AsyncSessionFactory(bind=integration_engine) as session:
        # Pre-clean
        await session.execute(delete(PartyCartItem))
        await session.execute(delete(PartyParticipant))
        await session.execute(delete(PartySession))
        await session.execute(delete(PartyPackItem))
        await session.execute(delete(PartyPack))
        await session.execute(delete(FulfillmentTaskItem))
        await session.execute(delete(OrderFulfillmentTask))
        await session.execute(delete(WarehouseBin))
        await session.execute(delete(Delivery))
        await session.execute(delete(OrderLine))
        await session.execute(delete(Order))
        await session.execute(delete(CartItem))
        await session.execute(delete(ShoppingCart))
        await session.execute(delete(InventoryBalance))
        await session.execute(delete(VariantPrice))
        await session.execute(delete(product_categories))
        await session.execute(delete(ProductVariant))
        await session.execute(delete(Product))
        await session.execute(delete(Category))
        await session.execute(delete(CustomerAddress))
        await session.execute(delete(FulfillmentCoverage))
        await session.execute(delete(Courier))
        await session.execute(delete(User))
        await session.execute(delete(FulfillmentLocation))
        await session.commit()

        # Seed Dark store & Coverage
        loc = FulfillmentLocation(
            id=uuid4(),
            code="DEL-GK-PARTY",
            name="GK Party Dark Store",
            is_active=True,
        )
        session.add(loc)
        await session.flush()
        seed_ids["location_id"] = str(loc.id)

        cov = FulfillmentCoverage(
            location_id=loc.id,
            postal_code="110048",
            priority=1,
            is_active=True,
        )
        session.add(cov)
        await session.flush()

        # Seed Host User
        host = User(
            id=uuid4(),
            email="party_host@drinkit.com",
            password_hash="argon2id$hashed",
            is_active=True,
        )
        session.add(host)
        await session.flush()
        seed_ids["host_id"] = str(host.id)

        # Seed Address
        address = CustomerAddress(
            user_id=host.id,
            label="GK Villa",
            recipient_name="Party Host",
            line1="Villa 5, Greater Kailash 1",
            postal_code="110048",
            city="New Delhi",
            state="Delhi",
            country_code="IN",
            is_default=True,
        )
        session.add(address)
        await session.flush()
        seed_ids["address_id"] = str(address.id)

        # Seed Product, Variant, Price, Stock
        cat = Category(name="Spirits & Soda", slug="spirits-soda", sort_order=1)
        session.add(cat)
        await session.flush()

        vodka = Product(
            name="Absolut Vodka",
            slug="absolut-vodka",
            brand="Absolut",
            is_alcoholic=True,
            abv_percent=Decimal("40.0"),
        )
        vodka.categories.append(cat)
        session.add(vodka)
        await session.flush()

        variant = ProductVariant(
            product_id=vodka.id,
            sku="ABSOLUT-750",
            name="750ml Bottle",
            quantity_value=Decimal("750"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(variant)
        await session.flush()
        seed_ids["variant_id"] = str(variant.id)

        price = VariantPrice(
            variant_id=variant.id,
            currency_code="INR",
            amount_minor=160000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        inv = InventoryBalance(
            location_id=loc.id,
            variant_id=variant.id,
            on_hand_quantity=Decimal("50"),
            reserved_quantity=Decimal("0"),
        )
        session.add_all([price, inv])
        await session.flush()

        # Create session
        party = await create_party_session(
            session,
            host_user_id=host.id,
            title="Cocktail Night",
            address_id=address.id,
        )
        seed_ids["session_id"] = str(party.id)
        seed_ids["invite_code"] = party.invite_code
        seed_ids["host_participant_id"] = str(party.participants[0].id)
        await session.commit()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSessionFactory(bind=integration_engine) as session:
            yield session

    async def override_get_current_user() -> User:
        return host

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, seed_ids, host
    finally:
        app.dependency_overrides.clear()
        async with AsyncSessionFactory(bind=integration_engine) as session:
            await session.execute(delete(PartyCartItem))
            await session.execute(delete(PartyParticipant))
            await session.execute(delete(PartySession))
            await session.execute(delete(PartyPackItem))
            await session.execute(delete(PartyPack))
            await session.execute(delete(FulfillmentTaskItem))
            await session.execute(delete(OrderFulfillmentTask))
            await session.execute(delete(WarehouseBin))
            await session.execute(delete(Delivery))
            await session.execute(delete(OrderLine))
            await session.execute(delete(Order))
            await session.execute(delete(InventoryBalance))
            await session.execute(delete(VariantPrice))
            await session.execute(delete(product_categories))
            await session.execute(delete(ProductVariant))
            await session.execute(delete(Product))
            await session.execute(delete(Category))
            await session.execute(delete(CustomerAddress))
            await session.execute(delete(FulfillmentCoverage))
            await session.execute(delete(Courier))
            await session.execute(delete(User))
            await session.execute(delete(FulfillmentLocation))
            await session.commit()


async def test_party_api_create_and_join(
    party_api_client: tuple[AsyncClient, dict[str, str], User],
) -> None:
    client, seed_ids, _ = party_api_client
    addr_id = seed_ids["address_id"]

    # 1. Host creates new party session via API
    resp_create = await client.post(
        "/api/v1/party/sessions",
        json={
            "title": "Weekend BBQ Party",
            "address_id": addr_id,
            "spending_limit_minor": 800000,
        },
    )
    assert resp_create.status_code == 201
    created_data = resp_create.json()
    assert created_data["title"] == "Weekend BBQ Party"
    invite_code = created_data["invite_code"]

    # 2. Lookup by code
    resp_lookup = await client.get(f"/api/v1/party/sessions/code/{invite_code}")
    assert resp_lookup.status_code == 200
    assert resp_lookup.json()["invite_code"] == invite_code

    # 3. Guest joins
    resp_join = await client.post(
        "/api/v1/party/sessions/join",
        json={"invite_code": invite_code, "nickname": "DJ Karan"},
    )
    assert resp_join.status_code == 201
    assert resp_join.json()["nickname"] == "DJ Karan"


async def test_party_api_items_lock_and_checkout(
    party_api_client: tuple[AsyncClient, dict[str, str], User],
) -> None:
    client, seed_ids, _ = party_api_client
    session_id = seed_ids["session_id"]
    part_id = seed_ids["host_participant_id"]
    variant_id = seed_ids["variant_id"]

    # 1. Add item to party cart
    resp_add = await client.post(
        f"/api/v1/party/sessions/{session_id}/items",
        json={
            "participant_id": part_id,
            "variant_id": variant_id,
            "quantity": 2,
            "note": "Extra chilled",
        },
    )
    assert resp_add.status_code == 200
    party_data = resp_add.json()
    assert len(party_data["items"]) == 1
    assert party_data["items"][0]["quantity"] == 2
    item_id = party_data["items"][0]["id"]

    # 2. Update item quantity
    resp_update = await client.patch(
        f"/api/v1/party/sessions/{session_id}/items/{item_id}",
        json={"participant_id": part_id, "quantity": 3},
    )
    assert resp_update.status_code == 200
    assert resp_update.json()["items"][0]["quantity"] == 3

    # 3. Lock party cart
    resp_lock = await client.post(f"/api/v1/party/sessions/{session_id}/lock")
    assert resp_lock.status_code == 200
    assert resp_lock.json()["status"] == "locked"

    # 4. Checkout
    resp_checkout = await client.post(
        f"/api/v1/party/sessions/{session_id}/checkout",
        json={"coupon_code": None, "points_to_redeem": 0},
    )
    assert resp_checkout.status_code == 200
    checkout_data = resp_checkout.json()
    assert checkout_data["status"] == "confirmed"
    assert checkout_data["order_id"] is not None


async def test_party_packs_api_catalog(
    party_api_client: tuple[AsyncClient, dict[str, str], User],
) -> None:
    client, seed_ids, _ = party_api_client
    variant_id = seed_ids["variant_id"]

    # 1. Create curated pack
    resp_create = await client.post(
        "/api/v1/party/packs",
        json={
            "name": "Absolut Night Station",
            "slug": "absolut-night-station",
            "description": "Premium vodka bundle with tonics",
            "theme": "cocktail",
            "bundle_price_minor": 150000,
            "discount_percent": 10,
            "items": [{"variant_id": variant_id, "quantity": 1}],
        },
    )
    assert resp_create.status_code == 201
    pack_data = resp_create.json()
    assert pack_data["slug"] == "absolut-night-station"

    # 2. List packs
    resp_list = await client.get("/api/v1/party/packs?theme=cocktail")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) >= 1

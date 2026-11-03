"""Integration tests for Party Mode and collaborative group ordering service."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionFactory
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
from app.modules.party.schemas import PartyPackCreateItem, PartySessionStatus, PartyTheme
from app.modules.party.service import (
    add_item_to_party_cart,
    add_party_pack_to_party_cart,
    checkout_party_cart,
    create_party_pack,
    create_party_session,
    get_party_session_by_code,
    get_party_session_details,
    join_party_session,
    list_party_packs,
    lock_party_cart,
    update_party_cart_item,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def party_db_session(
    integration_engine: AsyncEngine,
) -> AsyncIterator[AsyncSession]:
    """Yield clean test session with party seed data."""

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
            code="BLR-KOR-PARTY",
            name="Koramangala Party Hub",
            is_active=True,
        )
        session.add(loc)
        await session.flush()

        cov = FulfillmentCoverage(
            location_id=loc.id,
            postal_code="560095",
            priority=1,
            is_active=True,
        )
        session.add(cov)
        await session.flush()

        # Seed Users (Host & Guest)
        host = User(
            email="host_arpit@drinkit.com",
            password_hash="argon2id$hashed",
            is_active=True,
        )
        guest = User(
            email="guest_rohan@drinkit.com",
            password_hash="argon2id$hashed",
            is_active=True,
        )
        session.add_all([host, guest])
        await session.flush()

        # Seed Address
        address = CustomerAddress(
            user_id=host.id,
            label="Party Penthouse",
            recipient_name="Arpit Host",
            line1="Penthouse 12, Koramangala 4th Block",
            postal_code="560095",
            city="Bengaluru",
            state="Karnataka",
            country_code="IN",
            is_default=True,
        )
        session.add(address)
        await session.flush()

        # Seed Catalog Products & Variants
        cat = Category(name="Beers & Mixers", slug="beers-mixers", sort_order=1)
        session.add(cat)
        await session.flush()

        beer = Product(
            name="Corona Extra",
            slug="corona-extra",
            brand="Corona",
            is_alcoholic=True,
            abv_percent=Decimal("4.5"),
        )
        beer.categories.append(cat)
        session.add(beer)
        await session.flush()

        beer_var = ProductVariant(
            product_id=beer.id,
            sku="CORONA-330",
            name="330ml Bottle",
            quantity_value=Decimal("330"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(beer_var)
        await session.flush()

        lime = Product(
            name="Fresh Mexican Limes Pack",
            slug="fresh-mexican-limes-pack",
            brand="Drinkit Essentials",
            is_alcoholic=False,
            abv_percent=None,
        )
        lime.categories.append(cat)
        session.add(lime)
        await session.flush()

        lime_var = ProductVariant(
            product_id=lime.id,
            sku="LIME-PACK-4",
            name="4 Pack",
            quantity_value=Decimal("4"),
            quantity_unit="pcs",
            is_active=True,
        )
        session.add(lime_var)
        await session.flush()

        # Seed Prices & Inventory
        beer_price = VariantPrice(
            variant_id=beer_var.id,
            currency_code="INR",
            amount_minor=22000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        lime_price = VariantPrice(
            variant_id=lime_var.id,
            currency_code="INR",
            amount_minor=6000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        beer_inv = InventoryBalance(
            location_id=loc.id,
            variant_id=beer_var.id,
            on_hand_quantity=Decimal("120"),
            reserved_quantity=Decimal("0"),
        )
        lime_inv = InventoryBalance(
            location_id=loc.id,
            variant_id=lime_var.id,
            on_hand_quantity=Decimal("50"),
            reserved_quantity=Decimal("0"),
        )
        session.add_all([beer_price, lime_price, beer_inv, lime_inv])
        await session.commit()

        yield session

        # Teardown
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


async def test_party_session_creation_and_guest_joining(
    party_db_session: AsyncSession,
) -> None:
    session = party_db_session
    host = (
        await session.scalars(select(User).where(User.email == "host_arpit@drinkit.com"))
    ).first()
    guest = (
        await session.scalars(select(User).where(User.email == "guest_rohan@drinkit.com"))
    ).first()
    addr = (await session.scalars(select(CustomerAddress))).first()
    assert host and guest and addr

    # 1. Host creates party session
    party_resp = await create_party_session(
        session,
        host_user_id=host.id,
        title="Friday Night Pre-Game",
        address_id=addr.id,
        spending_limit_minor=1000000,
    )
    assert party_resp.title == "Friday Night Pre-Game"
    assert len(party_resp.invite_code) == 6
    assert party_resp.status == PartySessionStatus.ACTIVE.value
    assert len(party_resp.participants) == 1
    assert party_resp.participants[0].nickname == "Host"

    # 2. Guest joins using invite code
    guest_part = await join_party_session(
        session,
        invite_code=party_resp.invite_code,
        nickname="Rohan Guest",
        user_id=guest.id,
    )
    assert guest_part.nickname == "Rohan Guest"
    assert guest_part.role == "guest"

    # 3. Lookup by code
    fetched = await get_party_session_by_code(session, invite_code=party_resp.invite_code)
    assert len(fetched.participants) == 2


async def test_collaborative_cart_addition_and_locking(
    party_db_session: AsyncSession,
) -> None:
    session = party_db_session
    host = (
        await session.scalars(select(User).where(User.email == "host_arpit@drinkit.com"))
    ).first()
    addr = (await session.scalars(select(CustomerAddress))).first()
    beer_var = (
        await session.scalars(select(ProductVariant).where(ProductVariant.sku == "CORONA-330"))
    ).first()
    lime_var = (
        await session.scalars(select(ProductVariant).where(ProductVariant.sku == "LIME-PACK-4"))
    ).first()
    assert host and addr and beer_var and lime_var

    party = await create_party_session(
        session,
        host_user_id=host.id,
        title="House Party",
        address_id=addr.id,
    )
    host_part = party.participants[0]

    guest_part = await join_party_session(
        session,
        invite_code=party.invite_code,
        nickname="Priya",
    )

    # 1. Host adds beer
    item1 = await add_item_to_party_cart(
        session,
        session_id=party.id,
        participant_id=host_part.id,
        variant_id=beer_var.id,
        quantity=6,
        note="Chilled please",
    )
    assert item1.quantity == 6

    # 2. Guest adds limes
    item2 = await add_item_to_party_cart(
        session,
        session_id=party.id,
        participant_id=guest_part.id,
        variant_id=lime_var.id,
        quantity=2,
    )
    assert item2.quantity == 2

    # Verify group cart totals
    state = await get_party_session_details(session, session_id=party.id)
    assert len(state.items) == 2
    assert state.total_items_count == 8
    # 6 * 22000 (132000) + 2 * 6000 (12000) = 144000
    assert state.subtotal_minor == 144000

    # 3. Modify item
    await update_party_cart_item(
        session,
        session_id=party.id,
        item_id=item2.id,
        participant_id=guest_part.id,
        quantity=3,
    )
    state_after_update = await get_party_session_details(session, session_id=party.id)
    assert state_after_update.total_items_count == 9

    # 4. Host locks party cart
    locked_state = await lock_party_cart(session, session_id=party.id, host_user_id=host.id)
    assert locked_state.status == PartySessionStatus.LOCKED.value


async def test_party_pack_curated_bundle_and_checkout(
    party_db_session: AsyncSession,
) -> None:
    session = party_db_session
    host = (
        await session.scalars(select(User).where(User.email == "host_arpit@drinkit.com"))
    ).first()
    addr = (await session.scalars(select(CustomerAddress))).first()
    beer_var = (
        await session.scalars(select(ProductVariant).where(ProductVariant.sku == "CORONA-330"))
    ).first()
    lime_var = (
        await session.scalars(select(ProductVariant).where(ProductVariant.sku == "LIME-PACK-4"))
    ).first()
    assert host and addr and beer_var and lime_var

    # 1. Create curated bundle
    pack = await create_party_pack(
        session,
        name="Corona & Lime Party Station",
        slug="corona-lime-party-station",
        description="6 Coronas with fresh Mexican limes",
        theme=PartyTheme.PARTY,
        bundle_price_minor=125000,
        discount_percent=10,
        items=[
            PartyPackCreateItem(variant_id=beer_var.id, quantity=6),
            PartyPackCreateItem(variant_id=lime_var.id, quantity=1),
        ],
    )
    assert pack.name == "Corona & Lime Party Station"
    assert len(pack.items) == 2

    # 2. Browse packs
    packs_list = await list_party_packs(session, theme=PartyTheme.PARTY)
    assert len(packs_list) >= 1

    # 3. Create session & add pack
    party = await create_party_session(
        session,
        host_user_id=host.id,
        title="Sunset Session",
        address_id=addr.id,
    )
    host_part = party.participants[0]

    await add_party_pack_to_party_cart(
        session,
        session_id=party.id,
        participant_id=host_part.id,
        pack_id=pack.id,
    )

    details = await get_party_session_details(session, session_id=party.id)
    assert details.total_items_count == 7  # 6 beers + 1 lime pack

    # 4. Host converts party cart to order
    checkout_res = await checkout_party_cart(
        session,
        session_id=party.id,
        host_user_id=host.id,
    )
    assert checkout_res.status == "confirmed"
    assert checkout_res.order_id is not None

    # Verify session is marked ordered
    party_after = await session.scalar(select(PartySession).where(PartySession.id == party.id))
    assert party_after.status == PartySessionStatus.ORDERED.value
    assert party_after.closed_at is not None

    # Verify Order was created with lines
    order = await session.scalar(
        select(Order).options(selectinload(Order.lines)).where(Order.id == checkout_res.order_id)
    )
    assert order is not None
    assert len(order.lines) == 2

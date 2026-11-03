"""Integration tests for dark store warehouse operations service."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory
from app.models.address import CustomerAddress
from app.models.auth import User
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Category, Product, ProductVariant, product_categories
from app.models.delivery import Courier, Delivery
from app.models.inventory import FulfillmentLocation, InventoryBalance
from app.models.orders import Order, OrderLine
from app.models.pricing import VariantPrice
from app.models.warehouse import FulfillmentTaskItem, OrderFulfillmentTask, WarehouseBin
from app.modules.warehouse.schemas import BinZoneType, FulfillmentTaskStatus
from app.modules.warehouse.service import (
    complete_picking,
    create_fulfillment_task_for_order,
    create_warehouse_bin,
    dispatch_order_to_courier,
    get_warehouse_metrics,
    inward_stock_grn,
    list_warehouse_bins,
    pack_and_stage_order,
    scan_and_pick_item,
    start_picking_task,
    write_off_breakage_waste,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def warehouse_db_session(
    integration_engine: AsyncEngine,
) -> AsyncIterator[AsyncSession]:
    """Yield clean test session with warehouse seed data."""

    async with AsyncSessionFactory(bind=integration_engine) as session:
        # Pre-clean
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
        await session.execute(delete(Courier))
        await session.execute(delete(User))
        await session.execute(delete(FulfillmentLocation))
        await session.commit()

        # Seed Dark store
        loc = FulfillmentLocation(
            id=uuid4(),
            code="BLR-INDIRA-01",
            name="Indiranagar Dark Store",
            is_active=True,
        )
        session.add(loc)
        await session.flush()

        # Seed User (Picker / Customer)
        user = User(
            email="picker1@drinkit.com",
            password_hash="argon2id$hashed",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        # Seed Courier
        courier = Courier(
            id=uuid4(),
            name="Suresh Delivery Partner",
            phone="+919876543210",
            vehicle_type="scooter",
            is_active=True,
        )
        session.add(courier)
        await session.flush()

        # Seed Address
        address = CustomerAddress(
            user_id=user.id,
            label="Home",
            recipient_name="Rahul Customer",
            line1="Flat 402, 100ft Road",
            postal_code="560038",
            city="Bengaluru",
            state="Karnataka",
            country_code="IN",
            is_default=True,
        )
        session.add(address)
        await session.flush()

        # Seed Product & Variant
        cat = Category(name="Beer", slug="beer", sort_order=1)
        prod = Product(
            name="Bira 91 White",
            slug="bira-91-white",
            brand="Bira 91",
            is_alcoholic=True,
            abv_percent=Decimal("4.9"),
        )
        prod.categories.append(cat)
        session.add(prod)
        await session.flush()

        variant = ProductVariant(
            product_id=prod.id,
            sku="BIRA-WHITE-330",
            name="330ml Can",
            quantity_value=Decimal("330"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(variant)
        await session.flush()

        # Seed Inventory
        inv = InventoryBalance(
            location_id=loc.id,
            variant_id=variant.id,
            on_hand_quantity=Decimal("100"),
            reserved_quantity=Decimal("0"),
        )
        price = VariantPrice(
            variant_id=variant.id,
            currency_code="INR",
            amount_minor=18000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        session.add_all([inv, price])
        await session.flush()

        # Seed Order
        order = Order(
            user_id=user.id,
            address_id=address.id,
            status="confirmed",
            currency_code="INR",
            subtotal_minor=36000,
            tax_minor=6480,
            delivery_fee_minor=2900,
            total_minor=45380,
            payment_status="captured",
        )
        session.add(order)
        await session.flush()

        line = OrderLine(
            order_id=order.id,
            variant_id=variant.id,
            price_id=price.id,
            quantity=2,
            currency_code="INR",
            unit_price_minor=18000,
            line_total_minor=36000,
        )
        session.add(line)
        await session.commit()

        yield session

        # Teardown
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
        await session.execute(delete(Courier))
        await session.execute(delete(User))
        await session.execute(delete(FulfillmentLocation))
        await session.commit()


async def test_create_warehouse_bins_and_list(warehouse_db_session: AsyncSession) -> None:
    session = warehouse_db_session
    loc = (await session.scalars(select(FulfillmentLocation))).first()
    assert loc is not None

    bin1 = await create_warehouse_bin(
        session,
        location_id=loc.id,
        bin_code="AISLE-A1-01",
        zone_type=BinZoneType.COOLER,
    )
    assert bin1.bin_code == "AISLE-A1-01"
    assert bin1.zone_type == "cooler"

    bin2 = await create_warehouse_bin(
        session,
        location_id=loc.id,
        bin_code="BAY-01",
        zone_type=BinZoneType.DISPATCH_STAGING,
    )
    assert bin2.bin_code == "BAY-01"

    bins = await list_warehouse_bins(session, location_id=loc.id)
    assert len(bins) == 2

    staging_bins = await list_warehouse_bins(
        session,
        location_id=loc.id,
        zone_type=BinZoneType.DISPATCH_STAGING,
    )
    assert len(staging_bins) == 1
    assert staging_bins[0].bin_code == "BAY-01"


async def test_full_picking_packing_dispatch_lifecycle(
    warehouse_db_session: AsyncSession,
) -> None:
    session = warehouse_db_session
    loc = (await session.scalars(select(FulfillmentLocation))).first()
    order = (await session.scalars(select(Order))).first()
    user = (await session.scalars(select(User))).first()
    courier = (await session.scalars(select(Courier))).first()
    variant = (await session.scalars(select(ProductVariant))).first()
    assert loc and order and user and courier and variant

    # 1. Create fulfillment task
    task = await create_fulfillment_task_for_order(
        session,
        order_id=order.id,
        location_id=loc.id,
    )
    assert task.status == FulfillmentTaskStatus.PENDING
    assert len(task.items) == 1
    assert task.items[0].expected_quantity == 2
    assert task.items[0].picked_quantity == 0

    # 2. Start picking
    task = await start_picking_task(session, task_id=task.id, picker_id=user.id)
    assert task.status == FulfillmentTaskStatus.PICKING
    assert task.picker_id == user.id
    assert task.started_at is not None

    # 3. Scan & pick items
    item = await scan_and_pick_item(
        session,
        task_id=task.id,
        variant_id=variant.id,
        quantity=2,
        is_damaged=False,
    )
    assert item.picked_quantity == 2
    assert item.is_shortage is False

    # 4. Complete picking
    task = await complete_picking(session, task_id=task.id)
    assert task.status == FulfillmentTaskStatus.PICKED
    assert task.picked_at is not None

    # 5. Pack and stage in dispatch bay
    task = await pack_and_stage_order(
        session,
        task_id=task.id,
        packer_id=user.id,
        staging_bay="BAY-03",
        bag_seal_number="SEAL-BLR-12345",
    )
    assert task.status == FulfillmentTaskStatus.STAGED
    assert task.staging_bay == "BAY-03"
    assert task.bag_seal_number == "SEAL-BLR-12345"

    # 6. Handover to courier (Dispatch)
    task = await dispatch_order_to_courier(
        session,
        task_id=task.id,
        courier_id=courier.id,
    )
    assert task.status == FulfillmentTaskStatus.DISPATCHED
    assert task.dispatched_at is not None

    # Verify order is fulfilled
    refreshed_order = await session.scalar(select(Order).where(Order.id == order.id))
    assert refreshed_order.status == "fulfilled"


async def test_damaged_item_picking(warehouse_db_session: AsyncSession) -> None:
    session = warehouse_db_session
    loc = (await session.scalars(select(FulfillmentLocation))).first()
    order = (await session.scalars(select(Order))).first()
    user = (await session.scalars(select(User))).first()
    variant = (await session.scalars(select(ProductVariant))).first()
    assert loc and order and user and variant

    task = await create_fulfillment_task_for_order(
        session,
        order_id=order.id,
        location_id=loc.id,
    )
    await start_picking_task(session, task_id=task.id, picker_id=user.id)

    # Report damaged bottle
    item = await scan_and_pick_item(
        session,
        task_id=task.id,
        variant_id=variant.id,
        quantity=1,
        is_damaged=True,
    )
    assert item.is_damaged is True
    assert item.is_shortage is True


async def test_inventory_inwarding_and_breakage(warehouse_db_session: AsyncSession) -> None:
    session = warehouse_db_session
    loc = (await session.scalars(select(FulfillmentLocation))).first()
    variant = (await session.scalars(select(ProductVariant))).first()
    assert loc and variant

    # 1. Inward stock (GRN)
    await inward_stock_grn(
        session,
        location_id=loc.id,
        variant_id=variant.id,
        quantity=Decimal("50"),
        invoice_ref="INV-BLR-9988",
        idempotency_key="grn-test-01",
    )

    inv = await session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.location_id == loc.id,
            InventoryBalance.variant_id == variant.id,
        )
    )
    # Started with 100, inwarded 50 -> 150
    assert inv.on_hand_quantity == Decimal("150")

    # 2. Record breakage / waste
    await write_off_breakage_waste(
        session,
        location_id=loc.id,
        variant_id=variant.id,
        quantity=Decimal("3"),
        reason="Broken glass can in cooler",
        reported_by="Suresh Warehouse Incharge",
        idempotency_key="break-test-01",
    )

    inv_after = await session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.location_id == loc.id,
            InventoryBalance.variant_id == variant.id,
        )
    )
    # 150 - 3 = 147
    assert inv_after.on_hand_quantity == Decimal("147")


async def test_warehouse_metrics_calculation(warehouse_db_session: AsyncSession) -> None:
    session = warehouse_db_session
    loc = (await session.scalars(select(FulfillmentLocation))).first()
    order = (await session.scalars(select(Order))).first()
    assert loc and order

    await create_fulfillment_task_for_order(
        session,
        order_id=order.id,
        location_id=loc.id,
    )

    metrics = await get_warehouse_metrics(session, location_id=loc.id)
    assert metrics.location_id == loc.id
    assert metrics.pending_orders >= 1

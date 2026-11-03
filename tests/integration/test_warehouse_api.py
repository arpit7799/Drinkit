"""Integration tests for Warehouse Operations API endpoints."""

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
from app.models.address import CustomerAddress
from app.models.auth import User
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Category, Product, ProductVariant, product_categories
from app.models.delivery import Courier, Delivery
from app.models.inventory import FulfillmentLocation, InventoryBalance
from app.models.orders import Order, OrderLine
from app.models.pricing import VariantPrice
from app.models.warehouse import FulfillmentTaskItem, OrderFulfillmentTask, WarehouseBin
from app.modules.warehouse.service import create_fulfillment_task_for_order

pytestmark = pytest.mark.integration


@pytest.fixture
async def warehouse_api_client(
    integration_engine: AsyncEngine,
) -> AsyncIterator[tuple[AsyncClient, dict[str, str]]]:
    seed_ids: dict[str, str] = {}
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
            code="DEL-HAUZ-01",
            name="Hauz Khas Dark Store",
            is_active=True,
        )
        session.add(loc)
        await session.flush()
        seed_ids["location_id"] = str(loc.id)

        # Seed User
        user = User(
            email="warehouse_operator@drinkit.com",
            password_hash="argon2id$hashed",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        seed_ids["user_id"] = str(user.id)

        # Seed Courier
        courier = Courier(
            id=uuid4(),
            name="Manish Courier",
            phone="+919876543211",
            vehicle_type="scooter",
            is_active=True,
        )
        session.add(courier)
        await session.flush()
        seed_ids["courier_id"] = str(courier.id)

        # Seed Address
        address = CustomerAddress(
            user_id=user.id,
            label="Home",
            recipient_name="Amit Customer",
            line1="C-14 Hauz Khas",
            postal_code="110016",
            city="New Delhi",
            state="Delhi",
            country_code="IN",
            is_default=True,
        )
        session.add(address)
        await session.flush()

        # Seed Product, Variant, Price, Inventory
        cat = Category(name="Mixers", slug="mixers", sort_order=1)
        prod = Product(
            name="Schweppes Ginger Ale",
            slug="schweppes-ginger-ale",
            brand="Schweppes",
            is_alcoholic=False,
            abv_percent=None,
        )
        prod.categories.append(cat)
        session.add(prod)
        await session.flush()

        variant = ProductVariant(
            product_id=prod.id,
            sku="SCHW-GINGER-300",
            name="300ml Can",
            quantity_value=Decimal("300"),
            quantity_unit="ml",
            is_active=True,
        )
        session.add(variant)
        await session.flush()
        seed_ids["variant_id"] = str(variant.id)

        price = VariantPrice(
            variant_id=variant.id,
            currency_code="INR",
            amount_minor=6000,
            starts_at=datetime(2020, 1, 1, tzinfo=UTC),
            is_active=True,
        )
        inv = InventoryBalance(
            location_id=loc.id,
            variant_id=variant.id,
            on_hand_quantity=Decimal("80"),
            reserved_quantity=Decimal("0"),
        )
        session.add_all([price, inv])
        await session.flush()

        # Seed Order & Line
        order = Order(
            user_id=user.id,
            address_id=address.id,
            status="confirmed",
            currency_code="INR",
            subtotal_minor=12000,
            tax_minor=2160,
            delivery_fee_minor=2900,
            total_minor=17060,
            payment_status="captured",
        )
        session.add(order)
        await session.flush()
        seed_ids["order_id"] = str(order.id)

        line = OrderLine(
            order_id=order.id,
            variant_id=variant.id,
            price_id=price.id,
            quantity=2,
            currency_code="INR",
            unit_price_minor=6000,
            line_total_minor=12000,
        )
        session.add(line)
        await session.flush()

        # Create Task
        task = await create_fulfillment_task_for_order(
            session,
            order_id=order.id,
            location_id=loc.id,
        )
        seed_ids["task_id"] = str(task.id)
        await session.commit()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSessionFactory(bind=integration_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, seed_ids
    finally:
        app.dependency_overrides.clear()
        async with AsyncSessionFactory(bind=integration_engine) as session:
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
            await session.execute(delete(Courier))
            await session.execute(delete(User))
            await session.execute(delete(FulfillmentLocation))
            await session.commit()


async def test_warehouse_api_tasks_and_picking_flow(
    warehouse_api_client: tuple[AsyncClient, dict[str, str]],
) -> None:
    client, seed_ids = warehouse_api_client
    loc_id = seed_ids["location_id"]
    task_id = seed_ids["task_id"]
    user_id = seed_ids["user_id"]
    variant_id = seed_ids["variant_id"]
    courier_id = seed_ids["courier_id"]

    # 1. List tasks
    resp_list = await client.get(f"/api/v1/warehouse/tasks?location_id={loc_id}")
    assert resp_list.status_code == 200
    tasks_data = resp_list.json()
    assert len(tasks_data) == 1
    assert tasks_data[0]["status"] == "pending"

    # 2. Start picking
    resp_start = await client.post(
        f"/api/v1/warehouse/tasks/{task_id}/start",
        json={"picker_id": user_id},
    )
    assert resp_start.status_code == 200
    assert resp_start.json()["status"] == "picking"

    # 3. Pick item
    resp_pick = await client.post(
        f"/api/v1/warehouse/tasks/{task_id}/pick-item",
        json={"variant_id": variant_id, "quantity": 2, "is_damaged": False},
    )
    assert resp_pick.status_code == 200
    assert resp_pick.json()["picked_quantity"] == 2

    # 4. Complete picking
    resp_complete = await client.post(f"/api/v1/warehouse/tasks/{task_id}/complete-picking")
    assert resp_complete.status_code == 200
    assert resp_complete.json()["status"] == "picked"

    # 5. Pack and stage
    resp_pack = await client.post(
        f"/api/v1/warehouse/tasks/{task_id}/pack-and-stage",
        json={
            "packer_id": user_id,
            "staging_bay": "BAY-DEL-02",
            "bag_seal_number": "SEAL-998877",
        },
    )
    assert resp_pack.status_code == 200
    assert resp_pack.json()["status"] == "staged"
    assert resp_pack.json()["staging_bay"] == "BAY-DEL-02"

    # 6. Dispatch
    resp_dispatch = await client.post(
        f"/api/v1/warehouse/tasks/{task_id}/dispatch",
        json={"courier_id": courier_id},
    )
    assert resp_dispatch.status_code == 200
    assert resp_dispatch.json()["status"] == "dispatched"


async def test_warehouse_api_bins_and_inventory(
    warehouse_api_client: tuple[AsyncClient, dict[str, str]],
) -> None:
    client, seed_ids = warehouse_api_client
    loc_id = seed_ids["location_id"]
    variant_id = seed_ids["variant_id"]

    # 1. Create Bin
    resp_bin = await client.post(
        "/api/v1/warehouse/bins",
        json={
            "fulfillment_location_id": loc_id,
            "bin_code": "RACK-COOLER-01",
            "zone_type": "cooler",
        },
    )
    assert resp_bin.status_code == 201
    assert resp_bin.json()["bin_code"] == "RACK-COOLER-01"

    # 2. List Bins
    resp_bins = await client.get(f"/api/v1/warehouse/bins?location_id={loc_id}")
    assert resp_bins.status_code == 200
    assert len(resp_bins.json()) >= 1

    # 3. Inward inventory
    resp_inward = await client.post(
        "/api/v1/warehouse/inventory/inward",
        json={
            "location_id": loc_id,
            "variant_id": variant_id,
            "quantity": 24,
            "invoice_ref": "GRN-2026-091",
            "idempotency_key": "api-grn-01",
        },
    )
    assert resp_inward.status_code == 200
    assert resp_inward.json()["status"] == "inwarded"

    # 4. Breakage inventory
    resp_break = await client.post(
        "/api/v1/warehouse/inventory/breakage",
        json={
            "location_id": loc_id,
            "variant_id": variant_id,
            "quantity": 1,
            "reason": "Can punctured during staging",
            "reported_by": "Ramesh Operator",
            "idempotency_key": "api-break-01",
        },
    )
    assert resp_break.status_code == 200
    assert resp_break.json()["status"] == "breakage_recorded"

    # 5. Metrics
    resp_metrics = await client.get(f"/api/v1/warehouse/metrics?location_id={loc_id}")
    assert resp_metrics.status_code == 200
    assert resp_metrics.json()["location_id"] == loc_id

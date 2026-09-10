from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import AsyncSessionFactory
from app.core.exceptions import (
    AddressOwnershipError,
    CartNotFound,
)
from app.models.address import CustomerAddress, FulfillmentCoverage
from app.models.auth import User
from app.models.catalog import Product, ProductVariant
from app.models.inventory import FulfillmentLocation
from app.modules.cart.service import (
    add_cart_item,
    get_or_create_cart,
)
from app.modules.orders.service import create_order_from_cart
from app.modules.pricing.service import set_variant_price

pytestmark = pytest.mark.integration


async def _seed_user_address_variant_and_price(
    integration_engine: AsyncEngine,
) -> tuple[UUID, UUID, UUID, UUID]:
    user_id = uuid4()
    address_id = uuid4()
    product_id = uuid4()
    variant_id = uuid4()
    location_id = uuid4()
    location_code = f"MUM-{uuid4().hex[:8]}"
    async with AsyncSessionFactory(bind=integration_engine) as session:
        user = User(
            id=user_id,
            email=f"order-{user_id}@example.com",
            password_hash="$argon2id$v=19$m=1,t=1,p=1$test$test",
        )
        session.add(user)
        await session.flush()

        session.add(
            CustomerAddress(
                id=address_id,
                user_id=user_id,
                label="home",
                recipient_name="Test User",
                line1="123 Test St",
                line2=None,
                city="Mumbai",
                state="Maharashtra",
                postal_code="400001",
                country_code="IN",
                delivery_instructions=None,
                is_default=True,
                is_active=True,
            )
        )
        session.add(
            FulfillmentLocation(
                id=location_id,
                code=location_code,
                name="Mumbai Central",
                is_active=True,
            )
        )
        await session.flush()

        session.add(
            FulfillmentCoverage(
                location_id=location_id,
                postal_code="400001",
                priority=1,
                is_active=True,
            )
        )
        await session.flush()

        # Also need to ensure the old coverage for 400001 is deactivated
        from sqlalchemy import update

        from app.models.address import FulfillmentCoverage as FulfillmentCoverageModel

        await session.execute(
            update(FulfillmentCoverageModel)
            .where(
                FulfillmentCoverageModel.postal_code == "400001",
                FulfillmentCoverageModel.location_id != location_id,
            )
            .values(is_active=False)
        )
        session.add(
            Product(
                id=product_id,
                name="Order Test Product",
                slug=f"order-test-{product_id}",
                is_alcoholic=False,
            )
        )
        session.add(
            ProductVariant(
                id=variant_id,
                product_id=product_id,
                sku=f"ORDER-{variant_id}",
                name="One unit",
                quantity_value=Decimal("1"),
                quantity_unit="unit",
            )
        )
        await session.commit()
        await set_variant_price(
            session,
            variant_id=variant_id,
            currency_code="INR",
            amount_minor=1999,
        )
        # Create inventory balance for the variant at the location
        from app.models.inventory import InventoryBalance

        session.add(
            InventoryBalance(
                location_id=location_id,
                variant_id=variant_id,
                on_hand_quantity=Decimal("100"),
                reserved_quantity=Decimal("0"),
            )
        )
        await session.commit()
    return user_id, address_id, variant_id, product_id


async def test_order_creation_from_cart_freezes_line_prices(
    integration_engine: AsyncEngine,
):
    user_id, address_id, variant_id, product_id = await _seed_user_address_variant_and_price(
        integration_engine
    )

    async with AsyncSessionFactory(bind=integration_engine) as session:
        await get_or_create_cart(session, user_id=user_id)
        await add_cart_item(
            session, user_id=user_id, variant_id=variant_id, quantity=2, currency_code="INR"
        )

    async with AsyncSessionFactory(bind=integration_engine) as session:
        order = await create_order_from_cart(
            session,
            user_id=user_id,
            address_id=address_id,
        )

    assert order.status == "confirmed"
    assert order.currency_code == "INR"
    assert len(order.lines) == 1
    assert order.lines[0].variant_id == variant_id
    assert order.lines[0].quantity == 2
    assert order.lines[0].unit_price_minor == 1999
    assert order.lines[0].line_total_minor == 3998
    assert order.subtotal_minor == 3998
    # 18% GST on 3998 = 719.64 -> 719 in minor units (truncated)
    assert order.tax_minor == 719
    # Flat delivery fee of ₹29.00
    assert order.delivery_fee_minor == 2900
    assert order.total_minor == 3998 + 719 + 2900
    assert order.payment_status == "pending"


async def test_order_requires_cart_with_items(
    integration_engine: AsyncEngine,
):
    user_id, address_id, variant_id, product_id = await _seed_user_address_variant_and_price(
        integration_engine
    )

    async with AsyncSessionFactory(bind=integration_engine) as session:
        with pytest.raises(CartNotFound):
            await create_order_from_cart(session, user_id=user_id, address_id=address_id)


async def test_order_rejects_unknown_address(
    integration_engine: AsyncEngine,
):
    user_id, address_id, variant_id, product_id = await _seed_user_address_variant_and_price(
        integration_engine
    )
    unknown_address_id = uuid4()

    async with AsyncSessionFactory(bind=integration_engine) as session:
        await get_or_create_cart(session, user_id=user_id)
        await add_cart_item(
            session, user_id=user_id, variant_id=variant_id, quantity=1, currency_code="INR"
        )

    async with AsyncSessionFactory(bind=integration_engine) as session:
        with pytest.raises(AddressOwnershipError):
            await create_order_from_cart(session, user_id=user_id, address_id=unknown_address_id)


async def test_order_rejects_unknown_customer(
    integration_engine: AsyncEngine,
):
    address_id = uuid4()
    unknown_user_id = uuid4()

    async with AsyncSessionFactory(bind=integration_engine) as session:
        with pytest.raises(CartNotFound):
            await create_order_from_cart(session, user_id=unknown_user_id, address_id=address_id)

from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import AsyncSessionFactory
from app.core.exceptions import (
    CartCurrencyConflict,
    CartItemNotFound,
    InvalidCartRequest,
    VariantNotFound,
)
from app.models.auth import User
from app.models.cart import CartItem, ShoppingCart
from app.models.catalog import Product, ProductVariant
from app.models.orders import Order, OrderLine
from app.models.outbox_event import OutboxEvent
from app.modules.cart.service import (
    add_cart_item,
    get_cart,
    remove_cart_item,
    update_cart_item,
)
from app.modules.pricing.service import set_variant_price

pytestmark = pytest.mark.integration


@pytest.fixture
async def cart_scope(integration_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with AsyncSessionFactory(bind=integration_engine) as session:
        await session.execute(delete(CartItem))
        await session.execute(delete(ShoppingCart))
        await session.execute(delete(OrderLine))
        await session.execute(delete(Order))
        await session.execute(delete(ProductVariant))
        await session.execute(delete(Product))
        await session.execute(delete(User))
        await session.commit()


async def _seed_user_and_variant(integration_engine: AsyncEngine) -> tuple[UUID, UUID]:
    user_id = uuid4()
    product_id = uuid4()
    variant_id = uuid4()
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            User(
                id=user_id,
                email=f"cart-{user_id}@example.com",
                password_hash="$argon2id$v=19$m=1,t=1,p=1$test$test",
            )
        )
        session.add(
            Product(
                id=product_id,
                name="Cart Test Product",
                slug=f"cart-test-{product_id}",
                is_alcoholic=False,
            )
        )
        session.add(
            ProductVariant(
                id=variant_id,
                product_id=product_id,
                sku=f"CART-{variant_id}",
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
    return user_id, variant_id


async def test_cart_add_merges_variant_lines_and_snapshots_price(
    integration_engine: AsyncEngine,
    cart_scope: None,
):
    user_id, variant_id = await _seed_user_and_variant(integration_engine)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        first = await add_cart_item(
            session,
            user_id=user_id,
            variant_id=variant_id,
            quantity=2,
            currency_code="inr",
        )
        second = await add_cart_item(
            session,
            user_id=user_id,
            variant_id=variant_id,
            quantity=1,
            currency_code="INR",
        )
        loaded = await get_cart(session, user_id=user_id)

    assert first.id == second.id
    assert loaded is not None
    assert loaded.currency_code == "INR"
    assert len(loaded.items) == 1
    assert loaded.items[0].quantity == 3
    assert loaded.items[0].unit_price_minor == 1999
    assert loaded.items[0].currency_code == "INR"


async def test_cart_rejects_invalid_quantity_currency_and_missing_price(
    integration_engine: AsyncEngine,
    cart_scope: None,
):
    user_id, variant_id = await _seed_user_and_variant(integration_engine)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        with pytest.raises(InvalidCartRequest):
            await add_cart_item(
                session,
                user_id=user_id,
                variant_id=variant_id,
                quantity=0,
                currency_code="INR",
            )
        with pytest.raises(InvalidCartRequest):
            await add_cart_item(
                session,
                user_id=user_id,
                variant_id=variant_id,
                quantity=1000,
                currency_code="INR",
            )
        with pytest.raises(InvalidCartRequest):
            await add_cart_item(
                session,
                user_id=user_id,
                variant_id=variant_id,
                quantity=1,
                currency_code="US",
            )
        with pytest.raises(VariantNotFound):
            await add_cart_item(
                session,
                user_id=user_id,
                variant_id=uuid4(),
                quantity=1,
                currency_code="INR",
            )


async def test_cart_currency_is_fixed_and_item_mutations_are_owned_and_evented(
    integration_engine: AsyncEngine,
    cart_scope: None,
):
    user_id, variant_id = await _seed_user_and_variant(integration_engine)
    other_user_id = uuid4()
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            User(
                id=other_user_id,
                email=f"other-cart-{other_user_id}@example.com",
                password_hash="$argon2id$v=19$m=1,t=1,p=1$test$test",
            )
        )
        await session.commit()
        cart = await add_cart_item(
            session,
            user_id=user_id,
            variant_id=variant_id,
            quantity=1,
            currency_code="INR",
        )
        cart_id = cart.id
        created_events = list(
            await session.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == cart_id))
        )
        assert sorted(event.event_type for event in created_events) == sorted(
            ["cart.created", "cart.item.upserted"]
        )
        await session.commit()
        with pytest.raises(CartCurrencyConflict):
            await add_cart_item(
                session,
                user_id=user_id,
                variant_id=variant_id,
                quantity=1,
                currency_code="USD",
            )
        reloaded = await get_cart(session, user_id=user_id)
        assert reloaded is not None
        item_id = reloaded.items[0].id
        await session.commit()
        with pytest.raises(CartItemNotFound):
            await update_cart_item(
                session,
                user_id=other_user_id,
                item_id=item_id,
                quantity=2,
            )
        updated = await update_cart_item(
            session,
            user_id=user_id,
            item_id=item_id,
            quantity=4,
        )
        assert updated.items[0].quantity == 4
        removed = await remove_cart_item(session, user_id=user_id, item_id=item_id)
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.aggregate_id == cart_id)
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
            )
        )
    assert removed.items == []
    assert sorted(event.event_type for event in events) == sorted(
        [
            "cart.created",
            "cart.item.upserted",
            "cart.item.upserted",
            "cart.item.removed",
        ]
    )

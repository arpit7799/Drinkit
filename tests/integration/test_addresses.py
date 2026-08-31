import logging
from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import AsyncSessionFactory
from app.core.exceptions import FulfillmentLocationNotFound, InvalidCoverageRequest
from app.models.address import CustomerAddress, FulfillmentCoverage
from app.models.auth import User
from app.models.catalog import Product, ProductVariant
from app.models.inventory import FulfillmentLocation
from app.models.outbox_event import OutboxEvent
from app.modules.addresses.service import (
    AddressNotFound,
    create_address,
    deactivate_coverage,
    list_addresses,
    list_coverage,
    resolve_fulfillment_location,
    set_default_address,
    update_address,
    upsert_coverage,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def address_scope(integration_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with AsyncSessionFactory(bind=integration_engine) as session:
        await session.execute(delete(CustomerAddress))
        await session.execute(delete(FulfillmentCoverage))
        await session.execute(delete(FulfillmentLocation))
        await session.execute(delete(ProductVariant))
        await session.execute(delete(Product))
        await session.execute(delete(User))
        await session.commit()


async def _seed_user_and_locations(
    integration_engine: AsyncEngine,
) -> tuple[UUID, UUID, UUID, UUID]:
    user_id = uuid4()
    product_id = uuid4()
    variant_id = uuid4()
    first_location_id = uuid4()
    second_location_id = uuid4()
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            User(
                id=user_id,
                email=f"address-{user_id}@example.com",
                password_hash="$argon2id$v=19$m=1,t=1,p=1$test$test",
            )
        )
        session.add(
            Product(
                id=product_id,
                name="Address Test Product",
                slug=f"address-test-{product_id}",
                is_alcoholic=False,
            )
        )
        session.add(
            ProductVariant(
                id=variant_id,
                product_id=product_id,
                sku=f"ADDRESS-{variant_id}",
                name="One unit",
                quantity_value=Decimal("1"),
                quantity_unit="unit",
            )
        )
        session.add_all(
            [
                FulfillmentLocation(
                    id=first_location_id,
                    code=f"LOC-{first_location_id}",
                    name="North Hub",
                ),
                FulfillmentLocation(
                    id=second_location_id,
                    code=f"LOC-{second_location_id}",
                    name="South Hub",
                ),
            ]
        )
        await session.commit()
    return user_id, first_location_id, second_location_id, variant_id


async def test_default_address_is_replaced_and_fields_are_normalized(
    integration_engine: AsyncEngine,
    address_scope: None,
):
    user_id, _, _, _ = await _seed_user_and_locations(integration_engine)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        first = await create_address(
            session,
            user_id=user_id,
            label="  Home ",
            recipient_name="  Alice Example ",
            line1="  1 Main Street ",
            line2=None,
            city=" Bengaluru ",
            state=" Karnataka ",
            postal_code="560 001",
            country_code="in",
            delivery_instructions="  Call on arrival ",
            is_default=True,
        )
        second = await create_address(
            session,
            user_id=user_id,
            label="Office",
            recipient_name="Alice Example",
            line1="2 Work Street",
            line2=None,
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            country_code="IN",
            delivery_instructions=None,
            is_default=True,
        )
        addresses = await list_addresses(session, user_id=user_id)

    assert first.postal_code == "560001"
    assert first.country_code == "IN"
    assert first.label == "Home"
    assert first.delivery_instructions == "Call on arrival"
    assert second.is_default is True
    assert first.is_default is False
    assert [address.id for address in addresses] == [second.id, first.id]


async def test_address_serviceability_requires_ownership_and_selects_best_active_location(
    integration_engine: AsyncEngine,
    address_scope: None,
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.INFO, logger="app.modules.addresses.service")
    user_id, first_location_id, second_location_id, _ = await _seed_user_and_locations(
        integration_engine
    )
    other_user_id = uuid4()
    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            User(
                id=other_user_id,
                email=f"other-{other_user_id}@example.com",
                password_hash="$argon2id$v=19$m=1,t=1,p=1$test$test",
            )
        )
        session.add_all(
            [
                FulfillmentCoverage(
                    location_id=first_location_id,
                    postal_code="560001",
                    priority=20,
                ),
                FulfillmentCoverage(
                    location_id=second_location_id,
                    postal_code="560001",
                    priority=10,
                ),
                FulfillmentCoverage(
                    location_id=first_location_id,
                    postal_code="560002",
                    priority=1,
                    is_active=False,
                ),
            ]
        )
        await session.commit()
        address = await create_address(
            session,
            user_id=user_id,
            label="Home",
            recipient_name="Alice Example",
            line1="1 Main Street",
            line2=None,
            city="Bengaluru",
            state="Karnataka",
            postal_code="560 001",
            country_code="IN",
            delivery_instructions=None,
            is_default=True,
        )
        selected = await resolve_fulfillment_location(
            session,
            user_id=user_id,
            address_id=address.id,
        )
        with pytest.raises(AddressNotFound):
            await resolve_fulfillment_location(
                session,
                user_id=other_user_id,
                address_id=address.id,
            )

    assert selected is not None
    assert selected.id == second_location_id
    serviceability_logs = [
        record
        for record in caplog.records
        if record.message == "customer_address_serviceability_checked"
    ]
    assert serviceability_logs
    assert serviceability_logs[-1].serviceable is True
    assert serviceability_logs[-1].address_id == str(address.id)
    assert not hasattr(serviceability_logs[-1], "line1")


async def test_set_default_address_rejects_unknown_or_inactive_address(
    integration_engine: AsyncEngine,
    address_scope: None,
):
    user_id, _, _, _ = await _seed_user_and_locations(integration_engine)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        with pytest.raises(AddressNotFound):
            await set_default_address(session, user_id=user_id, address_id=uuid4())


async def test_coverage_management_is_idempotent_and_emits_outbox_events(
    integration_engine: AsyncEngine,
    address_scope: None,
):
    _, first_location_id, _, _ = await _seed_user_and_locations(integration_engine)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        first = await upsert_coverage(
            session,
            location_id=first_location_id,
            postal_code="560 001",
            priority=20,
        )
        second = await upsert_coverage(
            session,
            location_id=first_location_id,
            postal_code="560001",
            priority=5,
        )
        deactivated = await deactivate_coverage(session, coverage_id=first.id)
        all_coverages = await list_coverage(session, location_id=first_location_id)
        active_coverages = await list_coverage(
            session,
            location_id=first_location_id,
            active_only=True,
        )
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.aggregate_id == first.id)
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
            )
        )

    assert second.id == first.id
    assert second.postal_code == "560001"
    assert second.priority == 5
    assert deactivated.is_active is False
    assert [coverage.id for coverage in all_coverages] == [first.id]
    assert active_coverages == []
    assert [event.event_type for event in events] == [
        "fulfillment.coverage.upserted",
        "fulfillment.coverage.upserted",
        "fulfillment.coverage.deactivated",
    ]


async def test_coverage_management_rejects_invalid_input_and_unknown_location(
    integration_engine: AsyncEngine,
    address_scope: None,
):
    async with AsyncSessionFactory(bind=integration_engine) as session:
        with pytest.raises(InvalidCoverageRequest):
            await upsert_coverage(
                session,
                location_id=uuid4(),
                postal_code="560001",
                priority=-1,
            )
        with pytest.raises(FulfillmentLocationNotFound):
            await upsert_coverage(
                session,
                location_id=uuid4(),
                postal_code="560001",
            )
        with pytest.raises(InvalidCoverageRequest):
            await upsert_coverage(
                session,
                location_id=uuid4(),
                postal_code="   ",
            )


async def test_update_address_normalizes_postal_and_country_fields(
    integration_engine: AsyncEngine,
    address_scope: None,
):
    user_id, _, _, _ = await _seed_user_and_locations(integration_engine)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        address = await create_address(
            session,
            user_id=user_id,
            label="Home",
            recipient_name="Alice Example",
            line1="1 Main Street",
            line2=None,
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            country_code="IN",
            delivery_instructions=None,
            is_default=True,
        )
        updated = await update_address(
            session,
            user_id=user_id,
            address_id=address.id,
            values={"postal_code": " 560 002 ", "country_code": "gb"},
            is_default=None,
        )

    assert updated.postal_code == "560002"
    assert updated.country_code == "GB"

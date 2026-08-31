"""Customer address and fulfillment serviceability workflows."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import transaction
from app.core.exceptions import AddressNotFound, InvalidAddressRequest
from app.models.address import CustomerAddress, FulfillmentCoverage
from app.models.auth import User
from app.models.inventory import FulfillmentLocation

_TEXT_FIELDS = {
    "label",
    "recipient_name",
    "line1",
    "line2",
    "city",
    "state",
    "postal_code",
    "country_code",
    "delivery_instructions",
}


def _clean_text(value: str | None, *, required: bool = False) -> str | None:
    cleaned = value.strip() if value is not None else None
    if required and not cleaned:
        raise InvalidAddressRequest
    return cleaned or None


def normalize_postal_code(postal_code: str) -> str:
    """Return the canonical postal-code representation used for coverage lookup."""

    normalized = "".join(postal_code.split()).upper()
    if not normalized:
        raise InvalidAddressRequest
    return normalized


def normalize_country_code(country_code: str) -> str:
    """Return a canonical ISO-like two-letter country code."""

    normalized = country_code.strip().upper()
    if len(normalized) != 2 or not normalized.isalpha():
        raise InvalidAddressRequest
    return normalized


async def _lock_active_user(session: AsyncSession, user_id: UUID) -> User:
    user = await session.scalar(
        select(User).where(User.id == user_id, User.is_active.is_(True)).with_for_update()
    )
    if user is None:
        raise AddressNotFound
    return user


async def create_address(
    session: AsyncSession,
    *,
    user_id: UUID,
    label: str,
    recipient_name: str,
    line1: str,
    line2: str | None,
    city: str,
    state: str,
    postal_code: str,
    country_code: str,
    delivery_instructions: str | None,
    is_default: bool,
) -> CustomerAddress:
    """Create a normalized address and optionally make it the user's default."""

    values = {
        "label": _clean_text(label, required=True),
        "recipient_name": _clean_text(recipient_name, required=True),
        "line1": _clean_text(line1, required=True),
        "line2": _clean_text(line2),
        "city": _clean_text(city, required=True),
        "state": _clean_text(state, required=True),
        "postal_code": normalize_postal_code(postal_code),
        "country_code": normalize_country_code(country_code),
        "delivery_instructions": _clean_text(delivery_instructions),
    }

    async with transaction(session):
        await _lock_active_user(session, user_id)
        if is_default:
            await _clear_default_address(session, user_id)
        address = CustomerAddress(user_id=user_id, is_default=is_default, **values)
        session.add(address)
        await session.flush()
        return address


async def list_addresses(session: AsyncSession, *, user_id: UUID) -> Sequence[CustomerAddress]:
    """Return a user's active addresses with the default address first."""

    result = await session.scalars(
        select(CustomerAddress)
        .where(CustomerAddress.user_id == user_id, CustomerAddress.is_active.is_(True))
        .order_by(
            CustomerAddress.is_default.desc(),
            CustomerAddress.updated_at.desc(),
            CustomerAddress.id,
        )
    )
    return result.all()


async def get_address(
    session: AsyncSession,
    *,
    user_id: UUID,
    address_id: UUID,
    for_update: bool = False,
) -> CustomerAddress:
    """Load one active address belonging to the requested user."""

    statement = select(CustomerAddress).where(
        CustomerAddress.id == address_id,
        CustomerAddress.user_id == user_id,
        CustomerAddress.is_active.is_(True),
    )
    if for_update:
        statement = statement.with_for_update()
    address = await session.scalar(statement)
    if address is None:
        raise AddressNotFound
    return address


async def update_address(
    session: AsyncSession,
    *,
    user_id: UUID,
    address_id: UUID,
    values: dict[str, str | None],
    is_default: bool | None,
) -> CustomerAddress:
    """Update address fields and optionally change its default status."""

    if not values and is_default is None:
        raise InvalidAddressRequest

    async with transaction(session):
        await _lock_active_user(session, user_id)
        address = await get_address(
            session,
            user_id=user_id,
            address_id=address_id,
            for_update=True,
        )
        normalized: dict[str, str | None] = {}
        for field, value in values.items():
            if field not in _TEXT_FIELDS:
                raise InvalidAddressRequest
            normalized[field] = _clean_text(
                value,
                required=field in {"label", "recipient_name", "line1", "city", "state"},
            )
        if "postal_code" in values:
            normalized["postal_code"] = normalize_postal_code(values["postal_code"] or "")
        if "country_code" in values:
            normalized["country_code"] = normalize_country_code(values["country_code"] or "")
        if is_default:
            await _clear_default_address(session, user_id, except_id=address_id)
        for field, value in normalized.items():
            setattr(address, field, value)
        if is_default is not None:
            address.is_default = is_default
        await session.flush()
        await session.refresh(address)
        return address


async def set_default_address(
    session: AsyncSession,
    *,
    user_id: UUID,
    address_id: UUID,
) -> CustomerAddress:
    """Make one active address the user's only default address."""

    async with transaction(session):
        await _lock_active_user(session, user_id)
        address = await get_address(
            session,
            user_id=user_id,
            address_id=address_id,
            for_update=True,
        )
        await _clear_default_address(session, user_id, except_id=address_id)
        address.is_default = True
        await session.flush()
        await session.refresh(address)
        return address


async def deactivate_address(
    session: AsyncSession,
    *,
    user_id: UUID,
    address_id: UUID,
) -> None:
    """Deactivate an address without exposing a hard-delete operation."""

    async with transaction(session):
        await _lock_active_user(session, user_id)
        address = await get_address(
            session,
            user_id=user_id,
            address_id=address_id,
            for_update=True,
        )
        address.is_active = False
        address.is_default = False
        await session.flush()


async def resolve_fulfillment_location(
    session: AsyncSession,
    *,
    user_id: UUID,
    address_id: UUID,
) -> FulfillmentLocation | None:
    """Resolve an owned address to its highest-priority active fulfillment location."""

    address = await get_address(session, user_id=user_id, address_id=address_id)
    return await session.scalar(
        select(FulfillmentLocation)
        .join(FulfillmentCoverage, FulfillmentCoverage.location_id == FulfillmentLocation.id)
        .where(
            FulfillmentLocation.is_active.is_(True),
            FulfillmentCoverage.is_active.is_(True),
            FulfillmentCoverage.postal_code == address.postal_code,
        )
        .order_by(FulfillmentCoverage.priority, FulfillmentLocation.id)
    )


async def _clear_default_address(
    session: AsyncSession,
    user_id: UUID,
    except_id: UUID | None = None,
) -> None:
    statement = (
        update(CustomerAddress)
        .where(
            CustomerAddress.user_id == user_id,
            CustomerAddress.is_active.is_(True),
            CustomerAddress.is_default.is_(True),
        )
        .values(is_default=False)
    )
    if except_id is not None:
        statement = statement.where(CustomerAddress.id != except_id)
    await session.execute(statement)

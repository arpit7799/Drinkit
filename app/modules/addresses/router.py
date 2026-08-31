"""Authenticated customer address and serviceability routes."""

from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User
from app.modules.addresses.schemas import (
    AddressCreateRequest,
    AddressResponse,
    AddressUpdateRequest,
    FulfillmentLocationResponse,
    ServiceabilityResponse,
)
from app.modules.addresses.service import (
    create_address,
    deactivate_address,
    get_address,
    list_addresses,
    resolve_fulfillment_location,
    set_default_address,
    update_address,
)
from app.modules.auth.dependencies import get_current_user

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.post("", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def create(
    request: AddressCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AddressResponse:
    """Create an address owned by the authenticated customer."""

    address = await create_address(
        session,
        user_id=current_user.id,
        **request.model_dump(),
    )
    return AddressResponse.model_validate(address)


@router.get("", response_model=list[AddressResponse])
async def list_all(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Sequence[AddressResponse]:
    """List active addresses owned by the authenticated customer."""

    return [
        AddressResponse.model_validate(address)
        for address in await list_addresses(session, user_id=current_user.id)
    ]


@router.get("/{address_id}", response_model=AddressResponse)
async def get_one(
    address_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AddressResponse:
    """Return one active address owned by the authenticated customer."""

    address = await get_address(session, user_id=current_user.id, address_id=address_id)
    return AddressResponse.model_validate(address)


@router.patch("/{address_id}", response_model=AddressResponse)
async def update_one(
    address_id: UUID,
    request: AddressUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AddressResponse:
    """Update an address owned by the authenticated customer."""

    values = request.model_dump(exclude_unset=True)
    is_default = values.pop("is_default", None)
    address = await update_address(
        session,
        user_id=current_user.id,
        address_id=address_id,
        values=values,
        is_default=is_default,
    )
    return AddressResponse.model_validate(address)


@router.post("/{address_id}/default", response_model=AddressResponse)
async def make_default(
    address_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AddressResponse:
    """Make an active address the customer's default address."""

    address = await set_default_address(
        session,
        user_id=current_user.id,
        address_id=address_id,
    )
    return AddressResponse.model_validate(address)


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one(
    address_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Deactivate an address owned by the authenticated customer."""

    await deactivate_address(session, user_id=current_user.id, address_id=address_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{address_id}/serviceability", response_model=ServiceabilityResponse)
async def serviceability(
    address_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ServiceabilityResponse:
    """Report whether an owned address is covered by an active fulfillment location."""

    location = await resolve_fulfillment_location(
        session,
        user_id=current_user.id,
        address_id=address_id,
    )
    return ServiceabilityResponse(
        serviceable=location is not None,
        fulfillment_location=(
            FulfillmentLocationResponse.model_validate(location) if location is not None else None
        ),
    )

"""Party Mode, collaborative group ordering, and curated packs API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User
from app.modules.auth.dependencies import get_current_user
from app.modules.party.schemas import (
    AddPartyItemRequest,
    AddPartyPackRequest,
    CreatePartySessionRequest,
    JoinPartySessionRequest,
    PartyCheckoutRequest,
    PartyCheckoutResponse,
    PartyPackCreateRequest,
    PartyPackResponse,
    PartyParticipantResponse,
    PartySessionResponse,
    PartyTheme,
    UpdatePartyItemRequest,
)
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
    remove_party_cart_item,
    update_party_cart_item,
)

router = APIRouter(prefix="/party", tags=["party"])


@router.post("/sessions", response_model=PartySessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: CreatePartySessionRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PartySessionResponse:
    """Host creates a new collaborative party room with unique invite code."""

    return await create_party_session(
        session,
        host_user_id=current_user.id,
        title=req.title,
        address_id=req.address_id,
        spending_limit_minor=req.spending_limit_minor,
    )


@router.get("/sessions/{session_id}", response_model=PartySessionResponse)
async def get_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> PartySessionResponse:
    """Retrieve full party session room state with participants and group cart."""

    return await get_party_session_details(session, session_id=session_id)


@router.get("/sessions/code/{invite_code}", response_model=PartySessionResponse)
async def get_session_by_code(
    invite_code: str,
    session: AsyncSession = Depends(get_db),
) -> PartySessionResponse:
    """Lookup party room details by its 6-character invite code."""

    return await get_party_session_by_code(session, invite_code=invite_code)


@router.post(
    "/sessions/join", response_model=PartyParticipantResponse, status_code=status.HTTP_201_CREATED
)
async def join_session(
    req: JoinPartySessionRequest,
    session: AsyncSession = Depends(get_db),
) -> PartyParticipantResponse:
    """Guest joins an active party session using invite code."""

    return await join_party_session(
        session,
        invite_code=req.invite_code,
        nickname=req.nickname,
    )


@router.post("/sessions/{session_id}/items", response_model=PartySessionResponse)
async def add_item(
    session_id: UUID,
    req: AddPartyItemRequest,
    session: AsyncSession = Depends(get_db),
) -> PartySessionResponse:
    """Add a drink, mixer, or snack to the shared party cart."""

    await add_item_to_party_cart(
        session,
        session_id=session_id,
        participant_id=req.participant_id,
        variant_id=req.variant_id,
        quantity=req.quantity,
        note=req.note,
    )
    return await get_party_session_details(session, session_id=session_id)


@router.patch("/sessions/{session_id}/items/{item_id}", response_model=PartySessionResponse)
async def update_item(
    session_id: UUID,
    item_id: UUID,
    req: UpdatePartyItemRequest,
    session: AsyncSession = Depends(get_db),
) -> PartySessionResponse:
    """Modify item quantity in the party cart."""

    await update_party_cart_item(
        session,
        session_id=session_id,
        item_id=item_id,
        participant_id=req.participant_id,
        quantity=req.quantity,
    )
    return await get_party_session_details(session, session_id=session_id)


@router.delete("/sessions/{session_id}/items/{item_id}", response_model=PartySessionResponse)
async def remove_item(
    session_id: UUID,
    item_id: UUID,
    participant_id: UUID = Query(..., description="Participant removing the item"),
    session: AsyncSession = Depends(get_db),
) -> PartySessionResponse:
    """Remove item from the shared party cart."""

    await remove_party_cart_item(
        session,
        session_id=session_id,
        item_id=item_id,
        participant_id=participant_id,
    )
    return await get_party_session_details(session, session_id=session_id)


@router.post("/sessions/{session_id}/add-pack", response_model=PartySessionResponse)
async def add_pack_to_cart(
    session_id: UUID,
    req: AddPartyPackRequest,
    session: AsyncSession = Depends(get_db),
) -> PartySessionResponse:
    """Add all items of a curated party pack bundle directly to the party cart."""

    await add_party_pack_to_party_cart(
        session,
        session_id=session_id,
        participant_id=req.participant_id,
        pack_id=req.pack_id,
    )
    return await get_party_session_details(session, session_id=session_id)


@router.post("/sessions/{session_id}/lock", response_model=PartySessionResponse)
async def lock_cart(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PartySessionResponse:
    """Host locks the party cart before checkout."""

    return await lock_party_cart(session, session_id=session_id, host_user_id=current_user.id)


@router.post("/sessions/{session_id}/checkout", response_model=PartyCheckoutResponse)
async def checkout(
    session_id: UUID,
    req: PartyCheckoutRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PartyCheckoutResponse:
    """Host converts collaborative party cart to a confirmed quick-commerce order."""

    return await checkout_party_cart(
        session,
        session_id=session_id,
        host_user_id=current_user.id,
        coupon_code=req.coupon_code,
        points_to_redeem=req.points_to_redeem,
    )


@router.get("/packs", response_model=list[PartyPackResponse])
async def list_packs(
    theme: PartyTheme | None = Query(default=None, description="Optional theme filter"),
    session: AsyncSession = Depends(get_db),
) -> list[PartyPackResponse]:
    """Browse curated bundles for instant party checkout."""

    return await list_party_packs(session, theme=theme)


@router.post("/packs", response_model=PartyPackResponse, status_code=status.HTTP_201_CREATED)
async def create_pack(
    req: PartyPackCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> PartyPackResponse:
    """Create a curated party bundle or recovery kit."""

    return await create_party_pack(
        session,
        name=req.name,
        slug=req.slug,
        description=req.description,
        theme=req.theme,
        bundle_price_minor=req.bundle_price_minor,
        discount_percent=req.discount_percent,
        items=req.items,
    )

"""Party Mode and collaborative group ordering schemas."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PartySessionStatus(StrEnum):
    """Lifecycle statuses for a collaborative party ordering room."""

    ACTIVE = "active"
    LOCKED = "locked"
    CHECKOUT_PENDING = "checkout_pending"
    ORDERED = "ordered"
    CLOSED = "closed"


class PartyRole(StrEnum):
    """Participant role in party session."""

    HOST = "host"
    GUEST = "guest"


class PartyTheme(StrEnum):
    """Curated party bundle themes."""

    PARTY = "party"
    COCKTAIL = "cocktail"
    RECOVERY = "recovery"
    GAME_NIGHT = "game_night"
    BBQ = "bbq"


class CreatePartySessionRequest(BaseModel):
    """Request to create a new collaborative party session."""

    title: str = Field(min_length=1, max_length=160)
    address_id: UUID
    spending_limit_minor: int | None = Field(default=None, ge=0)


class JoinPartySessionRequest(BaseModel):
    """Request to join a party session using invite code."""

    invite_code: str = Field(min_length=6, max_length=6)
    nickname: str = Field(min_length=1, max_length=100)


class PartyParticipantResponse(BaseModel):
    """Party room member details."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    user_id: UUID | None = None
    nickname: str
    role: str
    is_active: bool


class PartyCartItemResponse(BaseModel):
    """Shared cart item attributed to a specific party participant."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    added_by_participant_id: UUID
    added_by_nickname: str
    variant_id: UUID
    sku: str
    name: str
    quantity: int
    unit_price_minor: int
    line_total_minor: int
    currency_code: str
    note: str | None = None


class PartySessionResponse(BaseModel):
    """Full party room state including participant list and live group cart."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    host_user_id: UUID
    title: str
    invite_code: str
    status: str
    spending_limit_minor: int | None = None
    delivery_address_id: UUID | None = None
    fulfillment_location_id: UUID | None = None
    subtotal_minor: int = 0
    total_items_count: int = 0
    participants: list[PartyParticipantResponse] = Field(default_factory=list)
    items: list[PartyCartItemResponse] = Field(default_factory=list)


class AddPartyItemRequest(BaseModel):
    """Add a drink, mixer, or snack to shared party cart."""

    participant_id: UUID
    variant_id: UUID
    quantity: int = Field(default=1, gt=0)
    note: str | None = Field(default=None, max_length=255)


class UpdatePartyItemRequest(BaseModel):
    """Update item quantity in party cart."""

    participant_id: UUID
    quantity: int = Field(gt=0)


class AddPartyPackRequest(BaseModel):
    """Add all items of a curated party pack to the party cart."""

    participant_id: UUID
    pack_id: UUID


class PartyCheckoutRequest(BaseModel):
    """Host checkout request converting group cart to confirmed order."""

    coupon_code: str | None = None
    points_to_redeem: int = Field(default=0, ge=0)


class PartyCheckoutResponse(BaseModel):
    """Result of converting collaborative cart to confirmed order."""

    order_id: UUID
    session_id: UUID
    total_minor: int
    status: str


class PartyPackItemDetail(BaseModel):
    """Constituent variant inside a curated party pack."""

    variant_id: UUID
    sku: str
    name: str
    quantity: int


class PartyPackCreateItem(BaseModel):
    """Variant specification when creating a party pack."""

    variant_id: UUID
    quantity: int = Field(gt=0)


class PartyPackCreateRequest(BaseModel):
    """Create a curated party bundle or recovery kit."""

    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=160)
    description: str | None = None
    theme: PartyTheme = PartyTheme.PARTY
    bundle_price_minor: int = Field(ge=0)
    discount_percent: int = Field(default=0, ge=0, le=100)
    items: list[PartyPackCreateItem] = Field(min_length=1)


class PartyPackResponse(BaseModel):
    """Curated party pack details."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None = None
    theme: str
    bundle_price_minor: int
    discount_percent: int
    is_active: bool
    items: list[PartyPackItemDetail] = Field(default_factory=list)

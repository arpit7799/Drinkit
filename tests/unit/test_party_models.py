"""Unit tests for Party Mode, collaborative carts, and curated party packs."""

from uuid import uuid4

from app.models.party import (
    PartyCartItem,
    PartyPack,
    PartyPackItem,
    PartyParticipant,
    PartySession,
)
from app.modules.party.schemas import (
    AddPartyItemRequest,
    CreatePartySessionRequest,
    JoinPartySessionRequest,
    PartyCheckoutRequest,
    PartyPackCreateItem,
    PartyPackCreateRequest,
    PartyRole,
    PartySessionStatus,
    PartyTheme,
)


def test_party_enums() -> None:
    assert PartySessionStatus.ACTIVE == "active"
    assert PartySessionStatus.LOCKED == "locked"
    assert PartySessionStatus.ORDERED == "ordered"
    assert PartySessionStatus.CLOSED == "closed"

    assert PartyRole.HOST == "host"
    assert PartyRole.GUEST == "guest"

    assert PartyTheme.PARTY == "party"
    assert PartyTheme.COCKTAIL == "cocktail"
    assert PartyTheme.RECOVERY == "recovery"
    assert PartyTheme.GAME_NIGHT == "game_night"


def test_party_session_and_participant_model() -> None:
    host_id = uuid4()
    session = PartySession(
        host_user_id=host_id,
        title="Arpit's Weekend Rooftop",
        invite_code="PRTY99",
        status="active",
        spending_limit_minor=1000000,
    )
    assert session.host_user_id == host_id
    assert session.invite_code == "PRTY99"
    assert session.status == "active"

    session_constraints = [c.name for c in PartySession.__table__.constraints]
    assert any("invite_code_length" in (c or "") for c in session_constraints)
    assert any("status_valid" in (c or "") for c in session_constraints)

    participant = PartyParticipant(
        session_id=session.id,
        user_id=uuid4(),
        nickname="Rohan",
        role="guest",
    )
    assert participant.nickname == "Rohan"
    assert participant.role == "guest"

    part_constraints = [c.name for c in PartyParticipant.__table__.constraints]
    assert any("role_valid" in (c or "") for c in part_constraints)


def test_party_cart_item_and_pack_models() -> None:
    session_id = uuid4()
    participant_id = uuid4()
    variant_id = uuid4()

    item = PartyCartItem(
        session_id=session_id,
        added_by_participant_id=participant_id,
        variant_id=variant_id,
        quantity=3,
        unit_price_minor=18000,
        currency_code="INR",
        note="For Rohan & Priya",
    )
    assert item.quantity == 3
    assert item.unit_price_minor == 18000

    item_constraints = [c.name for c in PartyCartItem.__table__.constraints]
    assert any("quantity_positive" in (c or "") for c in item_constraints)

    pack = PartyPack(
        name="The Gin & Tonic Station",
        slug="the-gin-and-tonic-station",
        theme="cocktail",
        bundle_price_minor=350000,
        discount_percent=15,
    )
    assert pack.theme == "cocktail"
    assert pack.discount_percent == 15

    pack_constraints = [c.name for c in PartyPack.__table__.constraints]
    assert any("theme_valid" in (c or "") for c in pack_constraints)

    pack_item = PartyPackItem(
        pack_id=pack.id,
        variant_id=variant_id,
        quantity=6,
    )
    assert pack_item.quantity == 6


def test_party_schema_validations() -> None:
    addr_id = uuid4()
    req = CreatePartySessionRequest(
        title="House Party",
        address_id=addr_id,
        spending_limit_minor=500000,
    )
    assert req.title == "House Party"

    join_req = JoinPartySessionRequest(
        invite_code="DRNK88",
        nickname="Kabir",
    )
    assert join_req.invite_code == "DRNK88"

    add_item_req = AddPartyItemRequest(
        participant_id=uuid4(),
        variant_id=uuid4(),
        quantity=2,
        note="Keep ice extra cold",
    )
    assert add_item_req.quantity == 2

    checkout_req = PartyCheckoutRequest(
        coupon_code="PARTY10",
        points_to_redeem=50,
    )
    assert checkout_req.coupon_code == "PARTY10"

    pack_req = PartyPackCreateRequest(
        name="Sunday Recovery Pack",
        slug="sunday-recovery-pack",
        theme=PartyTheme.RECOVERY,
        bundle_price_minor=45000,
        discount_percent=20,
        items=[PartyPackCreateItem(variant_id=uuid4(), quantity=2)],
    )
    assert pack_req.theme == PartyTheme.RECOVERY

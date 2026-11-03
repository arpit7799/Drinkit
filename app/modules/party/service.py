"""Party Mode, collaborative group ordering, and curated party pack workflows."""

import logging
import secrets
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import transaction
from app.core.exceptions import (
    AddressOwnershipError,
    InvalidOrderRequest,
    PartyCartEmpty,
    PartyHostPermissionRequired,
    PartyInviteCodeInvalid,
    PartyItemNotFound,
    PartyPackNotFound,
    PartyParticipantNotFound,
    PartySessionLocked,
    PartySessionNotFound,
    VariantNotFound,
)
from app.models.address import CustomerAddress
from app.models.catalog import ProductVariant
from app.models.inventory import FulfillmentLocation, InventoryBalance, InventoryReservation
from app.models.orders import Order, OrderLine
from app.models.outbox_event import OutboxEvent
from app.models.party import (
    PartyCartItem,
    PartyPack,
    PartyPackItem,
    PartyParticipant,
    PartySession,
)
from app.modules.addresses.service import resolve_fulfillment_location
from app.modules.party.schemas import (
    PartyCartItemResponse,
    PartyCheckoutResponse,
    PartyPackCreateItem,
    PartyPackItemDetail,
    PartyPackResponse,
    PartyParticipantResponse,
    PartyRole,
    PartySessionResponse,
    PartySessionStatus,
    PartyTheme,
)
from app.modules.pricing.service import get_current_variant_price
from app.modules.promotions.service import (
    award_loyalty_points,
    redeem_loyalty_points,
    validate_coupon,
)
from app.modules.promotions.tax import calculate_order_taxes
from app.modules.warehouse.service import create_fulfillment_task_for_order

logger = logging.getLogger(__name__)

INVITE_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DELIVERY_FEE_MINOR = 2900  # ₹29.00


async def _generate_unique_invite_code(session: AsyncSession) -> str:
    """Generate an unambiguous, collision-free 6-character party room code."""
    for _ in range(10):
        code = "".join(secrets.choice(INVITE_CODE_CHARS) for _ in range(6))
        existing = await session.scalar(
            select(PartySession).where(PartySession.invite_code == code)
        )
        if existing is None:
            return code
    raise RuntimeError("Failed to generate unique party invite code.")


async def create_party_session(
    session: AsyncSession,
    *,
    host_user_id: UUID,
    title: str,
    address_id: UUID,
    spending_limit_minor: int | None = None,
) -> PartySessionResponse:
    """Host launches a collaborative party group cart."""

    async with transaction(session):
        address = await session.scalar(
            select(CustomerAddress).where(
                CustomerAddress.id == address_id,
                CustomerAddress.user_id == host_user_id,
                CustomerAddress.is_active.is_(True),
            )
        )
        if address is None:
            raise AddressOwnershipError

        location = await resolve_fulfillment_location(
            session, user_id=host_user_id, address_id=address_id
        )
        invite_code = await _generate_unique_invite_code(session)

        party = PartySession(
            host_user_id=host_user_id,
            title=title.strip(),
            invite_code=invite_code,
            status=PartySessionStatus.ACTIVE.value,
            spending_limit_minor=spending_limit_minor,
            delivery_address_id=address_id,
            fulfillment_location_id=location.id if location else None,
        )
        session.add(party)
        await session.flush()

        # Add Host as initial participant
        host_participant = PartyParticipant(
            session_id=party.id,
            user_id=host_user_id,
            nickname="Host",
            role=PartyRole.HOST.value,
            is_active=True,
        )
        session.add(host_participant)
        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="party_session",
                aggregate_id=party.id,
                event_type="party.session.created",
                payload={
                    "host_user_id": str(host_user_id),
                    "invite_code": invite_code,
                    "title": party.title,
                },
            )
        )
        return await get_party_session_details(session, session_id=party.id)


async def get_party_session_details(
    session: AsyncSession,
    *,
    session_id: UUID,
) -> PartySessionResponse:
    """Retrieve complete party session room state with participants and items."""

    party = await session.scalar(
        select(PartySession)
        .options(
            selectinload(PartySession.participants),
            selectinload(PartySession.items),
        )
        .where(PartySession.id == session_id)
    )
    if party is None:
        raise PartySessionNotFound

    participant_map = {p.id: p.nickname for p in party.participants}
    variant_ids = [item.variant_id for item in party.items]

    variants_map: dict[UUID, ProductVariant] = {}
    if variant_ids:
        v_rows = (
            await session.scalars(select(ProductVariant).where(ProductVariant.id.in_(variant_ids)))
        ).all()
        variants_map = {v.id: v for v in v_rows}

    item_responses: list[PartyCartItemResponse] = []
    subtotal_minor = 0
    total_count = 0

    for item in party.items:
        v = variants_map.get(item.variant_id)
        sku = v.sku if v else "UNKNOWN"
        name = v.name if v else "Unknown Item"
        line_total = item.quantity * item.unit_price_minor
        subtotal_minor += line_total
        total_count += item.quantity

        item_responses.append(
            PartyCartItemResponse(
                id=item.id,
                session_id=item.session_id,
                added_by_participant_id=item.added_by_participant_id,
                added_by_nickname=participant_map.get(item.added_by_participant_id, "Guest"),
                variant_id=item.variant_id,
                sku=sku,
                name=name,
                quantity=item.quantity,
                unit_price_minor=item.unit_price_minor,
                line_total_minor=line_total,
                currency_code=item.currency_code,
                note=item.note,
            )
        )

    return PartySessionResponse(
        id=party.id,
        host_user_id=party.host_user_id,
        title=party.title,
        invite_code=party.invite_code,
        status=party.status,
        spending_limit_minor=party.spending_limit_minor,
        delivery_address_id=party.delivery_address_id,
        fulfillment_location_id=party.fulfillment_location_id,
        subtotal_minor=subtotal_minor,
        total_items_count=total_count,
        participants=[PartyParticipantResponse.model_validate(p) for p in party.participants],
        items=item_responses,
    )


async def get_party_session_by_code(
    session: AsyncSession,
    *,
    invite_code: str,
) -> PartySessionResponse:
    """Find and return party room details by its 6-character room code."""

    clean_code = invite_code.strip().upper()
    party = await session.scalar(select(PartySession).where(PartySession.invite_code == clean_code))
    if party is None:
        raise PartyInviteCodeInvalid
    return await get_party_session_details(session, session_id=party.id)


async def join_party_session(
    session: AsyncSession,
    *,
    invite_code: str,
    nickname: str,
    user_id: UUID | None = None,
) -> PartyParticipantResponse:
    """Guest joins an active party room."""

    clean_code = invite_code.strip().upper()
    clean_nick = nickname.strip()
    if not clean_nick:
        clean_nick = "Party Guest"

    async with transaction(session):
        party = await session.scalar(
            select(PartySession).where(PartySession.invite_code == clean_code).with_for_update()
        )
        if party is None or party.status not in (
            PartySessionStatus.ACTIVE.value,
            PartySessionStatus.LOCKED.value,
        ):
            raise PartyInviteCodeInvalid

        # If registered user already joined, return existing
        if user_id is not None:
            existing = await session.scalar(
                select(PartyParticipant).where(
                    PartyParticipant.session_id == party.id,
                    PartyParticipant.user_id == user_id,
                )
            )
            if existing is not None:
                return PartyParticipantResponse.model_validate(existing)

        participant = PartyParticipant(
            session_id=party.id,
            user_id=user_id,
            nickname=clean_nick,
            role=PartyRole.GUEST.value,
            is_active=True,
        )
        session.add(participant)
        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="party_session",
                aggregate_id=party.id,
                event_type="party.participant.joined",
                payload={"nickname": clean_nick, "user_id": str(user_id) if user_id else None},
            )
        )
        return PartyParticipantResponse.model_validate(participant)


async def add_item_to_party_cart(
    session: AsyncSession,
    *,
    session_id: UUID,
    participant_id: UUID,
    variant_id: UUID,
    quantity: int = 1,
    note: str | None = None,
) -> PartyCartItem:
    """Add a drink, snack, or mixer to the collaborative party cart."""

    if quantity <= 0:
        raise InvalidOrderRequest

    async with transaction(session):
        party = await session.scalar(
            select(PartySession).where(PartySession.id == session_id).with_for_update()
        )
        if party is None:
            raise PartySessionNotFound
        if party.status != PartySessionStatus.ACTIVE.value:
            raise PartySessionLocked

        participant = await session.scalar(
            select(PartyParticipant).where(
                PartyParticipant.id == participant_id,
                PartyParticipant.session_id == session_id,
            )
        )
        if participant is None or not participant.is_active:
            raise PartyParticipantNotFound

        # Fetch active variant price
        price = await get_current_variant_price(session, variant_id=variant_id, currency_code="INR")
        if price is None:
            raise VariantNotFound

        # Check existing item by participant
        existing_item = await session.scalar(
            select(PartyCartItem)
            .where(
                PartyCartItem.session_id == session_id,
                PartyCartItem.added_by_participant_id == participant_id,
                PartyCartItem.variant_id == variant_id,
            )
            .with_for_update()
        )

        if existing_item is not None:
            existing_item.quantity += quantity
            if note:
                existing_item.note = note.strip()
            item = existing_item
        else:
            item = PartyCartItem(
                session_id=session_id,
                added_by_participant_id=participant_id,
                variant_id=variant_id,
                quantity=quantity,
                unit_price_minor=price.amount_minor,
                currency_code="INR",
                note=note.strip() if note else None,
            )
            session.add(item)

        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="party_session",
                aggregate_id=party.id,
                event_type="party.cart.item_added",
                payload={
                    "session_id": str(session_id),
                    "participant_id": str(participant_id),
                    "variant_id": str(variant_id),
                    "quantity": quantity,
                },
            )
        )
        return item


async def update_party_cart_item(
    session: AsyncSession,
    *,
    session_id: UUID,
    item_id: UUID,
    participant_id: UUID,
    quantity: int,
) -> None:
    """Modify item quantity or delete item in party cart."""

    async with transaction(session):
        party = await session.scalar(
            select(PartySession).where(PartySession.id == session_id).with_for_update()
        )
        if party is None:
            raise PartySessionNotFound
        if party.status != PartySessionStatus.ACTIVE.value:
            raise PartySessionLocked

        item = await session.scalar(
            select(PartyCartItem).where(
                PartyCartItem.id == item_id,
                PartyCartItem.session_id == session_id,
            )
        )
        if item is None:
            raise PartyItemNotFound

        # Verify participant or host permission
        participant = await session.scalar(
            select(PartyParticipant).where(PartyParticipant.id == participant_id)
        )
        if participant is None:
            raise PartyParticipantNotFound

        if (
            item.added_by_participant_id != participant_id
            and participant.role != PartyRole.HOST.value
        ):
            raise PartyHostPermissionRequired

        if quantity <= 0:
            await session.delete(item)
        else:
            item.quantity = quantity
        await session.flush()


async def remove_party_cart_item(
    session: AsyncSession,
    *,
    session_id: UUID,
    item_id: UUID,
    participant_id: UUID,
) -> None:
    """Remove item from party cart."""

    await update_party_cart_item(
        session,
        session_id=session_id,
        item_id=item_id,
        participant_id=participant_id,
        quantity=0,
    )


async def add_party_pack_to_party_cart(
    session: AsyncSession,
    *,
    session_id: UUID,
    participant_id: UUID,
    pack_id: UUID,
) -> None:
    """Add all items in a curated bundle directly into the party cart."""

    async with transaction(session):
        pack = await session.scalar(
            select(PartyPack)
            .options(selectinload(PartyPack.items))
            .where(PartyPack.id == pack_id, PartyPack.is_active.is_(True))
        )
        if pack is None:
            raise PartyPackNotFound

        for pack_item in pack.items:
            await add_item_to_party_cart(
                session,
                session_id=session_id,
                participant_id=participant_id,
                variant_id=pack_item.variant_id,
                quantity=pack_item.quantity,
                note=f"Bundle: {pack.name}",
            )


async def lock_party_cart(
    session: AsyncSession,
    *,
    session_id: UUID,
    host_user_id: UUID,
) -> PartySessionResponse:
    """Host locks the party cart to prevent modifications before checkout."""

    async with transaction(session):
        party = await session.scalar(
            select(PartySession).where(PartySession.id == session_id).with_for_update()
        )
        if party is None:
            raise PartySessionNotFound
        if party.host_user_id != host_user_id:
            raise PartyHostPermissionRequired

        party.status = PartySessionStatus.LOCKED.value
        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="party_session",
                aggregate_id=party.id,
                event_type="party.cart.locked",
                payload={"session_id": str(session_id)},
            )
        )
        return await get_party_session_details(session, session_id=session_id)


async def checkout_party_cart(
    session: AsyncSession,
    *,
    session_id: UUID,
    host_user_id: UUID,
    coupon_code: str | None = None,
    points_to_redeem: int = 0,
) -> PartyCheckoutResponse:
    """Host converts collaborative party cart to a confirmed order."""

    async with transaction(session):
        party = await session.scalar(
            select(PartySession)
            .options(selectinload(PartySession.items))
            .where(PartySession.id == session_id)
            .with_for_update()
        )
        if party is None:
            raise PartySessionNotFound
        if party.host_user_id != host_user_id:
            raise PartyHostPermissionRequired
        if not party.items:
            raise PartyCartEmpty
        if party.status in (PartySessionStatus.ORDERED.value, PartySessionStatus.CLOSED.value):
            raise InvalidOrderRequest

        address = await session.scalar(
            select(CustomerAddress).where(CustomerAddress.id == party.delivery_address_id)
        )
        if address is None:
            raise AddressOwnershipError

        location = await session.scalar(
            select(FulfillmentLocation).where(
                FulfillmentLocation.id == party.fulfillment_location_id
            )
        )
        if location is None:
            location = await resolve_fulfillment_location(
                session, user_id=host_user_id, address_id=address.id
            )
            if location is None:
                raise InvalidOrderRequest

        # Consolidate duplicate variants across participants
        variant_totals: dict[UUID, int] = defaultdict(int)
        for item in party.items:
            variant_totals[item.variant_id] += item.quantity

        # Reserve inventory and build order lines
        order_lines: list[OrderLine] = []
        now = datetime.now(UTC)
        expires_at = now.replace(minute=(now.minute + 15) % 60)
        subtotal_minor = 0

        for variant_id, total_qty in variant_totals.items():
            price = await get_current_variant_price(
                session, variant_id=variant_id, currency_code="INR"
            )
            if price is None:
                raise VariantNotFound

            # Lock and reserve stock
            balance = await session.scalar(
                select(InventoryBalance)
                .where(
                    InventoryBalance.location_id == location.id,
                    InventoryBalance.variant_id == variant_id,
                )
                .with_for_update()
            )
            if (
                balance is None
                or (balance.on_hand_quantity - balance.reserved_quantity) < total_qty
            ):
                raise InvalidOrderRequest

            balance.reserved_quantity += Decimal(str(total_qty))
            res = InventoryReservation(
                location_id=location.id,
                variant_id=variant_id,
                reservation_key=f"party-{session_id}-{variant_id}-{now.timestamp()}",
                quantity=Decimal(str(total_qty)),
                status="consumed",
                expires_at=expires_at,
            )
            session.add(res)

            line_total = total_qty * price.amount_minor
            subtotal_minor += line_total

            order_lines.append(
                OrderLine(
                    variant_id=variant_id,
                    price_id=price.id,
                    quantity=total_qty,
                    currency_code="INR",
                    unit_price_minor=price.amount_minor,
                    line_total_minor=line_total,
                )
            )

        # Calculate taxes
        tax_items = [
            {
                "variant_id": line.variant_id,
                "line_subtotal_minor": line.line_total_minor,
            }
            for line in order_lines
        ]
        tax_res = await calculate_order_taxes(
            session,
            postal_code=address.postal_code,
            items=tax_items,
        )
        tax_minor = tax_res.total_tax_minor

        delivery_fee_minor = DELIVERY_FEE_MINOR
        total_minor = subtotal_minor + tax_minor + delivery_fee_minor

        # Apply coupon & loyalty
        if coupon_code:
            coupon, coupon_discount_minor = await validate_coupon(
                session,
                code=coupon_code,
                cart_subtotal_minor=subtotal_minor,
                customer_id=host_user_id,
            )
            total_minor = max(0, total_minor - coupon_discount_minor)

        if points_to_redeem > 0:
            redeemed_minor = await redeem_loyalty_points(
                session, customer_id=host_user_id, points_to_redeem=points_to_redeem
            )
            total_minor = max(0, total_minor - redeemed_minor)

        # Create Order
        order = Order(
            user_id=host_user_id,
            address_id=address.id,
            status="confirmed",
            currency_code="INR",
            subtotal_minor=subtotal_minor,
            tax_minor=tax_minor,
            delivery_fee_minor=delivery_fee_minor,
            total_minor=total_minor,
            payment_status="pending",
        )
        session.add(order)
        await session.flush()

        for line in order_lines:
            line.order_id = order.id
            session.add(line)
        await session.flush()

        # Create dark store fulfillment task for pickers
        await create_fulfillment_task_for_order(
            session,
            order_id=order.id,
            location_id=location.id,
        )

        # Award host loyalty points
        await award_loyalty_points(
            session,
            customer_id=host_user_id,
            order_id=order.id,
            order_total_minor=total_minor,
        )

        # Transition party status
        party.status = PartySessionStatus.ORDERED.value
        party.closed_at = now
        await session.flush()

        session.add(
            OutboxEvent(
                aggregate_type="party_session",
                aggregate_id=party.id,
                event_type="party.session.ordered",
                payload={"order_id": str(order.id), "total_minor": total_minor},
            )
        )
        return PartyCheckoutResponse(
            order_id=order.id,
            session_id=session_id,
            total_minor=total_minor,
            status="confirmed",
        )


async def create_party_pack(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    description: str | None,
    theme: PartyTheme,
    bundle_price_minor: int,
    discount_percent: int,
    items: list[PartyPackCreateItem],
) -> PartyPackResponse:
    """Create a curated party bundle or recovery pack."""

    async with transaction(session):
        pack = PartyPack(
            name=name.strip(),
            slug=slug.strip().lower(),
            description=description,
            theme=theme.value,
            bundle_price_minor=bundle_price_minor,
            discount_percent=discount_percent,
            is_active=True,
        )
        session.add(pack)
        await session.flush()

        for itm in items:
            p_item = PartyPackItem(
                pack_id=pack.id,
                variant_id=itm.variant_id,
                quantity=itm.quantity,
            )
            session.add(p_item)

        await session.flush()

        # Load details
        variant_ids = [itm.variant_id for itm in items]
        variants = (
            await session.scalars(select(ProductVariant).where(ProductVariant.id.in_(variant_ids)))
        ).all()
        v_map = {v.id: v for v in variants}

        details = [
            PartyPackItemDetail(
                variant_id=itm.variant_id,
                sku=v_map[itm.variant_id].sku if itm.variant_id in v_map else "SKU",
                name=v_map[itm.variant_id].name if itm.variant_id in v_map else "Item",
                quantity=itm.quantity,
            )
            for itm in items
        ]

        return PartyPackResponse(
            id=pack.id,
            name=pack.name,
            slug=pack.slug,
            description=pack.description,
            theme=pack.theme,
            bundle_price_minor=pack.bundle_price_minor,
            discount_percent=pack.discount_percent,
            is_active=pack.is_active,
            items=details,
        )


async def list_party_packs(
    session: AsyncSession,
    *,
    theme: PartyTheme | None = None,
) -> list[PartyPackResponse]:
    """Browse curated bundles for instant party checkout."""

    stmt = (
        select(PartyPack)
        .options(selectinload(PartyPack.items))
        .where(PartyPack.is_active.is_(True))
    )
    if theme is not None:
        stmt = stmt.where(PartyPack.theme == theme.value)

    packs = (await session.scalars(stmt)).all()
    variant_ids = [item.variant_id for p in packs for item in p.items]
    v_map: dict[UUID, ProductVariant] = {}
    if variant_ids:
        variants = (
            await session.scalars(select(ProductVariant).where(ProductVariant.id.in_(variant_ids)))
        ).all()
        v_map = {v.id: v for v in variants}

    results: list[PartyPackResponse] = []
    for p in packs:
        details = [
            PartyPackItemDetail(
                variant_id=it.variant_id,
                sku=v_map[it.variant_id].sku if it.variant_id in v_map else "SKU",
                name=v_map[it.variant_id].name if it.variant_id in v_map else "Item",
                quantity=it.quantity,
            )
            for it in p.items
        ]
        results.append(
            PartyPackResponse(
                id=p.id,
                name=p.name,
                slug=p.slug,
                description=p.description,
                theme=p.theme,
                bundle_price_minor=p.bundle_price_minor,
                discount_percent=p.discount_percent,
                is_active=p.is_active,
                items=details,
            )
        )
    return results

"""Alcohol compliance, KYC verification, dry days, and doorstep handover services."""

import hashlib
import logging
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AlcoholHoursRestriction,
    AlcoholVolumeExceeded,
    DeliveryComplianceNotFound,
    DryDayRestriction,
    InvalidHandoverOTP,
    KYCRequiredForAlcohol,
    UnderageAlcoholPurchase,
)
from app.models.compliance import (
    CustomerKYC,
    DeliveryComplianceLog,
    DryDaySchedule,
    KYCStatus,
    StateAlcoholRegulation,
)
from app.modules.compliance.schemas import KYCSubmissionRequest

logger = logging.getLogger(__name__)

DEFAULT_LEGAL_DRINKING_AGE = 21


def calculate_age(date_of_birth: date, as_of: date | None = None) -> int:
    """Calculate exact chronological age in years."""
    today = as_of or datetime.now(UTC).date()
    age = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1
    return age


def hash_id_number(id_number: str) -> str:
    """Produce SHA-256 hash of normalized government ID number."""
    normalized = id_number.strip().upper().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


async def get_customer_kyc(session: AsyncSession, customer_id: UUID) -> CustomerKYC | None:
    """Retrieve existing KYC verification record for customer."""
    return await session.scalar(select(CustomerKYC).where(CustomerKYC.customer_id == customer_id))


async def submit_customer_kyc(
    session: AsyncSession,
    customer_id: UUID,
    request: KYCSubmissionRequest,
) -> CustomerKYC:
    """Process and record customer government ID submission."""
    verified_age = calculate_age(request.date_of_birth)
    id_hash = hash_id_number(request.id_number)
    id_last4 = request.id_number.strip()[-4:]

    kyc = await get_customer_kyc(session, customer_id)
    now = datetime.now(UTC)

    if kyc is None:
        kyc = CustomerKYC(
            customer_id=customer_id,
            id_type=request.id_type,
            id_number_hash=id_hash,
            id_number_last4=id_last4,
            date_of_birth=request.date_of_birth,
            verified_age=verified_age,
            status=KYCStatus.VERIFIED if verified_age >= 18 else KYCStatus.REJECTED,
            rejection_reason=(
                None if verified_age >= 18 else "Age is below 18 years statutory threshold"
            ),
            verified_at=now if verified_age >= 18 else None,
        )
        session.add(kyc)
    else:
        kyc.id_type = request.id_type
        kyc.id_number_hash = id_hash
        kyc.id_number_last4 = id_last4
        kyc.date_of_birth = request.date_of_birth
        kyc.verified_age = verified_age
        kyc.status = KYCStatus.VERIFIED if verified_age >= 18 else KYCStatus.REJECTED
        kyc.rejection_reason = (
            None if verified_age >= 18 else "Age is below 18 years statutory threshold"
        )
        kyc.verified_at = now if verified_age >= 18 else None

    await session.flush()
    return kyc


async def get_state_regulation(
    session: AsyncSession, state_code: str
) -> StateAlcoholRegulation | None:
    """Fetch statutory alcohol parameters for a designated state."""
    return await session.scalar(
        select(StateAlcoholRegulation).where(
            StateAlcoholRegulation.state_code == state_code.strip().upper()
        )
    )


async def verify_alcohol_compliance(
    session: AsyncSession,
    *,
    customer_id: UUID,
    state_code: str,
    has_alcohol: bool,
    total_litres: Decimal = Decimal("0.0"),
    order_time: datetime | None = None,
) -> bool:
    """Verify statutory legal drinking age, KYC, dry days, and operating hours.

    Raises:
        KYCRequiredForAlcohol: When customer lacks a verified KYC record.
        UnderageAlcoholPurchase: When customer is below destination state LDA.
        DryDayRestriction: When delivery falls on a state-prohibited dry day.
        AlcoholHoursRestriction: When order is placed outside state sales hours.
        AlcoholVolumeExceeded: When total spirits volume exceeds legal cap.
    """
    if not has_alcohol:
        return True

    now = order_time or datetime.now(UTC)
    current_date = now.date()
    current_time = now.time()

    # 1. KYC verification check
    kyc = await get_customer_kyc(session, customer_id)
    if kyc is None or kyc.status != KYCStatus.VERIFIED:
        raise KYCRequiredForAlcohol()

    # 2. State legal drinking age check
    reg = await get_state_regulation(session, state_code)
    lda = reg.minimum_legal_drinking_age if reg else DEFAULT_LEGAL_DRINKING_AGE
    if kyc.verified_age < lda:
        logger.warning(
            "underage_alcohol_attempt",
            extra={"customer_id": str(customer_id), "age": kyc.verified_age, "lda": lda},
        )
        raise UnderageAlcoholPurchase()

    # 3. Dry day check
    dry_day = await session.scalar(
        select(DryDaySchedule).where(
            DryDaySchedule.state_code == state_code.strip().upper(),
            DryDaySchedule.dry_date == current_date,
        )
    )
    if dry_day is not None:
        if dry_day.is_full_day:
            raise DryDayRestriction()
        if (
            dry_day.start_time
            and dry_day.end_time
            and dry_day.start_time <= current_time <= dry_day.end_time
        ):
            raise DryDayRestriction()

    # 4. Operating hours check
    if reg is not None:
        if not (reg.operating_hours_start <= current_time <= reg.operating_hours_end):
            raise AlcoholHoursRestriction()

        # 5. Volume limitation check
        if total_litres > reg.max_spirits_litres_per_order:
            raise AlcoholVolumeExceeded()

    return True


async def create_delivery_compliance_log(
    session: AsyncSession,
    *,
    order_id: UUID,
    customer_id: UUID,
    courier_id: UUID | None = None,
) -> DeliveryComplianceLog:
    """Initialize doorstep compliance handover log with secure 6-digit OTP."""
    otp = f"{secrets.randbelow(900000) + 100000}"
    compliance_log = DeliveryComplianceLog(
        order_id=order_id,
        customer_id=customer_id,
        courier_id=courier_id,
        recipient_age_verified=False,
        handover_otp_verified=False,
        handover_otp=otp,
        audit_metadata={"created_at": datetime.now(UTC).isoformat()},
    )
    session.add(compliance_log)
    await session.flush()
    return compliance_log


async def verify_delivery_handover(
    session: AsyncSession,
    *,
    order_id: UUID,
    courier_id: UUID | None,
    handover_otp: str,
    recipient_age_confirmed: bool,
) -> DeliveryComplianceLog:
    """Verify courier handover at customer doorstep."""
    log = await session.scalar(
        select(DeliveryComplianceLog).where(DeliveryComplianceLog.order_id == order_id)
    )
    if log is None:
        raise DeliveryComplianceNotFound()

    if log.handover_otp != handover_otp.strip():
        raise InvalidHandoverOTP()

    log.handover_otp_verified = True
    log.recipient_age_verified = recipient_age_confirmed
    log.courier_id = courier_id or log.courier_id
    log.verified_at = datetime.now(UTC)

    meta = dict(log.audit_metadata or {})
    meta["verified_at"] = log.verified_at.isoformat()
    meta["courier_id"] = str(courier_id) if courier_id else None
    meta["recipient_age_confirmed"] = recipient_age_confirmed
    log.audit_metadata = meta

    await session.flush()
    return log

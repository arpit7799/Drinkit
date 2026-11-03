"""Integration tests for alcohol compliance, KYC, and regulatory verification."""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.database import AsyncSessionFactory
from app.core.exceptions import (
    AlcoholHoursRestriction,
    AlcoholVolumeExceeded,
    DryDayRestriction,
    InvalidHandoverOTP,
    KYCRequiredForAlcohol,
    UnderageAlcoholPurchase,
)
from app.models.address import CustomerAddress
from app.models.auth import User
from app.models.compliance import (
    DryDaySchedule,
    GovtIdType,
    KYCStatus,
    StateAlcoholRegulation,
)
from app.models.orders import Order
from app.modules.compliance.schemas import KYCSubmissionRequest
from app.modules.compliance.service import (
    calculate_age,
    create_delivery_compliance_log,
    hash_id_number,
    submit_customer_kyc,
    verify_alcohol_compliance,
    verify_delivery_handover,
)

pytestmark = pytest.mark.integration


def test_age_calculation_and_hashing():
    dob = date(2000, 1, 15)
    as_of = date(2026, 1, 14)
    assert calculate_age(dob, as_of=as_of) == 25
    as_of_birthday = date(2026, 1, 15)
    assert calculate_age(dob, as_of=as_of_birthday) == 26

    h1 = hash_id_number("ABCD1234E")
    h2 = hash_id_number("abcd1234e")
    assert h1 == h2
    assert len(h1) == 64


@pytest.mark.asyncio
async def test_kyc_submission_adult_vs_minor(integration_engine):
    user_id = uuid4()
    minor_id = uuid4()

    async with AsyncSessionFactory(bind=integration_engine) as session:
        # Create users
        session.add(
            User(
                id=user_id,
                email=f"adult-{user_id}@example.com",
                password_hash="test",
                is_active=True,
            )
        )
        session.add(
            User(
                id=minor_id,
                email=f"minor-{minor_id}@example.com",
                password_hash="test",
                is_active=True,
            )
        )
        await session.flush()

        # 1. Adult submission: Age 24
        req_adult = KYCSubmissionRequest(
            id_type=GovtIdType.AADHAAR,
            id_number="123456789012",
            date_of_birth=date(2002, 5, 20),
        )
        kyc_adult = await submit_customer_kyc(session, user_id, req_adult)
        await session.commit()

        assert kyc_adult.status == KYCStatus.VERIFIED
        assert kyc_adult.verified_age >= 21
        assert kyc_adult.id_number_last4 == "9012"
        assert kyc_adult.verified_at is not None

        # 2. Minor submission: Age 16
        req_minor = KYCSubmissionRequest(
            id_type=GovtIdType.PAN,
            id_number="ABCDE1234F",
            date_of_birth=date(2010, 8, 15),
        )
        kyc_minor = await submit_customer_kyc(session, minor_id, req_minor)
        await session.commit()

        assert kyc_minor.status == KYCStatus.REJECTED
        assert kyc_minor.verified_age < 18
        assert "below 18" in kyc_minor.rejection_reason


@pytest.mark.asyncio
async def test_verify_alcohol_compliance_regulations(integration_engine):
    user_id = uuid4()
    delhi_user_id = uuid4()
    state_code = "MH"
    delhi_state = "DL"

    async with AsyncSessionFactory(bind=integration_engine) as session:
        # Pre-clean regulations for isolation
        await session.execute(
            delete(DryDaySchedule).where(DryDaySchedule.state_code.in_([state_code, delhi_state]))
        )
        await session.execute(
            delete(StateAlcoholRegulation).where(
                StateAlcoholRegulation.state_code.in_([state_code, delhi_state])
            )
        )
        await session.commit()

        # Users: Adult user (age 22)
        session.add(
            User(
                id=user_id,
                email=f"comp-{user_id}@example.com",
                password_hash="test",
                is_active=True,
            )
        )
        session.add(
            User(
                id=delhi_user_id,
                email=f"delhi-{delhi_user_id}@example.com",
                password_hash="test",
                is_active=True,
            )
        )
        await session.flush()

        # KYC: Age 22
        req_user = KYCSubmissionRequest(
            id_type=GovtIdType.DRIVING_LICENSE,
            id_number="DL1420110012345",
            date_of_birth=date(2004, 3, 10),
        )
        await submit_customer_kyc(session, user_id, req_user)
        await submit_customer_kyc(session, delhi_user_id, req_user)

        # Regulations:
        # MH: LDA = 21, Operating Hours = 08:00 to 23:00, Max litres = 10.0L
        reg_mh = StateAlcoholRegulation(
            state_code=state_code,
            state_name="Maharashtra",
            minimum_legal_drinking_age=21,
            operating_hours_start=time(8, 0),
            operating_hours_end=time(23, 0),
            max_spirits_litres_per_order=Decimal("10.00"),
            delivery_handover_otp_required=True,
        )
        # DL: LDA = 25 (Delhi legal drinking age is 25)
        reg_dl = StateAlcoholRegulation(
            state_code=delhi_state,
            state_name="Delhi",
            minimum_legal_drinking_age=25,
            operating_hours_start=time(10, 0),
            operating_hours_end=time(22, 0),
            max_spirits_litres_per_order=Decimal("9.00"),
            delivery_handover_otp_required=True,
        )
        session.add_all([reg_mh, reg_dl])
        await session.commit()

        # 1. Non-alcoholic order passes with no KYC
        unverified_id = uuid4()
        session.add(
            User(
                id=unverified_id,
                email=f"unver-{unverified_id}@example.com",
                password_hash="test",
                is_active=True,
            )
        )
        await session.commit()
        assert (
            await verify_alcohol_compliance(
                session, customer_id=unverified_id, state_code="MH", has_alcohol=False
            )
            is True
        )

        # 2. Alcoholic order with unverified user raises KYCRequiredForAlcohol
        with pytest.raises(KYCRequiredForAlcohol):
            await verify_alcohol_compliance(
                session, customer_id=unverified_id, state_code="MH", has_alcohol=True
            )

        # 3. Adult (age 22) in MH (LDA 21) during operating hours passes
        order_time_valid = datetime(2026, 6, 15, 14, 0, tzinfo=UTC)
        assert (
            await verify_alcohol_compliance(
                session,
                customer_id=user_id,
                state_code=state_code,
                has_alcohol=True,
                total_litres=Decimal("2.5"),
                order_time=order_time_valid,
            )
            is True
        )

        # 4. Same adult (age 22) in Delhi (LDA 25) raises UnderageAlcoholPurchase
        with pytest.raises(UnderageAlcoholPurchase):
            await verify_alcohol_compliance(
                session,
                customer_id=delhi_user_id,
                state_code=delhi_state,
                has_alcohol=True,
                total_litres=Decimal("2.5"),
                order_time=order_time_valid,
            )

        # 5. Order on a dry day raises DryDayRestriction
        dry_date = date(2026, 10, 2)
        session.add(
            DryDaySchedule(
                state_code=state_code, dry_date=dry_date, reason="Gandhi Jayanti", is_full_day=True
            )
        )
        await session.commit()

        order_time_dry_day = datetime(2026, 10, 2, 14, 0, tzinfo=UTC)
        with pytest.raises(DryDayRestriction):
            await verify_alcohol_compliance(
                session,
                customer_id=user_id,
                state_code=state_code,
                has_alcohol=True,
                order_time=order_time_dry_day,
            )

        # 6. Order outside operating hours (e.g. 02:00 AM) raises AlcoholHoursRestriction
        late_night_time = datetime(2026, 6, 15, 2, 0, tzinfo=UTC)
        with pytest.raises(AlcoholHoursRestriction):
            await verify_alcohol_compliance(
                session,
                customer_id=user_id,
                state_code=state_code,
                has_alcohol=True,
                order_time=late_night_time,
            )

        # 7. Volume exceeding maximum allowed spirits raises AlcoholVolumeExceeded
        with pytest.raises(AlcoholVolumeExceeded):
            await verify_alcohol_compliance(
                session,
                customer_id=user_id,
                state_code=state_code,
                has_alcohol=True,
                total_litres=Decimal("15.0"),
                order_time=order_time_valid,
            )


@pytest.mark.asyncio
async def test_delivery_handover_otp_verification(integration_engine):
    user_id = uuid4()
    order_id = uuid4()
    address_id = uuid4()

    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            User(
                id=user_id,
                email=f"handover-{user_id}@example.com",
                password_hash="test",
                is_active=True,
            )
        )
        await session.flush()

        session.add(
            CustomerAddress(
                id=address_id,
                user_id=user_id,
                label="home",
                recipient_name="Tester",
                line1="Road 1",
                city="Mumbai",
                state="MH",
                postal_code="400001",
                country_code="IN",
                is_active=True,
            )
        )
        await session.flush()

        session.add(
            Order(
                id=order_id,
                user_id=user_id,
                address_id=address_id,
                status="confirmed",
                currency_code="INR",
                subtotal_minor=5000,
                tax_minor=1000,
                delivery_fee_minor=2900,
                total_minor=8900,
            )
        )
        await session.flush()

        # 1. Initialize compliance handover log
        log = await create_delivery_compliance_log(session, order_id=order_id, customer_id=user_id)
        await session.commit()

        assert len(log.handover_otp) == 6
        assert log.handover_otp_verified is False
        assert log.recipient_age_verified is False

        # 2. Invalid OTP fails
        with pytest.raises(InvalidHandoverOTP):
            await verify_delivery_handover(
                session,
                order_id=order_id,
                courier_id=None,
                handover_otp="000000",
                recipient_age_confirmed=True,
            )

        # 3. Valid OTP succeeds
        verified_log = await verify_delivery_handover(
            session,
            order_id=order_id,
            courier_id=None,
            handover_otp=log.handover_otp,
            recipient_age_confirmed=True,
        )
        await session.commit()

        assert verified_log.handover_otp_verified is True
        assert verified_log.recipient_age_verified is True
        assert verified_log.verified_at is not None

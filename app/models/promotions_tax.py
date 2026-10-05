"""Promotion and tax models."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DiscountType(StrEnum):
    """Type of discount."""

    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    BUY_X_GET_Y = "buy_x_get_y"


class CouponStatus(StrEnum):
    """Coupon lifecycle status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"


class LoyaltyTransactionType(StrEnum):
    """Type of loyalty point transaction."""

    EARN = "earn"
    REDEEM = "redeem"
    EXPIRE = "expire"
    ADJUST = "adjust"


class TaxCategory(StrEnum):
    """Product tax category for GST."""

    ALCOHOL = "alcohol"
    BEVERAGE_NON_ALCOHOLIC = "beverage_non_alcoholic"
    MIXER = "mixer"
    SNACK = "snack"
    ICE = "ice"
    PARTY_SUPPLY = "party_supply"
    RECOVERY = "recovery"


class Coupon(Base):
    """Promotional coupon with usage limits and constraints."""

    __tablename__ = "coupons"
    __table_args__ = (
        UniqueConstraint("code", name="uq_coupons_code"),
        CheckConstraint(
            "valid_from <= valid_until",
            name="ck_coupons_valid_window",
        ),
        CheckConstraint(
            "max_uses IS NULL OR max_uses > 0",
            name="ck_coupons_positive_max_uses",
        ),
        CheckConstraint(
            "max_uses_per_customer IS NULL OR max_uses_per_customer > 0",
            name="ck_coupons_positive_max_uses_per_customer",
        ),
        CheckConstraint(
            "discount_value > 0",
            name="ck_coupons_positive_discount",
        ),
        CheckConstraint(
            "(discount_type = 'PERCENTAGE' AND discount_value <= 100) "
            "OR discount_type != 'PERCENTAGE'",
            name="ck_coupons_percentage_max_100",
        ),
        CheckConstraint(
            "min_order_amount_minor IS NULL OR min_order_amount_minor >= 0",
            name="ck_coupons_nonnegative_min_order",
        ),
        CheckConstraint(
            "max_discount_minor IS NULL OR max_discount_minor > 0",
            name="ck_coupons_positive_max_discount",
        ),
        Index("ix_coupons_status", "status"),
        Index("ix_coupons_validity", "valid_from", "valid_until"),
        Index("ix_coupons_active_window", "status", "valid_from", "valid_until"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(DiscountType, name="discount_type_enum"),
        nullable=False,
        default=DiscountType.PERCENTAGE,
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    min_order_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_discount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_uses_per_customer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[CouponStatus] = mapped_column(
        Enum(CouponStatus, name="coupon_status_enum"),
        nullable=False,
        default=CouponStatus.ACTIVE,
    )
    applicable_categories: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    applicable_product_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    applicable_variant_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    excluded_categories: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    excluded_product_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    excluded_variant_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    first_order_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    new_customers_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CouponUsage(Base):
    """Track individual coupon usages for per-customer limits."""

    __tablename__ = "coupon_usages"
    __table_args__ = (
        UniqueConstraint("coupon_id", "customer_id", "order_id", name="uq_coupon_usage"),
        Index("ix_coupon_usages_coupon", "coupon_id"),
        Index("ix_coupon_usages_customer", "customer_id"),
        Index("ix_coupon_usages_order", "order_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    coupon_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("coupons.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    discount_applied_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    coupon: Mapped["Coupon"] = relationship()


class LoyaltyAccount(Base):
    """Customer loyalty points account."""

    __tablename__ = "loyalty_accounts"
    __table_args__ = (
        UniqueConstraint("customer_id", name="uq_loyalty_accounts_customer"),
        CheckConstraint(
            "points_balance >= 0",
            name="ck_loyalty_accounts_nonnegative_balance",
        ),
        CheckConstraint(
            "lifetime_earned >= 0",
            name="ck_loyalty_accounts_nonnegative_lifetime",
        ),
        Index("ix_loyalty_accounts_tier", "tier"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    points_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lifetime_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lifetime_redeemed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tier: Mapped[str] = mapped_column(String(50), nullable=False, default="bronze")
    tier_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class LoyaltyTransaction(Base):
    """Immutable log of loyalty point changes."""

    __tablename__ = "loyalty_transactions"
    __table_args__ = (
        CheckConstraint(
            "points_delta != 0",
            name="ck_loyalty_transactions_nonzero_delta",
        ),
        Index("ix_loyalty_transactions_account", "account_id"),
        Index("ix_loyalty_transactions_type", "transaction_type"),
        Index("ix_loyalty_transactions_order", "order_id"),
        Index("ix_loyalty_transactions_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("loyalty_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_type: Mapped[LoyaltyTransactionType] = mapped_column(
        Enum(LoyaltyTransactionType, name="loyalty_transaction_type_enum"),
        nullable=False,
    )
    points_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    order_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped["LoyaltyAccount"] = relationship()


class TaxRate(Base):
    """GST tax rate per state and category."""

    __tablename__ = "tax_rates"
    __table_args__ = (
        UniqueConstraint("state_code", "category", name="uq_tax_rates_state_category"),
        CheckConstraint(
            "rate_bps >= 0 AND rate_bps <= 10000",
            name="ck_tax_rates_rate_range",
        ),
        CheckConstraint(
            "cgst_rate_bps >= 0 AND cgst_rate_bps <= 10000",
            name="ck_tax_rates_cgst_range",
        ),
        CheckConstraint(
            "sgst_rate_bps >= 0 AND sgst_rate_bps <= 10000",
            name="ck_tax_rates_sgst_range",
        ),
        CheckConstraint(
            "igst_rate_bps >= 0 AND igst_rate_bps <= 10000",
            name="ck_tax_rates_igst_range",
        ),
        CheckConstraint(
            "cess_rate_bps >= 0",
            name="ck_tax_rates_cess_nonnegative",
        ),
        Index("ix_tax_rates_state", "state_code"),
        Index("ix_tax_rates_category", "category"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    state_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[TaxCategory] = mapped_column(
        Enum(TaxCategory, name="tax_category_enum"), nullable=False
    )
    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    cgst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sgst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    igst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cess_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TaxJurisdiction(Base):
    """Mapping of postal codes to tax states."""

    __tablename__ = "tax_jurisdictions"
    __table_args__ = (
        UniqueConstraint("postal_code", name="uq_tax_jurisdictions_postal"),
        Index("ix_tax_jurisdictions_state", "state_code"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    state_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

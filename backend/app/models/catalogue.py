"""Packages, features, pricing rules and occasions."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDelete, Timestamps, UUIDPrimaryKey
from app.db.types import Money, Percent, UTCDateTime, UUIDBinary, enum_check, uuid7

RULE_TYPES = ("BASE_DAYTYPE", "DATE_OVERRIDE", "DATE_RANGE", "PROMO", "GROUP_DISCOUNT")
DAY_TYPES = ("WEEKDAY", "WEEKEND")


class Package(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint("min_guests >= 1 AND max_guests >= min_guests", name="guest_range"),
        CheckConstraint("duration_min > 0", name="duration_positive"),
    )

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name_en: Mapped[str] = mapped_column(String(80))
    name_hi: Mapped[str] = mapped_column(String(80), default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    description_hi: Mapped[str] = mapped_column(Text, default="")
    duration_min: Mapped[int] = mapped_column(SmallInteger)
    games_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    formats_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    min_guests: Mapped[int] = mapped_column(SmallInteger, default=1)
    max_guests: Mapped[int] = mapped_column(SmallInteger)
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    features: Mapped[list[PackageFeature]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="PackageFeature.sort_order",
        lazy="selectin",
    )


class PackageFeature(Base):
    __tablename__ = "package_features"

    id: Mapped[uuid.UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid7)
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("packages.id", ondelete="CASCADE"), index=True
    )
    text_en: Mapped[str] = mapped_column(String(160))
    text_hi: Mapped[str] = mapped_column(String(160), default="")
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)

    package: Mapped[Package] = relationship(back_populates="features")


class PackagePricingRule(UUIDPrimaryKey, Timestamps, Base):
    """See app/services/pricing_engine.py for resolution semantics."""

    __tablename__ = "package_pricing_rules"
    __table_args__ = (
        enum_check("rule_type", RULE_TYPES, "rule_type"),
        CheckConstraint("day_type IS NULL OR day_type IN ('WEEKDAY', 'WEEKEND')", name="day_type"),
        CheckConstraint("price_per_person IS NULL OR price_per_person >= 0", name="price_non_negative"),
        CheckConstraint(
            "discount_pct IS NULL OR (discount_pct > 0 AND discount_pct <= 100)", name="discount_range"
        ),
        CheckConstraint("date_from IS NULL OR date_to IS NULL OR date_to >= date_from", name="date_order"),
        Index("ix_package_pricing_rules_lookup", "package_id", "rule_type", "is_active"),
    )

    package_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("packages.id", ondelete="CASCADE"), nullable=True
    )
    rule_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100), default="")
    day_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    min_guests: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price_per_person: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    discount_pct: Mapped[Decimal | None] = mapped_column(Percent(), nullable=True)
    priority: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Occasion(Base):
    __tablename__ = "occasions"

    id: Mapped[int] = mapped_column(SmallInteger().with_variant(Integer(), "sqlite"), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    label_en: Mapped[str] = mapped_column(String(64))
    label_hi: Mapped[str] = mapped_column(String(64), default="")
    always_enquiry: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_fields_schema: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

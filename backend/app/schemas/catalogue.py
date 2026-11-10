from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import ORMModel


class FeatureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str = Field(min_length=1, max_length=160)
    text_hi: str = Field(default="", max_length=160)


class FeatureOut(ORMModel):
    text_en: str
    text_hi: str


class _PackageFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name_en: str = Field(min_length=1, max_length=80)
    name_hi: str = Field(default="", max_length=80)
    description_en: str = Field(default="", max_length=2000)
    description_hi: str = Field(default="", max_length=2000)
    duration_min: int = Field(ge=5, le=480)
    games_count: int | None = Field(default=None, ge=1, le=100)
    formats_count: int | None = Field(default=None, ge=1, le=100)
    min_guests: int = Field(default=1, ge=1, le=1000)
    max_guests: int = Field(ge=1, le=1000)
    is_recommended: bool = False
    sort_order: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True
    features: list[FeatureIn] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _guest_range(self) -> _PackageFields:
        if self.max_guests < self.min_guests:
            raise ValueError("max_guests must be >= min_guests")
        return self


class PackageCreate(_PackageFields):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,32}$")


class PackageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name_en: str | None = Field(default=None, min_length=1, max_length=80)
    name_hi: str | None = Field(default=None, max_length=80)
    description_en: str | None = Field(default=None, max_length=2000)
    description_hi: str | None = Field(default=None, max_length=2000)
    duration_min: int | None = Field(default=None, ge=5, le=480)
    games_count: int | None = Field(default=None, ge=1, le=100)
    formats_count: int | None = Field(default=None, ge=1, le=100)
    min_guests: int | None = Field(default=None, ge=1, le=1000)
    max_guests: int | None = Field(default=None, ge=1, le=1000)
    is_recommended: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)
    is_active: bool | None = None
    features: list[FeatureIn] | None = Field(default=None, max_length=20)


class PackageOut(ORMModel):
    id: uuid.UUID
    code: str
    name_en: str
    name_hi: str
    description_en: str
    description_hi: str
    duration_min: int
    games_count: int | None
    formats_count: int | None
    min_guests: int
    max_guests: int
    is_recommended: bool
    sort_order: int
    is_active: bool
    features: list[FeatureOut]


class PackagePricePreview(BaseModel):
    date: str
    day_type: str
    price_per_person: Decimal
    guest_count: int | None
    estimated_total: Decimal | None
    eligible: bool


class PublicPackageOut(PackageOut):
    pricing: PackagePricePreview | None = None


class OccasionOut(ORMModel):
    code: str
    label_en: str
    label_hi: str
    always_enquiry: bool
    extra_fields_schema: list[dict[str, Any]]
    sort_order: int
    is_active: bool


class OccasionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label_en: str | None = Field(default=None, min_length=1, max_length=64)
    label_hi: str | None = Field(default=None, max_length=64)
    always_enquiry: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)
    is_active: bool | None = None

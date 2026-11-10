from __future__ import annotations

import datetime as dt
import uuid
from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.common import ORMModel

ExceptionType = Literal["HOLIDAY", "SPECIAL_HOURS", "BLACKOUT", "MANUAL_BLOCK"]
CapacityMode = Literal["EXCLUSIVE", "SHARED_SEATS"]


class BusinessHoursDay(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    open_time: time
    close_time: time
    is_closed: bool = False

    @model_validator(mode="after")
    def _order(self) -> BusinessHoursDay:
        if not self.is_closed and self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time (overnight hours are not supported)")
        return self


class BusinessHoursPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: list[BusinessHoursDay] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def _all_days(self) -> BusinessHoursPut:
        if sorted(d.weekday for d in self.days) != list(range(7)):
            raise ValueError("provide exactly one entry for each weekday 0-6")
        return self


class ScheduleExceptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: ExceptionType
    date: dt.date
    start_time: time | None = None
    end_time: time | None = None
    resource_id: uuid.UUID | None = None
    reason: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def _times(self) -> ScheduleExceptionIn:
        has_start, has_end = self.start_time is not None, self.end_time is not None
        if has_start != has_end:
            raise ValueError("start_time and end_time must be provided together")
        if has_start and self.end_time <= self.start_time:  # type: ignore[operator]
            raise ValueError("end_time must be after start_time")
        if self.type in ("SPECIAL_HOURS", "MANUAL_BLOCK") and not has_start:
            raise ValueError(f"{self.type} requires start_time and end_time")
        return self


class ScheduleExceptionOut(ORMModel):
    id: uuid.UUID
    type: str
    date: dt.date = Field(validation_alias="exception_date")
    start_time: time | None
    end_time: time | None
    resource_id: uuid.UUID | None
    reason: str


class ResourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    capacity_mode: CapacityMode = "EXCLUSIVE"
    default_capacity: int = Field(default=1, ge=1, le=1000)
    max_players: int = Field(ge=1, le=1000)
    slot_interval_min: int = Field(default=30, ge=5, le=240)
    buffer_min: int = Field(default=10, ge=0, le=120)
    is_active: bool = True


class ResourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    capacity_mode: CapacityMode | None = None
    default_capacity: int | None = Field(default=None, ge=1, le=1000)
    max_players: int | None = Field(default=None, ge=1, le=1000)
    slot_interval_min: int | None = Field(default=None, ge=5, le=240)
    buffer_min: int | None = Field(default=None, ge=0, le=120)
    is_active: bool | None = None


class ResourceOut(ORMModel):
    id: uuid.UUID
    name: str
    capacity_mode: str
    default_capacity: int
    max_players: int
    slot_interval_min: int
    buffer_min: int
    is_active: bool


class BusinessInfoOut(ORMModel):
    name: str
    address: str
    city: str
    postal_code: str
    timezone: str
    phone: str
    whatsapp: str
    email: str
    maps_url: str


class BusinessInfoPublic(BusinessInfoOut):
    hours: list[BusinessHoursDay]


class BusinessInfoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    city: str | None = Field(default=None, max_length=64)
    postal_code: str | None = Field(default=None, max_length=12)
    phone: str | None = Field(default=None, max_length=32)
    whatsapp: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    maps_url: str | None = Field(default=None, max_length=512, pattern=r"^https://")
    gstin: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z0-9]{10}[0-9A-Z]{3}$")

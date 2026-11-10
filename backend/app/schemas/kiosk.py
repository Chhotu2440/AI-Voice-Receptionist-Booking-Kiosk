from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KioskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)


class KioskConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    status: str | None = Field(default=None, pattern="^(ACTIVE|DISABLED)$")
    config: dict[str, Any] | None = None


class KioskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    status: str
    paired_at: dt.datetime | None
    app_version: str | None
    last_heartbeat_at: dt.datetime | None
    health: dict[str, Any]
    config: dict[str, Any]
    online: bool = False


class PairingCodeOut(BaseModel):
    kiosk: KioskOut
    pairing_code: str
    expires_at: dt.datetime


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairing_code: str = Field(min_length=6, max_length=16)


class RegisterOut(BaseModel):
    device_id: uuid.UUID
    device_secret: str
    name: str


class DeviceTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: uuid.UUID
    device_secret: str = Field(min_length=20, max_length=200)


class DeviceTokenOut(BaseModel):
    access_token: str
    expires_in: int


class HeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_version: str = Field(max_length=32)
    camera_ok: bool | None = None
    mic_ok: bool | None = None
    speaker_ok: bool | None = None
    voice_ok: bool | None = None


class HeartbeatOut(BaseModel):
    config: dict[str, Any]
    server_time: dt.datetime

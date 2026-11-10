from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=255)  # not format-validated: login must not leak rules
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth token type, not a secret)
    expires_in: int


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    name: str
    is_active: bool
    role_codes: list[str]
    last_login_at: datetime | None


class MeOut(UserOut):
    permissions: list[str]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)
    roles: list[str] = Field(min_length=1)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    roles: list[str] | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=12, max_length=256)

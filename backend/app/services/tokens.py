"""Capability tokens for holds and bookings.

Tokens are HMACs of the object id, so nothing secret is stored and idempotent replays can return the same
token. A caller must present the token to use/release a hold or to view a booking (prevents enumeration).
Rotating JWT_SECRET invalidates outstanding tokens (holds live minutes; booking tokens only gate self-view).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid

from app.core.config import Settings


def _key(settings: Settings) -> bytes:
    return hashlib.sha256(settings.jwt_secret.get_secret_value().encode() + b":capability-tokens").digest()


def make_token(settings: Settings, kind: str, object_id: uuid.UUID) -> str:
    mac = hmac.new(_key(settings), f"{kind}:{object_id}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


def verify_token(settings: Settings, kind: str, object_id: uuid.UUID, token: str | None) -> bool:
    if not token:
        return False
    return hmac.compare_digest(make_token(settings, kind, object_id), token)

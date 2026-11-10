"""Password hashing (Argon2id), JWT access tokens and opaque refresh tokens."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.exceptions import UnauthenticatedError
from app.core.timeutil import utcnow

_hasher = PasswordHasher()  # argon2id with library defaults (RFC 9106 low-memory profile)
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time verification; verifies against a dummy hash when the user doesn't exist."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(settings: Settings, subject: str, extra: dict[str, Any] | None = None) -> str:
    now = utcnow()
    claims: dict[str, Any] = {
        "sub": subject,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_token_ttl_seconds)).timestamp()),
        "typ": "access",
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_token(settings: Settings, token: str, expected_typ: str) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthenticatedError("Your session has expired. Please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthenticatedError("Invalid credentials.") from exc
    if claims.get("typ") != expected_typ:
        raise UnauthenticatedError("Invalid credentials.")
    return claims


def sign_payload(settings: Settings, typ: str, payload: dict[str, Any], ttl_seconds: int) -> str:
    """Signed, expiring token for stateless artefacts (e.g. price quotes)."""
    now = utcnow()
    claims = {
        **payload,
        "sub": payload.get("sub", typ),
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "typ": typ,
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

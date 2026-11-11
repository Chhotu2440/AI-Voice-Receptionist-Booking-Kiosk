"""Kiosk device lifecycle: admin creates a device and gets a one-time pairing code; the kiosk exchanges the
code for a long-lived device secret, then trades the secret for short-lived device JWTs (ADR-010)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthenticatedError
from app.core.security import create_access_token
from app.core.timeutil import utcnow
from app.models.kiosk import KioskDevice
from app.schemas.kiosk import HeartbeatIn, KioskConfigUpdate, KioskOut
from app.services import audit_service
from app.services.context import Actor

PAIRING_TTL = timedelta(minutes=15)
DEVICE_TOKEN_TTL_SECONDS = 3600
ONLINE_WINDOW = timedelta(minutes=3)
_PAIRING_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O/1/I/L

DEFAULT_CONFIG: dict[str, Any] = {
    "idle_timeout_s": 60,
    "success_reset_s": 20,
    "voice_enabled": True,
    "volume": 70,
    "assistant_name": "Zara",
    # On-device presence detection (CAM-01); tune per venue from the admin dashboard.
    "presence_enabled": True,
    "presence_min_face_area": 0.012,
    "presence_dwell_ms": 1200,
    "presence_leave_ms": 20000,
    "presence_debug": False,
}


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _normalize_code(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def kiosk_out(d: KioskDevice) -> KioskOut:
    out = KioskOut.model_validate(d)
    out.online = d.last_heartbeat_at is not None and utcnow() - d.last_heartbeat_at < ONLINE_WINDOW
    out.config = {**DEFAULT_CONFIG, **(d.config or {})}
    return out


def _new_pairing(device: KioskDevice) -> str:
    code = "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(8))
    device.pairing_code_hash = _sha(code)
    device.pairing_expires_at = utcnow() + PAIRING_TTL
    return f"{code[:4]}-{code[4:]}"


async def create(session: AsyncSession, name: str, actor: Actor) -> tuple[KioskDevice, str]:
    device = KioskDevice(name=name.strip(), status="PENDING", config={})
    code = _new_pairing(device)
    session.add(device)
    await session.flush()
    audit_service.record(session, actor, "kiosk.create", "kiosk", device.id, None, {"name": device.name})
    await session.commit()
    return device, code


async def repair(session: AsyncSession, device_id: uuid.UUID, actor: Actor) -> tuple[KioskDevice, str]:
    """Issue a new pairing code; the old device secret stops working once the new code is redeemed."""
    device = await get(session, device_id)
    code = _new_pairing(device)
    audit_service.record(session, actor, "kiosk.pairing_code", "kiosk", device.id)
    await session.commit()
    return device, code


async def get(session: AsyncSession, device_id: uuid.UUID) -> KioskDevice:
    device = await session.get(KioskDevice, device_id)
    if device is None:
        raise NotFoundError("Kiosk not found.")
    return device


async def list_all(session: AsyncSession) -> list[KioskDevice]:
    return list((await session.execute(select(KioskDevice).order_by(KioskDevice.created_at))).scalars())


async def update(
    session: AsyncSession, device_id: uuid.UUID, data: KioskConfigUpdate, actor: Actor
) -> KioskDevice:
    device = await get(session, device_id)
    patch = data.model_dump(exclude_unset=True)
    before = {k: getattr(device, k) for k in patch}
    if "config" in patch:
        patch["config"] = {**(device.config or {}), **patch["config"]}
    for key, value in patch.items():
        setattr(device, key, value)
    audit_service.record(session, actor, "kiosk.update", "kiosk", device.id, before, patch)
    await session.commit()
    return device


async def register(session: AsyncSession, pairing_code: str, ip: str | None) -> tuple[KioskDevice, str]:
    code_hash = _sha(_normalize_code(pairing_code))
    stmt = select(KioskDevice).where(KioskDevice.pairing_code_hash == code_hash).with_for_update()
    device = (await session.execute(stmt)).scalar_one_or_none()
    if device is None or device.pairing_expires_at is None or device.pairing_expires_at <= utcnow():
        raise UnauthenticatedError("That pairing code is invalid or has expired.")
    if device.status == "DISABLED":
        raise ForbiddenError("This kiosk is disabled.")
    secret = secrets.token_urlsafe(32)
    device.secret_hash = _sha(secret)
    device.pairing_code_hash, device.pairing_expires_at = None, None
    device.status, device.paired_at, device.last_ip = "ACTIVE", utcnow(), ip
    audit_service.record(session, Actor("KIOSK", str(device.id), ip), "kiosk.paired", "kiosk", device.id)
    await session.commit()
    return device, secret


async def issue_token(
    session: AsyncSession, settings: Settings, device_id: uuid.UUID, secret: str
) -> tuple[str, int]:
    device = await session.get(KioskDevice, device_id)
    if (
        device is None
        or device.secret_hash is None
        or not secrets.compare_digest(device.secret_hash, _sha(secret))
    ):
        raise UnauthenticatedError("Invalid device credentials.")
    if device.status != "ACTIVE":
        raise ForbiddenError("This kiosk is disabled.")
    token = create_access_token(
        settings,
        str(device.id),
        {"typ": "device", "exp": int((utcnow() + timedelta(seconds=DEVICE_TOKEN_TTL_SECONDS)).timestamp())},
    )
    return token, DEVICE_TOKEN_TTL_SECONDS


async def heartbeat(
    session: AsyncSession, device: KioskDevice, data: HeartbeatIn, ip: str | None
) -> dict[str, Any]:
    device.app_version = data.app_version
    device.last_heartbeat_at = utcnow()
    device.last_ip = ip
    device.health = data.model_dump(exclude={"app_version"}, exclude_none=True)
    await session.commit()
    return {**DEFAULT_CONFIG, **(device.config or {})}

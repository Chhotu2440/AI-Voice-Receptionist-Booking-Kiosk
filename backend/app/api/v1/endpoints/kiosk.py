"""Kiosk device endpoints (/kiosk/*) and admin kiosk management (/admin/kiosks)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.deps import (
    CurrentDevice,
    SessionDep,
    SettingsDep,
    client_ip,
    rate_limit,
    require_permission,
    user_actor,
)
from app.core.timeutil import utcnow
from app.models.identity import User
from app.schemas.kiosk import (
    DeviceTokenOut,
    DeviceTokenRequest,
    HeartbeatIn,
    HeartbeatOut,
    KioskConfigUpdate,
    KioskCreate,
    KioskOut,
    PairingCodeOut,
    RegisterOut,
    RegisterRequest,
)
from app.services import kiosk_device_service as svc

router = APIRouter(tags=["kiosk"])
pair_limit = Depends(rate_limit("kiosk-pair", "login_rate_limit_per_minute"))


def perm(*codes: str) -> Any:
    return Depends(require_permission(*codes))


@router.post("/kiosk/register", response_model=RegisterOut, dependencies=[pair_limit])
async def register(body: RegisterRequest, request: Request, session: SessionDep) -> RegisterOut:
    device, secret = await svc.register(session, body.pairing_code, client_ip(request))
    return RegisterOut(device_id=device.id, device_secret=secret, name=device.name)


@router.post("/kiosk/token", response_model=DeviceTokenOut, dependencies=[pair_limit])
async def token(body: DeviceTokenRequest, session: SessionDep, settings: SettingsDep) -> DeviceTokenOut:
    access, ttl = await svc.issue_token(session, settings, body.device_id, body.device_secret)
    return DeviceTokenOut(access_token=access, expires_in=ttl)


@router.post("/kiosk/heartbeat", response_model=HeartbeatOut)
async def heartbeat(
    body: HeartbeatIn, request: Request, session: SessionDep, device: CurrentDevice
) -> HeartbeatOut:
    config = await svc.heartbeat(session, device, body, client_ip(request))
    return HeartbeatOut(config=config, server_time=utcnow())


@router.get("/admin/kiosks", response_model=list[KioskOut])
async def list_kiosks(session: SessionDep, _: User = perm("kiosk.manage")) -> list[KioskOut]:
    return [svc.kiosk_out(d) for d in await svc.list_all(session)]


@router.post("/admin/kiosks", response_model=PairingCodeOut, status_code=201)
async def create_kiosk(
    body: KioskCreate, request: Request, session: SessionDep, user: User = perm("kiosk.manage")
) -> PairingCodeOut:
    device, code = await svc.create(session, body.name, user_actor(user, request))
    assert device.pairing_expires_at is not None
    return PairingCodeOut(
        kiosk=svc.kiosk_out(device), pairing_code=code, expires_at=device.pairing_expires_at
    )


@router.post("/admin/kiosks/{kiosk_id}/pairing-code", response_model=PairingCodeOut)
async def new_pairing_code(
    kiosk_id: uuid.UUID, request: Request, session: SessionDep, user: User = perm("kiosk.manage")
) -> PairingCodeOut:
    device, code = await svc.repair(session, kiosk_id, user_actor(user, request))
    assert device.pairing_expires_at is not None
    return PairingCodeOut(
        kiosk=svc.kiosk_out(device), pairing_code=code, expires_at=device.pairing_expires_at
    )


@router.patch("/admin/kiosks/{kiosk_id}", response_model=KioskOut)
async def update_kiosk(
    kiosk_id: uuid.UUID,
    body: KioskConfigUpdate,
    request: Request,
    session: SessionDep,
    user: User = perm("kiosk.manage"),
) -> KioskOut:
    return svc.kiosk_out(await svc.update(session, kiosk_id, body, user_actor(user, request)))

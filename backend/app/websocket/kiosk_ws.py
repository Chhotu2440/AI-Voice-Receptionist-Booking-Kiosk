"""Kiosk WebSocket (/ws/kiosk). Protocol (JSON text frames):

client -> server
    {"type": "auth", "token": "<device JWT>", "resume_session_id": "<optional>"}   (first frame, within 5 s)
    {"type": "intent", "id": "<client id>", "name": "<intent>", "payload": {...}}
    {"type": "ping"}
server -> client
    {"type": "state", "state": {...public snapshot...}, "allowed": [...], "in_reply_to": "<id>|null"}
    {"type": "error", "error": {"code", "message"}, "in_reply_to": "<id>|null"}
    {"type": "pong"}

The token travels in the first frame (not the URL) so it never lands in proxy access logs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import device_from_token
from app.core.exceptions import DomainError
from app.kiosk.flow import KioskFlow, allowed_intents
from app.kiosk.state import KioskState

log = logging.getLogger(__name__)
router = APIRouter()

AUTH_TIMEOUT_S = 5
MAX_FRAME_BYTES = 16_384


def _state_msg(s: KioskState, reply_to: str | None = None) -> dict[str, Any]:
    return {
        "type": "state",
        "state": s.public(),
        "allowed": sorted(allowed_intents(s)),
        "in_reply_to": reply_to,
    }


@router.websocket("/ws/kiosk")
async def kiosk_socket(ws: WebSocket) -> None:
    allowed_origins = ws.app.state.settings.cors_origins
    origin = ws.headers.get("origin")
    if allowed_origins and origin and origin not in allowed_origins:
        await ws.close(code=4403)
        return
    await ws.accept()
    flow: KioskFlow = ws.app.state.kiosk_flow
    send_lock = asyncio.Lock()

    async def send(msg: dict[str, Any]) -> None:
        async with send_lock:  # replies and pushed voice updates come from two tasks
            await ws.send_json(msg)

    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_S))
        if first.get("type") != "auth":
            raise ValueError("auth required")
        async with ws.app.state.sessionmaker() as db:
            device = await device_from_token(db, ws.app.state.settings, str(first.get("token", "")))
            device_id = str(device.id)
    except (TimeoutError, ValueError, DomainError):
        await ws.close(code=4401)
        return

    lock: asyncio.Lock = ws.app.state.kiosk_locks.setdefault(device_id, asyncio.Lock())
    async with lock:
        state = await flow.connect(device_id, first.get("resume_session_id"))
    await send(_state_msg(state))

    # Changes made by the voice agent (or the system) are pushed to the screen as they happen.
    updates = flow.bus.subscribe(device_id)

    async def forward_updates() -> None:
        while True:
            change = await updates.get()
            if change.source != "touch":
                await send(_state_msg(change.state))

    forwarder = asyncio.create_task(forward_updates())
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_FRAME_BYTES:
                await send({"type": "error", "error": {"code": "FRAME_TOO_LARGE", "message": ""}})
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ping":
                await send({"type": "pong"})
                continue
            if msg.get("type") != "intent":
                continue
            reply_to = str(msg["id"]) if msg.get("id") is not None else None
            payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
            try:
                async with lock:
                    state = await flow.handle(device_id, str(msg.get("name", "")), payload)
            except DomainError as exc:
                await send(
                    {
                        "type": "error",
                        "error": {"code": exc.code, "message": exc.message},
                        "in_reply_to": reply_to,
                    }
                )
                state = await flow.current(device_id)
            except Exception:
                log.exception("kiosk_intent_failed", extra={"intent": msg.get("name")})
                await send(
                    {
                        "type": "error",
                        "error": {"code": "INTERNAL", "message": "Something went wrong. Please try again."},
                        "in_reply_to": reply_to,
                    }
                )
                state = await flow.current(device_id)
            await send(_state_msg(state, reply_to))
    except WebSocketDisconnect:
        return
    finally:
        forwarder.cancel()
        flow.bus.unsubscribe(device_id, updates)

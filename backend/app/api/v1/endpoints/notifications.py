"""Interakt delivery webhooks and the admin notification log."""

from __future__ import annotations

import datetime as dt
import hmac
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.deps import SessionDep, SettingsDep, require_permission
from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.identity import User
from app.models.notification import NotificationLog
from app.schemas.common import Page, PageParams
from app.services import ai_usage_service, notification_service

router = APIRouter(tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    booking_id: uuid.UUID | None
    channel: str
    provider: str
    template: str
    to_masked: str
    status: str
    provider_message_id: str | None
    error: str | None
    attempts: int
    created_at: dt.datetime
    delivered_at: dt.datetime | None


@router.post("/webhooks/interakt/{token}", include_in_schema=False)
async def interakt_webhook(
    token: str, request: Request, session: SessionDep, settings: SettingsDep
) -> dict[str, str]:
    secret = settings.interakt_webhook_secret
    if secret is None or not hmac.compare_digest(token, secret.get_secret_value()):
        raise NotFoundError()  # don't reveal that the endpoint exists
    try:
        payload: Any = await request.json()
    except ValueError as exc:
        raise ValidationFailed("Invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValidationFailed("Invalid payload.")
    return {"status": await notification_service.handle_interakt_webhook(session, payload)}


@router.get("/admin/ai/usage")
async def ai_usage(
    session: SessionDep,
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    _: User = Depends(require_permission("dashboard.read")),
) -> dict[str, Any]:
    """Voice sessions, measured cost (USD and INR), cost per voice booking, and spend-cap status."""
    default_from, default_to = ai_usage_service.default_range()
    return await ai_usage_service.summary(session, date_from or default_from, date_to or default_to)


@router.get("/admin/notifications", response_model=Page[NotificationOut])
async def list_notifications(
    session: SessionDep,
    paging: PageParams = Depends(),
    booking_id: uuid.UUID | None = None,
    status: str | None = None,
    _: User = Depends(require_permission("booking.read")),
) -> Page[NotificationOut]:
    stmt = select(NotificationLog)
    if booking_id is not None:
        stmt = stmt.where(NotificationLog.booking_id == booking_id)
    if status:
        stmt = stmt.where(NotificationLog.status == status.upper())
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(NotificationLog.created_at.desc()).offset(paging.offset).limit(paging.page_size)
        )
    ).scalars()
    return Page(
        items=[NotificationOut.model_validate(r) for r in rows],
        page=paging.page,
        page_size=paging.page_size,
        total=int(total),
    )

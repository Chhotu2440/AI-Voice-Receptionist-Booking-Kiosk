"""Voice AI usage, cost and spend caps (VOICE-06).

Cost = provider-reported tokens x the price table in settings ("ai" section, editable by the owner).
Caps are checked before every voice session: once the daily or monthly cap is reached the kiosk keeps
working by touch only until the period rolls over (or the owner raises the cap).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import business_date_of, today_local, utcnow
from app.models.ai import AiUsageLog
from app.models.kiosk import KioskSession
from app.schemas.settings import AiSettings, ModelPrice
from app.services import settings_service
from app.voice.provider import UsageRecord

MILLION = Decimal(1_000_000)


def cost_usd(usage: UsageRecord, price: ModelPrice | None) -> Decimal:
    if price is None:
        return Decimal(0)
    uncached_text = max(0, usage.text_in_tokens - usage.text_cached_tokens)
    total = (
        Decimal(usage.audio_in_tokens) * price.audio_in
        + Decimal(usage.audio_out_tokens) * price.audio_out
        + Decimal(uncached_text) * price.text_in
        + Decimal(usage.text_cached_tokens) * price.text_cached
        + Decimal(usage.text_out_tokens) * price.text_out
    ) / MILLION
    return total.quantize(Decimal("0.00001"))


async def record(
    session: AsyncSession,
    *,
    device_id: str,
    kiosk_session_id: str | None,
    provider: str,
    model: str,
    started_at: datetime,
    usage: UsageRecord,
    tool_calls: int,
    tools_blocked: int,
    end_reason: str,
) -> AiUsageLog:
    ai = await settings_service.get_ai_settings(session)
    now = utcnow()
    row = AiUsageLog(
        device_id=uuid.UUID(device_id),
        kiosk_session_id=uuid.UUID(kiosk_session_id) if kiosk_session_id else None,
        provider=provider,
        model=model,
        business_date=business_date_of(started_at),
        started_at=started_at,
        ended_at=now,
        seconds=int((now - started_at).total_seconds()),
        audio_in_tokens=usage.audio_in_tokens,
        audio_out_tokens=usage.audio_out_tokens,
        text_in_tokens=usage.text_in_tokens,
        text_cached_tokens=usage.text_cached_tokens,
        text_out_tokens=usage.text_out_tokens,
        tool_calls=tool_calls,
        tools_blocked=tools_blocked,
        cost_usd=cost_usd(usage, ai.prices.get(model)),
        price_version=ai.price_version,
        end_reason=end_reason[:32],
    )
    session.add(row)
    await session.commit()
    return row


async def _spend_since(session: AsyncSession, first_day: date) -> Decimal:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(AiUsageLog.cost_usd), 0)).where(
                AiUsageLog.business_date >= first_day
            )
        )
    ).scalar_one()
    return Decimal(str(total))


@dataclass(frozen=True)
class CapStatus:
    allowed: bool
    today_usd: Decimal
    month_usd: Decimal
    reason: str = ""


async def check_caps(session: AsyncSession, settings_ai: AiSettings | None = None) -> CapStatus:
    ai = settings_ai or await settings_service.get_ai_settings(session)
    today = today_local()
    today_usd = await _spend_since(session, today)
    month_usd = await _spend_since(session, today.replace(day=1))
    if ai.daily_cap_usd and today_usd >= ai.daily_cap_usd:
        return CapStatus(False, today_usd, month_usd, "daily voice budget reached")
    if ai.monthly_cap_usd and month_usd >= ai.monthly_cap_usd:
        return CapStatus(False, today_usd, month_usd, "monthly voice budget reached")
    return CapStatus(True, today_usd, month_usd)


async def summary(session: AsyncSession, date_from: date, date_to: date) -> dict[str, Any]:
    ai = await settings_service.get_ai_settings(session)
    rows = (
        await session.execute(
            select(
                AiUsageLog.business_date,
                AiUsageLog.provider,
                func.count(),
                func.sum(AiUsageLog.cost_usd),
                func.sum(AiUsageLog.seconds),
                func.sum(AiUsageLog.tools_blocked),
            )
            .where(AiUsageLog.business_date >= date_from, AiUsageLog.business_date <= date_to)
            .group_by(AiUsageLog.business_date, AiUsageLog.provider)
            .order_by(AiUsageLog.business_date)
        )
    ).all()
    sessions = sum(int(r[2]) for r in rows)
    cost = sum((Decimal(str(r[3] or 0)) for r in rows), Decimal(0))
    voice_session_ids = select(AiUsageLog.kiosk_session_id).where(
        AiUsageLog.business_date >= date_from, AiUsageLog.business_date <= date_to
    )
    bookings = (
        await session.execute(
            select(func.count()).where(
                KioskSession.id.in_(voice_session_ids), KioskSession.booking_id.is_not(None)
            )
        )
    ).scalar_one()
    caps = await check_caps(session, ai)
    return {
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "voice_sessions": sessions,
        "voice_bookings": int(bookings),
        "cost_usd": str(cost.quantize(Decimal("0.01"))),
        "cost_inr": str((cost * ai.usd_inr).quantize(Decimal("1"))),
        "cost_per_session_usd": str((cost / sessions).quantize(Decimal("0.001"))) if sessions else None,
        "cost_per_booking_inr": str((cost * ai.usd_inr / bookings).quantize(Decimal("0.1")))
        if bookings
        else None,
        "by_day": [
            {
                "date": r[0].isoformat(),
                "provider": r[1],
                "sessions": int(r[2]),
                "cost_usd": str(Decimal(str(r[3] or 0)).quantize(Decimal("0.001"))),
                "minutes": round(int(r[4] or 0) / 60, 1),
                "phantom_answers_blocked": int(r[5] or 0),
            }
            for r in rows
        ],
        "caps": {
            "daily_cap_usd": str(ai.daily_cap_usd),
            "monthly_cap_usd": str(ai.monthly_cap_usd),
            "today_usd": str(caps.today_usd.quantize(Decimal("0.001"))),
            "month_usd": str(caps.month_usd.quantize(Decimal("0.001"))),
            "voice_allowed": caps.allowed,
            "reason": caps.reason,
        },
    }


def default_range() -> tuple[date, date]:
    today = today_local()
    return today - timedelta(days=29), today

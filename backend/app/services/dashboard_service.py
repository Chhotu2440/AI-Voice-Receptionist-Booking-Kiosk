"""Admin dashboard summary (doc 14 §4): today's bookings, revenue, kiosk funnel, popular packages, AI cost.

Revenue is always taken from the booking's pricing snapshot (what the customer was quoted), never recomputed.
Cancelled bookings are excluded from counts and revenue.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import local_to_utc, to_local, today_local, utcnow
from app.kiosk.state import FLOW
from app.models.ai import AiUsageLog
from app.models.booking import Booking, BookingPricingSnapshot, Customer, CustomEventEnquiry
from app.models.catalogue import Occasion, Package
from app.models.kiosk import KioskDevice, KioskSession
from app.services import ai_usage_service, settings_service
from app.services.kiosk_device_service import ONLINE_WINDOW

LIVE = ("CONFIRMED", "COMPLETED", "NO_SHOW", "PENDING_PAYMENT")
FUNNEL_STEPS = (
    ("started", "GREETING"),
    ("details", "GUEST_COUNT"),
    ("package", "PACKAGE_DISCOVERY"),
    ("slot", "SLOT_SELECTION"),
    ("summary", "BOOKING_SUMMARY"),
)


def _money(value: Any) -> str:
    return str(Decimal(str(value or 0)).quantize(Decimal("1")))


async def summary(session: AsyncSession, date_from: date, date_to: date) -> dict[str, Any]:
    today = today_local()
    live_in_range = (
        Booking.status.in_(LIVE),
        Booking.business_date >= date_from,
        Booking.business_date <= date_to,
    )

    by_day_rows = (
        await session.execute(
            select(
                Booking.business_date,
                func.count(Booking.id),
                func.sum(Booking.guest_count),
                func.sum(BookingPricingSnapshot.total),
            )
            .join(BookingPricingSnapshot, BookingPricingSnapshot.booking_id == Booking.id)
            .where(*live_in_range)
            .group_by(Booking.business_date)
            .order_by(Booking.business_date)
        )
    ).all()
    by_day = [
        {"date": r[0].isoformat(), "bookings": int(r[1]), "guests": int(r[2] or 0), "revenue": _money(r[3])}
        for r in by_day_rows
    ]

    packages = (
        await session.execute(
            select(Package.name_en, func.count(Booking.id), func.sum(BookingPricingSnapshot.total))
            .join(Package, Package.id == Booking.package_id)
            .join(BookingPricingSnapshot, BookingPricingSnapshot.booking_id == Booking.id)
            .where(*live_in_range)
            .group_by(Package.name_en)
            .order_by(func.count(Booking.id).desc())
        )
    ).all()
    occasions = (
        await session.execute(
            select(Occasion.label_en, func.count(Booking.id))
            .join(Occasion, Occasion.id == Booking.occasion_id)
            .where(*live_in_range)
            .group_by(Occasion.label_en)
            .order_by(func.count(Booking.id).desc())
        )
    ).all()
    channels = (
        await session.execute(
            select(Booking.channel, func.count(Booking.id)).where(*live_in_range).group_by(Booking.channel)
        )
    ).all()
    cancelled = (
        await session.execute(
            select(func.count(Booking.id)).where(
                Booking.status == "CANCELLED",
                Booking.business_date >= date_from,
                Booking.business_date <= date_to,
            )
        )
    ).scalar_one()

    # Kiosk funnel: how far each session got (furthest_state), and how many ended in a booking/enquiry.
    start_utc = local_to_utc(date_from, time(0))
    end_utc = local_to_utc(date_to + timedelta(days=1), time(0))
    sessions = (
        await session.execute(
            select(
                KioskSession.furthest_state,
                KioskSession.final_state,
                KioskSession.booking_id,
                KioskSession.enquiry_id,
                KioskSession.id,
                KioskSession.end_reason,
            ).where(KioskSession.started_at >= start_utc, KioskSession.started_at < end_utc)
        )
    ).all()
    order = {s: i for i, s in enumerate(FLOW)}
    furthest = [order.get(r[0] or r[1] or "GREETING", 0) for r in sessions]
    funnel = [
        {"step": name, "sessions": sum(1 for f in furthest if f >= order[state])}
        for name, state in FUNNEL_STEPS
    ]
    booked = sum(1 for r in sessions if r[2] is not None)
    funnel.append({"step": "booked", "sessions": booked})
    abandoned = Counter(
        (r[5] or "UNKNOWN") for r in sessions if r[2] is None and r[3] is None and r[5] is not None
    )

    voice_sessions = (
        await session.execute(
            select(func.count(func.distinct(AiUsageLog.kiosk_session_id))).where(
                AiUsageLog.business_date >= date_from, AiUsageLog.business_date <= date_to
            )
        )
    ).scalar_one()

    # Today at a glance.
    today_rows = (
        await session.execute(
            select(Booking, Customer.name)
            .join(Customer, Customer.id == Booking.customer_id)
            .where(Booking.business_date == today, Booking.status != "CANCELLED")
            .order_by(Booking.start_at)
        )
    ).all()
    now = utcnow()
    today_list = [
        {
            "id": str(b.id),
            "reference": b.reference,
            "start_time": to_local(b.start_at).strftime("%H:%M"),
            "end_time": to_local(b.end_at).strftime("%H:%M"),
            "customer_name": name,
            "guest_count": b.guest_count,
            "status": b.status,
            "channel": b.channel,
            "total": _money(b.pricing.total if b.pricing else 0),
            "upcoming": b.end_at > now,
        }
        for b, name in today_rows
    ]
    upcoming_week = (
        await session.execute(
            select(func.count(Booking.id)).where(
                Booking.status == "CONFIRMED",
                Booking.business_date > today,
                Booking.business_date <= today + timedelta(days=7),
            )
        )
    ).scalar_one()
    open_enquiries = (
        await session.execute(
            select(func.count(CustomEventEnquiry.id)).where(
                CustomEventEnquiry.status.in_(("NEW", "CONTACTED"))
            )
        )
    ).scalar_one()
    devices = (
        await session.execute(select(KioskDevice.last_heartbeat_at).where(KioskDevice.status == "ACTIVE"))
    ).all()
    online = sum(1 for (hb,) in devices if hb is not None and now - hb < ONLINE_WINDOW)
    caps = await ai_usage_service.check_caps(session)
    ai = await settings_service.get_ai_settings(session)

    total_revenue = sum((Decimal(str(r[3] or 0)) for r in by_day_rows), Decimal(0))
    total_bookings = sum(int(r[1]) for r in by_day_rows)
    return {
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "today": {
            "date": today.isoformat(),
            "bookings": len(today_list),
            "guests": sum(int(str(b["guest_count"])) for b in today_list),
            "revenue": _money(sum((Decimal(str(b["total"])) for b in today_list), Decimal(0))),
            "list": today_list,
        },
        "upcoming_7_days": int(upcoming_week),
        "open_enquiries": int(open_enquiries),
        "totals": {
            "bookings": total_bookings,
            "revenue": _money(total_revenue),
            "cancelled": int(cancelled),
            "average_booking": _money(total_revenue / total_bookings) if total_bookings else "0",
        },
        "by_day": by_day,
        "packages": [{"name": r[0], "bookings": int(r[1]), "revenue": _money(r[2])} for r in packages],
        "occasions": [{"name": r[0], "bookings": int(r[1])} for r in occasions],
        "channels": {r[0]: int(r[1]) for r in channels},
        "funnel": funnel,
        "kiosk_sessions": {
            "total": len(sessions),
            "voice": int(voice_sessions),
            "abandoned": dict(abandoned.most_common()),
        },
        "kiosks": {"active": len(devices), "online": online},
        "ai": {
            "today_usd": str(caps.today_usd.quantize(Decimal("0.01"))),
            "month_usd": str(caps.month_usd.quantize(Decimal("0.01"))),
            "month_inr": str((caps.month_usd * ai.usd_inr).quantize(Decimal("1"))),
            "daily_cap_usd": str(ai.daily_cap_usd),
            "monthly_cap_usd": str(ai.monthly_cap_usd),
            "voice_allowed": caps.allowed,
        },
    }

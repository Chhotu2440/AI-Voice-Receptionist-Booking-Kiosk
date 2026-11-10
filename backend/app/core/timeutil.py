"""Time helpers. Rule (ADR-014): instants are UTC; business calendar values are Asia/Kolkata."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("Asia/Kolkata")


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(UTC)


def now_local(tz: ZoneInfo = BUSINESS_TZ) -> datetime:
    return datetime.now(tz)


def today_local(tz: ZoneInfo = BUSINESS_TZ) -> date:
    """The business 'today'. Never use the server's local date or SQL CURRENT_DATE."""
    return now_local(tz).date()


def local_to_utc(d: date, t: time, tz: ZoneInfo = BUSINESS_TZ) -> datetime:
    return datetime.combine(d, t, tzinfo=tz).astimezone(UTC)


def to_local(dt: datetime, tz: ZoneInfo = BUSINESS_TZ) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime; expected timezone-aware UTC")
    return dt.astimezone(tz)


def business_date_of(dt: datetime, tz: ZoneInfo = BUSINESS_TZ) -> date:
    return to_local(dt, tz).date()

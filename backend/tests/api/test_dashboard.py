"""ADMIN dashboard summary: revenue from snapshots, cancellations excluded, funnel, permissions."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from tests.api.test_notifications import book, monday, settings  # noqa: F401  (fixture reuse)


async def test_dashboard_counts_live_bookings_and_revenue(
    client: AsyncClient,
    owner_headers: dict[str, str],
    maker: async_sessionmaker[AsyncSession],
    settings: Settings,  # noqa: F811
) -> None:
    first = await book(maker, settings, start="18:00")
    await book(maker, settings, start="20:00")
    cancel = await client.post(
        f"/api/v1/admin/bookings/{first['id']}/cancel",
        headers=owner_headers,
        json={"reason": "customer called"},
    )
    assert cancel.status_code == 200

    day = monday().isoformat()
    r = await client.get(f"/api/v1/admin/dashboard?from={day}&to={day}", headers=owner_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totals"]["bookings"] == 1 and body["totals"]["cancelled"] == 1
    assert int(body["totals"]["revenue"]) > 0
    assert body["by_day"] == [{"date": day, "bookings": 1, "guests": 4, "revenue": body["totals"]["revenue"]}]
    assert body["packages"][0]["bookings"] == 1
    assert body["channels"] == {"KIOSK": 1}
    assert [s["step"] for s in body["funnel"]] == [
        "started",
        "details",
        "package",
        "slot",
        "summary",
        "booked",
    ]
    assert body["ai"]["voice_allowed"] is True


async def test_dashboard_validates_range_and_permission(
    client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    bad = await client.get("/api/v1/admin/dashboard?from=2026-12-10&to=2026-12-01", headers=owner_headers)
    assert bad.status_code == 422
    assert (await client.get("/api/v1/admin/dashboard")).status_code == 401

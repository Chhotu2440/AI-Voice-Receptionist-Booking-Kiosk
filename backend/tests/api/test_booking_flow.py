"""Availability -> hold -> booking flow, cancellation, reschedule and enquiries (AVL/HOLD/BKG/ENQ-*)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.timeutil import today_local, utcnow
from app.models.booking import AvailabilitySlot, Booking, CustomerConsent, SlotHold
from app.services import hold_service
from tests.conftest import make_settings


@pytest.fixture
def settings() -> Settings:
    # The booking flow makes many calls per test; rate limits have their own tests.
    return make_settings(public_rate_limit_per_minute=10_000, booking_rate_limit_per_minute=10_000)


def next_weekday(weekday: int) -> date:
    d = today_local() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


MONDAY = next_weekday(0)
SATURDAY = next_weekday(5)


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def pkg(client: AsyncClient, code: str) -> str:
    pkgs = (await client.get("/api/v1/packages")).json()
    return next(p["id"] for p in pkgs if p["code"] == code)


async def hold(
    client: AsyncClient,
    code: str = "EXPERT",
    day: date = MONDAY,
    start: str = "18:00",
    guests: int = 4,
    headers: dict[str, str] | None = None,
) -> Any:
    body = {
        "package_id": await pkg(client, code),
        "date": day.isoformat(),
        "start_time": start,
        "guest_count": guests,
    }
    return await client.post("/api/v1/slot-holds", json=body, headers=headers or key())


def booking_body(h: dict[str, Any], **over: Any) -> dict[str, Any]:
    body = {
        "hold_id": h["hold_id"],
        "hold_token": h["hold_token"],
        "customer": {"name": "Riya Sharma", "phone": "+91 98765-43210"},
        "occasion_code": "BIRTHDAY",
        "occasion_details": {"birthday_person_name": "Aarav", "birthday_person_age": 12},
        "consents": {"whatsapp": True},
    }
    body.update(over)
    return body


async def starts(client: AsyncClient, code: str, day: date = MONDAY, guests: int = 4) -> list[str]:
    r = await client.post(
        "/api/v1/availability/slots",
        json={"package_id": await pkg(client, code), "date": day.isoformat(), "guest_count": guests},
    )
    assert r.status_code == 200, r.text
    return [s["start_time"] for s in r.json()["slots"]]


async def cells(maker: async_sessionmaker[AsyncSession]) -> dict[str, tuple[int, int]]:
    from app.core.timeutil import to_local

    async with maker() as s:
        rows = (await s.execute(select(AvailabilitySlot))).scalars().all()
    return {to_local(c.start_at).strftime("%Y-%m-%d %H:%M"): (c.held_qty, c.booked_qty) for c in rows}


# --- availability ---------------------------------------------------------------------------------


async def test_avl_full_day_of_starts(client: AsyncClient) -> None:
    beginner = await starts(client, "BEGINNER")
    assert beginner[0] == "11:00" and beginner[-1] == "21:30" and len(beginner) == 22
    assert (await starts(client, "EXPERT"))[-1] == "21:00"


async def test_avl_hold_blocks_overlapping_starts_including_buffer(client: AsyncClient) -> None:
    assert (await hold(client, "EXPERT", start="18:00")).status_code == 201
    beginner = await starts(client, "BEGINNER")
    assert "17:00" in beginner and "19:30" in beginner
    for blocked in ("17:30", "18:00", "18:30", "19:00"):
        assert blocked not in beginner


async def test_avl_dates_and_holiday(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    r = await client.post(
        "/api/v1/admin/schedule/exceptions",
        headers=owner_headers,
        json={"type": "HOLIDAY", "date": MONDAY.isoformat(), "reason": "Festival"},
    )
    assert r.status_code == 201
    dates = (
        await client.get(
            "/api/v1/availability/dates",
            params={
                "package_id": await pkg(client, "EXPERT"),
                "guests": 4,
                "from": MONDAY.isoformat(),
                "to": (MONDAY + timedelta(days=1)).isoformat(),
            },
        )
    ).json()
    assert dates[0] == {
        "date": MONDAY.isoformat(),
        "status": "CLOSED",
        "slots_available": 0,
        "closed_reason": "Festival",
    }
    assert dates[1]["status"] == "OPEN" and dates[1]["slots_available"] == 21
    h = await hold(client)
    assert h.status_code == 422 and h.json()["error"]["code"] == "DATE_CLOSED"


async def test_large_group_requires_enquiry(client: AsyncClient) -> None:
    r = await hold(client, guests=21)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ENQUIRY_REQUIRED"
    assert (await hold(client, guests=20)).status_code == 201


async def test_today_slots_respect_cutoff(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/availability/slots",
        json={
            "package_id": await pkg(client, "BEGINNER"),
            "date": today_local().isoformat(),
            "guest_count": 2,
        },
    )
    from datetime import datetime

    earliest = utcnow() + timedelta(minutes=15)
    assert all(datetime.fromisoformat(s["start_at"]) >= earliest for s in r.json()["slots"])


# --- holds -----------------------------------------------------------------------------------------


async def test_hold_conflict_and_validation(
    client: AsyncClient, maker: async_sessionmaker[AsyncSession]
) -> None:
    first = await hold(client, "EXPERT", start="18:00")
    assert first.status_code == 201
    h = first.json()
    assert h["start_time"] == "18:00" and h["end_time"] == "19:00" and h["can_extend"] is True
    second = await hold(client, "BEGINNER", start="18:30")
    assert second.status_code == 409 and second.json()["error"]["code"] == "SLOT_UNAVAILABLE"
    assert (await hold(client, start="18:15")).status_code == 409  # off-grid
    assert (await hold(client, start="21:30")).status_code == 409  # game would end after closing
    assert (await cells(maker))[f"{MONDAY} 19:00"] == (1, 0)


async def test_hold_idempotency(client: AsyncClient) -> None:
    headers = key()
    a = await hold(client, headers=headers)
    b = await hold(client, headers=headers)
    assert a.status_code == b.status_code == 201 and a.json()["hold_id"] == b.json()["hold_id"]
    c = await hold(client, start="12:00", headers=headers)
    assert c.status_code == 409 and c.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"
    no_key = await client.post(
        "/api/v1/slot-holds",
        json={
            "package_id": await pkg(client, "EXPERT"),
            "date": MONDAY.isoformat(),
            "start_time": "12:00",
            "guest_count": 2,
        },
    )
    assert no_key.status_code == 422


async def test_hold_status_extend_and_release(
    client: AsyncClient, maker: async_sessionmaker[AsyncSession]
) -> None:
    h = (await hold(client)).json()
    tok = {"X-Hold-Token": h["hold_token"]}
    st = (await client.get(f"/api/v1/slot-holds/{h['hold_id']}", headers=tok)).json()
    assert st["status"] == "ACTIVE" and 0 < st["seconds_remaining"] <= 300
    assert (
        await client.get(f"/api/v1/slot-holds/{h['hold_id']}", headers={"X-Hold-Token": "wrong-token-123"})
    ).status_code == 404
    assert (await client.post(f"/api/v1/slot-holds/{h['hold_id']}/extend", headers=tok)).status_code == 200
    again = await client.post(f"/api/v1/slot-holds/{h['hold_id']}/extend", headers=tok)
    assert again.status_code == 409
    assert (await client.delete(f"/api/v1/slot-holds/{h['hold_id']}", headers=tok)).status_code == 204
    assert (
        await client.delete(f"/api/v1/slot-holds/{h['hold_id']}", headers=tok)
    ).status_code == 204  # idempotent
    assert all(v == (0, 0) for v in (await cells(maker)).values())
    assert "18:00" in await starts(client, "EXPERT")


async def expire(maker: async_sessionmaker[AsyncSession], hold_id: str) -> None:
    async with maker() as s:
        row = await s.get(SlotHold, uuid.UUID(hold_id))
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
        await s.commit()


async def test_expired_holds_are_swept(client: AsyncClient, maker: async_sessionmaker[AsyncSession]) -> None:
    h = (await hold(client)).json()
    await expire(maker, h["hold_id"])
    async with maker() as s:
        assert await hold_service.expire_due_holds(s) == 1
    assert all(v == (0, 0) for v in (await cells(maker)).values())


async def test_expired_hold_released_lazily_when_slot_requested(
    client: AsyncClient, maker: async_sessionmaker[AsyncSession]
) -> None:
    h = (await hold(client, "EXPERT", start="18:00")).json()
    await expire(maker, h["hold_id"])
    # A different package overlapping the expired hold's cells (incl. 19:00, outside the new request).
    r = await hold(client, "BEGINNER", start="18:00")
    assert r.status_code == 201, r.text
    c = await cells(maker)
    assert (
        c[f"{MONDAY} 18:00"] == (1, 0) and c[f"{MONDAY} 18:30"] == (1, 0) and c[f"{MONDAY} 19:00"] == (0, 0)
    )


# --- bookings --------------------------------------------------------------------------------------


async def test_bkg_happy_path(client: AsyncClient, maker: async_sessionmaker[AsyncSession]) -> None:
    h = (await hold(client, "EXPERT", day=MONDAY, guests=4)).json()
    r = await client.post("/api/v1/bookings", json=booking_body(h), headers=key())
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "CONFIRMED" and b["reference"].startswith("PLT-") and len(b["reference"]) == 10
    assert b["payment_status"] == "PENDING" and b["payment_mode"] == "PAY_AT_VENUE"
    assert b["pricing"]["total"] == "2400.00" and b["pricing"]["day_type"] == "WEEKDAY"
    assert b["customer"] == {"name": "Riya Sharma", "phone_masked": "98•••••210"}
    assert (b["start_time"], b["end_time"], b["guest_count"]) == ("18:00", "19:00", 4)

    c = await cells(maker)
    assert [c[f"{MONDAY} {t}"] for t in ("18:00", "18:30", "19:00")] == [(0, 1)] * 3
    async with maker() as s:
        assert (await s.get(SlotHold, uuid.UUID(h["hold_id"]))).status == "CONVERTED"  # type: ignore[union-attr]
        consent = (await s.execute(select(CustomerConsent))).scalar_one()
        assert consent.granted is True and consent.purpose == "WHATSAPP_TRANSACTIONAL"
        booking = (await s.execute(select(Booking))).scalar_one()
        assert booking.customer.phone_e164 == "+919876543210"
        assert booking.occasion_details == {"birthday_person_name": "Aarav", "birthday_person_age": 12}
        assert [i.item_type for i in booking.items] == ["PACKAGE"]

    view = await client.get(f"/api/v1/bookings/{b['id']}", headers={"X-Booking-Token": b["booking_token"]})
    assert (
        view.status_code == 200
        and view.json()["reference"] == b["reference"]
        and view.json()["booking_token"] is None
    )
    assert (await client.get(f"/api/v1/bookings/{b['id']}")).status_code == 404
    assert "18:00" not in await starts(client, "EXPERT")


async def test_bkg_idempotent_replay_and_double_use(
    client: AsyncClient, maker: async_sessionmaker[AsyncSession]
) -> None:
    h = (await hold(client)).json()
    headers = key()
    a = await client.post("/api/v1/bookings", json=booking_body(h), headers=headers)
    b = await client.post("/api/v1/bookings", json=booking_body(h), headers=headers)
    assert a.status_code == b.status_code == 201 and a.json() == b.json()
    c = await client.post("/api/v1/bookings", json=booking_body(h), headers=key())
    assert c.status_code == 409 and c.json()["error"]["code"] == "HOLD_NOT_ACTIVE"
    async with maker() as s:
        assert (await s.execute(select(func.count()).select_from(Booking))).scalar_one() == 1


async def test_bkg_rejects_expired_hold_and_releases_it(
    client: AsyncClient, maker: async_sessionmaker[AsyncSession]
) -> None:
    h = (await hold(client)).json()
    await expire(maker, h["hold_id"])
    headers = key()
    r = await client.post("/api/v1/bookings", json=booking_body(h), headers=headers)
    assert r.status_code == 410 and r.json()["error"]["code"] == "HOLD_EXPIRED"
    assert all(v == (0, 0) for v in (await cells(maker)).values())
    # The failed key was not stored, so a retry gets a clean answer (still expired), not "in progress".
    r = await client.post("/api/v1/bookings", json=booking_body(h), headers=headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "HOLD_NOT_ACTIVE"


async def test_bkg_validation(client: AsyncClient) -> None:
    h = (await hold(client)).json()
    bad_token = await client.post(
        "/api/v1/bookings", json=booking_body(h, hold_token="x" * 20), headers=key()
    )
    assert bad_token.status_code == 404
    corp = await client.post(
        "/api/v1/bookings",
        json=booking_body(h, occasion_code="CORPORATE", occasion_details={}),
        headers=key(),
    )
    assert corp.status_code == 422 and corp.json()["error"]["code"] == "ENQUIRY_REQUIRED"
    phone = await client.post(
        "/api/v1/bookings",
        json=booking_body(h, customer={"name": "Riya", "phone": "12345 67890"}),
        headers=key(),
    )
    assert phone.status_code == 422
    name = await client.post(
        "/api/v1/bookings",
        json=booking_body(h, customer={"name": "R1ya <b>", "phone": "9876543210"}),
        headers=key(),
    )
    assert name.status_code == 422
    detail = await client.post(
        "/api/v1/bookings", json=booking_body(h, occasion_details={"discount": "50%"}), headers=key()
    )
    assert detail.status_code == 422
    ok = await client.post(
        "/api/v1/bookings",
        json=booking_body(h, occasion_code="FRIENDS_FAMILY", occasion_details={}),
        headers=key(),
    )
    assert ok.status_code == 201


async def test_bkg_price_changed_and_snapshot_immutable(
    client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    pid = await pkg(client, "EXPERT")
    quote = (
        await client.post(
            "/api/v1/pricing/calculate",
            json={"package_id": pid, "date": MONDAY.isoformat(), "guest_count": 4},
        )
    ).json()
    h = (await hold(client)).json()
    rules = (
        await client.get("/api/v1/admin/pricing-rules", headers=owner_headers, params={"package_id": pid})
    ).json()["items"]
    weekday = next(r for r in rules if r["day_type"] == "WEEKDAY")
    await client.patch(
        f"/api/v1/admin/pricing-rules/{weekday['id']}",
        headers=owner_headers,
        json={"price_per_person": "700.00"},
    )

    r = await client.post("/api/v1/bookings", json=booking_body(h, quote_id=quote["quote_id"]), headers=key())
    assert r.status_code == 409 and r.json()["error"]["code"] == "PRICE_CHANGED"
    assert r.json()["error"]["details"] == {"quoted_total": "2400.00", "total": "2800.00"}
    r = await client.post("/api/v1/bookings", json=booking_body(h), headers=key())  # hold still active
    assert r.status_code == 201 and r.json()["pricing"]["total"] == "2800.00"
    b = r.json()

    await client.patch(
        f"/api/v1/admin/pricing-rules/{weekday['id']}",
        headers=owner_headers,
        json={"price_per_person": "100.00"},
    )
    view = await client.get(f"/api/v1/bookings/{b['id']}", headers={"X-Booking-Token": b["booking_token"]})
    assert view.json()["pricing"]["total"] == "2800.00"  # PRC-002


async def test_bkg_block_added_after_hold(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    h = (await hold(client, start="18:00")).json()
    await client.post(
        "/api/v1/admin/schedule/exceptions",
        headers=owner_headers,
        json={"type": "MANUAL_BLOCK", "date": MONDAY.isoformat(), "start_time": "18:30", "end_time": "19:00"},
    )
    r = await client.post("/api/v1/bookings", json=booking_body(h), headers=key())
    assert r.status_code == 409 and r.json()["error"]["code"] == "SLOT_UNAVAILABLE"


async def test_capacity_check_constraint_is_enforced(
    client: AsyncClient, maker: async_sessionmaker[AsyncSession]
) -> None:
    await hold(client)
    async with maker() as s:
        cell = (await s.execute(select(AvailabilitySlot).limit(1))).scalar_one()
        cell.booked_qty = cell.capacity  # held 1 + booked 1 > capacity 1
        with pytest.raises(DBAPIError):  # IntegrityError on SQLite, OperationalError 3819 on MySQL
            await s.commit()


# --- admin: cancel, reschedule, status, search -------------------------------------------------------


async def book(client: AsyncClient, **hold_kw: Any) -> dict[str, Any]:
    h = (await hold(client, **hold_kw)).json()
    r = await client.post("/api/v1/bookings", json=booking_body(h), headers=key())
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_admin_cancel_frees_capacity(
    client: AsyncClient,
    owner_headers: dict[str, str],
    maker: async_sessionmaker[AsyncSession],
    make_user,
    login,  # type: ignore[no-untyped-def]
) -> None:
    b = await book(client)
    viewer = await login(*(await make_user("VIEWER")))
    assert (
        await client.post(f"/api/v1/admin/bookings/{b['id']}/cancel", headers=viewer, json={"reason": "test"})
    ).status_code == 403
    r = await client.post(
        f"/api/v1/admin/bookings/{b['id']}/cancel", headers=owner_headers, json={"reason": "Customer called"}
    )
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert [h["to_status"] for h in r.json()["history"]] == ["CONFIRMED", "CANCELLED"]
    assert all(v == (0, 0) for v in (await cells(maker)).values())
    again = await client.post(
        f"/api/v1/admin/bookings/{b['id']}/cancel", headers=owner_headers, json={"reason": "again"}
    )
    assert again.status_code == 409
    assert "18:00" in await starts(client, "EXPERT")


async def test_admin_reschedule_moves_capacity_and_reprices(
    client: AsyncClient, owner_headers: dict[str, str], maker: async_sessionmaker[AsyncSession]
) -> None:
    b = await book(client, day=MONDAY, start="18:00")
    new_hold = (await hold(client, day=SATURDAY, start="12:00")).json()
    r = await client.post(
        f"/api/v1/admin/bookings/{b['id']}/reschedule",
        headers=owner_headers,
        json={"hold_id": new_hold["hold_id"], "hold_token": new_hold["hold_token"], "reason": "Moved"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["date"], out["start_time"], out["pricing"]["total"]) == (
        SATURDAY.isoformat(),
        "12:00",
        "2600.00",
    )
    assert out["history"][-1]["details"]["from"]["total"] == "2400.00"
    c = await cells(maker)
    assert c[f"{MONDAY} 18:00"] == (0, 0) and c[f"{SATURDAY} 12:00"] == (0, 1)

    other = (await hold(client, "BEGINNER", day=SATURDAY, start="15:00")).json()
    mismatch = await client.post(
        f"/api/v1/admin/bookings/{b['id']}/reschedule",
        headers=owner_headers,
        json={"hold_id": other["hold_id"], "hold_token": other["hold_token"]},
    )
    assert mismatch.status_code == 422


async def test_admin_status_and_search(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    b = await book(client)
    early = await client.post(
        f"/api/v1/admin/bookings/{b['id']}/status", headers=owner_headers, json={"status": "COMPLETED"}
    )
    assert early.status_code == 409  # not started yet
    found = (
        await client.get("/api/v1/admin/bookings", headers=owner_headers, params={"phone": "9876543210"})
    ).json()
    assert found["total"] == 1 and found["items"][0]["customer_phone"] == "+919876543210"
    by_ref = (
        await client.get(
            "/api/v1/admin/bookings", headers=owner_headers, params={"reference": b["reference"].lower()}
        )
    ).json()
    assert by_ref["total"] == 1
    none = (
        await client.get("/api/v1/admin/bookings", headers=owner_headers, params={"status": ["CANCELLED"]})
    ).json()
    assert none["total"] == 0


async def test_staff_can_hold_and_book(client: AsyncClient, make_user, login) -> None:  # type: ignore[no-untyped-def]
    staff = await login(*(await make_user("STAFF")))
    body = {
        "package_id": await pkg(client, "INTERMEDIATE"),
        "date": MONDAY.isoformat(),
        "start_time": "13:00",
        "guest_count": 6,
    }
    h = await client.post("/api/v1/admin/slot-holds", json=body, headers=staff | key())
    assert h.status_code == 201, h.text
    r = await client.post("/api/v1/admin/bookings", json=booking_body(h.json()), headers=staff | key())
    assert r.status_code == 201 and r.json()["channel"] == "STAFF"


async def test_resource_grid_change_blocked_by_future_bookings(
    client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    await book(client)
    resource = (await client.get("/api/v1/admin/resources", headers=owner_headers)).json()[0]
    r = await client.patch(
        f"/api/v1/admin/resources/{resource['id']}", headers=owner_headers, json={"slot_interval_min": 15}
    )
    assert r.status_code == 409
    ok = await client.patch(
        f"/api/v1/admin/resources/{resource['id']}", headers=owner_headers, json={"buffer_min": 15}
    )
    assert ok.status_code == 200


# --- enquiries -------------------------------------------------------------------------------------


async def test_enquiry_flow(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    body = {
        "customer": {"name": "Anil Kapoor", "phone": "9811122233"},
        "occasion_code": "CORPORATE",
        "guest_count": 40,
        "preferred_date": (MONDAY + timedelta(days=7)).isoformat(),
        "details": {"company_name": "Acme India", "special_requirements": "Lunch for 40"},
    }
    r = await client.post("/api/v1/event-enquiries", json=body, headers=key())
    assert r.status_code == 201, r.text
    assert r.json()["reference"].startswith("ENQ-") and r.json()["status"] == "NEW"
    bad = await client.post("/api/v1/event-enquiries", json={**body, "details": {"x": "y"}}, headers=key())
    assert bad.status_code == 422
    listed = (
        await client.get("/api/v1/admin/enquiries", headers=owner_headers, params={"status": ["NEW"]})
    ).json()
    assert listed["total"] == 1 and listed["items"][0]["details"]["company_name"] == "Acme India"
    upd = await client.patch(
        f"/api/v1/admin/enquiries/{r.json()['id']}",
        headers=owner_headers,
        json={"status": "CONTACTED", "staff_notes": "Called, sending quote"},
    )
    assert upd.status_code == 200 and upd.json()["status"] == "CONTACTED"

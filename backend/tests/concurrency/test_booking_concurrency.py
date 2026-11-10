"""Concurrency tests (CONC-*). They need real row locking, so they only run on MySQL:

    TEST_DATABASE_URL=mysql+asyncmy://root:root@127.0.0.1:3306/plt_test pytest tests/concurrency

Each task uses its own session/connection, like separate kiosks and web users hitting the API at once.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from collections import Counter
from datetime import date, time, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import DomainError, SlotUnavailableError
from app.core.timeutil import today_local, utcnow
from app.models.booking import AvailabilitySlot, Booking, SlotHold
from app.models.catalogue import Package
from app.schemas.booking import BookingCreate, HoldCreate
from app.services import booking_service, hold_service
from app.services.context import Actor
from tests.conftest import TEST_DB_URL, make_settings

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL.startswith("mysql"),
    reason="concurrency tests need MySQL row locks (set TEST_DATABASE_URL)",
)

SETTINGS = make_settings()


def monday() -> date:
    d = today_local() + timedelta(days=1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


async def packages(maker: async_sessionmaker[AsyncSession]) -> dict[str, uuid.UUID]:
    async with maker() as s:
        return {p.code: p.id for p in (await s.execute(select(Package))).scalars()}


async def try_hold(
    maker: async_sessionmaker[AsyncSession],
    package_id: uuid.UUID,
    day: date,
    start: time,
    guests: int = 4,
    key: str | None = None,
) -> dict[str, Any] | None:
    async with maker() as s:
        try:
            _, body = await hold_service.create_hold(
                s,
                SETTINGS,
                HoldCreate(package_id=package_id, date=day, start_time=start, guest_count=guests),
                channel="WEB",
                idempotency_key=key or str(uuid.uuid4()),
            )
            return body
        except SlotUnavailableError:
            return None


async def assert_invariants(maker: async_sessionmaker[AsyncSession]) -> None:
    """held/booked counters equal the live holds/bookings on every cell and never exceed capacity."""
    async with maker() as s:
        cells = {c.id: c for c in (await s.execute(select(AvailabilitySlot))).scalars()}
        held: Counter[int] = Counter()
        for h in (await s.execute(select(SlotHold).where(SlotHold.status == "ACTIVE"))).scalars():
            for hc in h.cells:
                held[hc.slot_id] += h.units
        booked: Counter[int] = Counter()
        for b in (await s.execute(select(Booking).where(Booking.status == "CONFIRMED"))).scalars():
            for bs in b.slots:
                booked[bs.slot_id] += bs.units
    for cid, cell in cells.items():
        assert cell.held_qty == held[cid], f"cell {cell.start_at} held {cell.held_qty} != {held[cid]}"
        assert cell.booked_qty == booked[cid], (
            f"cell {cell.start_at} booked {cell.booked_qty} != {booked[cid]}"
        )
        assert cell.held_qty + cell.booked_qty <= cell.capacity


async def test_conc001_many_customers_same_slot_exactly_one_wins(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    pk = (await packages(maker))["EXPERT"]
    results = await asyncio.gather(*(try_hold(maker, pk, monday(), time(18)) for _ in range(30)))
    assert sum(r is not None for r in results) == 1
    await assert_invariants(maker)


async def test_conc002_overlapping_packages_only_one_wins(maker: async_sessionmaker[AsyncSession]) -> None:
    p = await packages(maker)
    attempts = [
        (p["EXPERT"], time(18)),  # 18:00-19:10 -> 18:00,18:30,19:00
        (p["BEGINNER"], time(18, 30)),  # 18:30,19:00
        (p["INTERMEDIATE"], time(17, 30)),  # 17:30,18:00 (45+10 -> 18:25)
        (p["BEGINNER"], time(19)),  # 19:00,19:30
    ] * 5
    random.shuffle(attempts)
    results = await asyncio.gather(*(try_hold(maker, pk, monday(), t) for pk, t in attempts))
    won = [r for r in results if r is not None]
    # All four candidates overlap the 18:00/18:30/19:00 cells pairwise in a chain; at most two can coexist
    # (e.g. 17:30 Intermediate + 18:30 Beginner). Verify via the invariant rather than a fixed count.
    assert 1 <= len(won) <= 2
    await assert_invariants(maker)


async def test_conc003_concurrent_booking_same_idempotency_key(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    pk = (await packages(maker))["EXPERT"]
    h = await try_hold(maker, pk, monday(), time(12))
    assert h is not None
    key = str(uuid.uuid4())
    data = BookingCreate(
        hold_id=h["hold_id"],
        hold_token=h["hold_token"],
        customer={"name": "Riya", "phone": "9876543210"},  # type: ignore[arg-type]
        occasion_code="FRIENDS_FAMILY",
    )

    async def attempt() -> dict[str, Any] | str:
        async with maker() as s:
            try:
                _, body = await booking_service.create_booking(
                    s, SETTINGS, data, channel="WEB", idempotency_key=key, actor=Actor("PUBLIC")
                )
                return body
            except DomainError as exc:
                return exc.code

    results = await asyncio.gather(*(attempt() for _ in range(8)))
    bodies = [r for r in results if isinstance(r, dict)]
    assert bodies, results
    assert len({b["id"] for b in bodies}) == 1
    assert all(r == "REQUEST_IN_PROGRESS" for r in results if isinstance(r, str))
    async with maker() as s:
        assert len((await s.execute(select(Booking))).scalars().all()) == 1
    await assert_invariants(maker)


async def test_conc004_two_holds_same_slot_race_to_book(maker: async_sessionmaker[AsyncSession]) -> None:
    """Website and kiosk hold different but overlapping slots; only valid holds can exist, both can book."""
    p = await packages(maker)
    a = await try_hold(maker, p["BEGINNER"], monday(), time(14))
    b = await try_hold(maker, p["BEGINNER"], monday(), time(15))
    assert a and b

    async def book(h: dict[str, Any], phone: str) -> str:
        async with maker() as s:
            data = BookingCreate(
                hold_id=h["hold_id"],
                hold_token=h["hold_token"],
                customer={"name": "Guest", "phone": phone},  # type: ignore[arg-type]
                occasion_code="FRIENDS_FAMILY",
            )
            _, body = await booking_service.create_booking(
                s, SETTINGS, data, channel="WEB", idempotency_key=str(uuid.uuid4()), actor=Actor("PUBLIC")
            )
            return str(body["status"])

    assert await asyncio.gather(book(a, "9876543210"), book(b, "9876543211")) == ["CONFIRMED", "CONFIRMED"]
    await assert_invariants(maker)


async def test_conc005_booking_races_hold_expiry(maker: async_sessionmaker[AsyncSession]) -> None:
    pk = (await packages(maker))["EXPERT"]
    h = await try_hold(maker, pk, monday(), time(16))
    assert h is not None
    async with maker() as s:
        row = await s.get(SlotHold, uuid.UUID(h["hold_id"]))
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
        await s.commit()

    async def book() -> str:
        async with maker() as s:
            data = BookingCreate(
                hold_id=h["hold_id"],
                hold_token=h["hold_token"],
                customer={"name": "Late", "phone": "9876543210"},  # type: ignore[arg-type]
                occasion_code="FRIENDS_FAMILY",
            )
            try:
                await booking_service.create_booking(
                    s, SETTINGS, data, channel="WEB", idempotency_key=str(uuid.uuid4()), actor=Actor("PUBLIC")
                )
                return "BOOKED"
            except DomainError as exc:
                return exc.code

    async def sweep() -> int:
        async with maker() as s:
            return await hold_service.expire_due_holds(s)

    outcome, _ = await asyncio.gather(book(), sweep())
    assert outcome in ("HOLD_EXPIRED", "HOLD_NOT_ACTIVE")  # never booked after expiry
    await assert_invariants(maker)


async def test_conc006_randomized_swarm_keeps_invariants(maker: async_sessionmaker[AsyncSession]) -> None:
    p = await packages(maker)
    codes = list(p)
    rng = random.Random(42)
    starts = [time(h, m) for h in range(11, 21) for m in (0, 30)]
    jobs = [
        try_hold(maker, p[rng.choice(codes)], monday(), rng.choice(starts), rng.randint(1, 20))
        for _ in range(60)
    ]
    results = await asyncio.gather(*jobs)
    holds = [r for r in results if r is not None]
    assert holds

    # Book half of the winners concurrently, release the rest.
    async def finish(i: int, h: dict[str, Any]) -> None:
        async with maker() as s:
            if i % 2 == 0:
                data = BookingCreate(
                    hold_id=h["hold_id"],
                    hold_token=h["hold_token"],
                    customer={"name": "Swarm", "phone": f"98765{i:05d}"},  # type: ignore[arg-type]
                    occasion_code="FRIENDS_FAMILY",
                )
                await booking_service.create_booking(
                    s, SETTINGS, data, channel="WEB", idempotency_key=str(uuid.uuid4()), actor=Actor("PUBLIC")
                )
            else:
                await hold_service.release_hold(s, SETTINGS, uuid.UUID(h["hold_id"]), h["hold_token"])

    await asyncio.gather(*(finish(i, h) for i, h in enumerate(holds)))
    await assert_invariants(maker)

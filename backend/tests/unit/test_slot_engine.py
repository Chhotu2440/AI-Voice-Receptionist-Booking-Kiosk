"""Slot engine unit tests (AVL-*). Times are IST; cells are compared in UTC."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from app.core.timeutil import BUSINESS_TZ
from app.services.slot_engine import (
    ExceptionView,
    HoursView,
    bookable,
    build_day_schedule,
    candidate_at,
    candidates,
    remaining_units,
)

DAY = date(2026, 11, 16)
HOURS = HoursView(time(11), time(22))
OPEN = build_day_schedule(HOURS, [])


def ist(h: int, m: int = 0, d: date = DAY) -> datetime:
    return datetime.combine(d, time(h, m), tzinfo=BUSINESS_TZ).astimezone(UTC)


def starts(duration: int, schedule=OPEN, interval: int = 30, buffer: int = 10) -> list[datetime]:  # type: ignore[no-untyped-def]
    return [
        c.start_at
        for c in candidates(DAY, schedule, interval_min=interval, duration_min=duration, buffer_min=buffer)
    ]


def test_starts_run_from_opening_until_game_fits_before_close() -> None:
    s30, s60 = starts(30), starts(60)
    assert s30[0] == ist(11) and s30[-1] == ist(21, 30) and len(s30) == 22
    assert s60[-1] == ist(21)


def test_avl002_expert_occupies_three_cells_with_buffer() -> None:
    c = candidate_at(DAY, time(18), OPEN, interval_min=30, duration_min=60, buffer_min=10)
    assert c is not None
    assert c.cells == (ist(18), ist(18, 30), ist(19))
    assert c.end_at == ist(19) and c.occupied_until == ist(19, 10)


def test_beginner_with_buffer_occupies_two_cells() -> None:
    c = candidate_at(DAY, time(18), OPEN, interval_min=30, duration_min=30, buffer_min=10)
    assert c is not None and c.cells == (ist(18), ist(18, 30))


def test_no_buffer_occupies_exact_cells() -> None:
    c = candidate_at(DAY, time(18), OPEN, interval_min=30, duration_min=45, buffer_min=0)
    assert c is not None and c.cells == (ist(18), ist(18, 30))


def test_buffer_clipped_at_closing() -> None:
    c = candidate_at(DAY, time(21), OPEN, interval_min=30, duration_min=60, buffer_min=10)
    assert c is not None and c.cells == (ist(21), ist(21, 30)) and c.occupied_until == ist(22)


def test_game_must_end_by_close() -> None:
    assert candidate_at(DAY, time(21, 30), OPEN, interval_min=30, duration_min=60, buffer_min=10) is None
    assert candidate_at(DAY, time(21, 30), OPEN, interval_min=30, duration_min=30, buffer_min=10) is not None


def test_misaligned_or_outside_hours_rejected() -> None:
    assert candidate_at(DAY, time(18, 15), OPEN, interval_min=30, duration_min=30, buffer_min=10) is None
    assert candidate_at(DAY, time(10, 30), OPEN, interval_min=30, duration_min=30, buffer_min=10) is None


def test_opening_not_on_grid_rounds_up() -> None:
    sched = build_day_schedule(HoursView(time(11, 15), time(22)), [])
    assert starts(30, sched)[0] == ist(11, 30)


def test_avl003_holiday_closes_day() -> None:
    sched = build_day_schedule(HOURS, [ExceptionView("HOLIDAY", reason="Diwali")])
    assert not sched.is_open and sched.closed_reason == "Diwali"
    assert starts(30, sched) == []


def test_closed_weekday_and_missing_hours() -> None:
    assert not build_day_schedule(HoursView(time(11), time(22), is_closed=True), []).is_open
    assert not build_day_schedule(None, []).is_open


def test_special_hours_replace_and_can_open_closed_day() -> None:
    special = [ExceptionView("SPECIAL_HOURS", time(14), time(18))]
    sched = build_day_schedule(HoursView(time(11), time(22), is_closed=True), special)
    s = starts(60, sched)
    assert s[0] == ist(14) and s[-1] == ist(17)


def test_manual_block_removes_overlapping_games_only() -> None:
    sched = build_day_schedule(HOURS, [ExceptionView("MANUAL_BLOCK", time(15), time(16))])
    s = starts(60, sched)
    assert ist(14) in s  # 14:00-15:00 ends exactly at block start (buffer may overlap)
    assert ist(14, 30) not in s and ist(15) not in s and ist(15, 30) not in s
    assert ist(16) in s


def test_timed_holiday_acts_as_block() -> None:
    sched = build_day_schedule(HOURS, [ExceptionView("HOLIDAY", time(11), time(13))])
    assert sched.is_open and starts(30, sched)[0] == ist(13)


def test_remaining_and_bookable() -> None:
    c = candidate_at(DAY, time(18), OPEN, interval_min=30, duration_min=60, buffer_min=10)
    assert c is not None
    free = {ist(18): 1, ist(18, 30): 1, ist(19): 0}
    assert remaining_units(c, free, 1) == 0
    assert not bookable(c, free, units=1, default_capacity=1, earliest_start=ist(9))
    assert bookable(c, {}, units=1, default_capacity=1, earliest_start=ist(9))  # cells not created yet
    assert not bookable(c, {}, units=1, default_capacity=1, earliest_start=ist(18) + timedelta(minutes=1))


def test_shared_capacity_remaining_is_minimum_across_cells() -> None:
    c = candidate_at(DAY, time(18), OPEN, interval_min=30, duration_min=60, buffer_min=10)
    assert c is not None
    assert remaining_units(c, {ist(18): 12, ist(18, 30): 5}, 20) == 5

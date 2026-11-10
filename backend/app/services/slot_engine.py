"""Pure slot engine: opening schedule, candidate start times and grid cells. No I/O.

Model (decisions D-01/D-02):
* Each resource has a fixed grid of *cells* aligned to local midnight, `slot_interval_min` long.
  Cells are the unit of capacity locking in the database (`availability_slots` rows).
* A booking that starts at T for a package of duration D occupies the window
  [T, min(T + D + buffer, close)) and therefore every cell overlapping that window.
  Example (30-min grid, 10-min buffer): Expert (60 min) at 18:00 occupies 18:00, 18:30 and 19:00,
  so the next possible start is 19:30.
* Start times are grid-aligned, at or after opening, and the game (not the buffer) must end by closing.
* Holidays/blackouts without times close the day; with times (and manual blocks) they block any game
  whose playing time overlaps them. Special hours replace the normal opening hours for that date.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.timeutil import BUSINESS_TZ


@dataclass(frozen=True)
class HoursView:
    open_time: time
    close_time: time
    is_closed: bool = False


@dataclass(frozen=True)
class ExceptionView:
    type: str  # HOLIDAY | SPECIAL_HOURS | BLACKOUT | MANUAL_BLOCK
    start_time: time | None = None
    end_time: time | None = None
    reason: str = ""


@dataclass(frozen=True)
class DaySchedule:
    is_open: bool
    open_time: time | None = None
    close_time: time | None = None
    blocks: tuple[tuple[time, time], ...] = ()
    closed_reason: str = ""


@dataclass(frozen=True)
class Candidate:
    start_at: datetime  # UTC
    end_at: datetime  # UTC, end of play
    occupied_until: datetime  # UTC, end of play + buffer (clipped at closing)
    cells: tuple[datetime, ...]  # UTC cell starts

    @property
    def duration(self) -> timedelta:
        return self.end_at - self.start_at


def build_day_schedule(hours: HoursView | None, exceptions: Sequence[ExceptionView]) -> DaySchedule:
    for exc in exceptions:
        if exc.type in ("HOLIDAY", "BLACKOUT") and exc.start_time is None:
            return DaySchedule(is_open=False, closed_reason=exc.reason or exc.type.title())

    special = [e for e in exceptions if e.type == "SPECIAL_HOURS" and e.start_time and e.end_time]
    if special:
        open_t, close_t = special[-1].start_time, special[-1].end_time
    elif hours is None or hours.is_closed:
        return DaySchedule(is_open=False, closed_reason="Closed")
    else:
        open_t, close_t = hours.open_time, hours.close_time
    assert open_t is not None and close_t is not None

    blocks = tuple(
        sorted(
            (e.start_time, e.end_time)
            for e in exceptions
            if e.type in ("HOLIDAY", "BLACKOUT", "MANUAL_BLOCK") and e.start_time and e.end_time
        )
    )
    return DaySchedule(is_open=True, open_time=open_t, close_time=close_t, blocks=blocks)


def _local(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz)


def _aligned(dt: datetime, interval: int) -> bool:
    minutes = dt.hour * 60 + dt.minute
    return dt.second == 0 and dt.microsecond == 0 and minutes % interval == 0


def _first_aligned_at_or_after(dt: datetime, interval: int) -> datetime:
    minutes = dt.hour * 60 + dt.minute + (1 if (dt.second or dt.microsecond) else 0)
    rounded = -(-minutes // interval) * interval
    return dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=rounded)


def _build(start: datetime, duration_min: int, buffer_min: int, interval: int, close: datetime) -> Candidate:
    end = start + timedelta(minutes=duration_min)
    occupied_until = min(end + timedelta(minutes=buffer_min), close)
    cells: list[datetime] = []
    cell = start
    while cell < occupied_until:
        cells.append(cell.astimezone(UTC))
        cell += timedelta(minutes=interval)
    return Candidate(start.astimezone(UTC), end.astimezone(UTC), occupied_until.astimezone(UTC), tuple(cells))


def _blocked(schedule: DaySchedule, d: date, start: datetime, end: datetime, tz: ZoneInfo) -> bool:
    for b_start, b_end in schedule.blocks:
        if start < _local(d, b_end, tz) and end > _local(d, b_start, tz):
            return True
    return False


def candidates(
    play_date: date,
    schedule: DaySchedule,
    *,
    interval_min: int,
    duration_min: int,
    buffer_min: int,
    tz: ZoneInfo = BUSINESS_TZ,
) -> list[Candidate]:
    """All structurally valid starts for the day (ignores occupancy and booking cut-offs)."""
    if not schedule.is_open or schedule.open_time is None or schedule.close_time is None:
        return []
    open_dt = _local(play_date, schedule.open_time, tz)
    close_dt = _local(play_date, schedule.close_time, tz)
    result: list[Candidate] = []
    start = _first_aligned_at_or_after(open_dt, interval_min)
    while start + timedelta(minutes=duration_min) <= close_dt:
        if not _blocked(schedule, play_date, start, start + timedelta(minutes=duration_min), tz):
            result.append(_build(start, duration_min, buffer_min, interval_min, close_dt))
        start += timedelta(minutes=interval_min)
    return result


def candidate_at(
    play_date: date,
    start_time: time,
    schedule: DaySchedule,
    *,
    interval_min: int,
    duration_min: int,
    buffer_min: int,
    tz: ZoneInfo = BUSINESS_TZ,
) -> Candidate | None:
    """The candidate starting at `start_time`, or None if that start is not valid for the day."""
    start = _local(play_date, start_time, tz)
    if not _aligned(start, interval_min):
        return None
    for c in candidates(
        play_date,
        schedule,
        interval_min=interval_min,
        duration_min=duration_min,
        buffer_min=buffer_min,
        tz=tz,
    ):
        if c.start_at == start.astimezone(UTC):
            return c
    return None


def remaining_units(candidate: Candidate, free_by_cell: Mapping[datetime, int], default_capacity: int) -> int:
    """Smallest free capacity across the cells the candidate needs (cells not yet created are empty)."""
    return min(free_by_cell.get(c, default_capacity) for c in candidate.cells)


def bookable(
    candidate: Candidate,
    free_by_cell: Mapping[datetime, int],
    *,
    units: int,
    default_capacity: int,
    earliest_start: datetime,
) -> bool:
    return (
        candidate.start_at >= earliest_start
        and remaining_units(candidate, free_by_cell, default_capacity) >= units
    )

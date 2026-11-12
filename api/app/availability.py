"""Availability engine: pure functions, no I/O.

A start time t is valid for a stylist when [t, t + duration + buffer):
  * lies fully inside one working window of that weekday's shift_template,
  * does not overlap breaks, time blocks, or any blocking booking (all passed in as `busy`),
  * and t >= now + min_lead, on a non-holiday date within max_advance_days.
Intervals are half-open, so back-to-back is allowed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .tz import at_local, local_date

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class Rules:
    tz: ZoneInfo
    slot_step_min: int = 15
    min_lead_min: int = 60
    max_advance_days: int = 30


@dataclass(frozen=True)
class ServiceSpec:
    duration_min: int
    buffer_min: int = 0

    @property
    def span(self) -> timedelta:
        return timedelta(minutes=self.duration_min + self.buffer_min)


@dataclass
class StaffSpec:
    id: str
    shift_template: dict
    service_ids: set = field(default_factory=set)


@dataclass(frozen=True)
class Slot:
    start: datetime
    staff_ids: tuple[str, ...]


def is_blocking(status: str, hold_expires_at: datetime | None, now: datetime) -> bool:
    """Does a booking occupy its slot? Cancelled/expired never; a lapsed hold counts as free."""
    if status in ("cancelled", "expired"):
        return False
    if status == "held" and hold_expires_at is not None and hold_expires_at < now:
        return False
    return True


def _overlaps(a: datetime, b: datetime, busy: list[Interval]) -> bool:
    return any(a < y and x < b for x, y in busy)


def break_intervals(template: dict, d: date, tz: ZoneInfo) -> list[Interval]:
    key = DAYS[d.weekday()]
    return [(at_local(d, b["start"], tz), at_local(d, b["end"], tz)) for b in template.get("breaks", {}).get(key, [])]


def working_windows(template: dict, d: date, tz: ZoneInfo) -> list[Interval]:
    key = DAYS[d.weekday()]
    return [(at_local(d, w["start"], tz), at_local(d, w["end"], tz)) for w in template.get(key, [])]


def staff_slots(
    rules: Rules,
    service: ServiceSpec,
    staff: StaffSpec,
    busy: list[Interval],
    d: date,
    now: datetime,
) -> list[datetime]:
    tz = rules.tz
    today = local_date(now, tz)
    if d < today or d > today + timedelta(days=rules.max_advance_days):
        return []
    earliest = now + timedelta(minutes=rules.min_lead_min)
    blocked = busy + break_intervals(staff.shift_template, d, tz)
    step = timedelta(minutes=rules.slot_step_min)
    midnight = at_local(d, "00:00", tz)
    out: list[datetime] = []
    for ws, we in working_windows(staff.shift_template, d, tz):
        # grid anchored to local midnight so 10:00 / 10:15 ... stay aligned
        k = -(-(ws - midnight) // step)
        t = midnight + k * step
        while t + service.span <= we:
            if t >= earliest and not _overlaps(t, t + service.span, blocked):
                out.append(t)
            t += step
    return out


def get_slots(
    rules: Rules,
    service_id: str,
    service: ServiceSpec,
    staffs: list[StaffSpec],
    busy_by_staff: dict[str, list[Interval]],
    holidays: set[date],
    d: date,
    now: datetime,
) -> list[Slot]:
    """Open start times for `d`. Several staff => union ("any available")."""
    if d in holidays:
        return []
    by_start: dict[datetime, list[str]] = {}
    for st in staffs:
        if service_id not in st.service_ids:
            continue
        for t in staff_slots(rules, service, st, busy_by_staff.get(st.id, []), d, now):
            by_start.setdefault(t, []).append(st.id)
    return [Slot(t, tuple(ids)) for t, ids in sorted(by_start.items())]


def day_counts(
    rules: Rules,
    service_id: str,
    service: ServiceSpec,
    staffs: list[StaffSpec],
    busy_by_staff: dict[str, list[Interval]],
    holidays: set[date],
    start: date,
    days: int,
    now: datetime,
) -> list[dict]:
    """Per-day open-slot counts from ONE preloaded busy set (no per-day queries)."""
    out = []
    today = local_date(now, rules.tz)
    for i in range(days):
        d = start + timedelta(days=i)
        n = len(get_slots(rules, service_id, service, staffs, busy_by_staff, holidays, d, now))
        # why a day has no times, so the calendar can say "Closed" instead of "Full"
        closed = "holiday" if d in holidays else ("out_of_range" if d > today + timedelta(days=rules.max_advance_days) else None)
        out.append({"date": d.isoformat(), "count": n, "full": n == 0, "closed": closed})
    return out


def pick_staff(candidate_ids: tuple[str, ...], booked_minutes: dict[str, int]) -> list[str]:
    """Any-available assignment order: fewest booked minutes that day first (ties: stable by id)."""
    return sorted(candidate_ids, key=lambda s: (booked_minutes.get(s, 0), s))


def part_of_day(dt: datetime, tz: ZoneInfo) -> str:
    h = dt.astimezone(tz).hour
    return "morning" if h < 12 else ("afternoon" if h < 17 else "evening")

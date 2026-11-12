from datetime import date, datetime, timedelta, timezone

from app.availability import (Rules, ServiceSpec, StaffSpec, day_counts, get_slots, is_blocking, pick_staff,
                              staff_slots)
from app.tz import day_bounds, local_date, zone

IST = zone("Asia/Kolkata")
RULES = Rules(tz=IST, slot_step_min=15, min_lead_min=60, max_advance_days=30)
NOW = datetime(2026, 11, 9, 8, 0, tzinfo=IST)  # Monday morning
WED = date(2026, 11, 11)


def t(d, hh, mm=0):
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST)


def tpl(start="10:00", end="20:00", off=(), breaks=None):
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    out = {d: ([] if d in off else [{"start": start, "end": end}]) for d in days}
    out["breaks"] = breaks or {}
    return out


def staff(sid="a", template=None, services=("s",)):
    return StaffSpec(sid, template or tpl(), set(services))


def starts(slots):
    return [s.start for s in slots]


def run(svc, staffs, busy=None, holidays=frozenset(), d=WED, now=NOW):
    return get_slots(RULES, "s", svc, staffs, busy or {}, set(holidays), d, now)


def test_basic_grid_and_last_slot_respects_span():
    s = starts(run(ServiceSpec(60, 0), [staff()]))
    assert s[0] == t(WED, 10) and s[-1] == t(WED, 19)  # 19:00 + 60m == shift end


def test_buffer_pushes_past_end_of_shift():
    s = starts(run(ServiceSpec(60, 15), [staff()]))
    assert s[-1] == t(WED, 18, 45)  # 19:00 would need until 20:15


def test_service_cannot_cross_break():
    st = staff(template=tpl(breaks={"wed": [{"start": "14:00", "end": "14:30"}]}))
    s = starts(run(ServiceSpec(60, 0), [st]))
    assert t(WED, 13, 0) in s and t(WED, 13, 15) not in s  # 13:15-14:15 hits break
    assert t(WED, 13, 30) not in s and t(WED, 14, 0) not in s
    assert t(WED, 14, 30) in s


def test_holiday_and_weekly_off():
    assert run(ServiceSpec(30), [staff()], holidays={WED}) == []
    assert run(ServiceSpec(30), [staff(template=tpl(off=("wed",)))]) == []


def test_partial_day_block():
    busy = {"a": [(t(WED, 12), t(WED, 15))]}
    s = starts(run(ServiceSpec(30, 0), [staff()], busy))
    assert t(WED, 11, 30) in s and t(WED, 11, 45) not in s and t(WED, 14, 45) not in s and t(WED, 15) in s


def test_today_past_hidden_and_min_lead():
    now = t(WED, 12, 10)
    s = starts(run(ServiceSpec(30, 0), [staff()], now=now))
    assert s[0] == t(WED, 13, 15)  # >= 13:10, on the 15-minute grid


def test_back_to_back_allowed():
    busy = {"a": [(t(WED, 10), t(WED, 11))]}
    assert t(WED, 11) in starts(run(ServiceSpec(30, 0), [staff()], busy))


def test_expired_hold_counts_as_free():
    assert not is_blocking("held", NOW - timedelta(minutes=1), NOW)
    assert is_blocking("held", NOW + timedelta(minutes=5), NOW)
    assert is_blocking("confirmed", None, NOW) and not is_blocking("cancelled", None, NOW)
    assert not is_blocking("expired", None, NOW)


def test_unqualified_staff_gets_no_slots():
    assert run(ServiceSpec(30), [staff(services=("other",))]) == []


def test_any_available_union():
    a, b = staff("a"), staff("b")
    busy = {"a": [(t(WED, 10), t(WED, 12))]}
    slots = run(ServiceSpec(30, 0), [a, b], busy)
    first = slots[0]
    assert first.start == t(WED, 10) and first.staff_ids == ("b",)
    at_noon = next(s for s in slots if s.start == t(WED, 12))
    assert set(at_noon.staff_ids) == {"a", "b"}
    assert pick_staff(at_noon.staff_ids, {"a": 120, "b": 30}) == ["b", "a"]


def test_ist_date_boundary():
    late = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)  # 23:30 IST on the 11th
    assert local_date(late, IST) == date(2026, 11, 11)
    assert local_date(datetime(2026, 11, 11, 19, 0, tzinfo=timezone.utc), IST) == date(2026, 11, 12)
    a, b = day_bounds(date(2026, 11, 11), IST)
    assert a <= late < b
    night = staff(template=tpl("22:00", "23:59"))
    s = staff_slots(RULES, ServiceSpec(30), night, [], WED, NOW)
    assert s[-1] == t(WED, 23, 15) and all(local_date(x, IST) == WED for x in s)


def test_max_advance_and_past_dates():
    assert run(ServiceSpec(30), [staff()], d=NOW.date() + timedelta(days=31)) == []
    assert run(ServiceSpec(30), [staff()], d=NOW.date() - timedelta(days=1)) == []
    assert run(ServiceSpec(30), [staff()], d=NOW.date() + timedelta(days=30)) != []


def test_day_counts_marks_full_days():
    counts = day_counts(RULES, "s", ServiceSpec(30), [staff()], {}, {WED}, NOW.date(), 14, NOW)
    assert len(counts) == 14
    wed = next(c for c in counts if c["date"] == WED.isoformat())
    assert wed["full"] and wed["count"] == 0
    assert next(c for c in counts if c["date"] == "2026-11-12")["count"] > 0

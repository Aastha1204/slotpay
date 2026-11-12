from datetime import date, datetime, timedelta

import psycopg
import pytest
from test_availability import IST, NOW, RULES, WED, staff
from test_manage import M, owner  # noqa: F401

from app.availability import ServiceSpec, day_counts


def test_day_counts_flag_holiday_and_out_of_range():
    start = NOW.date()
    counts = day_counts(RULES, "s", ServiceSpec(30), [staff()], {}, {WED}, start, 40, NOW)
    by = {c["date"]: c for c in counts}
    assert by[WED.isoformat()]["closed"] == "holiday" and by[WED.isoformat()]["full"]
    last_ok = (start + timedelta(days=RULES.max_advance_days)).isoformat()
    first_bad = (start + timedelta(days=RULES.max_advance_days + 1)).isoformat()
    assert by[last_ok]["closed"] is None and by[last_ok]["count"] > 0
    assert by[first_bad]["closed"] == "out_of_range" and by[first_bad]["count"] == 0
    assert by[start.isoformat()]["closed"] is None


def sid(dsn, name):
    with psycopg.connect(dsn) as c:
        return str(c.execute("select id from service where name=%s", (name,)).fetchone()[0])


def test_days_endpoint_returns_a_month_and_validates_range(client, migrated):
    svc = sid(migrated, "Hair Spa")
    r = client.get("/public/glow-studio/days", params={"service_id": svc, "days": 35}).json()["days"]
    assert len(r) == 35 and r[0]["date"] == datetime.now(IST).date().isoformat()
    assert all(set(d) == {"date", "count", "full", "closed"} for d in r)
    assert r[-1]["closed"] == "out_of_range"  # day 35 is beyond the 30-day booking window
    assert len(client.get("/public/glow-studio/days", params={"service_id": svc}).json()["days"]) == 14  # default unchanged
    assert client.get("/public/glow-studio/days", params={"service_id": svc, "days": 0}).status_code == 422
    assert client.get("/public/glow-studio/days", params={"service_id": svc, "days": 61}).status_code == 422


def test_days_endpoint_marks_a_business_holiday_as_closed(client, migrated, owner):
    svc = sid(migrated, "Hair Spa")
    d = (date.today() + timedelta(days=5)).isoformat()
    h = client.post(f"{M}/holidays", headers=owner, json={"date": d, "reason": "test holiday"}).json()["id"]
    try:
        days = client.get("/public/glow-studio/days", params={"service_id": svc, "days": 14}).json()["days"]
        day = next(x for x in days if x["date"] == d)
        assert day["closed"] == "holiday" and day["count"] == 0
    finally:
        client.delete(f"{M}/holidays/{h}", headers=owner)

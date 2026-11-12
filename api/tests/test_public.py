from datetime import date, datetime, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.tz import zone


@pytest.fixture()
def client(migrated, seeded, monkeypatch):
    from app import config

    monkeypatch.setenv("DATABASE_URL", migrated)
    config.get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c
    config.get_settings.cache_clear()


def sid(dsn, name):
    with psycopg.connect(dsn) as c:
        return c.execute("select id from service where name=%s", (name,)).fetchone()[0]


def test_days_14_entries(client, migrated):
    r = client.get("/public/glow-studio/days", params={"service_id": str(sid(migrated, "Hair Spa"))})
    assert r.status_code == 200
    days = r.json()["days"]
    assert len(days) == 14
    assert any(d["count"] > 0 for d in days)


def test_saturday_script_slot_open_for_neha(client, migrated, seeded):
    sat = seeded["script_saturday"]
    with psycopg.connect(migrated) as c:
        neha = str(c.execute("select id from staff where name='Neha'").fetchone()[0])
    r = client.get("/public/glow-studio/slots", params={
        "service_id": str(sid(migrated, "Hair Spa")), "staff_id": neha, "date": sat})
    assert r.status_code == 200
    starts = [s["start"] for g in r.json()["slots"].values() for s in g]
    assert f"{sat}T16:00:00+05:30" in starts
    assert f"{sat}T16:00:00+05:30" in [s["start"] for s in r.json()["slots"]["afternoon"]]
    # neighbouring Neha bookings are in place: 15:00 would collide with the 14:45 booking buffer
    assert f"{sat}T15:00:00+05:30" not in starts


def test_booked_slot_disappears(client, migrated, seeded):
    """A held booking removes the slot; an expired hold frees it."""
    sat = date.fromisoformat(seeded["script_saturday"])
    tz = zone("Asia/Kolkata")
    start = datetime(sat.year, sat.month, sat.day, 16, 0, tzinfo=tz)
    from psycopg.types.range import Range
    with psycopg.connect(migrated) as c:
        row = c.execute("select s.id, s.business_id, (select id from customer limit 1) from staff s where name='Neha'").fetchone()
        svc = sid(migrated, "Hair Spa")
        end = start + timedelta(minutes=60)
        c.execute("""insert into booking (business_id,customer_id,service_id,staff_id,time_range,block_range,status,
                       hold_expires_at,price_paise,public_token) values (%s,%s,%s,%s,%s,%s,'held',now()+interval '10 minutes',1,'m2tok')""",
                  (row[1], row[2], svc, row[0], Range(start, end, "[)"), Range(start, end + timedelta(minutes=10), "[)")))
        c.commit()
        params = {"service_id": str(svc), "staff_id": str(row[0]), "date": sat.isoformat()}
        got = [s["start"] for g in client.get("/public/glow-studio/slots", params=params).json()["slots"].values() for s in g]
        assert f"{sat}T16:00:00+05:30" not in got
        c.execute("update booking set hold_expires_at = now() - interval '1 minute' where public_token='m2tok'")
        c.commit()
        got = [s["start"] for g in client.get("/public/glow-studio/slots", params=params).json()["slots"].values() for s in g]
        assert f"{sat}T16:00:00+05:30" in got
        c.execute("delete from booking where public_token='m2tok'")
        c.commit()


def test_unknowns_404(client, migrated):
    assert client.get("/public/nope/days", params={"service_id": str(sid(migrated, "Hair Spa"))}).status_code == 404

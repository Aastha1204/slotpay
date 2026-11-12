import concurrent.futures as cf
from datetime import datetime, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.tz import zone


def ctx(dsn, seeded):
    with psycopg.connect(dsn) as c:
        svc = str(c.execute("select id from service where name='Hair Spa'").fetchone()[0])
        neha = str(c.execute("select id from staff where name='Neha'").fetchone()[0])
    sat = seeded["script_saturday"]
    return svc, neha, f"{sat}T16:00:00+05:30"


def body(svc, start, staff=None, phone="9876543210", **kw):
    b = {"service_id": svc, "start": start, "name": "Test User", "phone": phone, "whatsapp_opt_in": True,
         "policy_accepted": True}
    if staff:
        b["staff_id"] = staff
    return {**b, **kw}


def reset(dsn):
    with psycopg.connect(dsn) as c:
        c.execute("update booking set status='cancelled' where status in ('held','confirmed') and customer_id in "
                  "(select id from customer where consent_source='online_booking')")
        c.commit()


def test_hold_then_slot_gone_then_release(client, migrated, seeded):
    reset(migrated)
    svc, neha, start = ctx(migrated, seeded)
    r = client.post("/public/glow-studio/holds", json=body(svc, start, neha))
    assert r.status_code == 201, r.text
    h = r.json()
    r2 = client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9876543211"))
    assert r2.status_code == 409 and r2.json()["error"] == "SLOT_TAKEN"
    assert client.post(f"/public/holds/{h['booking_id']}/release", json={"public_token": "wrong"}).json() == {"released": False}
    assert client.post(f"/public/holds/{h['booking_id']}/release", json={"public_token": h["public_token"]}).json() == {"released": True}
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9876543211")).status_code == 201
    reset(migrated)


def test_validation(client, migrated, seeded):
    svc, neha, start = ctx(migrated, seeded)
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha, policy_accepted=False)).status_code == 422
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="12345")).status_code == 422
    assert client.post("/public/glow-studio/holds", json=body(svc, "2026-11-14T16:00:00", neha)).status_code == 422
    assert client.post("/public/glow-studio/holds", json=body(svc, "2026-11-14T03:00:00+05:30", neha)).status_code == 409


def test_any_available_assigns_a_qualified_stylist(client, migrated, seeded):
    reset(migrated)
    svc, neha, start = ctx(migrated, seeded)
    r = client.post("/public/glow-studio/holds", json=body(svc, start))
    assert r.status_code == 201 and r.json()["staff_id"] == neha  # only Neha does Hair Spa
    reset(migrated)


def test_expired_hold_frees_slot(client, migrated, seeded):
    reset(migrated)
    svc, neha, start = ctx(migrated, seeded)
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha)).status_code == 201
    with psycopg.connect(migrated) as c:
        c.execute("update booking set hold_expires_at = now() - interval '1 minute' where status='held'")
        c.commit()
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9876543299")).status_code == 201
    reset(migrated)


def test_business_and_stylists(client, migrated, seeded):
    b = client.get("/public/glow-studio").json()
    assert b["name"].startswith("Glow Studio") and len(b["services"]) == 18
    svc, *_ = ctx(migrated, seeded)
    s = client.get("/public/glow-studio/stylists", params={"service_id": svc}).json()["stylists"]
    assert [x["name"] for x in s] == ["Neha"] and s[0]["next_free"]


def test_20_concurrent_holds_one_wins(client, migrated, seeded):
    reset(migrated)
    svc, neha, start = ctx(migrated, seeded)

    def go(i):
        return client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone=f"98000000{i:02d}")).status_code

    with cf.ThreadPoolExecutor(20) as ex:
        codes = list(ex.map(go, range(20)))
    assert codes.count(201) == 1 and codes.count(409) == 19, codes
    reset(migrated)

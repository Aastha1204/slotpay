import csv
import io
from datetime import date, timedelta

import psycopg
import pytest
from test_admin import free_slots, ids, tok, walkin  # noqa: F401
from test_holds import reset

M = "/admin/manage"
TODAY = date.today()


@pytest.fixture()
def owner(migrated):
    return tok(migrated, "owner")


@pytest.fixture()
def front(migrated):
    return tok(migrated, "front_desk")


@pytest.fixture(autouse=True)
def cleanup(migrated):
    yield
    reset(migrated)
    with psycopg.connect(migrated) as c:
        c.execute("update booking set status='cancelled' where status in ('held','confirmed') and customer_id in "
                  "(select id from customer where consent_source in ('walk_in','phone'))")
        c.execute("delete from time_block where reason like 'Leave%' or reason like 'test%'")
        c.execute("delete from staff where name like 'Test%'")
        c.execute("delete from service where name like 'Test%'")
        c.execute("delete from business_holiday where reason like 'test%'")
        c.execute("update business set hold_minutes=10, cancellation_cutoff_hours=4, min_lead_min=60, slot_step_min=15, "
                  "advance_applies='always', max_advance_days=30, policy_text='Free cancellation up to 4 hours before your appointment. Later cancellations forfeit the advance.'")
        c.execute("update service set is_active=true")
        c.commit()


def svc_body(**kw):
    return {"category": "hair", "name": "Test Gloss", "duration_min": 30, "price_paise": 90000, "advance_type": "fixed",
            "advance_value": 20000, "buffer_min": 5, **kw}


def public(client):
    return client.get("/public/glow-studio").json()


# ---- permissions --------------------------------------------------------------
@pytest.mark.parametrize("path", [f"{M}/services", f"{M}/staff", f"{M}/settings", f"{M}/leave", "/admin/reports",
                                  "/admin/reports/export?table=summary"])
def test_front_desk_and_anonymous_are_locked_out(client, front, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers=front).status_code == 403


def test_front_desk_cannot_write_services_or_settings(client, front):
    assert client.post(f"{M}/services", headers=front, json=svc_body()).status_code == 403
    assert client.patch(f"{M}/settings", headers=front, json={"hold_minutes": 5}).status_code == 403
    assert client.post(f"{M}/staff", headers=front, json={"name": "Test X"}).status_code == 403


# ---- services -----------------------------------------------------------------
def test_service_crud_and_public_visibility(client, migrated, owner):
    r = client.post(f"{M}/services", headers=owner, json=svc_body())
    assert r.status_code == 201
    sid = r.json()["id"]
    assert client.post(f"{M}/services", headers=owner, json=svc_body()).status_code == 409  # duplicate name
    assert any(s["name"] == "Test Gloss" for s in public(client)["services"])
    assert client.patch(f"{M}/services/{sid}", headers=owner, json={"price_paise": 150000, "advance_type": "percent", "advance_value": 20}).status_code == 200
    s = next(x for x in client.get(f"{M}/services", headers=owner).json()["services"] if x["id"] == sid)
    assert s["price_paise"] == 150000 and s["advance_type"] == "percent" and s["advance_value"] == 20
    assert client.patch(f"{M}/services/{sid}", headers=owner, json={"is_active": False}).status_code == 200
    assert not any(x["name"] == "Test Gloss" for x in public(client)["services"])
    assert client.delete(f"{M}/services/{sid}", headers=owner).json() == {"deleted": True}
    assert client.delete(f"{M}/services/{sid}", headers=owner).status_code == 404


def test_service_validation(client, owner):
    assert client.post(f"{M}/services", headers=owner, json=svc_body(advance_type="percent", advance_value=150)).status_code == 422
    assert client.post(f"{M}/services", headers=owner, json=svc_body(duration_min=0)).status_code == 422
    assert client.post(f"{M}/services", headers=owner, json=svc_body(category="food")).status_code == 422
    assert client.patch(f"{M}/services/00000000-0000-0000-0000-000000000000", headers=owner, json={"name": "x"}).status_code == 404


def test_service_with_bookings_cannot_be_deleted(client, migrated, owner):
    svc, _ = ids(migrated, "Hair Spa", "Neha")
    assert client.delete(f"{M}/services/{svc}", headers=owner).status_code == 409


# ---- staff + shifts -----------------------------------------------------------
def staff_body(svc_ids, **kw):
    t = {d: [] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
    t["wed"] = [{"start": "11:00", "end": "15:00"}]
    t["breaks"] = {"wed": [{"start": "13:00", "end": "13:30"}]}
    return {"name": "Test Stylist", "title": "Guest", "shift_template": t, "service_ids": svc_ids, **kw}


def next_wed(skip=0):
    d = TODAY + timedelta(days=3 + skip)
    while d.weekday() != 2:
        d += timedelta(days=1)
    return d


def test_staff_create_shift_enforced_in_public_availability(client, migrated, owner):
    svc, _ = ids(migrated, "Hair Spa", "Neha")
    r = client.post(f"{M}/staff", headers=owner, json=staff_body([svc]))
    assert r.status_code == 201
    sid = r.json()["id"]
    st = client.get("/public/glow-studio/stylists", params={"service_id": svc}).json()["stylists"]
    assert "Test Stylist" in [x["name"] for x in st]
    wed = client.get("/public/glow-studio/slots", params={"service_id": svc, "staff_id": sid, "date": next_wed().isoformat()}).json()["slots"]
    starts = [s["start"][11:16] for g in wed.values() for s in g]
    assert starts[0] == "11:00" and "13:00" not in starts and "13:15" not in starts and "14:00" not in starts  # break + 70-min span
    thu = client.get("/public/glow-studio/slots", params={"service_id": svc, "staff_id": sid, "date": (next_wed() + timedelta(days=1)).isoformat()}).json()["slots"]
    assert all(not g for g in thu.values())
    # change the shift: Wednesday off, Thursday on
    t = staff_body([svc])["shift_template"]
    t["wed"], t["thu"], t["breaks"] = [], [{"start": "12:00", "end": "16:00"}], {}
    assert client.patch(f"{M}/staff/{sid}", headers=owner, json={"shift_template": t}).status_code == 200
    wed2 = client.get("/public/glow-studio/slots", params={"service_id": svc, "staff_id": sid, "date": next_wed().isoformat()}).json()["slots"]
    assert all(not g for g in wed2.values())


def test_staff_service_assignment_and_inactive_hidden(client, migrated, owner):
    hair_spa, _ = ids(migrated, "Hair Spa", "Neha")
    sana_svc, _ = ids(migrated, "Gel Polish", "Sana")
    sid = client.post(f"{M}/staff", headers=owner, json=staff_body([hair_spa])).json()["id"]
    assert client.patch(f"{M}/staff/{sid}", headers=owner, json={"service_ids": [sana_svc]}).status_code == 200
    names = lambda svc: [x["name"] for x in client.get("/public/glow-studio/stylists", params={"service_id": svc}).json()["stylists"]]  # noqa: E731
    assert "Test Stylist" in names(sana_svc) and "Test Stylist" not in names(hair_spa)
    assert client.patch(f"{M}/staff/{sid}", headers=owner, json={"is_active": False}).status_code == 200
    assert "Test Stylist" not in names(sana_svc)
    assert client.patch(f"{M}/staff/{sid}", headers=owner, json={"service_ids": ["00000000-0000-0000-0000-000000000000"]}).status_code == 422


@pytest.mark.parametrize("bad", [
    {"wed": [{"start": "15:00", "end": "11:00"}]},
    {"wed": [{"start": "10:00", "end": "13:00"}, {"start": "12:00", "end": "14:00"}]},
    {"wed": [{"start": "25:00", "end": "26:00"}]},
    {"funday": []},
    {"breaks": {"wed": [{"start": "13:30", "end": "13:00"}]}},
])
def test_invalid_shift_templates_rejected(client, owner, bad):
    assert client.post(f"{M}/staff", headers=owner, json={"name": "Test Bad", "shift_template": bad}).status_code == 422


def test_staff_with_bookings_cannot_be_deleted_but_unused_can(client, migrated, owner):
    _, neha = ids(migrated, "Hair Spa", "Neha")
    assert client.delete(f"{M}/staff/{neha}", headers=owner).status_code == 409
    sid = client.post(f"{M}/staff", headers=owner, json={"name": "Test Temp"}).json()["id"]
    assert client.delete(f"{M}/staff/{sid}", headers=owner).json() == {"deleted": True}


# ---- leave --------------------------------------------------------------------
def test_leave_blocks_days_and_refuses_over_bookings(client, migrated, owner):
    svc, _ = ids(migrated, "Hair Spa", "Neha")
    sid = client.post(f"{M}/staff", headers=owner, json=staff_body([svc])).json()["id"]
    wed = next_wed()
    r = client.post(f"{M}/leave", headers=owner, json={"staff_id": sid, "from_date": wed.isoformat(), "to_date": wed.isoformat(), "reason": "Wedding"})
    assert r.status_code == 201
    slots = client.get("/public/glow-studio/slots", params={"service_id": svc, "staff_id": sid, "date": wed.isoformat()}).json()["slots"]
    assert all(not g for g in slots.values())
    leave = client.get(f"{M}/leave", headers=owner).json()["leave"]
    mine = [x for x in leave if x["staff"] == "Test Stylist"]
    assert mine and mine[0]["from"] == wed.isoformat() and mine[0]["to"] == wed.isoformat() and mine[0]["reason"].startswith("Leave")
    assert client.post(f"{M}/leave", headers=owner, json={"staff_id": sid, "from_date": wed.isoformat(), "to_date": (wed - timedelta(days=1)).isoformat()}).status_code == 422
    # leave over a stylist who has bookings is refused
    _, neha = ids(migrated, "Hair Spa", "Neha")
    d = TODAY + timedelta(days=3)
    bad = client.post(f"{M}/leave", headers=owner, json={"staff_id": neha, "from_date": d.isoformat(), "to_date": (d + timedelta(days=5)).isoformat()})
    assert bad.status_code == 409


# ---- settings + holidays ------------------------------------------------------
def test_settings_roundtrip_and_public_effect(client, owner):
    r = client.patch(f"{M}/settings", headers=owner, json={"hold_minutes": 7, "cancellation_cutoff_hours": 6,
                                                            "policy_text": "Custom policy.", "name": "Glow Studio Salon & Spa"})
    assert r.status_code == 200
    got = client.get(f"{M}/settings", headers=owner).json()["settings"]
    assert got["hold_minutes"] == 7 and got["cancellation_cutoff_hours"] == 6 and got["policy_text"] == "Custom policy."
    pub = public(client)
    assert pub["hold_minutes"] == 7 and pub["cancellation_cutoff_hours"] == 6 and pub["policy_text"] == "Custom policy."


@pytest.mark.parametrize("bad", [{"slot_step_min": 7}, {"hold_minutes": 0}, {"advance_applies": "sometimes"}, {"cancellation_cutoff_hours": -1}, {}])
def test_settings_validation(client, owner, bad):
    assert client.patch(f"{M}/settings", headers=owner, json=bad).status_code == 422


def test_slot_step_changes_grid(client, migrated, owner):
    svc, neha = ids(migrated, "Blow-dry", "Neha")
    client.patch(f"{M}/settings", headers=owner, json={"slot_step_min": 30})
    d = (TODAY + timedelta(days=3)).isoformat()
    slots = client.get("/public/glow-studio/slots", params={"service_id": svc, "date": d}).json()["slots"]
    assert all(s["start"][14:16] in ("00", "30") for g in slots.values() for s in g)


def test_advance_only_on_weekends_setting_waives_weekday_advance(client, migrated, owner):
    client.patch(f"{M}/settings", headers=owner, json={"advance_applies": "weekends_and_holidays"})
    svc, _ = ids(migrated, "Men's Haircut", "Rohit")
    rohit = ids(migrated, "Men's Haircut", "Rohit")[1]
    slots = []
    for i in range(3, 25):  # first weekday (not Sat/Sun) on which Rohit has room
        day = TODAY + timedelta(days=i)
        if day.weekday() >= 5:
            continue
        slots = client.get("/admin/slots", params={"service_id": svc, "staff_id": rohit, "date": day.isoformat()}, headers=owner).json()["slots"]
        if len(slots) > 3:
            break
    if len(slots) <= 3:
        pytest.skip("Rohit has no free weekday slots in the next few weeks")
    r = client.post("/public/glow-studio/holds", json={"service_id": svc, "start": slots[2], "name": "Weekday Guest", "phone": "9877700001",
                                                       "whatsapp_opt_in": False, "policy_accepted": True})
    assert r.status_code == 201 and r.json()["status"] == "confirmed" and r.json()["order"] is None


def test_holiday_removes_slots_and_can_be_deleted(client, migrated, owner):
    svc, neha = ids(migrated, "Blow-dry", "Neha")
    d = (TODAY + timedelta(days=4)).isoformat()
    before = client.get("/public/glow-studio/slots", params={"service_id": svc, "date": d}).json()["slots"]
    h = client.post(f"{M}/holidays", headers=owner, json={"date": d, "reason": "test holiday"})
    assert h.status_code == 201
    after = client.get("/public/glow-studio/slots", params={"service_id": svc, "date": d}).json()["slots"]
    assert all(not g for g in after.values())
    assert client.delete(f"{M}/holidays/{h.json()['id']}", headers=owner).json() == {"deleted": True}
    again = client.get("/public/glow-studio/slots", params={"service_id": svc, "date": d}).json()["slots"]
    assert (any(before.values())) == (any(again.values()))
    assert client.delete(f"{M}/holidays/{h.json()['id']}", headers=owner).status_code == 404


# ---- reports ------------------------------------------------------------------
def sql(dsn, q, *a):
    with psycopg.connect(dsn) as c:
        return c.execute(q, a).fetchall()


def test_report_kpis_match_the_database(client, migrated, owner):
    r = client.get("/admin/reports", headers=owner).json()
    k = r["kpis"]
    start = (TODAY - timedelta(days=29))
    lo = f"{start} 00:00+05:30"
    hi = f"{TODAY + timedelta(days=1)} 00:00+05:30"
    done, rev = sql(migrated, "select count(*), coalesce(sum(price_paise),0) from booking where status='completed' and lower(time_range)>=%s and lower(time_range)<%s", lo, hi)[0]
    ns = sql(migrated, "select count(*) from booking where status='no_show' and lower(time_range)>=%s and lower(time_range)<%s", lo, hi)[0][0]
    can = sql(migrated, "select count(*) from booking where status='cancelled' and lower(time_range)>=%s and lower(time_range)<%s", lo, hi)[0][0]
    assert k["completed"] == done > 0 and k["revenue_paise"] == int(rev) and k["no_shows"] == ns and k["cancelled"] == can
    assert k["no_show_rate"] == round(100 * ns / (done + ns), 1)
    assert 0 <= k["cancellation_rate"] <= 100 and k["online_advance_collected_paise"] > 0
    assert k["net_advance_paise"] == k["online_advance_collected_paise"] - k["refunded_paise"]
    assert r["from"] == start.isoformat() and r["to"] == TODAY.isoformat()


def test_report_breakdowns(client, owner):
    r = client.get("/admin/reports", headers=owner).json()
    assert sum(s["revenue_paise"] for s in r["services"]) == r["kpis"]["revenue_paise"]
    revs = [s["revenue_paise"] for s in r["services"]]
    assert revs == sorted(revs, reverse=True) and len(r["services"]) > 3
    assert sum(s["revenue_paise"] for s in r["staff"]) == r["kpis"]["revenue_paise"]
    assert {s["name"] for s in r["staff"]} >= {"Neha", "Rohit", "Sana", "Meera"}
    for s in r["staff"]:
        assert s["shift_min"] > 0 and 0 < s["utilisation"] <= 100 and s["booked_min"] > 0
    assert len(r["daily"]) >= 14 and sum(d["bookings"] for d in r["daily"]) == r["kpis"]["bookings"]


def test_report_custom_range_and_limits(client, owner):
    a, b = (TODAY - timedelta(days=13)).isoformat(), (TODAY - timedelta(days=7)).isoformat()
    r = client.get("/admin/reports", params={"from": a, "to": b}, headers=owner).json()
    assert r["from"] == a and r["to"] == b and all(a <= d["date"] <= b for d in r["daily"])
    assert client.get("/admin/reports", params={"from": b, "to": a}, headers=owner).status_code == 422
    assert client.get("/admin/reports", params={"from": "2020-01-01", "to": "2026-01-01"}, headers=owner).status_code == 422


def test_csv_exports(client, owner):
    for table, head in [("services", "service"), ("staff", "stylist"), ("daily", "date"), ("summary", "metric")]:
        r = client.get("/admin/reports/export", params={"table": table}, headers=owner)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"] and table in r.headers["content-disposition"]
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0][0] == head and len(rows) > 1
    assert client.get("/admin/reports/export", params={"table": "nope"}, headers=owner).status_code == 422

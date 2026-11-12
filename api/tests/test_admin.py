import time
from datetime import date, datetime, timedelta

import jwt
import psycopg
import pytest
from conftest import JWT_SECRET
from test_holds import reset
from test_messaging import paid_booking, sched
from test_payments import q

TODAY = date.today()


def tok(dsn, role):
    with psycopg.connect(dsn) as c:
        uid = c.execute("select id from staff_user where role=%s", (role,)).fetchone()[0]
    t = jwt.encode({"sub": str(uid), "aud": "authenticated", "exp": int(time.time()) + 600}, JWT_SECRET, "HS256")
    return {"Authorization": f"Bearer {t}"}


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
        c.execute("delete from time_block where reason like 'test%'")
        c.execute("update business set cancellation_cutoff_hours=4")
        c.commit()


def ids(dsn, service, staff):
    with psycopg.connect(dsn) as c:
        return (str(c.execute("select id from service where name=%s", (service,)).fetchone()[0]),
                str(c.execute("select id from staff where name=%s", (staff,)).fetchone()[0]))


def free_slots(client, hdr, svc, stf, exclude=None, skip=0):
    for i in range(2 + skip, 12):
        d = (TODAY + timedelta(days=i)).isoformat()
        p = {"service_id": svc, "staff_id": stf, "date": d}
        if exclude:
            p["exclude_booking_id"] = exclude
        s = client.get("/admin/slots", params=p, headers=hdr).json()["slots"]
        if len(s) > 10:
            return s
    raise AssertionError("no free slots")


def walkin(client, hdr, svc, stf, start, phone="9822200001", source="walk_in", name="Walk In"):
    return client.post("/admin/bookings", headers=hdr, json={
        "service_id": svc, "staff_id": stf, "start": start, "name": name, "phone": phone, "source": source})


# ---- auth + calendar ----------------------------------------------------------
def test_calendar_requires_staff_token(client, migrated, front):
    assert client.get("/admin/calendar", params={"date": TODAY.isoformat()}).status_code == 401
    assert client.get("/admin/calendar", params={"date": TODAY.isoformat()}, headers=front).status_code == 200


def test_day_calendar_shape_and_cancelled_hidden(client, migrated, owner):
    d = (TODAY + timedelta(days=3)).isoformat()
    r = client.get("/admin/calendar", params={"date": d}, headers=owner).json()
    assert [s["name"] for s in r["staff"]] == ["Meera", "Neha", "Rohit", "Sana"]
    assert r["day_start_min"] == 600 and r["day_end_min"] == 1260 and r["bookings"]
    assert all(b["status"] in ("held", "confirmed", "completed", "no_show") for b in r["bookings"])
    full = client.get("/admin/calendar", params={"date": d, "include_cancelled": "true"}, headers=owner).json()
    assert len(full["bookings"]) >= len(r["bookings"])


def test_week_calendar_starts_monday(client, migrated, owner):
    r = client.get("/admin/calendar", params={"date": (TODAY + timedelta(days=2)).isoformat(), "view": "week"}, headers=owner).json()
    assert date.fromisoformat(r["range_start"]).weekday() == 0
    assert len({b["start"][:10] for b in r["bookings"]}) > 1


# ---- manual booking, blocks, statuses -----------------------------------------
def test_walkin_booking_confirmed_and_conflict(client, migrated, owner, wa):
    svc, stf = ids(migrated, "Men's Haircut", "Rohit")
    start = free_slots(client, owner, svc, stf)[2]
    r = walkin(client, owner, svc, stf, start)
    assert r.status_code == 201, r.text
    d = client.get(f"/admin/bookings/{r.json()['booking_id']}", headers=owner).json()
    assert d["status"] == "confirmed" and d["source"] == "walk_in" and d["payments"] == []
    assert walkin(client, owner, svc, stf, start, phone="9822200002").status_code == 409
    assert walkin(client, owner, svc, stf, start, phone="123").status_code == 422
    assert [m for m in d["messages"] if m["template"]], "confirmation message is logged"
    cal = client.get("/admin/calendar", params={"date": start[:10]}, headers=owner).json()
    assert any(b["id"] == r.json()["booking_id"] and b["source"] == "walk_in" for b in cal["bookings"])


def test_phone_source_and_customer_search(client, migrated, owner):
    svc, stf = ids(migrated, "Men's Haircut", "Rohit")
    start = free_slots(client, owner, svc, stf)[6]
    assert walkin(client, owner, svc, stf, start, phone="9822200003", source="phone", name="Phone Pal").status_code == 201
    hit = client.get("/admin/customers/search", params={"q": "98222000"}, headers=owner).json()["customers"]
    assert any(c["name"] == "Phone Pal" and c["phone"] == "+919822200003" for c in hit)
    by_name = client.get("/admin/customers/search", params={"q": "phone pal"}, headers=owner).json()["customers"]
    assert by_name


def test_block_time_removes_slots_and_conflicts(client, migrated, owner):
    svc, stf = ids(migrated, "Men's Haircut", "Rohit")
    slots = free_slots(client, owner, svc, stf)
    s0 = datetime.fromisoformat(slots[1])
    r = client.post("/admin/time-blocks", headers=owner, json={
        "staff_id": stf, "start": s0.isoformat(), "end": (s0 + timedelta(hours=1)).isoformat(), "reason": "test leave"})
    assert r.status_code == 201
    again = client.get("/admin/slots", params={"service_id": svc, "staff_id": stf, "date": slots[1][:10]}, headers=owner).json()["slots"]
    assert slots[1] not in again and slots[1 + 1] not in again
    cal = client.get("/admin/calendar", params={"date": slots[1][:10]}, headers=owner).json()
    assert any(t["reason"] == "test leave" for t in cal["time_blocks"])
    assert walkin(client, owner, svc, stf, slots[1]).status_code == 409
    assert client.delete(f"/admin/time-blocks/{r.json()['id']}", headers=owner).json() == {"deleted": True}
    assert client.delete(f"/admin/time-blocks/{r.json()['id']}", headers=owner).status_code == 404
    # blocking over an existing booking is refused
    b = walkin(client, owner, svc, stf, slots[1])
    assert b.status_code == 201
    clash = client.post("/admin/time-blocks", headers=owner, json={
        "staff_id": stf, "start": s0.isoformat(), "end": (s0 + timedelta(hours=1)).isoformat(), "reason": "test clash"})
    assert clash.status_code == 409


def test_status_transitions(client, migrated, owner):
    svc, stf = ids(migrated, "Men's Haircut", "Rohit")
    bid = walkin(client, owner, svc, stf, free_slots(client, owner, svc, stf)[3]).json()["booking_id"]
    assert client.post(f"/admin/bookings/{bid}/status", headers=owner, json={"status": "no_show"}).status_code == 200
    assert client.post(f"/admin/bookings/{bid}/status", headers=owner, json={"status": "completed"}).status_code == 409
    assert client.post(f"/admin/bookings/{bid}/status", headers=owner, json={"status": "cancelled"}).status_code == 422
    cal = client.get("/admin/calendar", params={"date": (TODAY + timedelta(days=2)).isoformat()}, headers=owner)
    assert cal.status_code == 200


# ---- reschedule ---------------------------------------------------------------
def test_reschedule_moves_booking_frees_old_slot_and_notifies(client, migrated, owner, wa):
    svc, stf = ids(migrated, "Men's Haircut", "Rohit")
    slots = free_slots(client, owner, svc, stf)
    bid = walkin(client, owner, svc, stf, slots[0]).json()["booking_id"]
    new_slots = free_slots(client, owner, svc, stf, exclude=bid)
    target = new_slots[-1]
    n = len(wa.sent)
    r = client.post(f"/admin/bookings/{bid}/reschedule", headers=owner, json={"start": target})
    assert r.status_code == 200, r.text
    d = client.get(f"/admin/bookings/{bid}", headers=owner).json()
    assert datetime.fromisoformat(d["start"]) == datetime.fromisoformat(target)
    freed = client.get("/admin/slots", params={"service_id": svc, "staff_id": stf, "date": slots[0][:10]}, headers=owner).json()["slots"]
    assert slots[0] in freed  # the old time is bookable again
    assert sched(migrated, bid)["confirmation"] == "sent"
    assert len(wa.sent) == n  # walk-ins aren't opted in for live WhatsApp; the simulator gets the notice
    sim = q(migrated, "select count(*) from message_log where booking_id=%s and channel='simulator' and template is not null", bid)
    assert sim[0][0] == 2  # original confirmation + reschedule notice


def test_reschedule_onto_taken_slot_is_409(client, migrated, owner):
    svc, stf = ids(migrated, "Men's Haircut", "Rohit")
    slots = free_slots(client, owner, svc, stf)
    a = walkin(client, owner, svc, stf, slots[0], phone="9822200010").json()["booking_id"]
    walkin(client, owner, svc, stf, slots[8], phone="9822200011")
    r = client.post(f"/admin/bookings/{a}/reschedule", headers=owner, json={"start": slots[8]})
    assert r.status_code == 409 and r.json()["error"] == "SLOT_TAKEN"
    d = client.get(f"/admin/bookings/{a}", headers=owner).json()
    assert datetime.fromisoformat(d["start"]) == datetime.fromisoformat(slots[0])


def test_reschedule_into_own_slot_overlap_allowed(client, migrated, owner):
    svc, stf = ids(migrated, "Men's Haircut", "Rohit")
    slots = free_slots(client, owner, svc, stf)
    a = walkin(client, owner, svc, stf, slots[0], phone="9822200012").json()["booking_id"]
    r = client.post(f"/admin/bookings/{a}/reschedule", headers=owner, json={"start": slots[1]})  # overlaps its own old range
    assert r.status_code == 200


# ---- cancel + refund ----------------------------------------------------------
def test_cancel_two_step_refund_flow(client, migrated, owner, rzp):
    h, pid, _ = paid_booking(client, migrated, seeded_info(migrated), rzp)
    prev = client.get(f"/admin/bookings/{h['booking_id']}/cancel-preview", headers=owner).json()
    assert prev["refund_eligible"] and prev["text"].startswith("More than 4 h before: full ₹200 refund") and prev["can_override"]
    r = client.post(f"/admin/bookings/{h['booking_id']}/cancel", headers=owner, json={})
    assert r.status_code == 200 and r.json()["refunded_paise"] == 20000
    d = client.get(f"/admin/bookings/{h['booking_id']}", headers=owner).json()
    assert d["status"] == "cancelled" and d["refunds"][0]["amount_paise"] == 20000 and d["payments"][0]["status"] == "refunded"
    assert client.post(f"/admin/bookings/{h['booking_id']}/cancel", headers=owner, json={}).status_code == 409


def test_cancel_in_window_forfeits_front_desk_cannot_override_owner_can(client, migrated, owner, front, rzp):
    h, pid, _ = paid_booking(client, migrated, seeded_info(migrated), rzp)
    with psycopg.connect(migrated) as c:
        c.execute("update business set cancellation_cutoff_hours=1000")
        c.commit()
    prev = client.get(f"/admin/bookings/{h['booking_id']}/cancel-preview", headers=front).json()
    assert not prev["refund_eligible"] and prev["text"].startswith("Within 1000 h") and not prev["can_override"]
    assert client.post(f"/admin/bookings/{h['booking_id']}/cancel", headers=front, json={"refund_override": True}).status_code == 403
    r = client.post(f"/admin/bookings/{h['booking_id']}/cancel", headers=owner, json={"refund_override": True})
    assert r.status_code == 200 and r.json()["refunded_paise"] == 20000 and len(rzp.refunds) == 1


def test_cancel_in_window_without_override_keeps_advance(client, migrated, front, rzp):
    h, pid, _ = paid_booking(client, migrated, seeded_info(migrated), rzp)
    with psycopg.connect(migrated) as c:
        c.execute("update business set cancellation_cutoff_hours=1000")
        c.commit()
    r = client.post(f"/admin/bookings/{h['booking_id']}/cancel", headers=front, json={})
    assert r.status_code == 200 and r.json()["refunded_paise"] == 0 and rzp.refunds == []
    d = client.get(f"/admin/bookings/{h['booking_id']}", headers=front).json()
    assert d["payments"][0]["status"] == "captured" and d["status"] == "cancelled"


def test_detail_includes_payment_and_message_history(client, migrated, owner, rzp):
    h, pid, _ = paid_booking(client, migrated, seeded_info(migrated), rzp)
    d = client.get(f"/admin/bookings/{h['booking_id']}", headers=owner).json()
    p = d["payments"][0]
    assert p["order_id"] == h["order"]["order_id"] and p["payment_id"] == pid and p["method"] == "upi" and p["amount_paise"] == 20000
    assert any("confirmed" in m["body"] for m in d["messages"])
    assert len([m for m in d["messages"] if m["direction"] == "out"]) == 1  # live+simulator mirror shown once


def seeded_info(dsn):
    d = date.today()
    return {"script_saturday": (d + timedelta(days=(5 - d.weekday()) % 7 or 7)).isoformat()}

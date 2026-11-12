import psycopg
from test_holds import body, ctx, reset
from test_messaging import paid_booking
from test_payments import make_hold, q, verify

K = {"key": "demo-key"}


def test_demo_requires_key(client):
    assert client.get("/demo/state").status_code == 403
    assert client.get("/demo/state", params={"key": "nope"}).status_code == 403
    assert client.get("/demo/state", headers={"x-demo-key": "demo-key"}).status_code == 200
    assert client.post("/demo/actions/double-booking-test").status_code == 403
    assert client.post("/demo/actions/reset").status_code == 403


def test_timeline_tells_the_payment_story_in_order(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    assert client.post(f"/public/holds/{h['booking_id']}/checkout-opened", json={"public_token": h["public_token"]}).json() == {"ok": True}
    assert verify(client, h, rzp.pay(h["order"]["order_id"], 20000)).json()["status"] == "confirmed"
    ev = client.get("/demo/timeline", params=K).json()["events"]
    mine = [e for e in ev if e["booking_id"] == h["booking_id"]][::-1]  # oldest first
    texts = [e["text"] for e in mine]
    order = ["Slot held", "Razorpay order created", "signature verified", "Booking confirmed", "WhatsApp confirmation sent", "Reminders scheduled for"]
    idx = [next(i for i, t in enumerate(texts) if o in t) for o in order]
    assert idx == sorted(idx), texts
    assert any("Checkout opened" in t for t in texts)
    assert any("₹200" in t for t in texts)
    st = client.get("/demo/state", params=K).json()
    assert st["slug"] == "glow-studio" and st["latest"]["booking_id"] == h["booking_id"] and st["latest"]["phone"] == "9876543210"
    reset(migrated)


def test_send_reminder_now(client, migrated, seeded, rzp, wa):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    wa.sent.clear()
    r = client.post("/demo/actions/send-reminder", params=K, json={"kind": "remind_24h"})
    assert r.status_code == 200 and r.json()["booking_id"] == h["booking_id"]
    assert [m["params"][3] for m in wa.sent if m["name"] == "slotpay_appointment_reminder"] == ["tomorrow"]
    client.post("/demo/actions/send-reminder", params=K, json={"kind": "remind_2h"})
    assert any(m["params"][3] == "in 2 hours" for m in wa.sent)
    assert client.post("/demo/actions/send-reminder", params=K, json={"kind": "bogus"}).status_code == 422
    reset(migrated)


def test_expire_all_holds(client, migrated, seeded, rzp):
    reset(migrated)
    svc, neha, start = ctx(migrated, seeded)
    hold = client.post("/public/glow-studio/holds", json=body(svc, start, neha)).json()
    assert client.post("/demo/actions/expire-holds", params=K).json()["expired"] >= 1
    assert client.get(f"/public/bookings/{hold['public_token']}").json()["status"] == "expired"
    assert client.post("/demo/actions/expire-holds", params=K).json()["expired"] == 0


def test_double_booking_test_one_wins_nineteen_rejected(client, migrated, seeded):
    reset(migrated)
    for _ in range(2):  # repeatable, leaves no rows behind
        r = client.post("/demo/actions/double-booking-test", params=K).json()
        assert r["booked"] == 1 and r["rejected"] == 19 and r["attempts"] == 20
        assert r["summary"] == "1 booked · 19 rejected by the database" and "Neha" in r["slot"]
        assert q(migrated, "select count(*) from booking where public_token like 'dbtest-%%'") == [(0,)]
    ev = client.get("/demo/timeline", params=K).json()["events"]
    assert any("Double-booking test · 1 booked · 19 rejected" in e["text"] for e in ev)


def test_owner_reset_restores_busy_calendar_in_under_10_seconds(client, migrated, seeded, rzp):
    from test_admin import tok
    front = tok(migrated, "front_desk")
    assert client.post("/admin/demo/reset", headers=front).status_code == 403
    h, _, (svc, neha, start) = paid_booking(client, migrated, seeded, rzp)
    r = client.post("/admin/demo/reset", headers=tok(migrated, "owner"))
    assert r.status_code == 200 and r.json()["seconds"] < 10 and r.json()["bookings"] > 300
    assert q(migrated, "select count(*) from business where slug='glow-studio'") == [(1,)]
    assert q(migrated, "select count(*) from booking where public_token=%s", h["public_token"]) == [(0,)]
    # the demo-script slot is free again
    svc2, neha2, start2 = ctx(migrated, seeded)
    assert client.post("/public/glow-studio/holds", json=body(svc2, start2, neha2, phone="9811100077")).status_code == 201
    reset(migrated)

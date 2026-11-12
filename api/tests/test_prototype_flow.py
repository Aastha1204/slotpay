import time

import pytest
from test_holds import body, ctx, reset
from test_payments import q, status

TICK = {"x-jobs-secret": "jobs-secret"}


@pytest.fixture()
def proto(client, monkeypatch):
    """Prototype mode with NO Razorpay keys (so the built-in mock is used) and reminders at demo speed (1 s / 2 s)."""
    from app import config
    from app.main import app
    from app.razorpay_client import get_rzp

    monkeypatch.setenv("PROTOTYPE_MODE", "true")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "")
    monkeypatch.setenv("REMINDER_DEMO_DELAY_SEC", "1")
    config.get_settings.cache_clear()
    app.dependency_overrides.pop(get_rzp, None)  # use the real dependency -> MockRazorpay
    return client


def hold(proto, migrated, seeded, phone="9876543210"):
    reset(migrated)
    svc, neha, start = ctx(migrated, seeded)
    r = proto.post("/public/glow-studio/holds", json=body(svc, start, neha, phone=phone))
    assert r.status_code == 201, r.text
    return r.json()


def test_status_reports_simulated_payments_and_whatsapp_mode(proto):
    s = proto.get("/prototype/status").json()
    assert s["enabled"] and s["payments"] == "simulated" and s["whatsapp"] == "both" and s["reminder_demo_delay_sec"] == 1


def test_whole_journey_book_pay_whatsapp_reminders_cancel(proto, migrated, seeded, wa):
    h = hold(proto, migrated, seeded)
    assert h["order"]["key_id"] == "rzp_mock" and h["order"]["order_id"].startswith("order_mock_")
    assert h["status"] == "held"

    paid = proto.post("/prototype/pay", json={"order_id": h["order"]["order_id"]})
    assert paid.status_code == 200 and paid.json()["status"] == "confirmed"
    again = proto.post("/prototype/pay", json={"order_id": h["order"]["order_id"]})  # idempotent
    assert again.status_code == 200 and again.json()["status"] == "confirmed"
    v = status(proto, h["public_token"])
    assert v["advance_paid_paise"] == 20000 and v["payment_status"] == "captured" and v["whatsapp_sent"] is True

    # 1) the booking confirmation reaches WhatsApp immediately
    assert [m["name"] for m in wa.sent] == ["slotpay_booking_confirmed"] and wa.sent[0]["to"] == "+919876543210"
    box = proto.get(f"/prototype/inbox/{h['public_token']}").json()
    assert [m["direction"] for m in box["messages"]] == ["out"] and "confirmed" in box["messages"][0]["body"]
    assert {r["kind"] for r in box["reminders"]} == {"remind_24h", "remind_2h"} and all(r["status"] == "pending" for r in box["reminders"])
    assert box["phone"] == "+91 9876543210" and box["customer"] == "Test"

    # 2) reminders arrive on their own (API tick), in order, with working buttons
    time.sleep(2.4)
    assert proto.post("/internal/jobs/tick", headers=TICK).json()["messages_sent"] == 2
    box = proto.get(f"/prototype/inbox/{h['public_token']}").json()
    bodies = [m["body"] for m in box["messages"]]
    assert len(bodies) == 3 and "tomorrow" in bodies[1] and "in 2 hours" in bodies[2]
    assert [b["text"] for b in box["messages"][1]["buttons"]] == ["Reschedule", "Cancel"]
    assert [m["name"] for m in wa.sent].count("slotpay_appointment_reminder") == 2
    assert all(r["status"] == "sent" for r in box["reminders"])
    assert proto.post("/internal/jobs/tick", headers=TICK).json()["messages_sent"] == 0  # not sent twice

    # 3) tapping Cancel on WhatsApp cancels, refunds (mock Razorpay) and replies
    cancel_btn = box["messages"][1]["buttons"][1]
    r = proto.post(f"/prototype/inbox/{h['public_token']}/button", json=cancel_btn)
    assert r.status_code == 200 and "refund" in r.json()["reply"] and "₹200" in r.json()["reply"]
    v = status(proto, h["public_token"])
    assert v["status"] == "cancelled" and v["refunded_paise"] == 20000 and v["payment_status"] == "refunded"
    assert q(migrated, "select status from refund where payment_id=(select id from payment where booking_id=%s)", h["booking_id"]) == [("processed",)]
    box = proto.get(f"/prototype/inbox/{h['public_token']}").json()
    assert box["booking_status"] == "cancelled" and box["messages"][-1]["direction"] == "out" and "cancelled" in box["messages"][-1]["body"]
    reset(migrated)


def test_reschedule_button_replies_with_link(proto, migrated, seeded):
    h = hold(proto, migrated, seeded)
    proto.post("/prototype/pay", json={"order_id": h["order"]["order_id"]})
    resched = {"payload": f"reschedule:{h['booking_id']}", "text": "Reschedule"}
    r = proto.post(f"/prototype/inbox/{h['public_token']}/button", json=resched)
    assert f"/b/glow-studio/reschedule/{h['public_token']}" in r.json()["reply"]
    reset(migrated)


def test_failed_test_upi_keeps_the_hold_then_success_confirms(proto, migrated, seeded):
    h = hold(proto, migrated, seeded)
    f = proto.post("/prototype/pay", json={"order_id": h["order"]["order_id"], "upi": "failure@razorpay"})
    assert f.status_code == 402 and "still held" in f.json()["detail"]
    assert status(proto, h["public_token"])["status"] == "held"
    assert proto.post("/prototype/pay", json={"order_id": h["order"]["order_id"], "upi": "success@razorpay"}).json()["status"] == "confirmed"
    reset(migrated)


def test_pay_only_accepts_mock_orders_and_prototype_mode(proto, migrated, seeded, monkeypatch):
    assert proto.post("/prototype/pay", json={"order_id": "order_RealOne123456"}).status_code == 422  # real orders can't be faked
    assert proto.post("/prototype/pay", json={"order_id": "order_mock_" + "0" * 14}).status_code == 404
    assert proto.get("/prototype/inbox/not-a-token").status_code == 404
    from app import config
    monkeypatch.setenv("PROTOTYPE_MODE", "false")
    config.get_settings.cache_clear()
    h_order = "order_mock_" + "a" * 14
    assert proto.post("/prototype/pay", json={"order_id": h_order}).status_code == 404
    assert proto.get("/prototype/inbox/whatever").status_code == 404


def test_without_demo_delay_reminders_follow_the_appointment(proto, migrated, seeded, monkeypatch):
    from app import config
    monkeypatch.setenv("REMINDER_DEMO_DELAY_SEC", "0")
    config.get_settings.cache_clear()
    h = hold(proto, migrated, seeded)
    proto.post("/prototype/pay", json={"order_id": h["order"]["order_id"]})
    box = proto.get(f"/prototype/inbox/{h['public_token']}").json()
    mins = {r["kind"]: r["in_sec"] for r in box["reminders"] if r["status"] == "pending"}
    assert all(s > 3600 for s in mins.values()), mins  # hours away (real schedule), not seconds
    reset(migrated)

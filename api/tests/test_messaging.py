import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from conftest import sign_payment
from test_holds import body, ctx, reset
from test_payments import expire_now, make_hold, q, status, verify

from app import messaging
from app.cancellation import cancel_booking, refund_eligible

PHONE = "9876543210"
KEY = {"key": "demo-key"}


def paid_booking(client, migrated, seeded, rzp, phone=PHONE):
    h, c = make_hold(client, migrated, seeded, phone=phone)
    pid = rzp.pay(h["order"]["order_id"], 20000)
    assert verify(client, h, pid).json()["status"] == "confirmed"
    return h, pid, c


def press(client, h, action, phone=PHONE, key=KEY):
    return client.post("/demo/whatsapp/button", params=key, json={
        "phone": phone, "payload": f"{action}:{h['booking_id']}", "text": action.title()})


def sched(dsn, bid):
    return dict(q(dsn, "select kind, status from scheduled_message where booking_id=%s", bid))


# ---- confirmation + scheduling ------------------------------------------------
def test_confirmation_sent_live_and_mirrored_and_reminders_queued(client, migrated, seeded, rzp, wa):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    assert len(wa.sent) == 1
    m = wa.sent[0]
    assert m["name"] == "slotpay_booking_confirmed" and m["to"] == "+91" + PHONE
    assert m["params"][0] == "Test" and m["params"][1] == "Hair Spa" and m["params"][5] == "200"
    assert m["suffix"].endswith(h["public_token"])
    chans = q(migrated, "select channel from message_log where booking_id=%s and direction='out' order by channel", h["booking_id"])
    assert chans == [("simulator",), ("whatsapp",)]
    s = sched(migrated, h["booking_id"])
    assert s["confirmation"] == "sent" and s["remind_24h"] == "pending" and s["remind_2h"] == "pending"
    st = status(client, h["public_token"])
    assert st["whatsapp_sent"] is True
    reset(migrated)


def test_past_reminders_are_skipped(client, migrated, seeded, rzp):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    async def go(now):
        async with await psycopg.AsyncConnection.connect(migrated) as c:
            await c.execute("delete from scheduled_message where booking_id=%s", (h["booking_id"],))
            await messaging.queue_confirmation_messages(c, h["booking_id"], start, now)
            await c.commit()
    start = q(migrated, "select lower(time_range) from booking where id=%s", h["booking_id"])[0][0]
    asyncio.run(go(start - timedelta(hours=1)))
    assert sched(migrated, h["booking_id"]) == {"confirmation": "pending", "remind_24h": "skipped", "remind_2h": "skipped"}
    asyncio.run(go(start - timedelta(hours=10)))
    assert sched(migrated, h["booking_id"])["remind_24h"] == "skipped" and sched(migrated, h["booking_id"])["remind_2h"] == "pending"
    reset(migrated)


def due(dsn, bid, kind):
    with psycopg.connect(dsn) as c:
        c.execute("update scheduled_message set send_at = now() - interval '1 minute', status='pending' "
                  "where booking_id=%s and kind=%s", (bid, kind))
        c.commit()


def tick(client):
    return client.post("/internal/jobs/tick", headers={"x-jobs-secret": "jobs-secret"}).json()


def test_tick_sends_due_reminder_with_buttons_once(client, migrated, seeded, rzp, wa):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    wa.sent.clear()
    due(migrated, h["booking_id"], "remind_24h")
    assert tick(client)["messages_sent"] >= 1
    r = [m for m in wa.sent if m["name"] == "slotpay_appointment_reminder"]
    assert len(r) == 1 and r[0]["params"][3] == "tomorrow"
    assert [b["text"] for b in r[0]["buttons"]] == ["Reschedule", "Cancel"]
    assert r[0]["buttons"][1]["payload"] == f"cancel:{h['booking_id']}"
    assert tick(client)["messages_sent"] == 0  # idempotent
    assert sched(migrated, h["booking_id"])["remind_24h"] == "sent"
    reset(migrated)


def test_retries_up_to_three_then_fails(client, migrated, seeded, rzp, wa, monkeypatch):
    from app import config
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    monkeypatch.setenv("WHATSAPP_MODE", "live")
    config.get_settings.cache_clear()
    wa.fail = 99
    for i in range(3):
        due(migrated, h["booking_id"], "remind_2h")
        tick(client)
    row = q(migrated, "select status, attempts, last_error from scheduled_message where booking_id=%s and kind='remind_2h'", h["booking_id"])[0]
    assert row[0] == "failed" and row[1] == 3 and "down" in row[2]
    reset(migrated)


def test_failed_attempt_retries_then_succeeds(client, migrated, seeded, rzp, wa, monkeypatch):
    from app import config
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    monkeypatch.setenv("WHATSAPP_MODE", "live")
    config.get_settings.cache_clear()
    wa.fail = 1
    due(migrated, h["booking_id"], "remind_2h")
    tick(client)
    assert sched(migrated, h["booking_id"])["remind_2h"] == "pending"
    due(migrated, h["booking_id"], "remind_2h")
    tick(client)
    assert sched(migrated, h["booking_id"])["remind_2h"] == "sent"
    reset(migrated)


def test_reminder_not_sent_for_cancelled_booking(client, migrated, seeded, rzp, wa):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    press(client, h, "cancel")
    wa.sent.clear()
    due(migrated, h["booking_id"], "remind_24h")
    tick(client)
    assert not any(m["name"] == "slotpay_appointment_reminder" for m in wa.sent)
    assert sched(migrated, h["booking_id"])["remind_24h"] == "skipped"
    reset(migrated)


# ---- buttons ------------------------------------------------------------------
def test_cancel_button_refunds_and_replies_and_frees_slot(client, migrated, seeded, rzp, wa):
    h, pid, (svc, neha, start) = paid_booking(client, migrated, seeded, rzp)
    r = press(client, h, "cancel")
    assert r.status_code == 200 and "refund" in r.json()["reply"] and "₹200" in r.json()["reply"]
    assert status(client, h["public_token"])["status"] == "cancelled"
    assert len(rzp.refunds) == 1 and rzp.refunds[0]["amount"] == 20000
    assert status(client, h["public_token"])["refunded_paise"] == 20000
    assert any(t["to"] == "+91" + PHONE and "cancelled" in t["text"] for t in wa.texts)
    assert any(m["name"] == "slotpay_booking_cancelled" for m in wa.sent)
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9876500010")).status_code == 201
    log = q(migrated, "select direction, body from message_log where booking_id=%s and (direction='in' or channel='simulator') order by created_at", h["booking_id"])
    assert ("in", "Cancel") in log
    assert press(client, h, "cancel").json()["reply"].endswith("already cancelled or completed.")  # idempotent
    assert len(rzp.refunds) == 1
    reset(migrated)


def test_cancel_inside_window_forfeits_advance(client, migrated, seeded, rzp, wa):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    start = q(migrated, "select lower(time_range) from booking where id=%s", h["booking_id"])[0][0]

    async def go():
        async with await psycopg.AsyncConnection.connect(migrated, row_factory=psycopg.rows.dict_row) as c:
            return await cancel_booking(c, rzp, uuid.UUID(h["booking_id"]), reason="t", actor="customer",
                                        now=start - timedelta(hours=2), provider=wa)
    res = asyncio.run(go())
    assert res["ok"] and not res["refund_eligible"] and res["refunded_paise"] == 0 and rzp.refunds == []
    line = q(migrated, "select body from message_log where booking_id=%s and channel='simulator' and template is not null order by created_at desc limit 1", h["booking_id"])
    assert "non-refundable" in line[0][0]
    reset(migrated)


def test_refund_eligibility_boundary():
    s = datetime(2026, 11, 14, 10, 30, tzinfo=timezone.utc)
    assert refund_eligible(s, s - timedelta(hours=4), 4)
    assert not refund_eligible(s, s - timedelta(hours=3, minutes=59), 4)


def test_reschedule_button_replies_with_link(client, migrated, seeded, rzp):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    reply = press(client, h, "reschedule").json()["reply"]
    assert f"/b/glow-studio/reschedule/{h['public_token']}" in reply
    assert status(client, h["public_token"])["status"] == "confirmed"
    reset(migrated)


def test_button_from_another_phone_is_ignored(client, migrated, seeded, rzp):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    assert press(client, h, "cancel", phone="9000000000").json()["reply"] == ""
    assert status(client, h["public_token"])["status"] == "confirmed"
    reset(migrated)


def test_simulator_endpoints_need_demo_key(client, migrated, seeded, rzp):
    assert client.get("/demo/whatsapp/messages", params={"phone": PHONE}).status_code == 403
    assert client.get("/demo/whatsapp/messages", params={"phone": PHONE, "key": "nope"}).status_code == 403
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    m = client.get("/demo/whatsapp/messages", params={"phone": PHONE, **KEY}).json()
    assert m["business"].startswith("Glow Studio") and any("confirmed" in x["body"] for x in m["messages"])
    reset(migrated)


# ---- inbound webhook ----------------------------------------------------------
def wa_post(client, payload, sig_ok=True):
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"wa-app-secret", raw, hashlib.sha256).hexdigest() if sig_ok else "sha256=bad"
    return client.post("/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": sig, "content-type": "application/json"})


def inbound(wamid, frm, payload, text="Cancel"):
    return {"entry": [{"changes": [{"value": {"messages": [{"from": frm, "id": wamid, "type": "button",
                                                            "button": {"payload": payload, "text": text}}]}}]}]}


def test_whatsapp_verify_handshake(client):
    ok = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wa-verify", "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    assert client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "1"}).status_code == 403


def test_inbound_requires_valid_signature(client, migrated, seeded, rzp):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    p = inbound("wamid.A1", "91" + PHONE, f"cancel:{h['booking_id']}")
    assert wa_post(client, p, sig_ok=False).status_code == 403
    assert status(client, h["public_token"])["status"] == "confirmed"
    reset(migrated)


def test_inbound_cancel_button_and_replay_dedupe(client, migrated, seeded, rzp, wa):
    h, _, _ = paid_booking(client, migrated, seeded, rzp)
    wid = f"wamid.{uuid.uuid4().hex[:8]}"
    p = inbound(wid, "91" + PHONE, f"cancel:{h['booking_id']}")
    assert wa_post(client, p).status_code == 200
    assert status(client, h["public_token"])["status"] == "cancelled"
    n_texts, n_ref = len(wa.texts), len(rzp.refunds)
    assert wa_post(client, p).status_code == 200  # Meta redelivery
    assert len(wa.texts) == n_texts and len(rzp.refunds) == n_ref == 1
    reset(migrated)


# ---- ics ----------------------------------------------------------------------
def test_ics(client, migrated, seeded, rzp):
    h, _, (svc, neha, start) = paid_booking(client, migrated, seeded, rzp)
    r = client.get(f"/public/bookings/{h['public_token']}/ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    day = seeded["script_saturday"].replace("-", "")
    assert f"DTSTART;TZID=Asia/Kolkata:{day}T160000" in r.text and "TZID:Asia/Kolkata" in r.text
    assert "LOCATION:Glow Studio Salon & Spa\\, Shop 4" in r.text and "\r\n" in r.text
    assert client.get("/public/bookings/nope/ics").status_code == 404
    reset(migrated)


# ---- late capture messaging ---------------------------------------------------
def test_slot_lost_sends_refund_message(client, migrated, seeded, rzp, wa):
    h, (svc, neha, start) = make_hold(client, migrated, seeded)
    expire_now(migrated, h["booking_id"])
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9876500020")).status_code == 201
    pid = rzp.pay(h["order"]["order_id"], 20000)
    verify(client, h, pid)
    msgs = q(migrated, "select body from message_log where booking_id=%s and channel='simulator'", h["booking_id"])
    assert any("refund of ₹200 has been initiated" in m[0] for m in msgs)
    assert not any(m["name"] == "slotpay_booking_confirmed" and m["to"] == "+91" + PHONE for m in wa.sent)
    reset(migrated)

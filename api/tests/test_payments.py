import hashlib
import hmac
import json
import uuid
from datetime import date

import psycopg
from conftest import sign_body, sign_payment
from test_holds import body, ctx, reset

from app.payments import compute_advance
from app.razorpay_client import verify_payment_signature, verify_webhook_signature


def q(dsn, sql, *a):
    with psycopg.connect(dsn) as c:
        return c.execute(sql, a).fetchall()


def make_hold(client, migrated, seeded, phone="9876543210"):
    reset(migrated)
    svc, neha, start = ctx(migrated, seeded)
    r = client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone=phone))
    assert r.status_code == 201, r.text
    return r.json(), (svc, neha, start)


def webhook(client, event, entity_key, entity, event_id=None, secret_ok=True):
    raw = json.dumps({"event": event, "payload": {entity_key: {"entity": entity}}}).encode()
    sig = sign_body(raw) if secret_ok else "bad"
    return client.post("/webhooks/razorpay", content=raw, headers={
        "x-razorpay-signature": sig, "x-razorpay-event-id": event_id or uuid.uuid4().hex,
        "content-type": "application/json"})


def status(client, token):
    return client.get(f"/public/bookings/{token}").json()


def verify(client, h, pid, sig=None):
    oid = h["order"]["order_id"]
    return client.post("/public/payments/verify", json={
        "razorpay_order_id": oid, "razorpay_payment_id": pid, "razorpay_signature": sig or sign_payment(oid, pid)})


def confirmed_count(dsn, booking_id):
    return q(dsn, "select count(*) from audit_event where booking_id=%s and type='booking_confirmed'", booking_id)


# ---- pure rules / signatures -------------------------------------------------
def test_signature_known_vector():
    exp = hmac.new(b"secret", b"order_ABC|pay_XYZ", hashlib.sha256).hexdigest()
    assert verify_payment_signature("order_ABC", "pay_XYZ", exp, "secret")
    assert not verify_payment_signature("order_ABC", "pay_XYZ", exp[:-1] + "0", "secret")
    assert not verify_payment_signature("order_ABC", "pay_OTHER", exp, "secret")
    assert not verify_payment_signature("order_ABC", "pay_XYZ", "", "secret")
    assert verify_webhook_signature(b"{}", hmac.new(b"s", b"{}", hashlib.sha256).hexdigest(), "s")
    assert not verify_webhook_signature(b"{}", "nope", "s")


def test_compute_advance_rules():
    base = dict(price_paise=120000, advance_type="fixed", advance_value=20000, skip_advance=False,
                advance_applies="always", day=date(2026, 11, 11), is_holiday=False)
    assert compute_advance(**base) == 20000
    assert compute_advance(**{**base, "skip_advance": True}) == 0
    assert compute_advance(**{**base, "advance_type": "none"}) == 0
    assert compute_advance(**{**base, "advance_type": "percent", "advance_value": 20, "price_paise": 280000}) == 56000
    wk = {**base, "advance_applies": "weekends_and_holidays"}
    assert compute_advance(**wk) == 0
    assert compute_advance(**{**wk, "day": date(2026, 11, 14)}) == 20000
    assert compute_advance(**{**wk, "is_holiday": True}) == 20000
    assert compute_advance(**{**base, "advance_value": 999999}) == 120000


# ---- hold -> order -----------------------------------------------------------
def test_hold_creates_order_and_payment_row(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    assert h["status"] == "held" and h["advance_paise"] == 20000
    assert h["order"]["amount_paise"] == 20000 and h["order"]["key_id"] == "rzp_test_key"
    assert q(migrated, "select status, amount_paise from payment where razorpay_order_id=%s",
             h["order"]["order_id"]) == [("created", 20000)]
    assert rzp.orders[0]["receipt"] == h["booking_id"]
    reset(migrated)


def test_order_failure_expires_hold_and_502(client, migrated, seeded, rzp):
    reset(migrated)
    rzp.fail_orders = True
    svc, neha, start = ctx(migrated, seeded)
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha)).status_code == 502
    rzp.fail_orders = False
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9876500001")).status_code == 201
    reset(migrated)


def test_zero_advance_confirms_immediately(client, migrated, seeded):
    reset(migrated)
    with psycopg.connect(migrated) as c:
        c.execute("insert into customer (business_id,name,phone_e164,consent_source,skip_advance) "
                  "select id,'Regular','+919811100001','online_booking',true from business where slug='glow-studio' "
                  "on conflict (business_id,phone_e164) do update set skip_advance=true")
        c.commit()
    svc, neha, start = ctx(migrated, seeded)
    r = client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9811100001")).json()
    assert r["status"] == "confirmed" and r["order"] is None
    assert status(client, r["public_token"])["status"] == "confirmed"
    reset(migrated)


# ---- verify ------------------------------------------------------------------
def test_verify_confirms_booking(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    pid = rzp.pay(h["order"]["order_id"], 20000)
    r = verify(client, h, pid)
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    s = status(client, h["public_token"])
    assert s["advance_paid_paise"] == 20000 and s["balance_paise"] == 100000 and s["payment_status"] == "captured"
    assert s["masked_phone"] == "+91 98xxxxx210"
    assert verify(client, h, pid).status_code == 200  # idempotent
    assert confirmed_count(migrated, h["booking_id"]) == [(1,)]
    reset(migrated)


def test_verify_rejects_bad_signature_and_does_not_confirm(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    pid = rzp.pay(h["order"]["order_id"], 20000)
    assert verify(client, h, pid, sig="deadbeef").status_code == 400
    assert status(client, h["public_token"])["status"] == "held"
    reset(migrated)


def test_verify_does_not_confirm_when_not_captured(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    pid = rzp.pay(h["order"]["order_id"], 20000, status="failed")
    assert verify(client, h, pid).json()["status"] == "held"
    reset(migrated)


def test_verify_captures_authorized_payment(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    pid = rzp.pay(h["order"]["order_id"], 20000, status="authorized")
    assert verify(client, h, pid).json()["status"] == "confirmed" and rzp.captured == [pid]
    reset(migrated)


def test_verify_rejects_amount_mismatch(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    pid = rzp.pay(h["order"]["order_id"], 100)
    assert verify(client, h, pid).status_code == 400
    assert status(client, h["public_token"])["status"] == "held"
    reset(migrated)


# ---- webhook -----------------------------------------------------------------
def test_webhook_bad_signature_rejected(client):
    r = webhook(client, "payment.captured", "payment", {"id": "x", "order_id": "y", "amount": 1}, secret_ok=False)
    assert r.status_code == 400


def test_webhook_confirms_and_replay_is_idempotent(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    ent = {"id": "pay_wh1", "order_id": h["order"]["order_id"], "amount": 20000, "method": "upi"}
    eid = uuid.uuid4().hex
    assert webhook(client, "payment.captured", "payment", ent, eid).json() == {"ok": True}
    assert status(client, h["public_token"])["status"] == "confirmed"
    assert webhook(client, "payment.captured", "payment", ent, eid).json() == {"ok": True, "duplicate": True}
    webhook(client, "payment.captured", "payment", ent)  # same capture, new event id: still harmless
    assert confirmed_count(migrated, h["booking_id"]) == [(1,)]
    reset(migrated)


def test_webhook_then_verify_race_confirms_once(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    pid = rzp.pay(h["order"]["order_id"], 20000)
    webhook(client, "payment.captured", "payment", {"id": pid, "order_id": h["order"]["order_id"], "amount": 20000})
    assert verify(client, h, pid).json()["status"] == "confirmed"
    assert confirmed_count(migrated, h["booking_id"]) == [(1,)]
    reset(migrated)


def test_failed_payment_keeps_hold_and_allows_retry(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    oid = h["order"]["order_id"]
    webhook(client, "payment.failed", "payment", {"id": "pay_f1", "order_id": oid, "amount": 20000, "method": "upi"})
    assert status(client, h["public_token"])["status"] == "held"
    assert q(migrated, "select status from payment where razorpay_order_id=%s", oid) == [("failed",)]
    pid = rzp.pay(oid, 20000)  # customer retries in Checkout and succeeds
    assert verify(client, h, pid).json()["status"] == "confirmed"
    reset(migrated)


def test_release_frees_slot_for_someone_else(client, migrated, seeded, rzp):
    h, (svc, neha, start) = make_hold(client, migrated, seeded)
    r = client.post(f"/public/holds/{h['booking_id']}/release", json={"public_token": h["public_token"]})
    assert r.json()["released"]
    assert client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9876500002")).status_code == 201
    reset(migrated)


# ---- late capture ------------------------------------------------------------
def expire_now(dsn, booking_id):
    with psycopg.connect(dsn) as c:
        c.execute("update booking set status='expired', hold_expires_at = now() - interval '1 minute' where id=%s",
                  (booking_id,))
        c.commit()


def test_late_capture_reconfirms_when_slot_still_free(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    expire_now(migrated, h["booking_id"])
    pid = rzp.pay(h["order"]["order_id"], 20000)
    assert verify(client, h, pid).json()["status"] == "confirmed"
    assert rzp.refunds == []
    reset(migrated)


def test_late_capture_refunded_when_slot_taken(client, migrated, seeded, rzp):
    h, (svc, neha, start) = make_hold(client, migrated, seeded)
    expire_now(migrated, h["booking_id"])
    other = client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9876500003"))
    assert other.status_code == 201  # someone else grabbed the slot
    pid = rzp.pay(h["order"]["order_id"], 20000)
    assert verify(client, h, pid).json()["status"] == "expired"
    assert len(rzp.refunds) == 1 and rzp.refunds[0]["amount"] == 20000 and rzp.refunds[0]["payment_id"] == pid
    s = status(client, h["public_token"])
    assert s["payment_status"] == "refunded" and s["refunded_paise"] == 20000
    reset(migrated)


def test_refund_processed_updates_refund_row(client, migrated, seeded, rzp):
    h, (svc, neha, start) = make_hold(client, migrated, seeded)
    expire_now(migrated, h["booking_id"])
    client.post("/public/glow-studio/holds", json=body(svc, start, neha, phone="9876500004"))
    pid = rzp.pay(h["order"]["order_id"], 20000)
    verify(client, h, pid)
    rid = rzp.refunds[0]["id"]
    with psycopg.connect(migrated) as c:
        c.execute("update refund set status='initiated' where razorpay_refund_id=%s", (rid,))
        c.commit()
    webhook(client, "refund.processed", "refund", {"id": rid, "payment_id": pid, "amount": 20000, "status": "processed"})
    assert q(migrated, "select status from refund where razorpay_refund_id=%s", rid) == [("processed",)]
    reset(migrated)


# ---- hold expiry job ---------------------------------------------------------
def test_tick_expires_stale_holds_and_requires_secret(client, migrated, seeded, rzp):
    h, _ = make_hold(client, migrated, seeded)
    assert client.post("/internal/jobs/tick").status_code == 401
    with psycopg.connect(migrated) as c:
        c.execute("update booking set hold_expires_at = now() - interval '1 minute' where id=%s", (h["booking_id"],))
        c.commit()
    hdr = {"x-jobs-secret": "jobs-secret"}
    assert client.post("/internal/jobs/tick", headers=hdr).json()["expired_holds"] >= 1
    assert status(client, h["public_token"])["status"] == "expired"
    assert client.post("/internal/jobs/tick", headers=hdr).json()["expired_holds"] == 0
    reset(migrated)

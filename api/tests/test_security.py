import hashlib
import hmac
import json

from conftest import sign_body

from app.razorpay_client import verify_payment_signature, verify_webhook_signature


def test_empty_secret_never_validates():
    forged = hmac.new(b"", b"order_1|pay_1", hashlib.sha256).hexdigest()
    assert not verify_payment_signature("order_1", "pay_1", forged, "")
    assert not verify_webhook_signature(b"{}", hmac.new(b"", b"{}", hashlib.sha256).hexdigest(), "")
    assert not verify_webhook_signature(b"{}", "", "secret")


def test_unconfigured_webhook_secret_rejects_forged_capture(client, monkeypatch):
    from app import config
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "")
    config.get_settings.cache_clear()
    raw = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "p", "order_id": "o", "amount": 1}}}}).encode()
    forged = hmac.new(b"", raw, hashlib.sha256).hexdigest()
    r = client.post("/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": forged, "x-razorpay-event-id": "e1"})
    assert r.status_code == 400


def test_jobs_secret_required_and_checked(client):
    assert client.post("/internal/jobs/tick").status_code == 401
    assert client.post("/internal/jobs/tick", headers={"x-jobs-secret": "wrong"}).status_code == 401
    assert client.post("/internal/jobs/tick", headers={"x-jobs-secret": "jobs-secret"}).status_code == 200


def test_rate_limit_uses_forwarded_client_ip(client, monkeypatch):
    from app import booking, config
    booking._hits.clear()
    body = {"service_id": "00000000-0000-0000-0000-000000000000", "start": "2026-01-01T10:00:00+05:30", "name": "x", "phone": "9876543210",
            "policy_accepted": True}
    # 20 calls from customer A use up A's budget only; customer B (different X-Forwarded-For) is unaffected
    for _ in range(20):
        client.post("/public/glow-studio/holds", json=body, headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1"})
    a = client.post("/public/glow-studio/holds", json=body, headers={"x-forwarded-for": "203.0.113.7"})
    b = client.post("/public/glow-studio/holds", json=body, headers={"x-forwarded-for": "198.51.100.9"})
    assert a.status_code == 429 and b.status_code != 429
    monkeypatch.setenv("TRUST_PROXY", "false")
    config.get_settings.cache_clear()
    booking._hits.clear()
    for _ in range(20):
        client.post("/public/glow-studio/holds", json=body, headers={"x-forwarded-for": "1.1.1.1"})
    assert client.post("/public/glow-studio/holds", json=body, headers={"x-forwarded-for": "2.2.2.2"}).status_code == 429  # header ignored


def test_reset_refused_unless_demo_mode(client, monkeypatch, migrated):
    from app import config
    from test_admin import tok
    monkeypatch.setenv("DEMO_MODE", "false")
    config.get_settings.cache_clear()
    assert client.post("/demo/actions/reset", params={"key": "demo-key"}).status_code == 403
    assert client.post("/admin/demo/reset", headers=tok(migrated, "owner")).status_code == 403

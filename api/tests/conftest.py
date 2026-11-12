import hashlib
import hmac
import itertools
import os
import pathlib
import sys
import uuid

import psycopg
import psycopg.conninfo
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "supabase" / "seed"))
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import migrate as migrate_mod  # noqa: E402
import seed as seed_mod  # noqa: E402
from app.razorpay_client import RazorpayError  # noqa: E402

JWT_SECRET = "test-secret-test-secret-test-secret-123"
KEY_SECRET = "rzp_test_secret_key_123"
WEBHOOK_SECRET = "whsec_test_123"


@pytest.fixture(scope="session")
def dsn():
    """Real Postgres: TEST_DATABASE_URL if set, else the local Docker container (port 54322)."""
    base = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute("drop database if exists slotpay_test with (force)")
        admin.execute("create database slotpay_test")
    yield psycopg.conninfo.make_conninfo(base, dbname="slotpay_test")
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute("drop database if exists slotpay_test with (force)")


@pytest.fixture(scope="session")
def migrated(dsn):
    with psycopg.connect(dsn) as c:
        migrate_mod.migrate(c)
    return dsn


@pytest.fixture()
def conn(migrated):
    with psycopg.connect(migrated) as c:
        yield c


@pytest.fixture(scope="session")
def seeded(migrated):
    with psycopg.connect(migrated) as c:
        info = seed_mod.seed(c)
    return info


class FakeRzp:
    """In-memory stand-in for RazorpayClient (same async interface)."""

    def __init__(self):
        self.payments: dict[str, dict] = {}
        self.orders: list[dict] = []
        self.refunds: list[dict] = []
        self.captured: list[str] = []
        self.fail_orders = False

    async def create_order(self, amount_paise, receipt, notes):
        if self.fail_orders:
            raise RazorpayError("boom")
        o = {"id": f"order_{uuid.uuid4().hex[:12]}", "amount": amount_paise, "receipt": receipt}
        self.orders.append(o)
        return o

    def pay(self, order_id, amount, status="captured", method="upi"):
        pid = f"pay_{uuid.uuid4().hex[:12]}"
        self.payments[pid] = {"id": pid, "order_id": order_id, "amount": amount, "status": status, "method": method}
        return pid

    async def fetch_payment(self, pid):
        return dict(self.payments[pid])

    async def capture(self, pid, amount):
        self.payments[pid]["status"] = "captured"
        self.captured.append(pid)
        return dict(self.payments[pid])

    async def refund(self, pid, amount, notes=None):
        r = {"id": f"rfnd_{uuid.uuid4().hex[:10]}", "payment_id": pid, "amount": amount, "status": "processed"}
        self.refunds.append(r)
        return r


class FakeWA:
    """Stand-in for the live WhatsApp provider."""

    def __init__(self):
        self.sent: list[dict] = []
        self.texts: list[dict] = []
        self.fail = 0  # number of upcoming sends that should raise

    async def send_template(self, to_e164, name, params, buttons, url_suffix):
        if self.fail > 0:
            self.fail -= 1
            raise RuntimeError("whatsapp down")
        self.sent.append({"to": to_e164, "name": name, "params": params, "buttons": buttons, "suffix": url_suffix})
        return f"wamid.{uuid.uuid4().hex[:10]}"

    async def send_text(self, to_e164, text):
        self.texts.append({"to": to_e164, "text": text})
        return f"wamid.{uuid.uuid4().hex[:10]}"


def sign_payment(order_id, payment_id):
    return hmac.new(KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def sign_body(raw: bytes):
    return hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


@pytest.fixture()
def rzp():
    return FakeRzp()


@pytest.fixture()
def wa():
    return FakeWA()


@pytest.fixture()
def client(migrated, seeded, monkeypatch, rzp, wa):
    from fastapi.testclient import TestClient

    from app import booking, config
    from app.messaging import get_provider
    from app.razorpay_client import get_rzp

    monkeypatch.setenv("DATABASE_URL", migrated)
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("JOBS_SECRET", "jobs-secret")
    monkeypatch.setenv("DEMO_KEY", "demo-key")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("WHATSAPP_MODE", "both")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "wa-app-secret")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "wa-verify")
    config.get_settings.cache_clear()
    booking._hits.clear()
    from app.main import app

    app.dependency_overrides[get_rzp] = lambda: rzp
    app.dependency_overrides[get_provider] = lambda: wa
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    config.get_settings.cache_clear()

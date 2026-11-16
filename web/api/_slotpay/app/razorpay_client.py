"""Thin Razorpay client (httpx) + signature helpers. Tests inject a fake with the same interface."""
import hashlib
import hmac

import httpx

from .config import get_settings

BASE = "https://api.razorpay.com/v1"


class RazorpayError(Exception):
    pass


def verify_payment_signature(order_id: str, payment_id: str, signature: str, secret: str) -> bool:
    """HMAC-SHA256 of 'order_id|payment_id' with the key secret, constant-time compare.
    An unset secret must never validate (an HMAC with an empty key is trivially forgeable)."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


class RazorpayClient:
    def __init__(self, key_id: str, key_secret: str):
        self.key_id, self.key_secret = key_id, key_secret

    async def _call(self, method: str, path: str, json: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15, auth=(self.key_id, self.key_secret)) as c:
                r = await c.request(method, f"{BASE}{path}", json=json)
        except httpx.HTTPError as e:
            raise RazorpayError(str(e)) from e
        if r.status_code >= 400:
            raise RazorpayError(f"{r.status_code}: {r.text[:200]}")
        return r.json()

    async def create_order(self, amount_paise: int, receipt: str, notes: dict) -> dict:
        return await self._call("POST", "/orders", {"amount": amount_paise, "currency": "INR", "receipt": receipt,
                                                    "notes": notes})

    async def fetch_payment(self, payment_id: str) -> dict:
        return await self._call("GET", f"/payments/{payment_id}")

    async def capture(self, payment_id: str, amount_paise: int) -> dict:
        return await self._call("POST", f"/payments/{payment_id}/capture", {"amount": amount_paise, "currency": "INR"})

    async def refund(self, payment_id: str, amount_paise: int, notes: dict | None = None) -> dict:
        return await self._call("POST", f"/payments/{payment_id}/refund", {"amount": amount_paise, "notes": notes or {}})


class MockRazorpay:
    """Prototype-only stand-in used when PROTOTYPE_MODE is on and no Razorpay keys are configured.

    Orders are fake (`order_mock_*`) and are paid through POST /prototype/pay, which runs the same
    confirm_booking() path as a real payment. Refunds succeed immediately. Never used when keys exist.
    """

    mock_key_id = "rzp_mock"

    async def create_order(self, amount_paise: int, receipt: str, notes: dict) -> dict:
        import uuid
        return {"id": f"order_mock_{uuid.uuid4().hex[:14]}", "amount": amount_paise, "receipt": receipt}

    async def fetch_payment(self, payment_id: str) -> dict:
        raise RazorpayError("mock payments are confirmed through /prototype/pay")

    async def capture(self, payment_id: str, amount_paise: int) -> dict:
        raise RazorpayError("mock payments are confirmed through /prototype/pay")

    async def refund(self, payment_id: str, amount_paise: int, notes: dict | None = None) -> dict:
        import uuid
        return {"id": f"rfnd_mock_{uuid.uuid4().hex[:12]}", "payment_id": payment_id, "amount": amount_paise, "status": "processed"}


def get_rzp() -> "RazorpayClient | MockRazorpay":
    s = get_settings()
    if s.prototype_mode and not s.razorpay_key_id:
        return MockRazorpay()
    return RazorpayClient(s.razorpay_key_id, s.razorpay_key_secret)

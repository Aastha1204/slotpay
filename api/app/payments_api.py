"""Verify endpoint, Razorpay webhook, public booking status."""
from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from . import db
from .config import get_settings
from . import messaging
from .payments import after_confirm_broadcast, audit, confirm_booking, issue_refund
from .razorpay_client import RazorpayError, get_rzp, verify_payment_signature, verify_webhook_signature
from .tz import zone

log = logging.getLogger("slotpay.payments")
router = APIRouter()


async def booking_view(conn, token: str) -> dict | None:
    r = await (await conn.execute(
        """select b.id, b.status, b.time_range, b.price_paise, b.advance_due_paise, b.advance_paid_paise,
                  b.hold_expires_at, b.public_token, s.name service_name, st.name staff_name,
                  bz.name business_name, bz.address, bz.maps_url, bz.slug, bz.timezone, bz.cancellation_cutoff_hours,
                  c.name customer_name, c.phone_e164
           from booking b join service s on s.id=b.service_id join staff st on st.id=b.staff_id
           join business bz on bz.id=b.business_id join customer c on c.id=b.customer_id
           where b.public_token=%s""", (token,))).fetchone()
    if not r:
        return None
    p = await (await conn.execute(
        "select status, refunded_paise from payment where booking_id=%s order by created_at desc limit 1", (r["id"],))).fetchone()
    tz = zone(r["timezone"])
    ph = r["phone_e164"]
    sent = await (await conn.execute(
        "select 1 from message_log where booking_id=%s and direction='out' and template is not null limit 1", (r["id"],))).fetchone()
    return {
        "booking_id": str(r["id"]), "status": r["status"], "service": r["service_name"], "stylist": r["staff_name"],
        "start": r["time_range"].lower.astimezone(tz).isoformat(), "end": r["time_range"].upper.astimezone(tz).isoformat(),
        "price_paise": r["price_paise"], "advance_paid_paise": r["advance_paid_paise"],
        "balance_paise": r["price_paise"] - r["advance_paid_paise"],
        "payment_status": p["status"] if p else None, "refunded_paise": p["refunded_paise"] if p else 0,
        "hold_expires_at": r["hold_expires_at"].isoformat() if r["hold_expires_at"] else None,
        "business": {"name": r["business_name"], "address": r["address"], "maps_url": r["maps_url"], "slug": r["slug"]},
        "customer_first_name": r["customer_name"].split()[0],
        "masked_phone": f"+91 {ph[3:5]}xxxxx{ph[-3:]}", "whatsapp_sent": bool(sent),
        "cancellation_cutoff_hours": r["cancellation_cutoff_hours"],
    }


@router.get("/public/bookings/{token}")
async def booking_status(token: str, conn=Depends(db.get_conn)):
    v = await booking_view(conn, token)
    if not v:
        raise HTTPException(404, "Booking not found")
    return v


class VerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


async def _finish(conn, rzp, provider, result: dict) -> None:
    await conn.commit()
    if result["outcome"] == "slot_lost":
        try:
            await issue_refund(conn, rzp, payment_row_id=result["payment_row_id"], amount_paise=result["amount_paise"],
                               reason="slot_no_longer_available")
            await messaging.queue_message(conn, result["booking_id"], "refund")
            await conn.commit()
        except Exception:  # surfaced in audit/logs; ops can refund from admin
            log.exception("auto refund failed")
    await after_confirm_broadcast(conn, result)
    try:  # message delivery must never break the payment response
        await messaging.send_due(conn, provider, booking_id=result["booking_id"])
    except Exception:  # noqa: BLE001
        log.exception("immediate send failed; the job tick will retry")


@router.post("/public/payments/verify")
async def verify_payment(body: VerifyIn, conn=Depends(db.get_conn), rzp=Depends(get_rzp),
                         provider=Depends(messaging.get_provider)):
    s = get_settings()
    if not verify_payment_signature(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature,
                                    s.razorpay_key_secret):
        raise HTTPException(400, "Payment signature could not be verified")
    pay = await (await conn.execute("select p.*, b.business_id, b.public_token from payment p join booking b on b.id=p.booking_id "
                                    "where razorpay_order_id=%s", (body.razorpay_order_id,))).fetchone()
    if not pay:
        raise HTTPException(404, "Unknown order")
    await audit(conn, pay["business_id"], pay["booking_id"], "signature_verified", {"payment_id": body.razorpay_payment_id})
    try:
        rp = await rzp.fetch_payment(body.razorpay_payment_id)
        if rp.get("order_id") != body.razorpay_order_id or rp.get("amount") != pay["amount_paise"]:
            raise HTTPException(400, "Payment does not match order")
        if rp.get("status") == "authorized":
            rp = await rzp.capture(body.razorpay_payment_id, pay["amount_paise"])
    except RazorpayError as e:
        log.warning("razorpay fetch failed: %s", e)
        await conn.commit()
        raise HTTPException(502, "We couldn't confirm your payment yet. Please wait a moment and check again.")
    if rp.get("status") == "captured":
        res = await confirm_booking(conn, order_id=body.razorpay_order_id, payment_id=body.razorpay_payment_id,
                                    method=rp.get("method"), amount_paise=pay["amount_paise"], raw=rp)
        await _finish(conn, rzp, provider, res)
    else:
        await conn.commit()
    view = await booking_view(conn, pay["public_token"])
    return {"status": view["status"], "payment_status": view["payment_status"], "public_token": pay["public_token"]}


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, conn=Depends(db.get_conn), rzp=Depends(get_rzp),
                           provider=Depends(messaging.get_provider)):
    raw = await request.body()
    if not verify_webhook_signature(raw, request.headers.get("x-razorpay-signature", ""),
                                    get_settings().razorpay_webhook_secret):
        raise HTTPException(400, "Bad signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Bad payload")
    event_id = request.headers.get("x-razorpay-event-id") or f"noid:{hashlib.sha256(raw).hexdigest()}"
    event = payload.get("event", "")
    ins = await (await conn.execute(
        """insert into webhook_event (id,source,event,payload) values (%s,'razorpay',%s,%s)
           on conflict (id) do nothing returning id""", (event_id, event, psycopg_json(payload)))).fetchone()
    if not ins:
        await conn.commit()
        return {"ok": True, "duplicate": True}

    ent = payload.get("payload", {})
    result = None
    if event == "payment.captured":
        p = ent["payment"]["entity"]
        result = await confirm_booking(conn, order_id=p["order_id"], payment_id=p["id"], method=p.get("method"),
                                       amount_paise=p["amount"], raw=p)
        if result["outcome"] != "unknown_order":
            await audit(conn, result["business_id"], result["booking_id"], "webhook_payment_captured", {"event_id": event_id})
    elif event == "payment.failed":
        p = ent["payment"]["entity"]
        # a failed attempt does NOT release the hold: Checkout lets the customer retry
        row = await (await conn.execute(
            """update payment set status='failed', razorpay_payment_id=coalesce(razorpay_payment_id,%s), method=%s
               where razorpay_order_id=%s and status in ('created','authorized','failed') returning booking_id""",
            (p["id"], p.get("method"), p["order_id"]))).fetchone()
        if row:
            b = await (await conn.execute("select business_id from booking where id=%s", (row["booking_id"],))).fetchone()
            await audit(conn, b["business_id"], row["booking_id"], "payment_failed",
                        {"reason": p.get("error_description", "")})
    elif event in ("refund.processed", "refund.failed"):
        r = ent["refund"]["entity"]
        await conn.execute("update refund set status=%s where razorpay_refund_id=%s",
                           ("processed" if event == "refund.processed" else "failed", r["id"]))
        row = await (await conn.execute(
            "select p.booking_id, b.business_id from refund rf join payment p on p.id=rf.payment_id "
            "join booking b on b.id=p.booking_id where rf.razorpay_refund_id=%s", (r["id"],))).fetchone()
        if row:
            await audit(conn, row["business_id"], row["booking_id"], event.replace(".", "_"), {"refund_id": r["id"]})
    await conn.execute("update webhook_event set processed_at=now() where id=%s", (event_id,))
    if result:
        await _finish(conn, rzp, provider, result)
    else:
        await conn.commit()
    return {"ok": True}


def psycopg_json(v):
    from psycopg.types.json import Jsonb
    return Jsonb(v)

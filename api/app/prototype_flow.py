"""Prototype-only flow endpoints (PROTOTYPE_MODE): simulated card/UPI payment and a live WhatsApp inbox.

These make the whole journey work without any external accounts:
  book -> (simulated) pay -> confirmation on WhatsApp -> reminders -> Cancel/Reschedule buttons.
The payment still goes through confirm_booking(), so DB state, audit trail, messages and the calendar behave exactly
as they do with real Razorpay. Orders that were created by the real Razorpay client are rejected here.
"""
from __future__ import annotations

import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, messaging
from .config import get_settings
from .payments import confirm_booking
from .payments_api import _finish, booking_view
from .razorpay_client import get_rzp
from .tz import zone
from .whatsapp_api import handle_button

router = APIRouter(prefix="/prototype")


def _enabled() -> None:
    if not get_settings().prototype_mode:
        raise HTTPException(404, "Prototype mode is off")


class PayIn(BaseModel):
    order_id: str = Field(pattern=r"^order_mock_[0-9a-f]{14}$")
    upi: str = "success@razorpay"


@router.post("/pay", dependencies=[Depends(_enabled)])
async def pay(body: PayIn, conn=Depends(db.get_conn), rzp=Depends(get_rzp), provider=Depends(messaging.get_provider)):
    """Pay a simulated order. `failure@razorpay` mimics Razorpay's failed-payment test UPI id."""
    pay_row = await (await conn.execute(
        "select p.id, p.amount_paise, p.status, b.public_token, b.business_id from payment p join booking b on b.id=p.booking_id "
        "where p.razorpay_order_id=%s", (body.order_id,))).fetchone()
    if not pay_row:
        raise HTTPException(404, "Unknown order")
    if body.upi.strip().lower().startswith("failure@"):
        await conn.execute("update payment set status='failed', method='upi' where id=%s and status='created'", (pay_row["id"],))
        await conn.commit()
        raise HTTPException(402, "Payment failed (test UPI id). Your slot is still held, try success@razorpay.")
    res = await confirm_booking(conn, order_id=body.order_id, payment_id=f"pay_mock_{uuid.uuid4().hex[:14]}", method="upi",
                                amount_paise=pay_row["amount_paise"], raw={"mock": True, "upi": body.upi})
    await _finish(conn, rzp, provider, res)
    view = await booking_view(conn, pay_row["public_token"])
    return {"status": view["status"], "public_token": pay_row["public_token"]}


async def _booking_by_token(conn, token: str) -> dict:
    b = await messaging.booking_ctx_by_token(conn, token)
    if not b:
        raise HTTPException(404, "Booking not found")
    return b


@router.get("/inbox/{token}", dependencies=[Depends(_enabled)])
async def inbox(token: str, conn=Depends(db.get_conn)):
    """The customer's WhatsApp conversation about this booking, plus the countdown to the next reminder."""
    b = await _booking_by_token(conn, token)
    tz = zone(b["timezone"])
    rows = await (await conn.execute(
        """select id, direction, body, buttons, created_at from message_log
           where booking_id=%s and (direction='in' or channel='simulator') order by created_at, id""", (b["id"],))).fetchall()
    sched = await (await conn.execute(
        "select kind, status, send_at from scheduled_message where booking_id=%s and kind in ('confirmation','remind_24h','remind_2h') "
        "order by send_at", (b["id"],))).fetchall()
    from datetime import datetime
    now = datetime.now(timezone.utc)
    return {
        "business": b["salon"], "customer": b["cname"].split()[0], "phone": "+91 " + b["phone_e164"][-10:],
        "demo_delay_sec": get_settings().reminder_demo_delay_sec, "booking_status": b["status"],
        "messages": [{"id": str(r["id"]), "direction": r["direction"], "body": r["body"], "buttons": r["buttons"],
                      "at": r["created_at"].astimezone(tz).isoformat()} for r in rows],
        "reminders": [{"kind": s["kind"], "status": s["status"], "in_sec": max(0, int((s["send_at"] - now).total_seconds()))} for s in sched if s["kind"] != "confirmation"],
    }


class ButtonIn(BaseModel):
    payload: str
    text: str = ""


@router.post("/inbox/{token}/button", dependencies=[Depends(_enabled)])
async def inbox_button(token: str, body: ButtonIn, conn=Depends(db.get_conn), rzp=Depends(get_rzp),
                       provider=Depends(messaging.get_provider)):
    """Tap a WhatsApp quick-reply button (Cancel / Reschedule) from the on-page phone."""
    b = await _booking_by_token(conn, token)
    reply = await handle_button(conn, rzp, provider, payload=body.payload, from_digits="91" + b["phone_e164"][-10:], button_text=body.text)
    return {"reply": reply}

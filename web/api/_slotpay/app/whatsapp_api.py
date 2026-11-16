"""WhatsApp inbound webhook, demo simulator endpoints, and the .ics calendar file."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from . import db, messaging
from .cancellation import cancel_booking
from .config import get_settings
from .messaging import get_provider
from .razorpay_client import get_rzp
from .tz import zone

log = logging.getLogger("slotpay.whatsapp")
router = APIRouter()


# ------------------------------------------------------------------ button handling
async def handle_button(conn, rzp, provider, *, payload: str, from_digits: str, button_text: str = "") -> str:
    """Shared by real WhatsApp and the simulator. Returns the reply text that was sent."""
    action, _, bid = payload.partition(":")
    try:
        booking_id = UUID(bid)
    except ValueError:
        return ""
    ctx = await messaging.booking_ctx(conn, booking_id)
    if not ctx or ctx["phone_e164"].lstrip("+") != from_digits.lstrip("+"):
        return ""  # unknown booking, or someone else's phone: ignore silently
    await messaging.log_msg(conn, booking_id=booking_id, customer_id=ctx["customer_id"], direction="in",
                            channel="simulator" if get_settings().whatsapp_mode == "simulator" else "whatsapp",
                            body=button_text or action.title())
    first = ctx["cname"].split()[0]
    if action == "cancel":
        res = await cancel_booking(conn, rzp, booking_id, reason="customer_whatsapp", actor="customer",
                                  provider=provider)
        if not res["ok"]:
            reply = f"Hi {first}, this booking is already cancelled or completed."
        elif res["refunded_paise"]:
            reply = (f"Hi {first}, your booking has been cancelled. Your ₹{res['refunded_paise'] // 100:,} advance "
                     "refund has been initiated and reaches you in 5-7 working days.")
        elif res["had_payment"]:
            reply = (f"Hi {first}, your booking has been cancelled. As it was within "
                     f"{ctx['cutoff']} hours of the appointment, the advance is non-refundable.")
        else:
            reply = f"Hi {first}, your booking has been cancelled."
    elif action == "reschedule":
        link = f"{get_settings().public_base_url}/b/{ctx['slug']}/reschedule/{ctx['public_token']}"
        reply = f"Hi {first}, you can pick a new time here: {link}"
    else:
        return ""
    await messaging.deliver_text(conn, provider, ctx, reply)
    await conn.commit()
    return reply


# ------------------------------------------------------------------ inbound webhook
@router.get("/webhooks/whatsapp")
async def whatsapp_verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and get_settings().whatsapp_verify_token and \
            hmac.compare_digest(q.get("hub.verify_token", ""), get_settings().whatsapp_verify_token):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed")


@router.post("/webhooks/whatsapp")
async def whatsapp_inbound(request: Request, conn=Depends(db.get_conn), rzp=Depends(get_rzp),
                           provider=Depends(get_provider)):
    raw = await request.body()
    secret = get_settings().whatsapp_app_secret
    sig = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(expected, sig):
        raise HTTPException(403, "Bad signature")
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Bad payload")
    from psycopg.types.json import Jsonb
    for entry in data.get("entry", []):
        for ch in entry.get("changes", []):
            for m in ch.get("value", {}).get("messages", []):
                mid = m.get("id", "")
                ins = await (await conn.execute(
                    "insert into webhook_event (id,source,event,payload) values (%s,'whatsapp',%s,%s) "
                    "on conflict (id) do nothing returning id", (mid, m.get("type", ""), Jsonb(m)))).fetchone()
                await conn.commit()
                if not ins:
                    continue  # duplicate delivery
                payload = text = ""
                if m.get("type") == "button":
                    payload, text = m["button"].get("payload", ""), m["button"].get("text", "")
                elif m.get("type") == "interactive":
                    br = m.get("interactive", {}).get("button_reply", {})
                    payload, text = br.get("id", ""), br.get("title", "")
                if payload:
                    await handle_button(conn, rzp, provider, payload=payload, from_digits=m.get("from", ""),
                                        button_text=text)
                await conn.execute("update webhook_event set processed_at=now() where id=%s", (mid,))
                await conn.commit()
    return {"ok": True}


# ------------------------------------------------------------------ simulator (demo)
def demo_key(key: str = Query(default="")) -> None:
    expected = get_settings().demo_key
    if not expected or not hmac.compare_digest(key, expected):
        raise HTTPException(403, "Demo key required")


@router.get("/demo/whatsapp/messages", dependencies=[Depends(demo_key)])
async def sim_messages(phone: str, conn=Depends(db.get_conn)):
    digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
    rows = await (await conn.execute(
        """select m.id, m.direction, m.body, m.buttons, m.template, m.status, m.created_at, b.business_id,
                  bz.name business_name
           from message_log m join customer c on c.id=m.customer_id
           left join booking b on b.id=m.booking_id left join business bz on bz.id=b.business_id
           where c.phone_e164 = %s and (m.direction='in' or m.channel='simulator') order by m.created_at, m.id""",
        ("+91" + digits,))).fetchall()
    return {"business": rows[-1]["business_name"] if rows else "Glow Studio Salon & Spa",
            "messages": [{"id": str(r["id"]), "direction": r["direction"], "body": r["body"], "buttons": r["buttons"],
                          "at": r["created_at"].astimezone(zone("Asia/Kolkata")).isoformat()} for r in rows]}


class ButtonIn(BaseModel):
    phone: str
    payload: str
    text: str = ""


@router.post("/demo/whatsapp/button", dependencies=[Depends(demo_key)])
async def sim_button(body: ButtonIn, conn=Depends(db.get_conn), rzp=Depends(get_rzp), provider=Depends(get_provider)):
    digits = "".join(ch for ch in body.phone if ch.isdigit())[-10:]
    reply = await handle_button(conn, rzp, provider, payload=body.payload, from_digits="91" + digits,
                                button_text=body.text)
    return {"reply": reply}


# ------------------------------------------------------------------ .ics
def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@router.get("/public/bookings/{token}/ics")
async def booking_ics(token: str, conn=Depends(db.get_conn)):
    r = await (await conn.execute(
        """select b.id, b.time_range, b.status, s.name service, st.name staff, bz.name salon, bz.address, bz.timezone
           from booking b join service s on s.id=b.service_id join staff st on st.id=b.staff_id
           join business bz on bz.id=b.business_id where b.public_token=%s""", (token,))).fetchone()
    if not r or r["status"] not in ("confirmed", "completed"):
        raise HTTPException(404, "Booking not found")
    tz = zone(r["timezone"])
    f = lambda d: d.astimezone(tz).strftime("%Y%m%dT%H%M%S")  # noqa: E731
    from datetime import datetime, timezone
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SlotPay//Glow Studio//EN", "CALSCALE:GREGORIAN",
             "BEGIN:VTIMEZONE", "TZID:Asia/Kolkata", "BEGIN:STANDARD", "DTSTART:19700101T000000",
             "TZOFFSETFROM:+0530", "TZOFFSETTO:+0530", "TZNAME:IST", "END:STANDARD", "END:VTIMEZONE",
             "BEGIN:VEVENT", f"UID:{r['id']}@slotpay", f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
             f"DTSTART;TZID=Asia/Kolkata:{f(r['time_range'].lower)}", f"DTEND;TZID=Asia/Kolkata:{f(r['time_range'].upper)}",
             f"SUMMARY:{_esc(r['service'] + ' at ' + r['salon'])}", f"LOCATION:{_esc(r['salon'] + ', ' + r['address'])}",
             f"DESCRIPTION:{_esc('With ' + r['staff'] + '. Balance payable at the salon.')}",
             "END:VEVENT", "END:VCALENDAR"]
    return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="appointment.ics"'})

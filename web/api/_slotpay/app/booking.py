"""Public catalogue + hold endpoints (M3). Payment is attached to holds in M4."""
from __future__ import annotations

import re
import secrets
import time as _time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.types.json import Jsonb
from psycopg.types.range import Range
import logging

from pydantic import BaseModel, Field, field_validator

from . import db, messaging, realtime
from .availability import get_slots, pick_staff, working_windows
from .config import get_settings
from .db import SlotTaken, is_exclusion_violation
from .payments import audit, compute_advance
from .razorpay_client import RazorpayError, get_rzp
from .public import _now, load_context
from .tz import day_bounds, zone

log = logging.getLogger("slotpay.booking")
router = APIRouter(prefix="/public")

_hits: dict[str, deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    """Caller IP. Behind a trusted proxy (Render/Vercel) the left-most X-Forwarded-For entry is the customer."""
    if get_settings().trust_proxy:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


def rate_limit(key: str, limit: int = 5, per: int = 60) -> None:
    q, now = _hits[key], _time.monotonic()
    while q and now - q[0] > per:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many attempts. Please wait a minute and try again.")
    q.append(now)


@router.get("/{slug}")
async def business(slug: str, conn=Depends(db.get_conn)):
    b = await (await conn.execute("select * from business where slug=%s", (slug,))).fetchone()
    if not b:
        raise HTTPException(404, "Business not found")
    tz = zone(b["timezone"])
    now = _now().astimezone(tz)
    svcs = await (await conn.execute(
        """select id, category, name, description, duration_min, price_paise, advance_type, advance_value
           from service where business_id=%s and is_active order by sort_order""", (b["id"],))).fetchall()
    shifts = [r["shift_template"] for r in await (await conn.execute(
        "select shift_template from staff where business_id=%s and is_active", (b["id"],))).fetchall()]
    wins = [w for t in shifts for w in working_windows(t, now.date(), tz)]
    close = max((w[1] for w in wins), default=None)
    open_ = min((w[0] for w in wins), default=None)
    return {
        "id": str(b["id"]), "slug": b["slug"], "name": b["name"], "address": b["address"], "phone": b["phone"], "email": b["email"],
        "maps_url": b["maps_url"], "timezone": b["timezone"], "hold_minutes": b["hold_minutes"],
        "cancellation_cutoff_hours": b["cancellation_cutoff_hours"], "policy_text": b["policy_text"],
        "open_now": bool(open_ and close and open_ <= now < close),
        "closes_at": close.isoformat() if close else None,
        "services": [{**s, "id": str(s["id"])} for s in svcs],
    }


@router.get("/{slug}/stylists")
async def stylists(slug: str, service_id: UUID, conn=Depends(db.get_conn)):
    now = _now()
    row = await (await conn.execute("select timezone from business where slug=%s", (slug,))).fetchone()
    if not row:
        raise HTTPException(404, "Business not found")
    start = now.astimezone(zone(row["timezone"])).date()
    rules, svc, staffs, busy, hol = await load_context(conn, slug, service_id, None, start, 14, now)
    info = {str(r["id"]): r for r in await (await conn.execute(
        "select id, name, title, bio, avatar_url from staff where id = any(%s)",
        ([UUID(s.id) for s in staffs],))).fetchall()}
    out = []
    for st in staffs:
        nxt = None
        for i in range(14):
            sl = get_slots(rules, str(service_id), svc, [st], busy, hol, start + timedelta(days=i), now)
            if sl:
                nxt = sl[0].start.astimezone(rules.tz).isoformat()
                break
        r = info[st.id]
        out.append({"id": st.id, "name": r["name"], "title": r["title"], "bio": r["bio"],
                    "avatar_url": r["avatar_url"], "next_free": nxt})
    return {"stylists": out}


class HoldIn(BaseModel):
    service_id: UUID
    staff_id: UUID | None = None
    start: datetime
    name: str = Field(min_length=1, max_length=80)
    phone: str
    whatsapp_opt_in: bool = False
    policy_accepted: bool

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        v = re.sub(r"[\s-]", "", v).removeprefix("+91")
        if not re.fullmatch(r"[6-9]\d{9}", v):
            raise ValueError("Enter a valid 10-digit mobile number")
        return v

    @field_validator("policy_accepted")
    @classmethod
    def _policy(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the cancellation policy")
        return v

    @field_validator("start")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("start must include a timezone offset")
        return v


@router.post("/{slug}/holds", status_code=201)
async def create_hold(slug: str, body: HoldIn, request: Request, conn=Depends(db.get_conn), rzp=Depends(get_rzp),
                      provider=Depends(messaging.get_provider)):
    rate_limit("ip:" + client_ip(request), limit=20)
    now = _now()
    biz = await (await conn.execute("select * from business where slug=%s", (slug,))).fetchone()
    if not biz:
        raise HTTPException(404, "Business not found")
    tz = zone(biz["timezone"])
    d = body.start.astimezone(tz).date()
    rules, svc, staffs, busy, hol = await load_context(conn, slug, body.service_id, body.staff_id, d, 1, now)
    slot = next((s for s in get_slots(rules, str(body.service_id), svc, staffs, busy, hol, d, now)
                 if s.start == body.start), None)
    if not slot:
        raise SlotTaken()
    lo, hi = day_bounds(d, tz)
    booked = {sid: int(sum((min(b, hi) - max(a, lo)).total_seconds() for a, b in iv if b > lo and a < hi) // 60)
              for sid, iv in busy.items()}
    order = pick_staff(slot.staff_ids, booked)

    phone = "+91" + body.phone
    rate_limit("phone:" + phone, limit=5)
    price = (await (await conn.execute("select price_paise from service where id=%s", (body.service_id,)))
             .fetchone())["price_paise"]
    start = body.start
    end = start + timedelta(minutes=svc.duration_min)
    block_end = end + timedelta(minutes=svc.buffer_min)
    cust = await (await conn.execute(
        """insert into customer (business_id,name,phone_e164,whatsapp_opt_in,consent_source)
           values (%s,%s,%s,%s,'online_booking')
           on conflict (business_id, phone_e164) do update set name=excluded.name,
             whatsapp_opt_in = customer.whatsapp_opt_in or excluded.whatsapp_opt_in
           returning id""", (biz["id"], body.name.strip(), phone, body.whatsapp_opt_in))).fetchone()
    active = (await (await conn.execute(
        "select count(*) n from booking where customer_id=%s and status='held' and hold_expires_at > now()",
        (cust["id"],))).fetchone())["n"]
    if active >= 3:
        raise HTTPException(429, "You already have 3 slots on hold. Finish or release one first.")

    booking = None
    for sid in order:
        await conn.execute(
            """update booking set status='expired' where staff_id=%s and status='held'
               and hold_expires_at < now() and block_range && %s""", (sid, Range(start, block_end, "[)")))
        try:
            async with conn.transaction():
                booking = await (await conn.execute(
                    """insert into booking (business_id,customer_id,service_id,staff_id,time_range,block_range,status,
                         hold_expires_at,source,price_paise,public_token)
                       values (%s,%s,%s,%s,%s,%s,'held', now() + make_interval(mins => %s),'online',%s,%s)
                       returning id, public_token, hold_expires_at, staff_id""",
                    (biz["id"], cust["id"], body.service_id, UUID(sid), Range(start, end, "[)"),
                     Range(start, block_end, "[)"), biz["hold_minutes"], price, secrets.token_urlsafe(16)))).fetchone()
            break
        except psycopg.Error as e:
            if is_exclusion_violation(e):
                continue
            raise
    if not booking:
        await conn.rollback()
        raise SlotTaken()
    await conn.execute(
        "insert into audit_event (business_id,booking_id,type,data) values (%s,%s,'slot_held',%s)",
        (biz["id"], booking["id"], Jsonb({"start": start.isoformat(), "staff_id": str(booking["staff_id"])})))
    await conn.commit()  # never hold a transaction open across HTTP calls
    await realtime.broadcast(realtime.slots_topic(biz["id"], d), "slot_held", {
        "event": "slot_held", "staff_id": str(booking["staff_id"]), "start": start.isoformat(),
        "end": block_end.isoformat()})

    # --- advance + Razorpay order (after commit) ---
    srv = await (await conn.execute("select advance_type, advance_value, price_paise from service where id=%s",
                                    (body.service_id,))).fetchone()
    skip = (await (await conn.execute("select skip_advance from customer where id=%s", (cust["id"],))).fetchone())["skip_advance"]
    is_hol = d in hol
    advance = compute_advance(price_paise=srv["price_paise"], advance_type=srv["advance_type"],
                              advance_value=srv["advance_value"], skip_advance=skip,
                              advance_applies=biz["advance_applies"], day=d, is_holiday=is_hol)
    out = {"booking_id": str(booking["id"]), "public_token": booking["public_token"],
           "staff_id": str(booking["staff_id"]), "hold_expires_at": booking["hold_expires_at"].isoformat(),
           "status": "held", "advance_paise": advance, "order": None}
    if advance == 0:
        await conn.execute("update booking set status='confirmed', hold_expires_at=null where id=%s", (booking["id"],))
        await audit(conn, biz["id"], booking["id"], "booking_confirmed", {"advance": 0})
        await messaging.queue_confirmation_messages(conn, booking["id"], start)
        await conn.commit()
        try:
            await messaging.send_due(conn, provider, booking_id=booking["id"])
        except Exception:  # noqa: BLE001
            log.exception("immediate send failed; the job tick will retry")
        out.update(status="confirmed", hold_expires_at=None)
        return out
    await conn.execute("update booking set advance_due_paise=%s where id=%s", (advance, booking["id"]))
    await conn.commit()
    try:
        order = await rzp.create_order(advance, str(booking["id"]), {"booking_id": str(booking["id"]), "business": slug})
    except RazorpayError:
        log.exception("order creation failed")
        await _expire(conn, booking["id"])
        raise HTTPException(502, "We couldn't start the payment. Your slot was released; please try again.")
    await conn.execute("insert into payment (booking_id,razorpay_order_id,amount_paise,status) values (%s,%s,%s,'created')",
                       (booking["id"], order["id"], advance))
    await audit(conn, biz["id"], booking["id"], "razorpay_order_created", {"order_id": order["id"], "amount_paise": advance})
    await conn.commit()
    out["order"] = {"order_id": order["id"], "key_id": getattr(rzp, "mock_key_id", None) or get_settings().razorpay_key_id, "amount_paise": advance}
    return out


async def _expire(conn, booking_id) -> None:
    await conn.execute("update booking set status='expired' where id=%s and status='held'", (booking_id,))
    await conn.commit()


@router.post("/holds/{booking_id}/checkout-opened")
async def checkout_opened(booking_id: UUID, body: "ReleaseIn", conn=Depends(db.get_conn)):
    row = await (await conn.execute("select business_id from booking where id=%s and public_token=%s and status='held'",
                                    (booking_id, body.public_token))).fetchone()
    if row:
        await audit(conn, row["business_id"], booking_id, "checkout_opened")
        await conn.commit()
    return {"ok": bool(row)}


class ReleaseIn(BaseModel):
    public_token: str


@router.post("/holds/{booking_id}/release")
async def release_hold(booking_id: UUID, body: ReleaseIn, conn=Depends(db.get_conn)):
    row = await (await conn.execute(
        """update booking set status='expired' where id=%s and public_token=%s and status='held'
           returning business_id, staff_id, time_range, block_range""", (booking_id, body.public_token))).fetchone()
    if not row:
        return {"released": False}
    await conn.execute("insert into audit_event (business_id,booking_id,type) values (%s,%s,'hold_released')",
                       (row["business_id"], booking_id))
    await conn.commit()
    tz_name = (await (await conn.execute("select timezone from business where id=%s",
                                         (row["business_id"],))).fetchone())["timezone"]
    lo = row["time_range"].lower
    await realtime.broadcast(
        realtime.slots_topic(row["business_id"], lo.astimezone(zone(tz_name)).date()), "slot_released",
        {"event": "slot_released", "staff_id": str(row["staff_id"]), "start": lo.isoformat(),
         "end": row["block_range"].upper.isoformat()})
    return {"released": True}

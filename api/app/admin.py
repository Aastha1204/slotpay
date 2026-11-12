"""Admin API (staff-authenticated, scoped to the staff member's business)."""
from __future__ import annotations

import dataclasses
import logging
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.range import Range
from pydantic import BaseModel, Field, field_validator

from . import db, messaging, realtime
from .auth import Staff, current_staff, require_role
from .availability import DAYS, break_intervals, get_slots, is_blocking, working_windows
from .cancellation import cancel_booking, refund_eligible
from .db import SlotTaken, is_exclusion_violation
from .payments import audit
from .public import load_context
from .razorpay_client import get_rzp
from .tz import day_bounds, zone

log = logging.getLogger("slotpay.admin")
router = APIRouter(prefix="/admin")


async def _biz(conn, staff: Staff) -> dict:
    return await (await conn.execute("select * from business where id=%s", (staff.business_id,))).fetchone()


async def _own_booking(conn, staff: Staff, booking_id: UUID) -> dict:
    b = await (await conn.execute("select * from booking where id=%s and business_id=%s",
                                  (booking_id, staff.business_id))).fetchone()
    if not b:
        raise HTTPException(404, "Booking not found")
    return b


def _hhmm(dt: datetime, tz) -> str:
    return dt.astimezone(tz).strftime("%H:%M")


# ------------------------------------------------------------------ calendar
@router.get("/calendar")
async def calendar(date: date, view: str = Query("day", pattern="^(day|week)$"), include_cancelled: bool = False,
                   staff: Staff = Depends(current_staff), conn=Depends(db.get_conn)):
    biz = await _biz(conn, staff)
    tz = zone(biz["timezone"])
    start = date - timedelta(days=date.weekday()) if view == "week" else date
    days = 7 if view == "week" else 1
    lo, _ = day_bounds(start, tz)
    _, hi = day_bounds(start + timedelta(days=days - 1), tz)
    now = datetime.now(timezone.utc)

    srows = await (await conn.execute(
        "select id, name, title, shift_template from staff where business_id=%s and is_active order by name", (biz["id"],))).fetchall()
    links = await (await conn.execute(
        "select ss.staff_id, ss.service_id from staff_service ss join staff s on s.id=ss.staff_id where s.business_id=%s", (biz["id"],))).fetchall()
    svc_by_staff: dict = {}
    for l in links:
        svc_by_staff.setdefault(l["staff_id"], []).append(str(l["service_id"]))

    open_, close_ = [], []
    staff_out = []
    for s in srows:
        wins = [] if view == "week" else [{"start": _hhmm(a, tz), "end": _hhmm(b, tz)} for a, b in working_windows(s["shift_template"], start, tz)]
        brks = [] if view == "week" else [{"start": _hhmm(a, tz), "end": _hhmm(b, tz)} for a, b in break_intervals(s["shift_template"], start, tz)]
        for d in range(days):
            for a, b in working_windows(s["shift_template"], start + timedelta(days=d), tz):
                open_.append(a.hour * 60 + a.minute); close_.append(b.hour * 60 + b.minute)
        staff_out.append({"id": str(s["id"]), "name": s["name"], "title": s["title"], "service_ids": svc_by_staff.get(s["id"], []),
                          "working": wins, "breaks": brks})
    day_start = min(open_, default=600) // 60 * 60
    day_end = -(-max(close_, default=1260) // 60) * 60

    statuses = "('held','confirmed','completed','no_show','cancelled','expired')" if include_cancelled else "('held','confirmed','completed','no_show')"
    brows = await (await conn.execute(
        f"""select b.id, b.status, b.staff_id, b.time_range, b.block_range, b.source, b.price_paise, b.advance_paid_paise,
                   b.hold_expires_at, b.created_at, s.name service, c.name customer, c.phone_e164,
                   (select p.status from payment p where p.booking_id=b.id order by p.created_at desc limit 1) payment_status
            from booking b join service s on s.id=b.service_id join customer c on c.id=b.customer_id
            where b.business_id=%s and b.status in {statuses} and b.time_range && tstzrange(%s,%s,'[)') order by lower(b.time_range)""",
        (biz["id"], lo, hi))).fetchall()
    bookings = [{
        "id": str(b["id"]), "status": b["status"], "staff_id": str(b["staff_id"]),
        "start": b["time_range"].lower.astimezone(tz).isoformat(), "end": b["time_range"].upper.astimezone(tz).isoformat(),
        "service": b["service"], "customer": b["customer"], "phone": b["phone_e164"], "source": b["source"],
        "price_paise": b["price_paise"], "advance_paid_paise": b["advance_paid_paise"],
        "hold_expires_at": b["hold_expires_at"].isoformat() if b["hold_expires_at"] else None,
        "payment_status": b["payment_status"], "created_at": b["created_at"].isoformat()}
        for b in brows if is_blocking(b["status"], b["hold_expires_at"], now) or b["status"] != "held"]
    tbs = await (await conn.execute(
        """select t.id, t.staff_id, t.time_range, t.reason from time_block t join staff s on s.id=t.staff_id
           where s.business_id=%s and t.time_range && tstzrange(%s,%s,'[)')""", (biz["id"], lo, hi))).fetchall()
    svcs = await (await conn.execute(
        "select id, name, category, duration_min, price_paise from service where business_id=%s and is_active order by sort_order", (biz["id"],))).fetchall()
    return {
        "business_id": str(biz["id"]), "date": date.isoformat(), "view": view, "range_start": start.isoformat(),
        "timezone": biz["timezone"],
        "day_start_min": day_start, "day_end_min": day_end, "staff": staff_out, "bookings": bookings,
        "time_blocks": [{"id": str(t["id"]), "staff_id": str(t["staff_id"]),
                         "start": t["time_range"].lower.astimezone(tz).isoformat(),
                         "end": t["time_range"].upper.astimezone(tz).isoformat(), "reason": t["reason"]} for t in tbs],
        "services": [{**s, "id": str(s["id"])} for s in svcs],
    }


# ------------------------------------------------------------------ detail
@router.get("/bookings/{booking_id}")
async def booking_detail(booking_id: UUID, staff: Staff = Depends(current_staff), conn=Depends(db.get_conn)):
    await _own_booking(conn, staff, booking_id)
    biz = await _biz(conn, staff)
    tz = zone(biz["timezone"])
    b = await (await conn.execute(
        """select b.*, s.name service, s.id service_id, st.name staff_name, c.name customer, c.phone_e164, c.whatsapp_opt_in
           from booking b join service s on s.id=b.service_id join staff st on st.id=b.staff_id
           join customer c on c.id=b.customer_id where b.id=%s""", (booking_id,))).fetchone()
    pays = await (await conn.execute("select * from payment where booking_id=%s order by created_at", (booking_id,))).fetchall()
    refunds = await (await conn.execute(
        "select r.* from refund r join payment p on p.id=r.payment_id where p.booking_id=%s order by r.created_at", (booking_id,))).fetchall()
    msgs = await (await conn.execute(
        """select m.direction, m.channel, m.template, m.body, m.status, m.created_at from message_log m
           where m.booking_id=%s and not (m.channel='whatsapp' and m.direction='out' and exists
             (select 1 from message_log x where x.booking_id=m.booking_id and x.channel='simulator' and x.body=m.body))
           order by m.created_at""", (booking_id,))).fetchall()
    cutoff = biz["cancellation_cutoff_hours"]
    eligible = refund_eligible(b["time_range"].lower, datetime.now(timezone.utc), cutoff)
    return {
        "id": str(b["id"]), "status": b["status"], "source": b["source"], "service": b["service"], "service_id": str(b["service_id"]),
        "staff": b["staff_name"], "staff_id": str(b["staff_id"]),
        "start": b["time_range"].lower.astimezone(tz).isoformat(), "end": b["time_range"].upper.astimezone(tz).isoformat(),
        "customer": {"name": b["customer"], "phone": b["phone_e164"], "whatsapp_opt_in": b["whatsapp_opt_in"]},
        "price_paise": b["price_paise"], "advance_paid_paise": b["advance_paid_paise"],
        "hold_expires_at": b["hold_expires_at"].isoformat() if b["hold_expires_at"] else None,
        "payments": [{"order_id": p["razorpay_order_id"], "payment_id": p["razorpay_payment_id"], "method": p["method"],
                      "amount_paise": p["amount_paise"], "status": p["status"], "refunded_paise": p["refunded_paise"],
                      "is_seeded": p["is_seeded"]} for p in pays],
        "refunds": [{"id": r["razorpay_refund_id"], "amount_paise": r["amount_paise"], "status": r["status"]} for r in refunds],
        "messages": [{"direction": m["direction"], "channel": m["channel"], "template": m["template"], "body": m["body"],
                      "at": m["created_at"].astimezone(tz).isoformat()} for m in msgs],
        "cancel_policy": {"cutoff_hours": cutoff, "refund_eligible": eligible,
                          "text": (f"More than {cutoff} h before: full ₹{b['advance_paid_paise'] // 100:,} refund" if eligible
                                   else f"Within {cutoff} h: advance forfeited")},
    }


# ------------------------------------------------------------------ customers + manual booking
@router.get("/customers/search")
async def customer_search(q: str = Query(min_length=2), staff: Staff = Depends(current_staff), conn=Depends(db.get_conn)):
    digits = re.sub(r"\D", "", q)
    rows = await (await conn.execute(
        """select id, name, phone_e164 from customer where business_id=%s and (phone_e164 like %s or lower(name) like %s)
           order by name limit 8""", (staff.business_id, f"%{digits}%" if digits else "%@@none@@%", f"%{q.lower()}%"))).fetchall()
    return {"customers": [{"id": str(r["id"]), "name": r["name"], "phone": r["phone_e164"]} for r in rows]}


class ManualBookingIn(BaseModel):
    service_id: UUID
    staff_id: UUID
    start: datetime
    name: str = Field(min_length=1, max_length=80)
    phone: str
    source: str = Field(default="walk_in", pattern="^(walk_in|phone)$")
    whatsapp_opt_in: bool = False

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        v = re.sub(r"[\s-]", "", v).removeprefix("+91")
        if not re.fullmatch(r"[6-9]\d{9}", v):
            raise ValueError("Enter a valid 10-digit mobile number")
        return v

    @field_validator("start")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("start must include a timezone offset")
        return v


async def _admin_slot_ok(conn, staff: Staff, service_id: UUID, staff_id: UUID, start: datetime, exclude: UUID | None):
    biz = await _biz(conn, staff)
    tz = zone(biz["timezone"])
    d = start.astimezone(tz).date()
    now = datetime.now(timezone.utc)
    rules, svc, staffs, busy, hol = await load_context(conn, biz["slug"], service_id, staff_id, d, 1, now, exclude)
    rules = dataclasses.replace(rules, min_lead_min=0)  # front desk may book "right now"
    ok = any(s.start == start for s in get_slots(rules, str(service_id), svc, staffs, busy, hol, d, now))
    if not ok:
        raise SlotTaken()
    return biz, svc


@router.post("/bookings", status_code=201)
async def create_booking(body: ManualBookingIn, staff: Staff = Depends(current_staff), conn=Depends(db.get_conn),
                         provider=Depends(messaging.get_provider)):
    biz, svc = await _admin_slot_ok(conn, staff, body.service_id, body.staff_id, body.start, None)
    price = (await (await conn.execute("select price_paise from service where id=%s", (body.service_id,))).fetchone())["price_paise"]
    end = body.start + timedelta(minutes=svc.duration_min)
    block_end = end + timedelta(minutes=svc.buffer_min)
    cust = await (await conn.execute(
        """insert into customer (business_id,name,phone_e164,whatsapp_opt_in,consent_source)
           values (%s,%s,%s,%s,%s)
           on conflict (business_id, phone_e164) do update set name=excluded.name,
             whatsapp_opt_in = customer.whatsapp_opt_in or excluded.whatsapp_opt_in returning id""",
        (biz["id"], body.name.strip(), "+91" + body.phone, body.whatsapp_opt_in, body.source))).fetchone()
    try:
        async with conn.transaction():
            b = await (await conn.execute(
                """insert into booking (business_id,customer_id,service_id,staff_id,time_range,block_range,status,source,
                     price_paise,public_token) values (%s,%s,%s,%s,%s,%s,'confirmed',%s,%s,%s) returning id, public_token""",
                (biz["id"], cust["id"], body.service_id, body.staff_id, Range(body.start, end, "[)"),
                 Range(body.start, block_end, "[)"), body.source, price, secrets.token_urlsafe(16)))).fetchone()
    except psycopg.Error as e:
        if is_exclusion_violation(e):
            await conn.rollback()
            raise SlotTaken()
        raise
    await audit(conn, biz["id"], b["id"], "booking_created_by_staff", {"source": body.source, "staff_user": str(staff.id)})
    await messaging.queue_confirmation_messages(conn, b["id"], body.start)
    await conn.commit()
    await _notify(conn, biz, b["id"], body.staff_id, body.start, block_end, "booking_created")
    try:
        await messaging.send_due(conn, provider, booking_id=b["id"])
    except Exception:  # noqa: BLE001
        log.exception("send failed; tick will retry")
    return {"booking_id": str(b["id"]), "public_token": b["public_token"]}


async def _notify(conn, biz, booking_id, staff_id, start, block_end, event: str, old: tuple | None = None) -> None:
    tz = zone(biz["timezone"])
    payload = {"event": event, "booking_id": str(booking_id), "staff_id": str(staff_id), "start": start.isoformat(),
               "end": block_end.isoformat()}
    await realtime.broadcast(realtime.admin_topic(biz["id"]), event, payload)
    await realtime.broadcast(realtime.slots_topic(biz["id"], start.astimezone(tz).date()), "slot_held", payload)
    if old:
        await realtime.broadcast(realtime.slots_topic(biz["id"], old[0].astimezone(tz).date()), "slot_released",
                                 {"event": "slot_released", "staff_id": str(old[2]), "start": old[0].isoformat(),
                                  "end": old[1].isoformat()})


# ------------------------------------------------------------------ time blocks
class BlockIn(BaseModel):
    staff_id: UUID
    start: datetime
    end: datetime
    reason: str = Field(default="", max_length=120)

    @field_validator("start", "end")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must include a timezone offset")
        return v


@router.post("/time-blocks", status_code=201)
async def create_block(body: BlockIn, staff: Staff = Depends(current_staff), conn=Depends(db.get_conn)):
    if body.end <= body.start:
        raise HTTPException(422, "End must be after start")
    own = await (await conn.execute("select 1 from staff where id=%s and business_id=%s", (body.staff_id, staff.business_id))).fetchone()
    if not own:
        raise HTTPException(404, "Stylist not found")
    try:
        async with conn.transaction():
            r = await (await conn.execute("insert into time_block (staff_id,time_range,reason) values (%s,%s,%s) returning id",
                                          (body.staff_id, Range(body.start, body.end, "[)"), body.reason))).fetchone()
    except psycopg.Error as e:
        if is_exclusion_violation(e):
            await conn.rollback()
            raise HTTPException(409, "That time already has a booking. Move or cancel it first.")
        raise
    await conn.commit()
    return {"id": str(r["id"])}


@router.delete("/time-blocks/{block_id}")
async def delete_block(block_id: UUID, staff: Staff = Depends(current_staff), conn=Depends(db.get_conn)):
    r = await (await conn.execute(
        "delete from time_block t using staff s where t.id=%s and s.id=t.staff_id and s.business_id=%s returning t.id",
        (block_id, staff.business_id))).fetchone()
    await conn.commit()
    if not r:
        raise HTTPException(404, "Block not found")
    return {"deleted": True}


# ------------------------------------------------------------------ statuses
class StatusIn(BaseModel):
    status: str = Field(pattern="^(completed|no_show)$")


@router.post("/bookings/{booking_id}/status")
async def set_status(booking_id: UUID, body: StatusIn, staff: Staff = Depends(current_staff), conn=Depends(db.get_conn)):
    r = await (await conn.execute(
        "update booking set status=%s where id=%s and business_id=%s and status='confirmed' returning id",
        (body.status, booking_id, staff.business_id))).fetchone()
    if not r:
        await conn.rollback()
        raise HTTPException(409, "Only confirmed bookings can be marked completed or no-show")
    await audit(conn, staff.business_id, booking_id, f"booking_{body.status}", {"staff_user": str(staff.id)})
    await conn.commit()
    return {"status": body.status}


# ------------------------------------------------------------------ slots + reschedule
@router.get("/slots")
async def admin_slots(service_id: UUID, staff_id: UUID, date: date, exclude_booking_id: UUID | None = None,
                      staff: Staff = Depends(current_staff), conn=Depends(db.get_conn)):
    biz = await _biz(conn, staff)
    now = datetime.now(timezone.utc)
    rules, svc, staffs, busy, hol = await load_context(conn, biz["slug"], service_id, staff_id, date, 1, now, exclude_booking_id)
    rules = dataclasses.replace(rules, min_lead_min=0)
    slots = get_slots(rules, str(service_id), svc, staffs, busy, hol, date, now)
    return {"slots": [s.start.astimezone(rules.tz).isoformat() for s in slots]}


class RescheduleIn(BaseModel):
    start: datetime
    staff_id: UUID | None = None


@router.post("/bookings/{booking_id}/reschedule")
async def reschedule(booking_id: UUID, body: RescheduleIn, staff: Staff = Depends(current_staff), conn=Depends(db.get_conn),
                     provider=Depends(messaging.get_provider)):
    b = await _own_booking(conn, staff, booking_id)
    if b["status"] not in ("confirmed", "held"):
        raise HTTPException(409, "Only upcoming bookings can be rescheduled")
    new_staff = body.staff_id or b["staff_id"]
    biz, svc = await _admin_slot_ok(conn, staff, b["service_id"], new_staff, body.start, booking_id)
    end = body.start + timedelta(minutes=svc.duration_min)
    block_end = end + timedelta(minutes=svc.buffer_min)
    old = (b["time_range"].lower, b["block_range"].upper, b["staff_id"])
    try:
        async with conn.transaction():  # one transaction; the exclusion constraint protects the move
            await conn.execute("update booking set staff_id=%s, time_range=%s, block_range=%s where id=%s",
                               (new_staff, Range(body.start, end, "[)"), Range(body.start, block_end, "[)"), booking_id))
            await conn.execute("delete from scheduled_message where booking_id=%s and kind in ('confirmation','remind_24h','remind_2h')",
                               (booking_id,))
            if b["status"] == "confirmed":
                await messaging.queue_confirmation_messages(conn, booking_id, body.start)
    except psycopg.Error as e:
        if is_exclusion_violation(e):
            await conn.rollback()
            raise SlotTaken()
        raise
    await audit(conn, biz["id"], booking_id, "booking_rescheduled",
                {"from": old[0].isoformat(), "to": body.start.isoformat(), "staff_user": str(staff.id)})
    await conn.commit()
    await _notify(conn, biz, booking_id, new_staff, body.start, block_end, "booking_rescheduled", old)
    try:  # customer is notified with the confirmation template carrying the new time
        await messaging.send_due(conn, provider, booking_id=booking_id)
    except Exception:  # noqa: BLE001
        log.exception("send failed; tick will retry")
    return {"start": body.start.isoformat()}


# ------------------------------------------------------------------ cancel
@router.get("/bookings/{booking_id}/cancel-preview")
async def cancel_preview(booking_id: UUID, staff: Staff = Depends(current_staff), conn=Depends(db.get_conn)):
    d = await booking_detail(booking_id, staff, conn)
    return {**d["cancel_policy"], "advance_paid_paise": d["advance_paid_paise"], "can_override": staff.role == "owner"}


class CancelIn(BaseModel):
    refund_override: bool = False


@router.post("/bookings/{booking_id}/cancel")
async def admin_cancel(booking_id: UUID, body: CancelIn, staff: Staff = Depends(current_staff), conn=Depends(db.get_conn),
                       rzp=Depends(get_rzp), provider=Depends(messaging.get_provider)):
    await _own_booking(conn, staff, booking_id)
    if body.refund_override and staff.role != "owner":
        raise HTTPException(403, "Only the owner can refund outside the policy")
    res = await cancel_booking(conn, rzp, booking_id, reason="cancelled_by_staff", actor="staff",
                               force_refund=body.refund_override, provider=provider)
    if not res["ok"]:
        raise HTTPException(409, "This booking can't be cancelled")
    return res

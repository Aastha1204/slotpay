"""Presenter console API (/demo/*, protected by DEMO_KEY) + owner-only demo reset."""
from __future__ import annotations

import asyncio
import hmac
import importlib.util
import logging
import pathlib
import sys
import time
from datetime import date, datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from psycopg.types.json import Jsonb
from psycopg.types.range import Range
from pydantic import BaseModel, Field

from . import booking as booking_mod
from . import db, messaging
from .auth import Staff, require_role
from .availability import get_slots
from .config import get_settings
from .public import load_context
from .tz import zone

log = logging.getLogger("slotpay.demo")
router = APIRouter()


def demo_auth(key: str = Query(default=""), x_demo_key: str | None = Header(default=None)) -> None:
    expected = get_settings().demo_key
    given = key or x_demo_key or ""
    if not expected or not hmac.compare_digest(given, expected):
        raise HTTPException(403, "Demo key required")


auth = [Depends(demo_auth)]


# ------------------------------------------------------------------ timeline text
def _t(iso: str | None, tz) -> str:
    if not iso:
        return ""
    d = datetime.fromisoformat(iso).astimezone(tz)
    return f"{d:%a} {d.day} {d:%b}, {d.hour % 12 or 12}:{d:%M} {'AM' if d.hour < 12 else 'PM'}"


def describe(type_: str, data: dict, service: str | None, tz) -> str:
    who = f" · {service}" if service else ""
    d = data or {}
    return {
        "slot_held": f"Slot held{who}" + (f" · {_t(d.get('start'), tz)}" if d.get("start") else ""),
        "razorpay_order_created": f"Razorpay order created · {d.get('order_id', '')} · ₹{(d.get('amount_paise') or 0) // 100}",
        "checkout_opened": "Razorpay Checkout opened on the customer's phone",
        "signature_verified": "Payment signature verified on the server (HMAC-SHA256)",
        "webhook_payment_captured": "Webhook payment.captured received and deduplicated",
        "booking_confirmed": f"Booking confirmed{who}",
        "whatsapp_sent": f"WhatsApp {str(d.get('kind', 'message')).replace('_', ' ')} sent" + (" (live)" if d.get("live") else " (simulator)"),
        "messages_scheduled": (f"Reminders scheduled for {_t(d.get('remind_24h'), tz)} and {_t(d.get('remind_2h'), tz)}"
                               if d.get("remind_24h") else "Reminders scheduled"),
        "hold_released": "Hold released (customer closed Checkout)",
        "hold_expired": "Hold expired and the slot reopened",
        "booking_cancelled": "Booking cancelled" + (" · refund eligible" if d.get("refund_eligible") else " · advance forfeited"),
        "refund_initiated": f"Refund initiated · ₹{(d.get('amount_paise') or 0) // 100}",
        "refund_processed": "Refund processed by Razorpay",
        "refund_failed": "Refund failed at Razorpay",
        "payment_failed": "Payment attempt failed (hold kept so the customer can retry)",
        "late_capture_reconfirmed": "Late payment arrived; slot still free, booking re-confirmed",
        "late_capture_slot_lost": "Late payment arrived but the slot was taken, so a refund was issued",
        "booking_created_by_staff": f"Booking added by staff ({d.get('source', '')})",
        "booking_rescheduled": f"Booking rescheduled to {_t(d.get('to'), tz)}",
        "booking_no_show": "Marked no-show", "booking_completed": "Marked completed",
        "demo_reset": "Demo data reset",
        "double_booking_test": f"Double-booking test · {d.get('summary', '')}",
    }.get(type_, type_.replace("_", " "))


# ------------------------------------------------------------------ state + timeline
async def latest_booking(conn, business_id):
    return await (await conn.execute(
        """select b.id, b.status, c.name, c.phone_e164 from audit_event a join booking b on b.id=a.booking_id
           join customer c on c.id=b.customer_id where a.business_id=%s and a.type in ('slot_held','booking_created_by_staff')
           order by a.created_at desc limit 1""", (business_id,))).fetchone()


@router.get("/demo/state", dependencies=auth)
async def state(conn=Depends(db.get_conn)):
    b = await (await conn.execute("select id, slug, name from business order by created_at desc limit 1")).fetchone()
    if not b:
        raise HTTPException(404, "No demo business. Run the seed.")
    lb = await latest_booking(conn, b["id"])
    held = (await (await conn.execute("select count(*) n from booking where business_id=%s and status='held' and hold_expires_at > now()", (b["id"],))).fetchone())["n"]
    return {"slug": b["slug"], "name": b["name"], "booking_url": f"{get_settings().public_base_url}/b/{b['slug']}",
            "active_holds": held,
            "latest": ({"booking_id": str(lb["id"]), "status": lb["status"], "name": lb["name"], "phone": lb["phone_e164"][-10:]} if lb else None)}


@router.get("/demo/timeline", dependencies=auth)
async def timeline(limit: int = Query(default=60, ge=1, le=200), conn=Depends(db.get_conn)):
    b = await (await conn.execute("select id, timezone from business order by created_at desc limit 1")).fetchone()
    if not b:
        return {"events": []}
    tz = zone(b["timezone"])
    rows = await (await conn.execute(
        """select a.id, a.type, a.data, a.created_at, a.booking_id, s.name service from audit_event a
           left join booking bk on bk.id=a.booking_id left join service s on s.id=bk.service_id
           where a.business_id=%s order by a.created_at desc, a.id limit %s""", (b["id"], limit))).fetchall()
    return {"events": [{"id": str(r["id"]), "type": r["type"], "text": describe(r["type"], r["data"], r["service"], tz),
                        "at": r["created_at"].astimezone(tz).isoformat(), "booking_id": str(r["booking_id"]) if r["booking_id"] else None}
                       for r in rows]}


# ------------------------------------------------------------------ actions
class ReminderIn(BaseModel):
    kind: str = Field(pattern="^(remind_24h|remind_2h)$")


@router.post("/demo/actions/send-reminder", dependencies=auth)
async def send_reminder(body: ReminderIn, conn=Depends(db.get_conn), provider=Depends(messaging.get_provider)):
    b = await (await conn.execute("select id from business order by created_at desc limit 1")).fetchone()
    lb = await latest_booking(conn, b["id"])
    target = lb["id"] if lb and lb["status"] == "confirmed" else None
    if not target:
        r = await (await conn.execute("select id from booking where business_id=%s and status='confirmed' and lower(time_range) > now() "
                                      "order by created_at desc limit 1", (b["id"],))).fetchone()
        target = r["id"] if r else None
    if not target:
        raise HTTPException(409, "No confirmed upcoming booking to remind. Make a booking first.")
    await conn.execute(
        """insert into scheduled_message (booking_id,kind,send_at,status) values (%s,%s,now(),'pending')
           on conflict (booking_id,kind) do update set status='pending', send_at=now(), attempts=0""", (target, body.kind))
    await conn.commit()
    sent = await messaging.send_due(conn, provider, booking_id=target)
    return {"sent": sent, "booking_id": str(target), "kind": body.kind}


@router.post("/demo/actions/expire-holds", dependencies=auth)
async def expire_holds(conn=Depends(db.get_conn)):
    rows = await (await conn.execute("update booking set status='expired', hold_expires_at = now() where status='held' returning id, business_id")).fetchall()
    for r in rows:
        await conn.execute("insert into audit_event (business_id,booking_id,type) values (%s,%s,'hold_expired')", (r["business_id"], r["id"]))
    await conn.commit()
    return {"expired": len(rows)}


async def run_double_booking(conn, attempts: int = 20) -> dict:
    biz = await (await conn.execute("select * from business order by created_at desc limit 1")).fetchone()
    tz = zone(biz["timezone"])
    now = datetime.now(timezone.utc)
    svc = await (await conn.execute("select id, duration_min, buffer_min, price_paise from service where business_id=%s and name='Hair Spa'", (biz["id"],))).fetchone()
    stf = await (await conn.execute("select id, name from staff where business_id=%s and name='Neha'", (biz["id"],))).fetchone()
    if not svc or not stf:
        raise HTTPException(409, "Demo data missing. Reset the demo first.")
    today = now.astimezone(tz).date()
    sat = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    rules, spec, staffs, busy, hol = await load_context(conn, biz["slug"], svc["id"], stf["id"], sat, 1, now)
    slots = get_slots(rules, str(svc["id"]), spec, staffs, busy, hol, sat, now)
    if not slots:
        raise HTTPException(409, "No free slot on the demo Saturday. Reset the demo first.")
    slot = next((s for s in slots if s.start.astimezone(tz).hour == 16 and s.start.astimezone(tz).minute == 0), slots[len(slots) // 2])
    start = slot.start
    end = start + timedelta(minutes=spec.duration_min)
    block = end + timedelta(minutes=spec.buffer_min)
    cust = await (await conn.execute(
        """insert into customer (business_id,name,phone_e164,consent_source) values (%s,'Demo Tester','+919000000000','demo_test')
           on conflict (business_id,phone_e164) do update set name=excluded.name returning id""", (biz["id"],))).fetchone()
    await conn.commit()

    dsn = get_settings().database_url
    conns = [await psycopg.AsyncConnection.connect(dsn) for _ in range(attempts)]  # truly simultaneous sessions
    go = asyncio.Event()

    async def attempt(i: int, c) -> str:
        await go.wait()
        try:
            await c.execute(
                """insert into booking (business_id,customer_id,service_id,staff_id,time_range,block_range,status,hold_expires_at,
                     price_paise,public_token) values (%s,%s,%s,%s,%s,%s,'held',now() + interval '1 minute',%s,%s)""",
                (biz["id"], cust["id"], svc["id"], stf["id"], Range(start, end, "[)"), Range(start, block, "[)"),
                 svc["price_paise"], f"dbtest-{time.time_ns()}-{i}"))
            await c.commit()
            return "booked"
        except psycopg.Error as e:
            await c.rollback()
            if db.is_exclusion_violation(e):
                return "rejected"
            raise
        finally:
            await c.close()

    tasks = [asyncio.create_task(attempt(i, c)) for i, c in enumerate(conns)]
    t0 = time.perf_counter()
    go.set()
    results = await asyncio.gather(*tasks)
    elapsed = int((time.perf_counter() - t0) * 1000)
    booked, rejected = results.count("booked"), results.count("rejected")
    await conn.execute("delete from booking where customer_id=%s and public_token like 'dbtest-%%'", (cust["id"],))  # synthetic rows
    summary = f"{booked} booked · {rejected} rejected by the database"
    await conn.execute("insert into audit_event (business_id,type,data) values (%s,'double_booking_test',%s)",
                       (biz["id"], Jsonb({"summary": summary, "attempts": attempts})))
    await conn.commit()
    d = start.astimezone(tz)
    return {"attempts": attempts, "booked": booked, "rejected": rejected, "elapsed_ms": elapsed, "summary": summary,
            "slot": f"{d:%a} {d.day} {d:%b}, {d.hour % 12 or 12}:{d:%M} {'AM' if d.hour < 12 else 'PM'} · {stf['name']} · Hair Spa"}


@router.post("/demo/actions/double-booking-test", dependencies=auth)
async def double_booking_test(conn=Depends(db.get_conn)):
    return await run_double_booking(conn)


# ------------------------------------------------------------------ reset
def _load_seed():
    here = pathlib.Path(__file__).resolve()
    for cand in (here.parents[2] / "supabase" / "seed" / "seed.py", here.parents[1] / "seed" / "seed.py"):
        if cand.exists():
            spec = importlib.util.spec_from_file_location("slotpay_seed", cand)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["slotpay_seed"] = mod
            spec.loader.exec_module(mod)
            return mod
    raise RuntimeError("seed script not found")


def _do_reset() -> dict:
    if not get_settings().demo_mode:
        raise HTTPException(403, "Demo mode is off. Set DEMO_MODE=true to allow resetting data.")
    seed = _load_seed()
    t0 = time.perf_counter()
    with psycopg.connect(get_settings().database_url) as c:
        out = seed.seed(c)
    return {"seconds": round(time.perf_counter() - t0, 2), "bookings": out["bookings"], "script_saturday": out["script_saturday"]}


@router.post("/demo/actions/reset", dependencies=auth)
async def reset_demo():
    return await asyncio.to_thread(_do_reset)


@router.post("/admin/demo/reset")
async def reset_demo_owner(_: Staff = Depends(require_role("owner"))):
    return await asyncio.to_thread(_do_reset)

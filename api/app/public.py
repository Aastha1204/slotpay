"""Public (unauthenticated) read endpoints: day strip and slots."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from . import db
from .availability import (Rules, ServiceSpec, StaffSpec, day_counts, get_slots, is_blocking, part_of_day)
from .tz import day_bounds, zone

router = APIRouter(prefix="/public")


async def load_context(conn, slug: str, service_id: UUID, staff_id: UUID | None, start: date, days: int, now: datetime,
                       exclude_booking: UUID | None = None):
    """One round of queries for the whole date range (never one query per day)."""
    biz = await (await conn.execute("select * from business where slug=%s", (slug,))).fetchone()
    if not biz:
        raise HTTPException(404, "Business not found")
    svc = await (await conn.execute(
        "select id, duration_min, buffer_min from service where id=%s and business_id=%s and is_active",
        (service_id, biz["id"]))).fetchone()
    if not svc:
        raise HTTPException(404, "Service not found")
    tz = zone(biz["timezone"])
    rows = await (await conn.execute(
        """select s.id, s.shift_template from staff s join staff_service ss on ss.staff_id=s.id
           where ss.service_id=%s and s.business_id=%s and s.is_active and (%s::uuid is null or s.id=%s::uuid)""",
        (service_id, biz["id"], staff_id, staff_id))).fetchall()
    if staff_id and not rows:
        raise HTTPException(404, "Stylist not available for this service")
    staffs = [StaffSpec(str(r["id"]), r["shift_template"], {str(service_id)}) for r in rows]
    lo, _ = day_bounds(start, tz)
    _, hi = day_bounds(start + timedelta(days=days - 1), tz)
    ids = [r["id"] for r in rows]
    busy: dict[str, list] = {str(i): [] for i in ids}
    for b in await (await conn.execute(
            """select staff_id, block_range, status, hold_expires_at from booking
               where staff_id = any(%s) and status not in ('cancelled','expired')
                 and block_range && tstzrange(%s,%s,'[)') and (%s::uuid is null or id <> %s::uuid)""",
            (ids, lo, hi, exclude_booking, exclude_booking))).fetchall():
        if is_blocking(b["status"], b["hold_expires_at"], now):
            busy[str(b["staff_id"])].append((b["block_range"].lower, b["block_range"].upper))
    for b in await (await conn.execute(
            "select staff_id, time_range from time_block where staff_id = any(%s) and time_range && tstzrange(%s,%s,'[)')",
            (ids, lo, hi))).fetchall():
        busy[str(b["staff_id"])].append((b["time_range"].lower, b["time_range"].upper))
    hol = {r["date"] for r in await (await conn.execute(
        "select date from business_holiday where business_id=%s and date between %s and %s",
        (biz["id"], start, start + timedelta(days=days)))).fetchall()}
    rules = Rules(tz, biz["slot_step_min"], biz["min_lead_min"], biz["max_advance_days"])
    return rules, ServiceSpec(svc["duration_min"], svc["buffer_min"]), staffs, busy, hol


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/{slug}/days")
async def days(slug: str, service_id: UUID, staff_id: UUID | None = None, days: int = Query(14, ge=1, le=60),
               conn=Depends(db.get_conn)):
    now = _now()
    tz_name = (await (await conn.execute("select timezone from business where slug=%s", (slug,))).fetchone() or {}).get("timezone")
    if not tz_name:
        raise HTTPException(404, "Business not found")
    start = now.astimezone(zone(tz_name)).date()
    rules, svc, staffs, busy, hol = await load_context(conn, slug, service_id, staff_id, start, days, now)
    return {"days": day_counts(rules, str(service_id), svc, staffs, busy, hol, start, days, now)}


@router.get("/{slug}/slots")
async def slots(slug: str, service_id: UUID, date: date, staff_id: UUID | None = None, conn=Depends(db.get_conn)):
    now = _now()
    rules, svc, staffs, busy, hol = await load_context(conn, slug, service_id, staff_id, date, 1, now)
    out: dict[str, list] = {"morning": [], "afternoon": [], "evening": []}
    for s in get_slots(rules, str(service_id), svc, staffs, busy, hol, date, now):
        out[part_of_day(s.start, rules.tz)].append(
            {"start": s.start.astimezone(rules.tz).isoformat(), "staff_ids": list(s.staff_ids)})
    return {"date": date.isoformat(), "timezone": rules.tz.key, "slots": out}

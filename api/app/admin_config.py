"""Owner-only management API: services, staff & shifts, leave, settings, holidays."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from psycopg.types.range import Range
from pydantic import BaseModel, Field, field_validator

from . import db
from .auth import Staff, require_role
from .availability import DAYS
from .db import is_exclusion_violation
from .tz import day_bounds, zone

router = APIRouter(prefix="/admin/manage")
owner = require_role("owner")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _sets(model: BaseModel, allowed: set[str]) -> tuple[str, list]:
    data = {k: v for k, v in model.model_dump(exclude_unset=True).items() if k in allowed}
    if not data:
        raise HTTPException(422, "Nothing to update")
    return ", ".join(f"{k}=%s" for k in data), list(data.values())


# ------------------------------------------------------------------ services
class ServiceIn(BaseModel):
    category: str = Field(pattern="^(hair|skin|nails|spa)$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    duration_min: int = Field(ge=5, le=480)
    price_paise: int = Field(ge=0, le=100_000_00)
    advance_type: str = Field(default="fixed", pattern="^(none|fixed|percent)$")
    advance_value: int = Field(default=0, ge=0)
    buffer_min: int = Field(default=0, ge=0, le=120)
    is_active: bool = True
    sort_order: int = 0

    @field_validator("advance_value")
    @classmethod
    def _pct(cls, v, info):
        if info.data.get("advance_type") == "percent" and v > 100:
            raise ValueError("Percent advance cannot exceed 100")
        return v


class ServicePatch(BaseModel):
    category: str | None = Field(default=None, pattern="^(hair|skin|nails|spa)$")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=400)
    duration_min: int | None = Field(default=None, ge=5, le=480)
    price_paise: int | None = Field(default=None, ge=0, le=100_000_00)
    advance_type: str | None = Field(default=None, pattern="^(none|fixed|percent)$")
    advance_value: int | None = Field(default=None, ge=0)
    buffer_min: int | None = Field(default=None, ge=0, le=120)
    is_active: bool | None = None
    sort_order: int | None = None


@router.get("/services")
async def list_services(s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    rows = await (await conn.execute("select * from service where business_id=%s order by sort_order, name", (s.business_id,))).fetchall()
    return {"services": [{**r, "id": str(r["id"]), "business_id": None, "created_at": None, "updated_at": None} for r in rows]}


@router.post("/services", status_code=201)
async def create_service(b: ServiceIn, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    try:
        r = await (await conn.execute(
            """insert into service (business_id,category,name,description,duration_min,price_paise,advance_type,advance_value,
                 buffer_min,is_active,sort_order) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
            (s.business_id, b.category, b.name, b.description, b.duration_min, b.price_paise, b.advance_type, b.advance_value,
             b.buffer_min, b.is_active, b.sort_order))).fetchone()
    except psycopg.errors.UniqueViolation:
        await conn.rollback()
        raise HTTPException(409, "A service with that name already exists")
    await conn.commit()
    return {"id": str(r["id"])}


@router.patch("/services/{sid}")
async def patch_service(sid: UUID, b: ServicePatch, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    sets, vals = _sets(b, set(ServicePatch.model_fields))
    if b.advance_type == "percent" and (b.advance_value or 0) > 100:
        raise HTTPException(422, "Percent advance cannot exceed 100")
    try:
        r = await (await conn.execute(f"update service set {sets} where id=%s and business_id=%s returning id", (*vals, sid, s.business_id))).fetchone()
    except psycopg.errors.UniqueViolation:
        await conn.rollback()
        raise HTTPException(409, "A service with that name already exists")
    await conn.commit()
    if not r:
        raise HTTPException(404, "Service not found")
    return {"ok": True}


@router.delete("/services/{sid}")
async def delete_service(sid: UUID, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    try:
        r = await (await conn.execute("delete from service where id=%s and business_id=%s returning id", (sid, s.business_id))).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        await conn.rollback()
        raise HTTPException(409, "This service has bookings. Deactivate it instead of deleting.")
    await conn.commit()
    if not r:
        raise HTTPException(404, "Service not found")
    return {"deleted": True}


# ------------------------------------------------------------------ staff + shifts
def validate_template(t: dict) -> dict:
    if not isinstance(t, dict):
        raise ValueError("shift_template must be an object")
    out: dict = {}
    for k, v in t.items():
        if k == "breaks":
            if not isinstance(v, dict):
                raise ValueError("breaks must be an object")
            out["breaks"] = {d: _windows(d, w, "break") for d, w in v.items()}
        elif k in DAYS:
            out[k] = _windows(k, v, "shift")
        else:
            raise ValueError(f"Unknown key {k}")
    for d in DAYS:
        out.setdefault(d, [])
    out.setdefault("breaks", {})
    return out


def _windows(day: str, w, what: str) -> list[dict]:
    if day not in DAYS or not isinstance(w, list):
        raise ValueError(f"Invalid {what} for {day}")
    res = []
    for x in w:
        if not (isinstance(x, dict) and HHMM.match(str(x.get("start", ""))) and HHMM.match(str(x.get("end", "")))):
            raise ValueError(f"{day}: times must be HH:MM")
        if x["start"] >= x["end"]:
            raise ValueError(f"{day}: end must be after start")
        res.append({"start": x["start"], "end": x["end"]})
    res.sort(key=lambda r: r["start"])
    for a, b in zip(res, res[1:]):
        if a["end"] > b["start"]:
            raise ValueError(f"{day}: {what} times overlap")
    return res


class StaffIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    title: str = Field(default="", max_length=80)
    bio: str = Field(default="", max_length=400)
    avatar_url: str = Field(default="", max_length=300)
    is_active: bool = True
    shift_template: dict = Field(default_factory=dict)
    service_ids: list[UUID] = Field(default_factory=list)

    @field_validator("shift_template")
    @classmethod
    def _t(cls, v):
        return validate_template(v)


class StaffPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    title: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=400)
    avatar_url: str | None = Field(default=None, max_length=300)
    is_active: bool | None = None
    shift_template: dict | None = None
    service_ids: list[UUID] | None = None

    @field_validator("shift_template")
    @classmethod
    def _t(cls, v):
        return validate_template(v) if v is not None else v


async def _set_services(conn, staff_id, business_id, ids: list[UUID]) -> None:
    ok = await (await conn.execute("select id from service where business_id=%s and id = any(%s)", (business_id, ids))).fetchall()
    if len(ok) != len(set(ids)):
        raise HTTPException(422, "Unknown service")
    await conn.execute("delete from staff_service where staff_id=%s", (staff_id,))
    for i in set(ids):
        await conn.execute("insert into staff_service values (%s,%s)", (staff_id, i))


@router.get("/staff")
async def list_staff(s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    rows = await (await conn.execute("select id,name,title,bio,avatar_url,is_active,shift_template from staff where business_id=%s order by name", (s.business_id,))).fetchall()
    links = await (await conn.execute("select ss.* from staff_service ss join staff st on st.id=ss.staff_id where st.business_id=%s", (s.business_id,))).fetchall()
    by: dict = {}
    for l in links:
        by.setdefault(l["staff_id"], []).append(str(l["service_id"]))
    return {"staff": [{**r, "id": str(r["id"]), "service_ids": by.get(r["id"], [])} for r in rows]}


@router.post("/staff", status_code=201)
async def create_staff(b: StaffIn, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    try:
        r = await (await conn.execute(
            "insert into staff (business_id,name,title,bio,avatar_url,is_active,shift_template) values (%s,%s,%s,%s,%s,%s,%s) returning id",
            (s.business_id, b.name, b.title, b.bio, b.avatar_url, b.is_active, Jsonb(b.shift_template)))).fetchone()
    except psycopg.errors.UniqueViolation:
        await conn.rollback()
        raise HTTPException(409, "A stylist with that name already exists")
    await _set_services(conn, r["id"], s.business_id, b.service_ids)
    await conn.commit()
    return {"id": str(r["id"])}


@router.patch("/staff/{sid}")
async def patch_staff(sid: UUID, b: StaffPatch, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    own = await (await conn.execute("select 1 from staff where id=%s and business_id=%s", (sid, s.business_id))).fetchone()
    if not own:
        raise HTTPException(404, "Stylist not found")
    data = b.model_dump(exclude_unset=True)
    ids = data.pop("service_ids", None)
    if data:
        if "shift_template" in data:
            data["shift_template"] = Jsonb(data["shift_template"])
        try:
            await conn.execute(f"update staff set {', '.join(f'{k}=%s' for k in data)} where id=%s", (*data.values(), sid))
        except psycopg.errors.UniqueViolation:
            await conn.rollback()
            raise HTTPException(409, "A stylist with that name already exists")
    if ids is not None:
        await _set_services(conn, sid, s.business_id, ids)
    await conn.commit()
    return {"ok": True}


@router.delete("/staff/{sid}")
async def delete_staff(sid: UUID, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    try:
        r = await (await conn.execute("delete from staff where id=%s and business_id=%s returning id", (sid, s.business_id))).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        await conn.rollback()
        raise HTTPException(409, "This stylist has bookings. Mark them inactive instead of deleting.")
    await conn.commit()
    if not r:
        raise HTTPException(404, "Stylist not found")
    return {"deleted": True}


# ------------------------------------------------------------------ leave (entered as time blocks)
class LeaveIn(BaseModel):
    staff_id: UUID
    from_date: date
    to_date: date
    reason: str = Field(default="Leave", max_length=120)


@router.get("/leave")
async def list_leave(s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    tz_name = (await (await conn.execute("select timezone from business where id=%s", (s.business_id,))).fetchone())["timezone"]
    tz = zone(tz_name)
    rows = await (await conn.execute(
        """select t.id, t.staff_id, st.name, t.time_range, t.reason from time_block t join staff st on st.id=t.staff_id
           where st.business_id=%s and upper(t.time_range) > now() and t.reason like 'Leave%%' order by lower(t.time_range)""", (s.business_id,))).fetchall()
    return {"leave": [{"id": str(r["id"]), "staff_id": str(r["staff_id"]), "staff": r["name"], "reason": r["reason"],
                       "from": r["time_range"].lower.astimezone(tz).date().isoformat(),
                       "to": (r["time_range"].upper.astimezone(tz) - timedelta(seconds=1)).date().isoformat()} for r in rows]}


@router.post("/leave", status_code=201)
async def add_leave(b: LeaveIn, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    if b.to_date < b.from_date:
        raise HTTPException(422, "End date must be on or after the start date")
    row = await (await conn.execute(
        "select b.timezone from staff st join business b on b.id=st.business_id where st.id=%s and st.business_id=%s", (b.staff_id, s.business_id))).fetchone()
    if not row:
        raise HTTPException(404, "Stylist not found")
    tz = zone(row["timezone"])
    lo, _ = day_bounds(b.from_date, tz)
    _, hi = day_bounds(b.to_date, tz)
    reason = b.reason if b.reason.startswith("Leave") else f"Leave · {b.reason}"
    try:
        async with conn.transaction():
            r = await (await conn.execute("insert into time_block (staff_id,time_range,reason) values (%s,%s,%s) returning id",
                                          (b.staff_id, Range(lo, hi, "[)"), reason))).fetchone()
    except psycopg.Error as e:
        if is_exclusion_violation(e):
            await conn.rollback()
            raise HTTPException(409, "There are bookings in that period. Reschedule or cancel them first.")
        raise
    await conn.commit()
    return {"id": str(r["id"])}


# ------------------------------------------------------------------ settings + holidays
class SettingsPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=120)
    maps_url: str | None = Field(default=None, max_length=400)
    hold_minutes: int | None = Field(default=None, ge=2, le=60)
    cancellation_cutoff_hours: int | None = Field(default=None, ge=0, le=168)
    min_lead_min: int | None = Field(default=None, ge=0, le=1440)
    slot_step_min: int | None = None
    max_advance_days: int | None = Field(default=None, ge=1, le=365)
    advance_applies: str | None = Field(default=None, pattern="^(always|weekends_and_holidays)$")
    policy_text: str | None = Field(default=None, max_length=2000)

    @field_validator("slot_step_min")
    @classmethod
    def _step(cls, v):
        if v is not None and v not in (5, 10, 15, 20, 30, 60):
            raise ValueError("Slot step must be 5, 10, 15, 20, 30 or 60 minutes")
        return v


@router.get("/settings")
async def get_settings_(s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    b = await (await conn.execute("select * from business where id=%s", (s.business_id,))).fetchone()
    hol = await (await conn.execute("select id, date, reason from business_holiday where business_id=%s order by date", (s.business_id,))).fetchall()
    keys = SettingsPatch.model_fields
    return {"settings": {k: b[k] for k in keys}, "slug": b["slug"],
            "holidays": [{"id": str(h["id"]), "date": h["date"].isoformat(), "reason": h["reason"]} for h in hol]}


@router.patch("/settings")
async def patch_settings(b: SettingsPatch, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    sets, vals = _sets(b, set(SettingsPatch.model_fields))
    await conn.execute(f"update business set {sets} where id=%s", (*vals, s.business_id))
    await conn.commit()
    return {"ok": True}


class HolidayIn(BaseModel):
    date: date
    reason: str = Field(default="", max_length=120)


@router.post("/holidays", status_code=201)
async def add_holiday(b: HolidayIn, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    r = await (await conn.execute(
        "insert into business_holiday (business_id,date,reason) values (%s,%s,%s) on conflict (business_id,date) do update set reason=excluded.reason returning id",
        (s.business_id, b.date, b.reason))).fetchone()
    await conn.commit()
    return {"id": str(r["id"])}


@router.delete("/holidays/{hid}")
async def delete_holiday(hid: UUID, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    r = await (await conn.execute("delete from business_holiday where id=%s and business_id=%s returning id", (hid, s.business_id))).fetchone()
    await conn.commit()
    if not r:
        raise HTTPException(404, "Holiday not found")
    return {"deleted": True}

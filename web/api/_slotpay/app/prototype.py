"""Prototype mode: one-click access to every surface of the demo (admin login without typing a token).

DEMO ONLY. Enabled by PROTOTYPE_MODE=true. It mints a short-lived staff JWT for the seeded owner or front-desk
user, which only works when the API verifies tokens with SUPABASE_JWT_SECRET (HS256). Never enable on a real salon.
"""
import time
from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .config import get_settings

router = APIRouter(prefix="/prototype")


def _enabled() -> None:
    if not get_settings().prototype_mode:
        raise HTTPException(404, "Prototype mode is off")


@router.get("/status")
async def status():
    s = get_settings()
    return {
        "enabled": s.prototype_mode, "can_login": bool(s.prototype_mode and s.supabase_jwt_secret),
        "payments": "razorpay" if s.razorpay_key_id else ("simulated" if s.prototype_mode else "off"),
        "whatsapp": s.whatsapp_mode, "reminder_demo_delay_sec": s.reminder_demo_delay_sec,
        "whatsapp_live_configured": bool(s.whatsapp_phone_number_id and s.whatsapp_access_token),
    }


class LoginIn(BaseModel):
    role: str = Field(default="owner", pattern="^(owner|front_desk)$")


@router.post("/login", dependencies=[Depends(_enabled)])
async def login(body: LoginIn, conn=Depends(db.get_conn)):
    s = get_settings()
    if not s.supabase_jwt_secret:
        raise HTTPException(501, "Prototype login needs SUPABASE_JWT_SECRET (HS256 tokens)")
    row = await (await conn.execute("select id, email, role from staff_user where role=%s order by created_at limit 1", (body.role,))).fetchone()
    if not row:
        raise HTTPException(404, "No demo staff user. Reset the demo first.")
    ttl = int(timedelta(hours=8).total_seconds())
    token = jwt.encode({"sub": str(row["id"]), "aud": "authenticated", "exp": int(time.time()) + ttl}, s.supabase_jwt_secret, "HS256")
    return {"token": token, "role": row["role"], "email": row["email"], "expires_in": ttl}


@router.get("/summary", dependencies=[Depends(_enabled)])
async def summary(conn=Depends(db.get_conn)):
    q = lambda sql: conn.execute(sql)  # noqa: E731
    b = await (await q("select id, slug, name from business order by created_at desc limit 1")).fetchone()
    if not b:
        return {"ready": False}
    one = lambda r: r  # noqa: E731
    n = {}
    for key, sql in {
        "services": "select count(*) n from service where is_active",
        "stylists": "select count(*) n from staff where is_active",
        "customers": "select count(*) n from customer",
        "upcoming_bookings": "select count(*) n from booking where status in ('confirmed','held') and lower(time_range) > now()",
        "completed_bookings": "select count(*) n from booking where status='completed'",
    }.items():
        n[key] = (await (await q(sql)).fetchone())["n"]
    latest = await (await q(
        """select c.phone_e164 from audit_event a join booking bk on bk.id=a.booking_id join customer c on c.id=bk.customer_id
           where a.type in ('slot_held','booking_created_by_staff') order by a.created_at desc limit 1""")).fetchone()
    return {"ready": True, "slug": b["slug"], "name": b["name"], "counts": n, "latest_phone": latest["phone_e164"][-10:] if latest else None}

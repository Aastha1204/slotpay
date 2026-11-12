"""Idempotent job tick: expire stale holds. (Reminders are added in M5.)"""
import asyncio
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from . import db, messaging, realtime
from .config import get_settings
from .tz import zone

log = logging.getLogger("slotpay.jobs")
router = APIRouter()


async def expire_stale_holds(conn) -> int:
    rows = await (await conn.execute(
        """update booking set status='expired' where status='held' and hold_expires_at < now()
           returning id, business_id, staff_id, time_range, block_range""")).fetchall()
    for r in rows:
        await conn.execute("insert into audit_event (business_id,booking_id,type) values (%s,%s,'hold_expired')",
                           (r["business_id"], r["id"]))
    await conn.commit()
    for r in rows:
        tz = (await (await conn.execute("select timezone from business where id=%s", (r["business_id"],))).fetchone())["timezone"]
        lo = r["time_range"].lower
        await realtime.broadcast(realtime.slots_topic(r["business_id"], lo.astimezone(zone(tz)).date()), "slot_released",
                                 {"event": "slot_released", "staff_id": str(r["staff_id"]), "start": lo.isoformat(),
                                  "end": r["block_range"].upper.isoformat()})
    return len(rows)


async def tick(provider=None) -> dict:
    async with db.connection() as conn:
        expired = await expire_stale_holds(conn)
        sent = await messaging.send_due(conn, provider or messaging.get_provider())
        return {"expired_holds": expired, "messages_sent": sent}


@router.post("/internal/jobs/tick")
async def tick_endpoint(x_jobs_secret: str | None = Header(default=None), provider=Depends(messaging.get_provider)):
    secret = get_settings().jobs_secret
    if not secret or not hmac.compare_digest(x_jobs_secret or "", secret):
        raise HTTPException(401, "Unauthorized")
    return await tick(provider)


async def scheduler_loop(interval: int = 60) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await tick()
        except Exception:
            log.exception("job tick failed")

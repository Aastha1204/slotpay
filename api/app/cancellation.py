"""Cancellation policy + cancel flow (shared by WhatsApp 'Cancel', and the admin in M6)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import messaging, realtime
from .payments import audit, issue_refund
from .tz import zone

log = logging.getLogger("slotpay.cancel")


def refund_eligible(start: datetime, now: datetime, cutoff_hours: int) -> bool:
    """Free cancellation at least `cutoff_hours` before the start; later cancellations forfeit the advance."""
    return start - now >= timedelta(hours=cutoff_hours)


async def cancel_booking(conn, rzp, booking_id, *, reason: str, actor: str, force_refund: bool = False,
                         now: datetime | None = None, provider=None) -> dict:
    """Cancels a held/confirmed booking, refunds if the policy allows (or `force_refund`), queues the
    'cancelled' message and frees the slot. Idempotent: an already-cancelled booking returns ok=False."""
    now = now or datetime.now(timezone.utc)
    b = await (await conn.execute(
        """select b.*, bz.cancellation_cutoff_hours cutoff, bz.timezone tzname from booking b
           join business bz on bz.id=b.business_id where b.id=%s for update of b""", (booking_id,))).fetchone()
    if not b or b["status"] not in ("held", "confirmed"):
        await conn.commit()
        return {"ok": False, "reason": "not_cancellable", "status": b["status"] if b else None}
    start = b["time_range"].lower
    eligible = refund_eligible(start, now, b["cutoff"]) or force_refund
    await conn.execute(
        "update booking set status='cancelled', cancelled_at=now(), cancel_reason=%s, hold_expires_at=null where id=%s",
        (reason, booking_id))
    await messaging.skip_pending(conn, booking_id)
    await audit(conn, b["business_id"], booking_id, "booking_cancelled",
                {"actor": actor, "reason": reason, "refund_eligible": eligible, "forced": force_refund})
    pay = await (await conn.execute(
        "select id, status, amount_paise, refunded_paise from payment where booking_id=%s and status in "
        "('captured','partially_refunded') order by created_at desc limit 1", (booking_id,))).fetchone()
    await conn.commit()

    refunded = 0
    if pay and eligible:
        try:
            r = await issue_refund(conn, rzp, payment_row_id=pay["id"], amount_paise=pay["amount_paise"] - pay["refunded_paise"],
                                   reason=f"cancelled_by_{actor}")
            refunded = r.get("amount_paise", 0)
        except Exception:  # noqa: BLE001 - surfaced in audit; owner can refund from admin
            log.exception("refund on cancel failed")
            await audit(conn, b["business_id"], booking_id, "refund_failed_on_cancel", {})
            await conn.commit()
    await messaging.queue_message(conn, booking_id, "cancelled")
    await conn.commit()
    if provider is not None:  # send now; otherwise the job tick delivers it within a minute
        try:
            await messaging.send_due(conn, provider, booking_id=booking_id)
        except Exception:  # noqa: BLE001
            log.exception("immediate cancel message failed; tick will retry")

    lo = start
    await realtime.broadcast(realtime.slots_topic(b["business_id"], lo.astimezone(zone(b["tzname"])).date()),
                             "slot_released", {"event": "slot_released", "staff_id": str(b["staff_id"]),
                                               "start": lo.isoformat(), "end": b["block_range"].upper.isoformat()})
    await realtime.broadcast(realtime.admin_topic(b["business_id"]), "booking_cancelled",
                             {"event": "booking_cancelled", "booking_id": str(booking_id), "staff_id": str(b["staff_id"]),
                              "start": lo.isoformat(), "end": b["time_range"].upper.isoformat()})
    return {"ok": True, "refund_eligible": eligible, "refunded_paise": refunded, "had_payment": bool(pay)}

"""Payment domain logic: advance rules, the single idempotent confirm_booking(), refunds."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import messaging, realtime
from .db import is_exclusion_violation
from .tz import zone

log = logging.getLogger("slotpay.payments")


def compute_advance(*, price_paise: int, advance_type: str, advance_value: int, skip_advance: bool,
                    advance_applies: str, day: date, is_holiday: bool) -> int:
    """Advance in paise. Zero if skipped by customer, service rule, or the business only charges on weekends/holidays."""
    if skip_advance or advance_type == "none":
        return 0
    if advance_applies == "weekends_and_holidays" and not (day.weekday() >= 5 or is_holiday):
        return 0
    if advance_type == "fixed":
        amount = advance_value
    else:  # percent, rounded to whole rupees
        amount = (price_paise * advance_value // 100 + 50) // 100 * 100
    return min(amount, price_paise)


async def audit(conn, business_id, booking_id, type_: str, data: dict | None = None) -> None:
    await conn.execute("insert into audit_event (business_id,booking_id,type,data) values (%s,%s,%s,%s)",
                       (business_id, booking_id, type_, Jsonb(data or {})))


async def confirm_booking(conn, *, order_id: str, payment_id: str, method: str | None, amount_paise: int,
                          raw: dict | None = None) -> dict:
    """Idempotent. Used by BOTH /payments/verify and the webhook.

    Returns {"outcome": confirmed | already | slot_lost | unknown_order, ...}.
    The caller must commit, and on slot_lost call issue_refund() after the commit.
    """
    pay = await (await conn.execute("select * from payment where razorpay_order_id=%s for update", (order_id,))).fetchone()
    if not pay:
        return {"outcome": "unknown_order"}
    b = await (await conn.execute("select * from booking where id=%s for update", (pay["booking_id"],))).fetchone()
    base = {"booking_id": b["id"], "business_id": b["business_id"], "payment_row_id": pay["id"],
            "amount_paise": amount_paise, "staff_id": b["staff_id"], "time_range": b["time_range"],
            "block_range": b["block_range"]}
    if pay["status"] in ("captured", "refunded", "partially_refunded"):
        return {"outcome": "already", **base, "status": b["status"]}

    await conn.execute(
        "update payment set status='captured', razorpay_payment_id=%s, method=%s, raw=%s where id=%s",
        (payment_id, method, Jsonb(raw or {}), pay["id"]))

    if b["status"] == "held":
        await conn.execute(
            "update booking set status='confirmed', hold_expires_at=null, advance_paid_paise=%s where id=%s",
            (amount_paise, b["id"]))
    elif b["status"] == "confirmed":
        pass
    elif b["status"] == "expired":
        # Late capture: let the exclusion constraint decide whether the slot is still ours.
        try:
            async with conn.transaction():
                await conn.execute(
                    "update booking set status='confirmed', hold_expires_at=null, advance_paid_paise=%s where id=%s",
                    (amount_paise, b["id"]))
        except psycopg.Error as e:
            if not is_exclusion_violation(e):
                raise
            await audit(conn, b["business_id"], b["id"], "late_capture_slot_lost", {"payment_id": payment_id})
            return {"outcome": "slot_lost", **base}
        await audit(conn, b["business_id"], b["id"], "late_capture_reconfirmed", {"payment_id": payment_id})
    else:  # cancelled / completed etc: money arrived for a booking that can't proceed
        return {"outcome": "slot_lost", **base}

    await audit(conn, b["business_id"], b["id"], "booking_confirmed", {"payment_id": payment_id, "amount_paise": amount_paise})
    await messaging.queue_confirmation_messages(conn, b["id"], b["time_range"].lower)
    return {"outcome": "confirmed", **base}


async def after_confirm_broadcast(conn, result: dict) -> None:
    """Best-effort realtime fan-out; no personal data in payloads."""
    if result.get("outcome") != "confirmed":
        return
    tz_name = (await (await conn.execute("select timezone from business where id=%s", (result["business_id"],))).fetchone())["timezone"]
    lo = result["time_range"].lower
    await realtime.broadcast(realtime.admin_topic(result["business_id"]), "booking_confirmed",
                             {"event": "booking_confirmed", "booking_id": str(result["booking_id"]),
                              "staff_id": str(result["staff_id"]), "start": lo.isoformat(),
                              "end": result["time_range"].upper.isoformat()})
    await realtime.broadcast(realtime.slots_topic(result["business_id"], lo.astimezone(zone(tz_name)).date()),
                             "slot_held", {"event": "slot_held", "staff_id": str(result["staff_id"]),
                                           "start": lo.isoformat(), "end": result["block_range"].upper.isoformat()})


async def issue_refund(conn, rzp, *, payment_row_id: UUID, amount_paise: int, reason: str) -> dict:
    """Call Razorpay Refunds API, then record the refund and update the payment. Commits itself."""
    pay = await (await conn.execute("select * from payment where id=%s", (payment_row_id,))).fetchone()
    if not pay or not pay["razorpay_payment_id"]:
        raise ValueError("payment has no captured razorpay payment")
    remaining = pay["amount_paise"] - pay["refunded_paise"]
    amount = min(amount_paise, remaining)
    if amount <= 0:
        return {"refunded": False}
    await conn.commit()  # never hold a transaction open across the HTTP call
    r = await rzp.refund(pay["razorpay_payment_id"], amount, {"booking_id": str(pay["booking_id"]), "reason": reason})
    new_total = pay["refunded_paise"] + amount
    status = "refunded" if new_total >= pay["amount_paise"] else "partially_refunded"
    await conn.execute(
        """insert into refund (payment_id,razorpay_refund_id,amount_paise,status,reason) values (%s,%s,%s,%s,%s)
           on conflict (razorpay_refund_id) do nothing""",
        (pay["id"], r["id"], amount, r.get("status", "pending"), reason))
    await conn.execute("update payment set refunded_paise=%s, status=%s where id=%s", (new_total, status, pay["id"]))
    b = await (await conn.execute("select business_id from booking where id=%s", (pay["booking_id"],))).fetchone()
    await audit(conn, b["business_id"], pay["booking_id"], "refund_initiated", {"amount_paise": amount, "reason": reason})
    await conn.commit()
    return {"refunded": True, "refund_id": r["id"], "amount_paise": amount}

"""Messaging: provider interface (WhatsApp Cloud + simulator), templates, scheduling, retrying sender."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx
from psycopg.types.json import Jsonb

from .config import get_settings
from .tz import zone

log = logging.getLogger("slotpay.messaging")
GRAPH = "https://graph.facebook.com/v21.0"

# Template bodies mirror the templates submitted in WhatsApp Manager (used by the simulator).
BODIES = {
    "confirmed": "Hi {1}, your {2} with {3} at {4} is confirmed for {5}. Advance paid: ₹{6}. "
                 "Balance is payable at the salon. Booking ID: {7}. See you soon!",
    "reminder": "Hi {1}, a reminder that your {2} at {3} is {4} at {5}. Free cancellation is available until {6}. "
                "Tap a button below if your plans change.",
    "cancelled": "Hi {1}, your booking {2} has been cancelled. {3} Thank you for letting us know.",
}


class Provider(Protocol):
    async def send_template(self, to_e164: str, name: str, params: list[str], buttons: list[dict],
                            url_suffix: str | None) -> str: ...
    async def send_text(self, to_e164: str, text: str) -> str: ...


class WhatsAppCloudProvider:
    """Meta WhatsApp Cloud API. Business-initiated messages MUST be approved templates."""

    def __init__(self):
        s = get_settings()
        self.url = f"{GRAPH}/{s.whatsapp_phone_number_id}/messages"
        self.headers = {"Authorization": f"Bearer {s.whatsapp_access_token}"}

    async def _post(self, payload: dict) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(self.url, headers=self.headers, json={"messaging_product": "whatsapp", **payload})
        if r.status_code >= 400:
            raise RuntimeError(f"whatsapp {r.status_code}: {r.text[:200]}")
        return r.json()["messages"][0]["id"]

    async def send_template(self, to_e164, name, params, buttons, url_suffix):
        comps: list[dict] = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
        for i, b in enumerate(buttons):
            comps.append({"type": "button", "sub_type": "quick_reply", "index": str(i),
                          "parameters": [{"type": "payload", "payload": b["payload"]}]})
        if url_suffix:
            comps.append({"type": "button", "sub_type": "url", "index": "0",
                          "parameters": [{"type": "text", "text": url_suffix}]})
        return await self._post({"to": to_e164.lstrip("+"), "type": "template",
                                 "template": {"name": name, "language": {"code": "en"}, "components": comps}})

    async def send_text(self, to_e164, text):
        return await self._post({"to": to_e164.lstrip("+"), "type": "text", "text": {"body": text}})


def get_provider() -> Provider:
    return WhatsAppCloudProvider()


def template_name(key: str) -> str:
    s = get_settings()
    return {"confirmed": s.whatsapp_template_confirmed, "reminder": s.whatsapp_template_reminder,
            "cancelled": s.whatsapp_template_cancelled}[key]


def fmt_dt(dt: datetime, tz) -> str:
    d = dt.astimezone(tz)
    h = d.hour % 12 or 12
    return f"{d:%a}, {d.day} {d:%b} at {h}:{d:%M} {'AM' if d.hour < 12 else 'PM'}"


def fmt_time(dt: datetime, tz) -> str:
    d = dt.astimezone(tz)
    return f"{d.hour % 12 or 12}:{d:%M} {'AM' if d.hour < 12 else 'PM'}"


def rupees(paise: int) -> str:
    return f"{paise // 100:,}"


async def booking_ctx(conn, booking_id) -> dict | None:
    return await (await conn.execute(
        """select b.id, b.status, b.time_range, b.advance_paid_paise, b.public_token, b.business_id,
                  s.name service, st.name staff, bz.name salon, bz.slug, bz.timezone,
                  bz.cancellation_cutoff_hours cutoff, c.id customer_id, c.name cname, c.phone_e164, c.whatsapp_opt_in
           from booking b join service s on s.id=b.service_id join staff st on st.id=b.staff_id
           join business bz on bz.id=b.business_id join customer c on c.id=b.customer_id where b.id=%s""",
        (booking_id,))).fetchone()


async def refund_line(conn, booking_id, kind: str) -> str:
    p = await (await conn.execute("select amount_paise, refunded_paise, status from payment where booking_id=%s "
                                  "order by created_at desc limit 1", (booking_id,))).fetchone()
    if kind == "refund":
        return (f"Sorry, that slot was taken before your payment completed. A full refund of "
                f"₹{rupees(p['refunded_paise'] or p['amount_paise'])} has been initiated." if p else "")
    if not p or p["status"] == "created" or p["status"] == "failed":
        return "No payment was taken."
    if p["refunded_paise"] > 0:
        return f"Your ₹{rupees(p['refunded_paise'])} advance refund has been initiated and reaches you in 5-7 working days."
    return "As this was within the free-cancellation window, the advance is non-refundable."


def build_message(kind: str, ctx: dict, line: str = "") -> tuple[str, list[str], list[dict], str | None]:
    """Returns (template_key, params, buttons, url_suffix)."""
    tz = zone(ctx["timezone"])
    first = ctx["cname"].split()[0]
    short = ctx["id"].hex[:8].upper()
    start = ctx["time_range"].lower
    if kind == "confirmation":
        return ("confirmed", [first, ctx["service"], ctx["staff"], ctx["salon"], fmt_dt(start, tz),
                              rupees(ctx["advance_paid_paise"]), short], [],
                f"{ctx['slug']}/confirm/{ctx['public_token']}")
    if kind in ("remind_24h", "remind_2h"):
        when = "tomorrow" if kind == "remind_24h" else "in 2 hours"
        deadline = fmt_dt(start - timedelta(hours=ctx["cutoff"]), tz)
        return ("reminder", [first, ctx["service"], ctx["salon"], when, fmt_time(start, tz), deadline], [
            {"text": "Reschedule", "payload": f"reschedule:{ctx['id']}"},
            {"text": "Cancel", "payload": f"cancel:{ctx['id']}"}], None)
    return ("cancelled", [first, short, line], [], None)  # cancelled / refund


def render(key: str, params: list[str]) -> str:
    out = BODIES[key]
    for i, p in enumerate(params, 1):
        out = out.replace("{%d}" % i, p)
    return out


async def log_msg(conn, *, booking_id, customer_id, direction, channel, template=None, body="", buttons=None,
                  provider_id=None, status="sent") -> None:
    await conn.execute(
        """insert into message_log (booking_id,customer_id,direction,channel,template,body,buttons,provider_message_id,status)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (booking_id, customer_id, direction, channel, template, body, Jsonb(buttons) if buttons else None,
         provider_id, status))


async def deliver_template(conn, provider: Provider, ctx: dict, kind: str) -> None:
    """Send one templated message per WHATSAPP_MODE. Raises if the only required channel failed."""
    mode = get_settings().whatsapp_mode
    line = await refund_line(conn, ctx["id"], kind) if kind in ("cancelled", "refund") else ""
    key, params, buttons, suffix = build_message(kind, ctx, line)
    body = render(key, params)
    name = template_name(key)
    live_ok, live_err = None, None
    if mode in ("live", "both") and ctx["whatsapp_opt_in"]:
        try:
            mid = await provider.send_template(ctx["phone_e164"], name, params, buttons, suffix)
            await log_msg(conn, booking_id=ctx["id"], customer_id=ctx["customer_id"], direction="out", channel="whatsapp",
                          template=name, body=body, buttons=buttons, provider_id=mid)
            live_ok = True
        except Exception as e:  # noqa: BLE001
            live_ok, live_err = False, str(e)
            log.warning("live whatsapp send failed: %s", e)
    if mode in ("simulator", "both"):
        await log_msg(conn, booking_id=ctx["id"], customer_id=ctx["customer_id"], direction="out", channel="simulator",
                      template=name, body=body, buttons=buttons)
    if mode == "live" and live_ok is False:
        raise RuntimeError(live_err)
    await conn.execute(
        "insert into audit_event (business_id,booking_id,type,data) values (%s,%s,'whatsapp_sent',%s)",
        (ctx["business_id"], ctx["id"], Jsonb({"kind": kind, "template": name, "live": bool(live_ok)})))
    if kind == "confirmation":  # timeline: confirmed -> WhatsApp sent -> reminders scheduled for ...
        st = ctx["time_range"].lower
        await conn.execute(
            "insert into audit_event (business_id,booking_id,type,data) values (%s,%s,'messages_scheduled',%s)",
            (ctx["business_id"], ctx["id"], Jsonb({"remind_24h": (st - timedelta(hours=24)).isoformat(),
                                                   "remind_2h": (st - timedelta(hours=2)).isoformat()})))


async def deliver_text(conn, provider: Provider, ctx: dict, text: str) -> None:
    """Free-form reply (allowed: the customer just messaged us)."""
    mode = get_settings().whatsapp_mode
    if mode in ("live", "both") and ctx["whatsapp_opt_in"]:
        try:
            mid = await provider.send_text(ctx["phone_e164"], text)
            await log_msg(conn, booking_id=ctx["id"], customer_id=ctx["customer_id"], direction="out",
                          channel="whatsapp", body=text, provider_id=mid)
        except Exception:  # noqa: BLE001
            log.warning("live whatsapp text failed", exc_info=True)
    if mode in ("simulator", "both"):
        await log_msg(conn, booking_id=ctx["id"], customer_id=ctx["customer_id"], direction="out",
                      channel="simulator", body=text)


async def queue_confirmation_messages(conn, booking_id, start: datetime, now: datetime | None = None) -> None:
    """confirmation now; remind_24h / remind_2h at start-24h / start-2h (already-past ones are marked skipped)."""
    now = now or datetime.now(timezone.utc)
    rows = [("confirmation", now, "pending")]
    demo = get_settings().reminder_demo_delay_sec
    if demo > 0:  # prototype: show the reminders arriving within seconds instead of 24 h / 2 h before
        rows += [("remind_24h", now + timedelta(seconds=demo), "pending"), ("remind_2h", now + timedelta(seconds=2 * demo), "pending")]
    else:
        for kind, hrs in (("remind_24h", 24), ("remind_2h", 2)):
            at = start - timedelta(hours=hrs)
            rows.append((kind, at, "pending" if at > now else "skipped"))
    for kind, at, st in rows:
        await conn.execute(
            "insert into scheduled_message (booking_id,kind,send_at,status) values (%s,%s,%s,%s) "
            "on conflict (booking_id, kind) do nothing", (booking_id, kind, at, st))


async def queue_message(conn, booking_id, kind: str) -> None:
    await conn.execute(
        "insert into scheduled_message (booking_id,kind,send_at,status) values (%s,%s,now(),'pending') "
        "on conflict (booking_id, kind) do update set status='pending', send_at=now(), attempts=0", (booking_id, kind))


async def skip_pending(conn, booking_id, kinds=("remind_24h", "remind_2h", "confirmation")) -> None:
    await conn.execute("update scheduled_message set status='skipped' where booking_id=%s and status='pending' "
                       "and kind = any(%s)", (booking_id, list(kinds)))


async def send_due(conn, provider: Provider, booking_id=None, max_attempts: int = 3) -> int:
    """Send due messages. Claims each row atomically (attempts+1, pushes send_at 5 min) so no HTTP call
    happens inside an open row lock; retries up to max_attempts. Idempotent across overlapping ticks."""
    await conn.commit()
    sent = 0
    ids = [r["id"] for r in await (await conn.execute(
        "select id from scheduled_message where status='pending' and send_at <= now() "
        "and (%s::uuid is null or booking_id=%s::uuid) order by send_at limit 50", (booking_id, booking_id))).fetchall()]
    await conn.commit()
    for sid in ids:
        row = await (await conn.execute(
            """update scheduled_message set attempts=attempts+1, send_at=now()+interval '5 minutes'
               where id=%s and status='pending' and send_at <= now() returning *""", (sid,))).fetchone()
        await conn.commit()
        if not row:
            continue  # someone else claimed it
        ctx = await booking_ctx(conn, row["booking_id"])
        needs_confirmed = row["kind"] in ("confirmation", "remind_24h", "remind_2h")
        if not ctx or (needs_confirmed and ctx["status"] != "confirmed"):
            await conn.execute("update scheduled_message set status='skipped' where id=%s", (sid,))
            await conn.commit()
            continue
        try:
            await deliver_template(conn, provider, ctx, row["kind"])
            await conn.execute("update scheduled_message set status='sent', last_error=null where id=%s", (sid,))
            sent += 1
        except Exception as e:  # noqa: BLE001
            await conn.rollback()
            st = "failed" if row["attempts"] >= max_attempts else "pending"
            await conn.execute("update scheduled_message set status=%s, last_error=%s where id=%s", (st, str(e)[:300], sid))
        await conn.commit()
    return sent


async def booking_ctx_by_token(conn, token: str) -> dict | None:
    row = await (await conn.execute("select id from booking where public_token=%s", (token,))).fetchone()
    return await booking_ctx(conn, row["id"]) if row else None

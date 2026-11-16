"""Supabase Realtime Broadcast (REST). Payloads never carry personal data. No-op if unconfigured."""
import logging

import httpx

from .config import get_settings

log = logging.getLogger("slotpay.realtime")


async def broadcast(topic: str, event: str, payload: dict) -> None:
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_role_key):
        return
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            await c.post(
                f"{s.supabase_url}/realtime/v1/api/broadcast",
                headers={"apikey": s.supabase_service_role_key, "Authorization": f"Bearer {s.supabase_service_role_key}"},
                json={"messages": [{"topic": topic, "event": event, "payload": payload, "private": False}]},
            )
    except Exception:  # broadcast is best-effort; clients also poll every 10s
        log.warning("realtime broadcast failed", exc_info=True)


def slots_topic(business_id, day) -> str:
    return f"slots:{business_id}:{day}"


def admin_topic(business_id) -> str:
    return f"admin:{business_id}"

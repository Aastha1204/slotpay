"""Owner-only reports + CSV export."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from . import db
from .auth import Staff, require_role
from .availability import break_intervals, working_windows
from .tz import day_bounds, zone

router = APIRouter(prefix="/admin/reports")
owner = require_role("owner")
LIVE = ("confirmed", "completed", "no_show")


def _rate(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


async def build(conn, staff: Staff, start: date | None, end: date | None) -> dict:
    biz = await (await conn.execute("select id, timezone from business where id=%s", (staff.business_id,))).fetchone()
    tz = zone(biz["timezone"])
    today = datetime.now(tz).date()
    end = end or today
    start = start or end - timedelta(days=29)
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "Choose a date range of at most one year")
    lo, _ = day_bounds(start, tz)
    _, hi = day_bounds(end, tz)
    bid = biz["id"]

    by_status = {r["status"]: r for r in await (await conn.execute(
        """select status, count(*) n, coalesce(sum(price_paise),0) rev from booking
           where business_id=%s and lower(time_range) >= %s and lower(time_range) < %s group by status""", (bid, lo, hi))).fetchall()}
    n = lambda st: by_status.get(st, {}).get("n", 0)  # noqa: E731
    booked = sum(n(s) for s in LIVE)
    pay = await (await conn.execute(
        """select coalesce(sum(p.amount_paise),0) collected, coalesce(sum(p.refunded_paise),0) refunded
           from payment p join booking b on b.id=p.booking_id where b.business_id=%s
             and p.status in ('captured','refunded','partially_refunded')
             and lower(b.time_range) >= %s and lower(b.time_range) < %s""", (bid, lo, hi))).fetchone()
    kpis = {
        "bookings": booked, "completed": n("completed"), "no_shows": n("no_show"), "cancelled": n("cancelled"),
        "online_advance_collected_paise": int(pay["collected"]), "refunded_paise": int(pay["refunded"]),
        "net_advance_paise": int(pay["collected"] - pay["refunded"]),
        "no_show_rate": _rate(n("no_show"), n("completed") + n("no_show")),
        "cancellation_rate": _rate(n("cancelled"), booked + n("cancelled")),
        "revenue_paise": int(by_status.get("completed", {}).get("rev", 0)),
    }
    services = await (await conn.execute(
        """select s.name, s.category, count(*) n, coalesce(sum(b.price_paise),0) rev from booking b join service s on s.id=b.service_id
           where b.business_id=%s and b.status='completed' and lower(b.time_range) >= %s and lower(b.time_range) < %s
           group by s.name, s.category order by rev desc, n desc""", (bid, lo, hi))).fetchall()
    stf = await (await conn.execute(
        """select st.id, st.name, st.shift_template,
                  coalesce(sum(extract(epoch from (upper(b.time_range)-lower(b.time_range)))/60) filter (where b.status in ('confirmed','completed','no_show')),0) booked_min,
                  coalesce(sum(b.price_paise) filter (where b.status='completed'),0) rev,
                  count(*) filter (where b.status='completed') done
           from staff st left join booking b on b.staff_id=st.id and lower(b.time_range) >= %s and lower(b.time_range) < %s
           where st.business_id=%s and st.is_active group by st.id, st.name, st.shift_template order by st.name""", (lo, hi, bid))).fetchall()
    hol = {r["date"] for r in await (await conn.execute("select date from business_holiday where business_id=%s", (bid,))).fetchall()}
    staff_out = []
    for s in stf:
        shift = 0.0
        d = start
        while d <= end:
            if d not in hol:
                win = working_windows(s["shift_template"], d, tz)
                brk = break_intervals(s["shift_template"], d, tz)
                shift += sum((b - a).total_seconds() / 60 for a, b in win) - sum((b - a).total_seconds() / 60 for a, b in brk if win)
            d += timedelta(days=1)
        avail = max(shift, 0.0)  # utilisation = booked minutes / shift minutes (holidays excluded)
        booked_min = float(s["booked_min"])
        staff_out.append({"name": s["name"], "booked_min": round(booked_min), "shift_min": round(avail),
                          "utilisation": _rate(booked_min, avail), "revenue_paise": int(s["rev"]), "completed": s["done"]})
    daily = await (await conn.execute(
        """select to_char(lower(time_range) at time zone %s, 'YYYY-MM-DD') d, count(*) filter (where status in ('confirmed','completed','no_show')) n,
                  count(*) filter (where status='cancelled') c
           from booking where business_id=%s and lower(time_range) >= %s and lower(time_range) < %s group by 1 order by 1""",
        (biz["timezone"], bid, lo, hi))).fetchall()
    return {
        "from": start.isoformat(), "to": end.isoformat(), "kpis": kpis,
        "services": [{"name": r["name"], "category": r["category"], "count": r["n"], "revenue_paise": int(r["rev"])} for r in services],
        "staff": staff_out,
        "daily": [{"date": r["d"], "bookings": r["n"], "cancelled": r["c"]} for r in daily],
    }


@router.get("")
async def report(from_: date | None = Query(default=None, alias="from"), to: date | None = None,
                 s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    return await build(conn, s, from_, to)


@router.get("/export")
async def export(table: str = Query(pattern="^(services|staff|daily|summary)$"), from_: date | None = Query(default=None, alias="from"),
                 to: date | None = None, s: Staff = Depends(owner), conn=Depends(db.get_conn)):
    r = await build(conn, s, from_, to)
    out = io.StringIO()
    w = csv.writer(out)
    if table == "services":
        w.writerow(["service", "category", "completed_bookings", "revenue_inr"])
        for x in r["services"]:
            w.writerow([x["name"], x["category"], x["count"], x["revenue_paise"] / 100])
    elif table == "staff":
        w.writerow(["stylist", "booked_minutes", "shift_minutes", "utilisation_pct", "completed", "revenue_inr"])
        for x in r["staff"]:
            w.writerow([x["name"], x["booked_min"], x["shift_min"], x["utilisation"], x["completed"], x["revenue_paise"] / 100])
    elif table == "daily":
        w.writerow(["date", "bookings", "cancelled"])
        for x in r["daily"]:
            w.writerow([x["date"], x["bookings"], x["cancelled"]])
    else:
        w.writerow(["metric", "value"])
        for k, v in r["kpis"].items():
            w.writerow([k, v / 100 if k.endswith("_paise") else v])
    name = f"slotpay-{table}-{r['from']}-to-{r['to']}.csv"
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})

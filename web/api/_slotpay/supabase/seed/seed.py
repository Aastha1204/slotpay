"""Idempotent demo seed for Glow Studio Salon & Spa (fictional).

Usage:  python supabase/seed/seed.py          (reads DATABASE_URL, optional SUPABASE_URL +
                                                SUPABASE_SERVICE_ROLE_KEY to create Auth users)
Re-running wipes and rebuilds the demo business, relative to today's date.

Phone numbers: +91 99999 000NN (NN = 01..40) -- obviously fake, one documented test range.
"""
from __future__ import annotations

import os
import random
import secrets
import sys
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb
from psycopg.types.range import Range

IST = ZoneInfo("Asia/Kolkata")
SLUG = "glow-studio"
DEMO_PASSWORD = "GlowDemo#2026"  # demo only
OWNER_EMAIL = "owner@glowstudio.demo"
FRONT_EMAIL = "frontdesk@glowstudio.demo"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# category, name, duration, price INR (GST-inclusive), buffer
SERVICES = [
    ("hair", "Men's Haircut", 30, 300, 5),
    ("hair", "Women's Haircut & Styling", 45, 700, 5),
    ("hair", "Blow-dry", 30, 500, 5),
    ("hair", "Hair Spa", 60, 1200, 10),
    ("hair", "Root Touch-up", 60, 1400, 10),
    ("hair", "Global Hair Colour", 120, 2800, 15),
    ("hair", "Keratin Smoothening", 150, 3200, 15),
    ("hair", "Bridal Hair & Makeup Trial", 120, 3500, 15),
    ("skin", "Clean-up", 40, 600, 5),
    ("skin", "Classic Facial", 60, 1100, 10),
    ("skin", "D-Tan Facial", 60, 1400, 10),
    ("skin", "Hydra Glow Facial", 75, 2500, 10),
    ("nails", "Classic Manicure", 40, 500, 5),
    ("nails", "Classic Pedicure", 50, 700, 5),
    ("nails", "Gel Polish", 45, 900, 5),
    ("nails", "Nail Extensions with Art", 90, 1800, 10),
    ("spa", "Head & Shoulder Massage", 30, 700, 5),
    ("spa", "Swedish Full-body Massage", 60, 2000, 10),
]

# name, title, weekly off, lunch break, services
STAFF = [
    ("Neha", "Senior Stylist", "mon", ("13:00", "13:45"),
     ["Women's Haircut & Styling", "Blow-dry", "Hair Spa", "Root Touch-up", "Global Hair Colour",
      "Bridal Hair & Makeup Trial"]),
    ("Rohit", "Stylist", "tue", ("14:00", "14:45"),
     ["Men's Haircut", "Global Hair Colour", "Root Touch-up", "Keratin Smoothening"]),
    ("Sana", "Skin & Nail Specialist", "wed", ("13:30", "14:15"),
     ["Clean-up", "Classic Facial", "D-Tan Facial", "Classic Manicure", "Classic Pedicure", "Gel Polish",
      "Nail Extensions with Art"]),
    ("Meera", "Spa Therapist", "thu", ("14:30", "15:15"),
     ["Head & Shoulder Massage", "Swedish Full-body Massage", "Classic Facial", "D-Tan Facial",
      "Hydra Glow Facial", "Clean-up"]),
]

FIRST = ["Priya", "Anjali", "Sneha", "Kavya", "Ritika", "Pooja", "Neelam", "Divya", "Aarti", "Shruti",
         "Rahul", "Amit", "Vikram", "Sanjay", "Rohan", "Karan", "Nikhil", "Manish", "Deepak", "Arjun",
         "Isha", "Tanvi", "Mansi", "Payal", "Swati", "Ankita", "Komal", "Madhuri", "Rutuja", "Sayali",
         "Omkar", "Pranav", "Siddharth", "Yash", "Tejas", "Gauri", "Nupur", "Rekha", "Smita", "Varsha"]
LAST = ["Sharma", "Patil", "Joshi", "Kulkarni", "Deshmukh", "Shah", "Mehta", "Iyer", "Nair", "Gupta",
        "Singh", "Kapoor", "Jadhav", "More", "Pawar", "Chavan", "Naik", "Desai", "Bhat", "Rao"]


def advance_for(price_inr: int) -> tuple[str, int]:
    """Spec: INR100 under 800; INR200 for 800-1999; 20% from 2000."""
    if price_inr < 800:
        return "fixed", 100 * 100
    if price_inr < 2000:
        return "fixed", 200 * 100
    return "percent", 20


def advance_due_paise(price_paise: int, atype: str, avalue: int) -> int:
    if atype == "fixed":
        return min(avalue, price_paise)
    if atype == "percent":
        return (price_paise * avalue // 100 + 50) // 100 * 100  # whole rupees
    return 0


def at(d: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=IST)


def shift_template(off: str, lunch: tuple[str, str]) -> dict:
    t: dict = {d: ([] if d == off else [{"start": "10:00", "end": "21:00"}]) for d in DAYS}
    t["breaks"] = {d: [{"start": lunch[0], "end": lunch[1]}] for d in DAYS if d != off}
    return t


def upcoming_saturday(today: date) -> date:
    return today + timedelta(days=(5 - today.weekday()) % 7 or 7)


def create_auth_users(conn_users: list[tuple[str, str]]) -> dict[str, uuid.UUID]:
    """Create Supabase Auth users via admin API when configured; else deterministic UUIDs."""
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    ids: dict[str, uuid.UUID] = {}
    if url and key:
        import httpx
        h = {"apikey": key, "Authorization": f"Bearer {key}"}
        for email, _ in conn_users:
            r = httpx.post(f"{url}/auth/v1/admin/users", headers=h, timeout=20,
                           json={"email": email, "password": DEMO_PASSWORD, "email_confirm": True})
            if r.status_code in (200, 201):
                ids[email] = uuid.UUID(r.json()["id"])
            else:  # already exists -> look it up
                lst = httpx.get(f"{url}/auth/v1/admin/users?per_page=200", headers=h, timeout=20).json()
                for u in lst.get("users", []):
                    if u["email"] == email:
                        ids[email] = uuid.UUID(u["id"])
        return ids
    for email, _ in conn_users:
        ids[email] = uuid.uuid5(uuid.NAMESPACE_DNS, email)
    print("NOTE: Supabase Auth not configured; staff_user rows use placeholder ids "
          "(set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY and re-run to create real logins).")
    return ids


def seed(conn: psycopg.Connection, now: datetime | None = None, rng_seed: int = 42) -> dict:
    rng = random.Random(rng_seed)
    now = (now or datetime.now(IST)).astimezone(IST)
    today = now.date()
    cur = conn.cursor()

    # wipe previous demo business (cascade) -> idempotent
    cur.execute("delete from booking where business_id in (select id from business where slug = %s)", (SLUG,))
    cur.execute("delete from business where slug = %s", (SLUG,))

    cur.execute(
        """insert into business (slug,name,address,phone,email,maps_url,policy_text)
           values (%s,%s,%s,%s,%s,%s,%s) returning id""",
        (SLUG, "Glow Studio Salon & Spa",
         "Shop 4, Gokhale Road, Naupada, Thane West, Maharashtra 400602", "+91 99999 00000",
         "hello@glowstudio.demo", "https://maps.google.com/?q=Thane+West",
         "Free cancellation up to 4 hours before your appointment. Later cancellations forfeit the advance."),
    )
    biz = cur.fetchone()[0]

    # holidays: Diwali-ish day and one more upcoming date
    for d, reason in [(today + timedelta(days=20), "Festival holiday"), (today + timedelta(days=27), "Staff outing")]:
        cur.execute("insert into business_holiday (business_id,date,reason) values (%s,%s,%s)", (biz, d, reason))

    svc: dict[str, dict] = {}
    for i, (cat, name, dur, price, buf) in enumerate(SERVICES):
        atype, aval = advance_for(price)
        cur.execute(
            """insert into service (business_id,category,name,description,duration_min,price_paise,
                 advance_type,advance_value,buffer_min,sort_order) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
            (biz, cat, name, "", dur, price * 100, atype, aval, buf, i),
        )
        svc[name] = dict(id=cur.fetchone()[0], dur=dur, price=price * 100, buf=buf, atype=atype, aval=aval)

    staff: dict[str, dict] = {}
    for name, title, off, lunch, names in STAFF:
        st = shift_template(off, lunch)
        cur.execute(
            "insert into staff (business_id,name,title,shift_template) values (%s,%s,%s,%s) returning id",
            (biz, name, title, Jsonb(st)),
        )
        sid = cur.fetchone()[0]
        for n in names:
            cur.execute("insert into staff_service values (%s,%s)", (sid, svc[n]["id"]))
        staff[name] = dict(id=sid, tpl=st, services=names, busy=[])  # busy: list[(start,end)] block ranges

    # staff users
    users = [(OWNER_EMAIL, "owner"), (FRONT_EMAIL, "front_desk")]
    ids = create_auth_users(users)
    for email, role in users:
        cur.execute("insert into staff_user (id,business_id,email,role) values (%s,%s,%s,%s) "
                    "on conflict (id) do update set business_id=excluded.business_id, role=excluded.role",
                    (ids[email], biz, email, role))

    # customers
    customers = []
    for i in range(40):
        name = f"{FIRST[i]} {rng.choice(LAST)}"
        phone = f"+919999900{i + 1:03d}"
        cur.execute(
            """insert into customer (business_id,name,phone_e164,whatsapp_opt_in,consent_source,skip_advance)
               values (%s,%s,%s,%s,%s,%s) returning id""",
            (biz, name, phone, True, "seed", i in (0, 1)),
        )
        customers.append(cur.fetchone()[0])

    # occupancy bookkeeping
    def windows(s: dict, d: date) -> list[tuple[datetime, datetime]]:
        key = DAYS[d.weekday()]
        out = []
        for w in s["tpl"].get(key, []):
            ws, we = at(d, w["start"]), at(d, w["end"])
            cuts = sorted((at(d, b["start"]), at(d, b["end"])) for b in s["tpl"]["breaks"].get(key, []))
            cur_s = ws
            for bs, be in cuts:
                if bs > cur_s:
                    out.append((cur_s, bs))
                cur_s = max(cur_s, be)
            if cur_s < we:
                out.append((cur_s, we))
        return out

    def free(s: dict, a: datetime, b: datetime) -> bool:
        return all(b <= x or a >= y for x, y in s["busy"])

    stats = dict(bookings=0, online_paid=0)
    booking_rows: list[tuple] = []  # inserted in one pipelined batch (fast even over a remote connection)
    payment_rows: list[tuple] = []

    def insert_booking(s_name: str, svc_name: str, start: datetime, d: date, keep: bool = False) -> None:
        s, sv = staff[s_name], svc[svc_name]
        end = start + timedelta(minutes=sv["dur"])
        block_end = end + timedelta(minutes=sv["buf"])
        s["busy"].append((start, block_end))
        past = start < now
        r = rng.random()
        if past:
            status = "completed" if r < 0.84 else ("no_show" if r < 0.92 else "cancelled")
        else:
            status = "confirmed" if (r < 0.93 or keep) else "cancelled"  # keep: never cancel the demo-slot neighbours
        source = rng.choices(["online", "walk_in", "phone"], [0.55, 0.3, 0.15])[0]
        due = advance_due_paise(sv["price"], sv["atype"], sv["aval"]) if source == "online" else 0
        paid = due if (source == "online" and status != "cancelled") else 0
        bid = uuid.uuid4()
        booking_rows.append((bid, biz, rng.choice(customers), sv["id"], s["id"], Range(start, end, "[)"),
                             Range(start, block_end, "[)"), status, source, sv["price"], due, paid,
                             secrets.token_urlsafe(16), (start - timedelta(hours=6)) if status == "cancelled" else None,
                             "customer request" if status == "cancelled" else None))
        stats["bookings"] += 1
        if due:
            payment_rows.append((bid, f"order_seed_{bid.hex[:14]}", f"pay_seed_{bid.hex[:14]}", due,
                                 "refunded" if status == "cancelled" else "captured", due if status == "cancelled" else 0))
            stats["online_paid"] += 1

    sat = upcoming_saturday(today)
    for offset in range(-14, 8):
        d = today + timedelta(days=offset)
        is_weekend = d.weekday() >= 5
        for s_name, s in staff.items():
            s["busy"] = []
            wins = windows(s, d)
            if not wins:
                continue
            # demo-script slot: Neha, next Saturday 16:00-17:00 stays free
            if s_name == "Neha" and d == sat:
                s["busy"].append((at(d, "15:50"), at(d, "17:10")))
                insert_booking("Neha", "Women's Haircut & Styling", at(d, "14:45"), d, keep=True)
                insert_booking("Neha", "Blow-dry", at(d, "17:15"), d, keep=True)
            total = sum((b - a).total_seconds() / 60 for a, b in wins)
            if offset < 0:
                target = rng.uniform(0.50, 0.70)
            else:
                target = rng.uniform(0.68, 0.76) if is_weekend else rng.uniform(0.55, 0.66)
            booked_min = 0.0
            for _ in range(400):
                if booked_min >= target * total:
                    break
                svc_name = rng.choice(s["services"])
                sv = svc[svc_name]
                span = timedelta(minutes=sv["dur"] + sv["buf"])
                ws, we = rng.choice(wins)
                latest = we - span
                if latest < ws:
                    continue
                slots = int((latest - ws).total_seconds() // 900)
                start = ws + timedelta(minutes=15 * rng.randint(0, slots))
                if not free(s, start, start + span):
                    continue
                if start >= now and start < now + timedelta(hours=1):
                    continue  # respect min lead time so "today" looks real
                insert_booking(s_name, svc_name, start, d)
                booked_min += sv["dur"] + sv["buf"]

    cur.executemany(
        """insert into booking (id,business_id,customer_id,service_id,staff_id,time_range,block_range,status,source,
             price_paise,advance_due_paise,advance_paid_paise,public_token,cancelled_at,cancel_reason)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", booking_rows)
    cur.executemany(
        """insert into payment (booking_id,razorpay_order_id,razorpay_payment_id,amount_paise,status,method,refunded_paise,is_seeded)
           values (%s,%s,%s,%s,%s,'upi',%s,true)""", payment_rows)

    # audit trail entry so the presenter timeline is non-empty after reset
    cur.execute("insert into audit_event (business_id,type,data) values (%s,'demo_reset',%s)",
                (biz, Jsonb({"seeded_at": now.isoformat(), "script_slot": f"{sat} 16:00-17:00 Neha"})))
    conn.commit()
    return dict(business_id=biz, script_saturday=sat.isoformat(), **stats)


def main() -> None:
    dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
    with psycopg.connect(dsn) as conn:
        out = seed(conn)
    print("Seeded:", out)
    print(f"Demo logins (demo only): {OWNER_EMAIL} / {FRONT_EMAIL}  password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    sys.exit(main())

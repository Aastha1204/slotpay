import itertools
from datetime import datetime, timedelta

import psycopg
import pytest
import seed as seed_mod
from psycopg import errors
from psycopg.types.range import Range

_n = itertools.count()


def _ids(conn, staff="Rohit"):
    return conn.execute(
        """select s.id, s.business_id, (select id from service limit 1), (select id from customer limit 1)
           from staff s where name=%s""",
        (staff,),
    ).fetchone()


def _insert(conn, sid, biz, svc, cust, start, mins=30, buf=5, status="confirmed"):
    end = start + timedelta(minutes=mins)
    return conn.execute(
        """insert into booking (business_id,customer_id,service_id,staff_id,time_range,block_range,status,
             price_paise,public_token) values (%s,%s,%s,%s,%s,%s,%s,100,%s)""",
        (biz, cust, svc, sid, Range(start, end, "[)"), Range(start, end + timedelta(minutes=buf), "[)"),
         status, f"tok{next(_n)}"),
    )


def ist(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=seed_mod.IST)


def test_seed_is_idempotent(migrated, seeded):
    with psycopg.connect(migrated) as c:
        seed_mod.seed(c)
        seed_mod.seed(c)
        q = lambda sql: c.execute(sql).fetchone()[0]  # noqa: E731
        assert q("select count(*) from business where slug='glow-studio'") == 1
        assert q("select count(*) from service") == 18
        assert q("select count(*) from staff") == 4
        assert q("select count(*) from customer") == 40
        assert q("select count(*) from booking") > 100
        assert q("select count(*) from payment where is_seeded") > 10


def test_overlapping_booking_fails_23P01(conn, seeded):
    sid, biz, svc, cust = _ids(conn)
    start = ist(2031, 1, 6, 11)
    _insert(conn, sid, biz, svc, cust, start)
    conn.commit()
    with pytest.raises(errors.ExclusionViolation) as e:
        _insert(conn, sid, biz, svc, cust, start + timedelta(minutes=10))
    assert e.value.sqlstate == "23P01"
    conn.rollback()


def test_buffer_counts_but_adjacent_blocks_are_allowed(conn, seeded):
    sid, biz, svc, cust = _ids(conn)
    start = ist(2031, 1, 7, 11)
    _insert(conn, sid, biz, svc, cust, start, mins=30, buf=10)  # block ends 11:40
    conn.commit()
    with pytest.raises(errors.ExclusionViolation):
        _insert(conn, sid, biz, svc, cust, start + timedelta(minutes=35))
    conn.rollback()
    _insert(conn, sid, biz, svc, cust, start + timedelta(minutes=40))  # half-open: adjacent ok
    conn.commit()


def test_cancelled_and_expired_free_the_slot(conn, seeded):
    sid, biz, svc, cust = _ids(conn)
    start = ist(2031, 1, 8, 11)
    for st in ("cancelled", "expired", "held"):
        _insert(conn, sid, biz, svc, cust, start, status=st)
    conn.commit()


def test_time_block_conflicts_both_directions(conn, seeded):
    sid, biz, svc, cust = _ids(conn)
    start = ist(2031, 1, 9, 11)
    conn.execute("insert into time_block (staff_id,time_range,reason) values (%s,%s,'leave')",
                 (sid, Range(start, start + timedelta(hours=1), "[)")))
    conn.commit()
    with pytest.raises(errors.ExclusionViolation):
        _insert(conn, sid, biz, svc, cust, start + timedelta(minutes=15))
    conn.rollback()
    _insert(conn, sid, biz, svc, cust, start + timedelta(hours=2))
    conn.commit()
    with pytest.raises(errors.ExclusionViolation):
        conn.execute("insert into time_block (staff_id,time_range) values (%s,%s)",
                     (sid, Range(start + timedelta(hours=2), start + timedelta(hours=3), "[)")))
    conn.rollback()


def test_rls_enabled_everywhere_and_no_policies(conn, seeded):
    off = conn.execute("select tablename from pg_tables where schemaname='public' and not rowsecurity "
                       "and tablename <> 'schema_migrations'").fetchall()
    assert off == []
    assert conn.execute("select count(*) from pg_policies where schemaname='public'").fetchone()[0] == 0


def test_demo_script_slot_is_free(conn, seeded):
    sat = datetime.fromisoformat(seeded["script_saturday"]).date()
    a = datetime(sat.year, sat.month, sat.day, 16, tzinfo=seed_mod.IST)
    neha = conn.execute("select id from staff where name='Neha'").fetchone()[0]
    clash = conn.execute(
        "select count(*) from booking where staff_id=%s and status not in ('cancelled','expired') and block_range && %s",
        (neha, Range(a, a + timedelta(hours=1), "[)"))).fetchone()[0]
    assert clash == 0
    assert sat.weekday() == 5


def test_advance_rules():
    assert seed_mod.advance_for(300) == ("fixed", 10000)
    assert seed_mod.advance_for(1200) == ("fixed", 20000)  # Hair Spa => INR 200
    assert seed_mod.advance_for(2800) == ("percent", 20)
    assert seed_mod.advance_due_paise(280000, "percent", 20) == 56000

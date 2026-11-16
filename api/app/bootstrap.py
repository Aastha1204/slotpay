"""First-use database setup for serverless deployments (Vercel + Neon).

There is no deploy hook or long-lived process there, so the first request of each cold instance makes sure the
schema exists and the demo salon is seeded. A Postgres advisory lock keeps concurrent cold starts from doing it twice.
"""
import asyncio
import importlib.util
import logging
import os
import pathlib

import psycopg

from .config import get_settings

log = logging.getLogger("slotpay.bootstrap")
_ready = False
_lock = asyncio.Lock()
LOCK_ID = 746_100_001


def _root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for p in (here.parents[1], here.parents[2]):  # bundled copy (api/_slotpay) or the repository root
        if (p / "supabase" / "migrations").is_dir():
            return p
    raise RuntimeError("supabase/migrations not found")


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _setup() -> dict:
    root = _root()
    dsn = os.getenv("DATABASE_URL_UNPOOLED") or get_settings().database_url  # DDL + advisory locks need a direct connection
    migrate = _load(root / "scripts" / "migrate.py", "slotpay_migrate")
    seed = _load(root / "supabase" / "seed" / "seed.py", "slotpay_seed")
    with psycopg.connect(dsn, autocommit=True) as lock_conn:
        lock_conn.execute("select pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            with psycopg.connect(dsn) as conn:
                applied = migrate.migrate(conn)
                empty = conn.execute("select count(*) from business").fetchone()[0] == 0
                out = seed.seed(conn) if empty else {}
            return {"migrations": applied, "seeded": bool(out)}
        finally:
            lock_conn.execute("select pg_advisory_unlock(%s)", (LOCK_ID,))


async def ensure_ready() -> None:
    global _ready
    if _ready:
        return
    async with _lock:
        if _ready:
            return
        log.info("bootstrap: %s", await asyncio.to_thread(_setup))
        _ready = True

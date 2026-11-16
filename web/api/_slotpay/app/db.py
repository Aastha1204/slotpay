"""Database access + Postgres error mapping.

All writes go through the API over a server-side connection (RLS has no policies for anon).
"""
from contextlib import asynccontextmanager

import psycopg
from fastapi import Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import SERVERLESS, get_settings

pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    global pool
    pool = AsyncConnectionPool(
        get_settings().database_url,
        min_size=1,
        max_size=10,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    await pool.open()


async def close_pool() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None


@asynccontextmanager
async def connection():
    if SERVERLESS:
        # Functions are short-lived and may run on a fresh event loop each time: one connection per request
        # (Neon's pooled endpoint absorbs the churn; prepared statements are off for PgBouncer).
        conn = await psycopg.AsyncConnection.connect(get_settings().database_url, row_factory=dict_row, prepare_threshold=None)
        try:
            yield conn
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
        finally:
            await conn.close()
        return
    assert pool is not None, "pool not opened"
    async with pool.connection() as conn:
        yield conn


async def get_conn():
    async with connection() as conn:
        yield conn


class SlotTaken(Exception):
    """Raised when the exclusion constraint (23P01) rejects an overlapping booking."""


def is_exclusion_violation(exc: BaseException) -> bool:
    return isinstance(exc, psycopg.errors.ExclusionViolation) or getattr(exc, "sqlstate", None) == "23P01"


async def slot_taken_handler(_: Request, __: SlotTaken) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "SLOT_TAKEN", "message": "That slot was just taken. Please pick another time."},
    )

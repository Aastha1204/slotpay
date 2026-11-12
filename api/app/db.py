"""Database access + Postgres error mapping.

All writes go through the API over a server-side connection (RLS has no policies for anon).
"""
from contextlib import asynccontextmanager

import psycopg
from fastapi import Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import get_settings

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

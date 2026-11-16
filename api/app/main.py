import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .auth import Staff, current_staff, require_role
from .config import SERVERLESS, get_settings
from . import bootstrap
from . import jobs
from .admin import router as admin_router
from .demo import router as demo_router
from .prototype import router as prototype_router
from .prototype_flow import router as prototype_flow_router
from .admin_config import router as config_router
from .reports import router as reports_router
from .booking import router as booking_router
from .payments_api import router as payments_router
from .whatsapp_api import router as whatsapp_router
from .public import router as public_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("slotpay")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.open_pool()
    task = asyncio.create_task(jobs.scheduler_loop(5 if get_settings().reminder_demo_delay_sec else 60))
    yield
    task.cancel()
    await db.close_pool()


app = FastAPI(title="SlotPay API", lifespan=lifespan)
app.add_exception_handler(db.SlotTaken, db.slot_taken_handler)
app.include_router(public_router)
app.include_router(payments_router)
app.include_router(jobs.router)
app.include_router(whatsapp_router)
app.include_router(admin_router)
app.include_router(demo_router)
app.include_router(prototype_router)
app.include_router(prototype_flow_router)
app.include_router(config_router)
app.include_router(reports_router)
app.include_router(booking_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    return response


_last_tick = 0.0


@app.middleware("http")
async def serverless_boot(request: Request, call_next):
    """On Vercel there is no startup hook or background loop: prepare the database on first use and run the
    job tick (expire holds, send due WhatsApp reminders) at most every 5 s while the API is being used."""
    global _last_tick
    if SERVERLESS and request.url.path != "/health":
        await bootstrap.ensure_ready()
        now = time.monotonic()
        if now - _last_tick >= 5:
            _last_tick = now
            try:
                await jobs.tick()
            except Exception:
                log.exception("job tick failed")
    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/db")
async def health_db():
    async with db.connection() as conn:
        cur = await conn.execute(
            "select (select count(*) from pg_extension where extname='btree_gist') as gist,"
            " (select count(*) from pg_constraint where conname='booking_no_overlap') as guard"
        )
        row = await cur.fetchone()
    ok = bool(row["gist"] and row["guard"])
    return {"status": "ok" if ok else "degraded", "btree_gist": bool(row["gist"]), "overlap_guard": bool(row["guard"])}


@app.get("/admin/me")
async def admin_me(staff: Staff = Depends(current_staff)):
    return {"id": str(staff.id), "email": staff.email, "role": staff.role, "business_id": str(staff.business_id)}


@app.get("/admin/owner-check")
async def owner_check(staff: Staff = Depends(require_role("owner"))):
    return {"ok": True}

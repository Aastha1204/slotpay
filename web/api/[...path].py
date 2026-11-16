"""Vercel Function entry: serves the FastAPI app under /api/* (same origin as the website, so no CORS).

The application code lives in api/_slotpay (a copy of /api/app + migrations + seed, kept in sync by
scripts/sync_vercel_api.py), because a Vercel project can only bundle files inside its Root Directory (web/).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_slotpay"))

from app.main import app as _api  # noqa: E402


async def app(scope, receive, send):
    if scope["type"] == "lifespan":  # nothing to start or stop: the database is prepared on first request
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] in ("http", "websocket"):
        path = scope.get("path", "/")
        if path == "/api" or path.startswith("/api/"):
            path = path[4:] or "/"
            scope = {**scope, "path": path, "raw_path": path.encode()}
    await _api(scope, receive, send)

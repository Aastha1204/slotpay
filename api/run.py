"""Dev/prod entrypoint. On Windows uvicorn's default Proactor loop breaks psycopg async; use the selector loop."""
import asyncio
import os
import sys

import uvicorn

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    cfg = uvicorn.Config("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), loop="none", proxy_headers=True, forwarded_allow_ips="*")
    asyncio.run(uvicorn.Server(cfg).serve())

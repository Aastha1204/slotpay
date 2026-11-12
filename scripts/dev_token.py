"""DEV ONLY: mint an admin JWT for local testing without Supabase Auth.
Usage: SUPABASE_JWT_SECRET=... DATABASE_URL=... python scripts/dev_token.py owner|front_desk
Paste the token on /admin/login (shown only when NEXT_PUBLIC_DEV_AUTH=1)."""
import os
import sys
import time

import jwt
import psycopg

role = sys.argv[1] if len(sys.argv) > 1 else "owner"
dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
with psycopg.connect(dsn) as c:
    uid = c.execute("select id from staff_user where role=%s limit 1", (role,)).fetchone()[0]
print(jwt.encode({"sub": str(uid), "aud": "authenticated", "exp": int(time.time()) + 8 * 3600},
                 os.environ["SUPABASE_JWT_SECRET"], "HS256"))

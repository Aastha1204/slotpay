"""Apply supabase/migrations/*.sql in order (tracked in schema_migrations). Usage: python scripts/migrate.py"""
import os
import pathlib

import psycopg

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "supabase" / "migrations"


def migrate(conn: psycopg.Connection) -> list[str]:
    conn.execute(
        "create table if not exists schema_migrations (name text primary key, applied_at timestamptz default now())"
    )
    conn.commit()
    done = {r[0] for r in conn.execute("select name from schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        conn.execute(f.read_text(encoding="utf-8"))
        conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))
        conn.commit()
        applied.append(f.name)
    return applied


if __name__ == "__main__":
    dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
    with psycopg.connect(dsn) as c:
        print("applied:", migrate(c))

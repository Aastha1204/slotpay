import time

import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

SECRET = "test-secret-test-secret-test-secret-123"


@pytest.fixture()
def client(migrated, seeded, monkeypatch):
    from app import config

    monkeypatch.setenv("DATABASE_URL", migrated)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    config.get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c
    config.get_settings.cache_clear()


def token(sub):
    return jwt.encode({"sub": str(sub), "aud": "authenticated", "exp": int(time.time()) + 600}, SECRET, "HS256")


def user_id(dsn, role):
    with psycopg.connect(dsn) as c:
        return c.execute("select id from staff_user where role=%s", (role,)).fetchone()[0]


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/health/db").json()
    assert r["status"] == "ok" and r["overlap_guard"] and r["btree_gist"]


def test_admin_requires_token(client):
    assert client.get("/admin/me").status_code == 401
    assert client.get("/admin/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_roles(client, migrated):
    o = {"Authorization": f"Bearer {token(user_id(migrated, 'owner'))}"}
    f = {"Authorization": f"Bearer {token(user_id(migrated, 'front_desk'))}"}
    assert client.get("/admin/me", headers=o).json()["role"] == "owner"
    assert client.get("/admin/owner-check", headers=o).status_code == 200
    assert client.get("/admin/owner-check", headers=f).status_code == 403
    stranger = {"Authorization": f"Bearer {token('00000000-0000-0000-0000-000000000000')}"}
    assert client.get("/admin/me", headers=stranger).status_code == 403

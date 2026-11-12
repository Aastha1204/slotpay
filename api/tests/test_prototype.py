from conftest import JWT_SECRET  # noqa: F401


def test_prototype_off_by_default(client, monkeypatch):
    from app import config
    monkeypatch.setenv("PROTOTYPE_MODE", "false")
    config.get_settings.cache_clear()
    s0 = client.get("/prototype/status").json()
    assert s0["enabled"] is False and s0["can_login"] is False and s0["payments"] == "razorpay"
    assert client.post("/prototype/login", json={"role": "owner"}).status_code == 404
    assert client.get("/prototype/summary").status_code == 404


def test_login_issues_working_tokens_for_each_role(client, monkeypatch):
    from app import config
    monkeypatch.setenv("PROTOTYPE_MODE", "true")
    config.get_settings.cache_clear()
    s1 = client.get("/prototype/status").json()
    assert s1["enabled"] is True and s1["can_login"] is True
    for role in ("owner", "front_desk"):
        r = client.post("/prototype/login", json={"role": role})
        assert r.status_code == 200 and r.json()["role"] == role and r.json()["expires_in"] == 8 * 3600
        me = client.get("/admin/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
        assert me.status_code == 200 and me.json()["role"] == role
    owner = client.post("/prototype/login", json={"role": "owner"}).json()["token"]
    front = client.post("/prototype/login", json={"role": "front_desk"}).json()["token"]
    assert client.get("/admin/manage/services", headers={"Authorization": f"Bearer {owner}"}).status_code == 200
    assert client.get("/admin/manage/services", headers={"Authorization": f"Bearer {front}"}).status_code == 403


def test_login_validation_and_missing_secret(client, monkeypatch):
    from app import config
    monkeypatch.setenv("PROTOTYPE_MODE", "true")
    config.get_settings.cache_clear()
    assert client.post("/prototype/login", json={"role": "admin"}).status_code == 422
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    config.get_settings.cache_clear()
    assert client.post("/prototype/login", json={"role": "owner"}).status_code == 501
    assert client.get("/prototype/status").json()["can_login"] is False


def test_summary_counts(client, monkeypatch):
    from app import config
    monkeypatch.setenv("PROTOTYPE_MODE", "true")
    config.get_settings.cache_clear()
    s = client.get("/prototype/summary").json()
    assert s["ready"] and s["slug"] == "glow-studio"
    assert s["counts"]["services"] == 18 and s["counts"]["stylists"] == 4 and s["counts"]["customers"] >= 40
    assert s["counts"]["upcoming_bookings"] > 20 and s["counts"]["completed_bookings"] > 50

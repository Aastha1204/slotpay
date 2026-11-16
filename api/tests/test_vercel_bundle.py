"""web/api/_slotpay (what the Vercel Function bundles) must match the real sources: run scripts/sync_vercel_api.py."""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_vercel_bundle_is_in_sync():
    spec = importlib.util.spec_from_file_location("sync_vercel_api", ROOT / "scripts" / "sync_vercel_api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stale = [str(d.relative_to(ROOT)) for f, d in mod.files() if not d.exists() or d.read_bytes() != f.read_bytes()]
    assert not stale, f"run `python scripts/sync_vercel_api.py` (stale: {stale[:5]})"

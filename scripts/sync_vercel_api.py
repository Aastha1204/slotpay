"""Copy the API (app + migrations + seed) into web/api/_slotpay so the Vercel Function (Root Directory = web/) can bundle it.
Run after changing anything under api/app, supabase/ or scripts/migrate.py:  python scripts/sync_vercel_api.py
A test (api/tests/test_vercel_bundle.py) fails when the copy is stale."""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEST = ROOT / "web" / "api" / "_slotpay"
PAIRS = [("api/app", "app"), ("supabase/migrations", "supabase/migrations"), ("supabase/seed/seed.py", "supabase/seed/seed.py"),
         ("scripts/migrate.py", "scripts/migrate.py")]


def files():
    for src, dst in PAIRS:
        s = ROOT / src
        for f in ([s] if s.is_file() else sorted(p for p in s.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")):
            yield f, DEST / dst / f.relative_to(s) if s.is_dir() else DEST / dst


if __name__ == "__main__":
    if DEST.exists():
        shutil.rmtree(DEST)
    for f, d in files():
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, d)
    print("synced", sum(1 for _ in files()), "files ->", DEST)

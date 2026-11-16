# Deploying SlotPay (Vercel web + hosted API)

The website on Vercel is only the front end. It talks to the FastAPI server through `/api/*`, so the API (and its Postgres) must be hosted somewhere public. If it is not, the booking page shows **"We couldn't reach the server"**, because the web app falls back to `http://localhost:8000`.

## 1. Database
Create a Postgres with the `btree_gist` extension (Supabase works). Copy its connection string as `DATABASE_URL`.

## 2. API (Render)
Create a Render Blueprint from this repo (`render.yaml`). Set `DATABASE_URL`, `SUPABASE_JWT_SECRET` (any long random string in prototype mode), `WEB_ORIGIN` and `PUBLIC_BASE_URL` (both your Vercel URL). The container runs migrations on start. Seed the demo data once from your machine:

```
DATABASE_URL=<same url> python supabase/seed/seed.py
```

Check `https://<your-api>.onrender.com/health` returns 200.

## 3. Vercel environment variables (Project -> Settings -> Environment Variables)
| Name | Value |
|---|---|
| `API_INTERNAL_URL` | `https://<your-api>.onrender.com` |
| `NEXT_PUBLIC_API_BASE_URL` | `/api` |
| `NEXT_PUBLIC_PROTOTYPE` | `1` |
| `NEXT_PUBLIC_DEMO_KEY` | same value as the API's `DEMO_KEY` |

Set the Vercel **Root Directory** to `web`, then redeploy (the `NEXT_PUBLIC_*` values are baked in at build time).

## Vercel-only deployment (what slotpay.vercel.app uses)
No separate API host is needed: `web/api/index.py` serves the FastAPI app at `/api/*`, and a Neon Postgres connected from Vercel's Storage tab supplies `DATABASE_URL`. The first request migrates and seeds the demo salon. Prototype mode, simulated payments and the WhatsApp simulator are on by default (see `get_settings()` in `api/app/config.py`). After changing `api/app`, `supabase/` or `scripts/migrate.py`, run `python scripts/sync_vercel_api.py` and commit `web/api/_slotpay`. To run the browser tests against it: `E2E_BASE_URL=https://slotpay.vercel.app npx playwright test`.

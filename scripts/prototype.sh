#!/usr/bin/env bash
# One command to run the whole SlotPay prototype as ONE website: http://localhost:3100
#   scripts/prototype.sh            (PY=/path/to/python to pick the interpreter; PORT=3100 to change the port)
# Starts: Postgres (Docker) -> migrations + demo data -> API (port 8000, hidden behind /api) -> web app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-python}"
PORT="${PORT:-3100}"
DEMO_KEY="${DEMO_KEY:-demo123}"
JWT_SECRET="${SUPABASE_JWT_SECRET:-local-prototype-jwt-secret-0123456789abcdef}"
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"

echo "==> Database"
docker start slotpay-pg >/dev/null 2>&1 || docker run -d --name slotpay-pg -e POSTGRES_PASSWORD=postgres -p 54322:5432 postgres:16 >/dev/null
until docker exec slotpay-pg pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done

echo "==> Migrations + demo data"
"$PY" "$ROOT/scripts/migrate.py"
"$PY" "$ROOT/supabase/seed/seed.py" | grep -E "Seeded|Demo logins" || true

echo "==> API (internal, port 8000)"
(
  cd "$ROOT/api"
  PROTOTYPE_MODE=true DEMO_MODE=true DEMO_KEY="$DEMO_KEY" JOBS_SECRET=prototype SUPABASE_JWT_SECRET="$JWT_SECRET" \
  WEB_ORIGIN="http://localhost:$PORT" PUBLIC_BASE_URL="http://localhost:$PORT" WHATSAPP_MODE=simulator REMINDER_DEMO_DELAY_SEC="${REMINDER_DEMO_DELAY_SEC:-20}" \
  exec "$PY" run.py
) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
until curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; do sleep 1; done

echo "==> Web (building once, then serving)"
cd "$ROOT/web"
[ -d node_modules ] || npm install
export NEXT_PUBLIC_PROTOTYPE=1 NEXT_PUBLIC_DEMO_KEY="$DEMO_KEY" NEXT_PUBLIC_API_BASE_URL=/api API_INTERNAL_URL=http://localhost:8000
rm -rf .next && npm run build >/dev/null
echo
echo "  SlotPay prototype is ready:  http://localhost:$PORT   (hub: http://localhost:$PORT/prototype)"
echo
NEXT_TELEMETRY_DISABLED=1 npx next start -p "$PORT"

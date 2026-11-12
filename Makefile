# On Windows without make, use scripts/dev.ps1 (same targets).
PY ?= python
export DATABASE_URL ?= postgresql://postgres:postgres@127.0.0.1:54322/postgres

prototype:   ## everything as one website at http://localhost:3100
	bash scripts/prototype.sh
db-up:        ## local Postgres 16 in Docker (port 54322)
	docker start slotpay-pg 2>/dev/null || docker run -d --name slotpay-pg -e POSTGRES_PASSWORD=postgres -p 54322:5432 postgres:16
migrate:
	$(PY) scripts/migrate.py
seed: migrate
	$(PY) supabase/seed/seed.py
reset-demo: seed
dev:
	cd api && $(PY) -m uvicorn app.main:app --reload --port 8000 & cd web && npm run dev
test:
	cd api && $(PY) -m pytest -q
concurrency-test:
	cd api && $(PY) -m pytest -q -k concurrent

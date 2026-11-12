param([Parameter(Mandatory)][ValidateSet('db-up','migrate','seed','reset-demo','test','api','web')]$Task)
$py = if ($env:PY) { $env:PY } else { 'python' }
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:54322/postgres' }
Set-Location (Split-Path $PSScriptRoot)
switch ($Task) {
  'db-up' { docker start slotpay-pg 2>$null; if ($LASTEXITCODE) { docker run -d --name slotpay-pg -e POSTGRES_PASSWORD=postgres -p 54322:5432 postgres:16 } }
  'migrate' { & $py scripts/migrate.py }
  { $_ -in 'seed','reset-demo' } { & $py scripts/migrate.py; & $py supabase/seed/seed.py }
  'test' { Set-Location api; & $py -m pytest -q }
  'api' { Set-Location api; & $py -m uvicorn app.main:app --reload --port 8000 }
  'web' { Set-Location web; npm run dev }
}

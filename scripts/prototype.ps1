# One command to run the whole SlotPay prototype as ONE website: http://localhost:3100
#   powershell -ExecutionPolicy Bypass -File scripts\prototype.ps1
#   $env:PY = "C:\path\to\python.exe"   # optional: pick the Python interpreter (venv with api\requirements.txt)
# Starts: Postgres (Docker) -> migrations + demo data -> API (port 8000, hidden behind /api) -> web app.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = if ($env:PY) { $env:PY } else { "python" }
$port = if ($env:PORT) { $env:PORT } else { "3100" }
$demoKey = if ($env:DEMO_KEY) { $env:DEMO_KEY } else { "demo123" }
$jwt = if ($env:SUPABASE_JWT_SECRET) { $env:SUPABASE_JWT_SECRET } else { "local-prototype-jwt-secret-0123456789abcdef" }
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres" }

Write-Host "==> Database"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  for ($i = 0; $i -lt 40; $i++) { Start-Sleep 5; docker info *> $null; if ($LASTEXITCODE -eq 0) { break } }
}
docker start slotpay-pg *> $null
if ($LASTEXITCODE -ne 0) { docker run -d --name slotpay-pg -e POSTGRES_PASSWORD=postgres -p 54322:5432 postgres:16 | Out-Null }
do { Start-Sleep 1; docker exec slotpay-pg pg_isready -U postgres *> $null } until ($LASTEXITCODE -eq 0)

Write-Host "==> Migrations + demo data"
& $py "$root\scripts\migrate.py"
& $py "$root\supabase\seed\seed.py" | Select-String "Seeded|Demo logins"

Write-Host "==> API (internal, port 8000)"
$env:PROTOTYPE_MODE = "true"; $env:DEMO_MODE = "true"; $env:DEMO_KEY = $demoKey; $env:JOBS_SECRET = "prototype"
$env:SUPABASE_JWT_SECRET = $jwt; $env:WEB_ORIGIN = "http://localhost:$port"; $env:PUBLIC_BASE_URL = "http://localhost:$port"; $env:WHATSAPP_MODE = "simulator"; $env:REMINDER_DEMO_DELAY_SEC = $(if ($env:REMINDER_DEMO_DELAY_SEC) { $env:REMINDER_DEMO_DELAY_SEC } else { "20" })
$api = Start-Process -FilePath $py -ArgumentList "run.py" -WorkingDirectory "$root\api" -PassThru -WindowStyle Hidden
do { Start-Sleep 1; try { $ok = (Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { $ok = $false } } until ($ok)

Write-Host "==> Web (building once, then serving)"
Set-Location "$root\web"
if (-not (Test-Path node_modules)) { npm install }
$env:NEXT_PUBLIC_PROTOTYPE = "1"; $env:NEXT_PUBLIC_DEMO_KEY = $demoKey; $env:NEXT_PUBLIC_API_BASE_URL = "/api"; $env:API_INTERNAL_URL = "http://localhost:8000"
if (Test-Path .next) { Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue }
$buildLog = cmd /c "npm run build 2>&1"
if ($LASTEXITCODE -ne 0) {
  $buildLog | Select-Object -Last 40 | ForEach-Object { Write-Host $_ }
  if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force }
  throw "Web build failed (see the log above)."
}
Write-Host ""
Write-Host "  SlotPay prototype is ready:  http://localhost:$port   (hub: http://localhost:$port/prototype)" -ForegroundColor Green
Write-Host ""
try { $env:NEXT_TELEMETRY_DISABLED = "1"; npx next start -p $port } finally { if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force } }


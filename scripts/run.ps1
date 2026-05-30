# Run Noteration: build the frontend, apply migrations, and serve the whole app
# (REST API + the built React bundle) on http://localhost:8000.
#
# Usage (from anywhere):  powershell -ExecutionPolicy Bypass -File scripts\run.ps1
# Stop with Ctrl+C. Always rebuilds so you never serve a stale bundle.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python venv not found at $python. Create it with: python -m venv .venv"
}

Set-Location $root

Write-Host "==> Building frontend (npm run build)..." -ForegroundColor Cyan
npm run build

Write-Host "==> Applying database migrations..." -ForegroundColor Cyan
Push-Location (Join-Path $root "backend")
try {
    & $python -m alembic upgrade head
}
finally {
    Pop-Location
}

Write-Host "==> Noteration is running at http://localhost:8000 (Ctrl+C to stop)" -ForegroundColor Green
& $python -m uvicorn backend.main:app --port 8000

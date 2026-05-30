# Dev mode with hot reload: starts the FastAPI backend (uvicorn --reload) on
# :8000 in a new window, then the Vite dev server on :5173 (which proxies /api
# to the backend). Open http://localhost:5173. Stop Vite with Ctrl+C; close the
# backend window separately.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
Set-Location $root

Write-Host "==> Starting backend (uvicorn --reload) on :8000 in a new window..." -ForegroundColor Cyan
Start-Process -FilePath $python `
    -ArgumentList "-m", "uvicorn", "backend.main:app", "--reload", "--port", "8000" `
    -WorkingDirectory $root

Write-Host "==> Starting Vite dev server on http://localhost:5173 ..." -ForegroundColor Green
npm run dev

<#
  EQAL launcher (Windows / PowerShell):  .\start.ps1  [-Port 8811] [-No2FA] [-Rebuild] [-Reset]
  First run: creates the virtualenv, installs dependencies, migrates the SQLite DB, loads demo data,
  builds the React app, then serves everything (API + frontend) from one port, with the job runner
  (reminders, auto-close, retention) alongside.
#>
param([int]$Port = 8811, [switch]$No2FA, [switch]$Rebuild, [switch]$Reset)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$be = Join-Path $root "backend"; $fe = Join-Path $root "frontend"
$py = Join-Path $be ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
  Write-Host "Creating virtualenv + installing backend dependencies..." -ForegroundColor Cyan
  python -m venv (Join-Path $be ".venv")
  & $py -m pip install --quiet -r (Join-Path $be "requirements.txt")
}
if ($Reset) { Remove-Item (Join-Path $be "db.sqlite3"), (Join-Path $be "media_private") -Recurse -Force -ErrorAction SilentlyContinue }
if ($Rebuild -or -not (Test-Path (Join-Path $fe "dist\index.html"))) {
  Write-Host "Building frontend..." -ForegroundColor Cyan
  Push-Location $fe
  if (-not (Test-Path "node_modules")) { npm install --no-audit --no-fund }
  npm run build
  Pop-Location
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
  throw "Port $Port is already in use. Pick another one:  .\start.ps1 -Port 8900"
}
$env:EQAL_FRONTEND_URL = "http://127.0.0.1:$Port"
$env:EQAL_CORS_ORIGINS = "http://127.0.0.1:$Port,http://localhost:$Port,http://localhost:5173"
if ($No2FA) { $env:EQAL_REQUIRE_2FA = "0"; Write-Host "2FA DISABLED (local demo only)" -ForegroundColor Yellow }
Push-Location $be
& $py manage.py migrate -v0
& $py manage.py seed_demo
Start-Process -FilePath $py -ArgumentList "manage.py", "run_jobs", "--loop" -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $root "jobs.log") -RedirectStandardError (Join-Path $root "jobs.err.log")
Write-Host "`nEQAL running at http://127.0.0.1:$Port   (Ctrl+C to stop)" -ForegroundColor Green
& $py manage.py runserver "127.0.0.1:$Port" --noreload
Pop-Location

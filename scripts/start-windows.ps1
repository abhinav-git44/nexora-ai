# One-command local start for Windows (Docker Desktop required).
# Usage (from the repository folder):
#   powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1
# Options:
#   -NoSeed   skip loading the labelled demo workspace
#   -Stop     stop the stack (data is kept)

param([switch]$NoSeed, [switch]$Stop)

# "Continue": Docker writes normal progress to stderr, which PowerShell 5.1 would otherwise treat as fatal.
# Each step checks $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$compose = @("compose", "-f", "deployment/docker-compose.yml", "--env-file", ".env")

function Fail($msg) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

function Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

if ($Stop) {
    Step "Stopping NEXORA AI"
    & docker @compose down
    exit $LASTEXITCODE
}

Step "Checking Docker Desktop"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "The 'docker' command was not found. Install Docker Desktop (https://www.docker.com/products/docker-desktop/), restart PowerShell, then run this script again."
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $exe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $exe) {
        Write-Host "Docker engine is not running - starting Docker Desktop and waiting up to 3 minutes..." -ForegroundColor Yellow
        Start-Process $exe
    } else {
        Write-Host "Docker engine is not running - please start Docker Desktop. Waiting up to 3 minutes..." -ForegroundColor Yellow
    }
    for ($i = 0; $i -lt 36; $i++) {
        Start-Sleep -Seconds 5
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) { break }
        Write-Host "." -NoNewline
    }
    Write-Host ""
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Docker reported:" -ForegroundColor Yellow
        & docker info 2>&1 | Select-Object -Last 5 | ForEach-Object { Write-Host "  $_" }
        Fail "Docker engine is still not available. Open Docker Desktop, wait until it shows 'Engine running', then run this script again."
    }
}
Write-Host "Docker engine is running."

function New-Secret([int]$bytes) {
    $buf = New-Object byte[] $bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buf)
    $rng.Dispose()
    return [Convert]::ToBase64String($buf)
}

if (-not (Test-Path ".env")) {
    Step "Creating .env with fresh secrets"
    Copy-Item ".env.example" ".env"
    $jwt = New-Secret 48
    $fernet = (New-Secret 32).Replace("+", "-").Replace("/", "_")
    Add-Content ".env" "JWT_SECRET=$jwt"
    Add-Content ".env" "ENCRYPTION_KEY=$fernet"
    Add-Content ".env" "SUPER_ADMIN_EMAILS=admin@example.com"
} else {
    Step "Using existing .env"
}

Step "Building and starting containers (first run takes several minutes)"
& docker @compose up -d --build
if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed. Scroll up for the first error message." }

Step "Waiting for the app to become healthy"
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:3000/api/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 5
}
if (-not $ok) {
    Write-Host "Recent API logs:" -ForegroundColor Yellow
    & docker @compose logs --tail 40 api
    Fail "The app did not become healthy within 5 minutes."
}

if (-not $NoSeed) {
    Step "Loading the demo workspace (skipped automatically if already loaded)"
    & docker @compose run --rm -v "${root}\scripts:/scripts" api python /scripts/seed_demo.py 2>&1 |
        Where-Object { $_ -match "Seeded|already present|Login:" }
    if ($LASTEXITCODE -ne 0) { Write-Host "Demo seeding failed; the app still works without it." -ForegroundColor Yellow }
}

Step "NEXORA AI is running at http://localhost:3000"
Write-Host "  Demo workspace : demo.owner@example.com / DemoPassw0rd!"
Write-Host "  Admin console  : admin@example.com / DemoPassw0rd!  (http://localhost:3000/admin)"
Write-Host "  Stop           : powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1 -Stop"
Start-Process "http://localhost:3000"

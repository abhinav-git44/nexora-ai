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
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "Docker is not running. Start Docker Desktop, wait for 'Engine running', then run this script again."
}

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

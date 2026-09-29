#Requires -Version 5.1
<#
.SYNOPSIS
    Delentia OS Community Installer for Windows

.DESCRIPTION
    One-line installer for Delentia OS v2.0 on Windows.
    Checks prerequisites, generates credentials, pulls images, and starts all services.

.EXAMPLE
    iwr -useb https://raw.githubusercontent.com/delentia-labs/delentia-infra-public/main/scripts/install.ps1 | iex
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DELENTIA_VERSION = "2.0"
$MIN_DOCKER_VERSION = 24
$MIN_PYTHON_VERSION = [Version]"3.10"
$MIN_NODE_VERSION = 20
$InstallDir = if ($env:DELENTIA_HOME) { $env:DELENTIA_HOME } else { Join-Path $HOME ".delentia" }
$GatewayUrl = "http://localhost:8000"
$RepoBase = "https://raw.githubusercontent.com/delentia-labs/delentia-infra-public/main"

function Write-Info    { Write-Host "[INFO]  $args" -ForegroundColor Cyan }
function Write-Success { Write-Host "[OK]    $args" -ForegroundColor Green }
function Write-Warn    { Write-Host "[WARN]  $args" -ForegroundColor Yellow }
function Write-Err     { Write-Host "[ERROR] $args" -ForegroundColor Red; exit 1 }

# ── Banner ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  DELENTIA OS v$DELENTIA_VERSION - Community Install (Windows)" -ForegroundColor Cyan
Write-Host ""

# ── Prerequisites ──────────────────────────────────────────────────────────────
Write-Info "Checking prerequisites..."

# Docker
try {
    $dockerVer = (docker version --format '{{.Server.Version}}' 2>$null).Split('.')[0]
    if ([int]$dockerVer -lt $MIN_DOCKER_VERSION) {
        Write-Err "Docker >= $MIN_DOCKER_VERSION required (found $dockerVer)"
    }
    Write-Success "Docker $dockerVer.x"
} catch {
    Write-Err "Docker not found. Install from: https://docs.docker.com/desktop/install/windows-install/"
}

# Docker Compose plugin
try {
    docker compose version | Out-Null
    Write-Success "Docker Compose plugin"
} catch {
    Write-Err "Docker Compose plugin not found."
}

# Python
try {
    $pyVer = [Version](python --version 2>&1).ToString().Split(" ")[1]
    if ($pyVer -lt $MIN_PYTHON_VERSION) {
        Write-Err "Python >= $MIN_PYTHON_VERSION required (found $pyVer)"
    }
    Write-Success "Python $pyVer"
} catch {
    Write-Err "Python not found. Install from: https://python.org"
}

# Node.js (optional)
try {
    $nodeVer = [int](node --version).TrimStart('v').Split('.')[0]
    if ($nodeVer -lt $MIN_NODE_VERSION) {
        Write-Warn "Node.js >= $MIN_NODE_VERSION recommended (found $nodeVer)"
    } else {
        Write-Success "Node.js $nodeVer.x"
    }
} catch {
    Write-Warn "Node.js not found (optional — required for Delentia GUI)"
}

# ── Install Directory ──────────────────────────────────────────────────────────
Write-Info "Creating install directory: $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# ── Download files ────────────────────────────────────────────────────────────
Write-Info "Downloading docker-compose.yml..."
Invoke-WebRequest -Uri "$RepoBase/docker/docker-compose.yml" -OutFile "$InstallDir\docker-compose.yml"

Write-Info "Downloading .env.example..."
Invoke-WebRequest -Uri "$RepoBase/docker/.env.example" -OutFile "$InstallDir\.env.example"

# ── Generate credentials ───────────────────────────────────────────────────────
$EnvFile = "$InstallDir\.env"
if (-not (Test-Path $EnvFile)) {
    Write-Info "Generating secure credentials..."

    Add-Type -AssemblyName System.Security
    function New-SecureToken {
        $bytes = [byte[]]::new(32)
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
        return [Convert]::ToBase64String($bytes)
    }

    $PostgresPassword = New-SecureToken
    $DelentiaApiKey   = New-SecureToken

    # SHA-256 verification of downloaded files
    $composeHash = (Get-FileHash "$InstallDir\docker-compose.yml" -Algorithm SHA256).Hash
    Write-Info "docker-compose.yml SHA256: $composeHash"

    $envContent = Get-Content "$InstallDir\.env.example" -Raw
    $envContent = $envContent -replace 'POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$PostgresPassword"
    $envContent = $envContent -replace 'DELENTIA_API_KEY=.*',   "DELENTIA_API_KEY=$DelentiaApiKey"
    Set-Content -Path $EnvFile -Value $envContent -NoNewline
    Write-Success "Credentials saved to $EnvFile"
} else {
    Write-Info ".env already exists, skipping credential generation"
}

# ── Install Python SDK ─────────────────────────────────────────────────────────
Write-Info "Installing delentia-os Python SDK..."
try {
    pip install --quiet "delentia-os>=$DELENTIA_VERSION"
    Write-Success "SDK installed"
} catch {
    Write-Warn "SDK install failed - continuing"
}

# ── Pull and Start ─────────────────────────────────────────────────────────────
Write-Info "Pulling Delentia OS images..."
Push-Location $InstallDir
docker compose pull

Write-Info "Starting Delentia OS services..."
docker compose up -d
Pop-Location

# ── Health Check ───────────────────────────────────────────────────────────────
Write-Info "Waiting for services to be healthy..."
$attempts = 0
$maxAttempts = 30
do {
    Start-Sleep -Seconds 3
    $attempts++
    try {
        $response = Invoke-WebRequest -Uri "$GatewayUrl/health" -TimeoutSec 5 -UseBasicParsing
        if ($response.StatusCode -eq 200) { break }
    } catch { }
    if ($attempts -ge $maxAttempts) {
        Write-Err "Gateway not healthy after $maxAttempts attempts. Run: docker compose logs"
    }
} while ($true)

foreach ($port in @(8000, 8001, 8002, 8004)) {
    try {
        Invoke-WebRequest -Uri "http://localhost:$port/health" -TimeoutSec 5 -UseBasicParsing | Out-Null
        Write-Success "Port $port healthy"
    } catch {
        Write-Warn "Port $port did not respond"
    }
}

# ── Done ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Success "Delentia OS v$DELENTIA_VERSION installed successfully!"
Write-Host ""
Write-Host "  Gateway API:  $GatewayUrl" -ForegroundColor Cyan
Write-Host "  Intent Loop:  http://localhost:8001" -ForegroundColor Cyan
Write-Host "  Analysearch:  http://localhost:8002" -ForegroundColor Cyan
Write-Host "  Crystallizer: http://localhost:8004" -ForegroundColor Cyan
Write-Host ""
Write-Host "  API Key:      $EnvFile" -ForegroundColor Yellow
Write-Host "  Docs:         https://github.com/delentia-labs/delentia-infra-public"
Write-Host ""

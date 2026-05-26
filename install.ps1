#Requires -Version 5.1
# JobPilot v2 — one-command installer for Windows (PowerShell)
# Usage: iwr https://raw.githubusercontent.com/arvindsoni2/jobpilot-v2/main/install.ps1 | iex
# Or locally: .\install.ps1

param (
    [string]$InstallDir = "$env:LOCALAPPDATA\JobPilot"
)

$ErrorActionPreference = "Stop"

function Write-Info  { param($msg) Write-Host "[jobpilot] $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "[jobpilot] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "[jobpilot] $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "[jobpilot] $msg" -ForegroundColor Red; exit 1 }

# ── Prerequisites ──────────────────────────────────────────────────

Write-Info "Checking prerequisites…"

# Docker Desktop or Podman Desktop
$dockerCmd = $null
if (Get-Command "docker" -ErrorAction SilentlyContinue) {
    $dockerCmd = "docker"
    Write-Ok "docker found: $(Get-Command docker | Select-Object -ExpandProperty Source)"
} elseif (Get-Command "podman" -ErrorAction SilentlyContinue) {
    $dockerCmd = "podman"
    Write-Ok "podman found: $(Get-Command podman | Select-Object -ExpandProperty Source)"
} else {
    Write-Fail "docker or podman not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop/"
}

# Docker Compose
$composeCmd = $null
try {
    & $dockerCmd compose version 2>$null | Out-Null
    $composeCmd = "$dockerCmd compose"
    Write-Ok "Compose command: $composeCmd"
} catch {
    if (Get-Command "docker-compose" -ErrorAction SilentlyContinue) {
        $composeCmd = "docker-compose"
        Write-Ok "Compose command: $composeCmd"
    } else {
        Write-Fail "docker compose not found. Update Docker Desktop or install Docker Compose."
    }
}

if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
    Write-Fail "git not found. Install from https://git-scm.com/download/win"
}
Write-Ok "git found."

# ── Clone or update ────────────────────────────────────────────────

if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Info "Existing install found at $InstallDir — updating…"
    git -C $InstallDir pull --ff-only
} else {
    Write-Info "Cloning JobPilot v2 to $InstallDir…"
    git clone https://github.com/arvindsoni2/jobpilot-v2.git $InstallDir
}

Set-Location $InstallDir

# ── Data directory ─────────────────────────────────────────────────

if (-not (Test-Path "data")) { New-Item -ItemType Directory -Path "data" | Out-Null }

if (-not (Test-Path "data\profile.yaml") -and (Test-Path "examples\profile_uk_contractor.yaml")) {
    Write-Info "Creating data\profile.yaml from UK contractor example…"
    Copy-Item "examples\profile_uk_contractor.yaml" "data\profile.yaml"
    Write-Warn "Edit data\profile.yaml with your own details before starting."
}

# ── .env file ──────────────────────────────────────────────────────

if (-not (Test-Path ".env")) {
    Write-Info "Creating .env from template…"
    @"
# LLM provider - uncomment the one you want to use.
# You can also add/update keys via the Settings → AI Provider tab in the UI.
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=AIza...
# For Ollama (local, free) — no key needed. Set llm.provider: ollama in profile.yaml.

# Optional tuning
# SCRAPE_INTERVAL_HOURS=4
# SCORE_THRESHOLD=0.75
# LOG_LEVEL=INFO
"@ | Out-File -Encoding UTF8 ".env"
    Write-Warn ".env created. Add at least one LLM provider key, or use Settings → AI Provider after first start."
}

# ── Build & start ──────────────────────────────────────────────────

Write-Info "Building containers (first run may take 2–3 minutes)…"
Invoke-Expression "$composeCmd build"

Write-Info "Starting JobPilot…"
Invoke-Expression "$composeCmd up -d"

# ── Done ───────────────────────────────────────────────────────────

Write-Host ""
Write-Ok "JobPilot v2 is running!"
Write-Host ""
Write-Host "  Dashboard:  http://localhost:3000"
Write-Host "  API docs:   http://localhost:8000/docs"
Write-Host ""
Write-Warn "If this is your first run, the onboarding wizard will appear automatically."
Write-Host ""
Write-Host "  Manage:  Set-Location $InstallDir; $composeCmd ps"
Write-Host "  Logs:    Set-Location $InstallDir; $composeCmd logs -f"
Write-Host "  Stop:    Set-Location $InstallDir; $composeCmd down"
Write-Host ""

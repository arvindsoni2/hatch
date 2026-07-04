#Requires -Version 5.1
# Hatch one-command installer for Windows PowerShell.
# Usage: iwr https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.ps1 | iex

param (
    [string]$InstallDir = "$env:LOCALAPPDATA\Hatch",
    [ValidateSet("AiLater", "Cloud", "Local", "Advanced")]
    [string]$Mode
)

$ErrorActionPreference = "Stop"

function Write-Info { param($Message) Write-Host "[hatch] $Message" -ForegroundColor Cyan }
function Write-Ok { param($Message) Write-Host "[hatch] $Message" -ForegroundColor Green }
function Write-Warn { param($Message) Write-Host "[hatch] $Message" -ForegroundColor Yellow }
function Write-Fail { param($Message) Write-Host "[hatch] $Message" -ForegroundColor Red; exit 1 }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail "Docker Desktop is required: https://www.docker.com/products/docker-desktop/"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Fail "Git is required: https://git-scm.com/download/win"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Fail "Python 3.10 or newer is required: https://www.python.org/downloads/windows/"
}

try {
    docker compose version | Out-Null
} catch {
    Write-Fail "Docker Compose is unavailable. Start or update Docker Desktop."
}

if (-not $Mode) {
    if ($env:CI -or [Console]::IsInputRedirected) {
        $Mode = "AiLater"
    } else {
        $Choice = Read-Host "AI setup: [1] later (recommended), [2] cloud, [3] local, [4] advanced"
        $Mode = switch ($Choice) {
            "2" { "Cloud" }
            "3" { "Local" }
            "4" { "Advanced" }
            default { "AiLater" }
        }
    }
}

if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Info "Updating the existing install at $InstallDir"
    git -C $InstallDir pull --ff-only
} else {
    Write-Info "Cloning Hatch to $InstallDir"
    git clone https://github.com/arvindsoni2/hatch.git $InstallDir
}

Set-Location $InstallDir
$HatchHome = if ($env:HATCH_HOME) { $env:HATCH_HOME } else { Join-Path $env:USERPROFILE ".hatch" }
$env:HATCH_HOME = $HatchHome
@("bin", "config", "models", "probe", "logs", "backups") | ForEach-Object {
    New-Item -ItemType Directory -Force -Path (Join-Path $HatchHome $_) | Out-Null
}
$InstallState = @{
    schema_version = 1
    managed = $true
    source_dir = $InstallDir
    installed_mode = $Mode
} | ConvertTo-Json
$InstallState | Set-Content (Join-Path $HatchHome "config\install.json")
Copy-Item (Join-Path $InstallDir "hatch.ps1") (Join-Path $HatchHome "bin\hatch.ps1") -Force

if (-not (Test-Path "data\profile.yaml")) {
    if (Test-Path "data\profile.yaml.example") {
        Copy-Item "data\profile.yaml.example" "data\profile.yaml"
    } else {
        Write-Fail "data\profile.yaml.example is missing. Re-clone Hatch before installing."
    }
    Write-Warn "Complete onboarding in the browser or edit data\profile.yaml."
}

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
    } else {
        Write-Fail ".env.example is missing. Re-clone Hatch before installing."
    }
}

Write-Info "Building Hatch containers"
docker compose -f docker-compose.easy.yml up -d --build
if ($Mode -eq "Local") {
    & (Join-Path $HatchHome "bin\hatch.ps1") probe
    & (Join-Path $HatchHome "bin\hatch.ps1") models install
} elseif ($Mode -eq "Cloud") {
    Write-Info "Choose a provider in Hatch, then run: hatch secrets set <provider>"
}

Write-Host ""
Write-Ok "Hatch is running"
Write-Host "  Dashboard: http://localhost:3000"
Write-Host "  API docs:  http://localhost:8000/docs"
Write-Host "  CLI:       $HatchHome\bin\hatch.ps1 status"

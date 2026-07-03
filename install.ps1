#Requires -Version 5.1
# Hatch one-command installer for Windows PowerShell.
# Usage: iwr https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.ps1 | iex

param (
    [string]$InstallDir = "$env:LOCALAPPDATA\Hatch"
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

try {
    docker compose version | Out-Null
} catch {
    Write-Fail "Docker Compose is unavailable. Start or update Docker Desktop."
}

if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Info "Updating the existing install at $InstallDir"
    git -C $InstallDir pull --ff-only
} else {
    Write-Info "Cloning Hatch to $InstallDir"
    git clone https://github.com/arvindsoni2/hatch.git $InstallDir
}

Set-Location $InstallDir
New-Item -ItemType Directory -Force -Path "data\models" | Out-Null

$Models = @(
    @{
        Name = "Qwen3-8B-Q5_K_M.gguf"
        Url = "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q5_K_M.gguf"
    },
    @{
        Name = "Qwen3-0.6B-Q8_0.gguf"
        Url = "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf"
    }
)

foreach ($Model in $Models) {
    $Destination = Join-Path "data\models" $Model.Name
    if ((Test-Path $Destination) -and ((Get-Item $Destination).Length -gt 0)) {
        Write-Ok "$($Model.Name) already exists"
    } else {
        $Partial = "$Destination.part"
        Write-Info "Downloading $($Model.Name). This is a one-time download."
        if (Test-Path $Partial) {
            Remove-Item $Partial -Force
        }
        Invoke-WebRequest -Uri $Model.Url -OutFile $Partial -UseBasicParsing
        if ((-not (Test-Path $Partial)) -or ((Get-Item $Partial).Length -eq 0)) {
            Write-Fail "Downloaded $($Model.Name), but the file is empty. Re-run the installer to retry."
        }
        Move-Item $Partial $Destination -Force
    }
}

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
docker compose build
Write-Info "Starting Hatch"
docker compose up -d

Write-Host ""
Write-Ok "Hatch is running"
Write-Host "  Dashboard: http://localhost:3000"
Write-Host "  API docs:  http://localhost:8000/docs"
Write-Host "  Logs:      docker compose logs -f"

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
        Name = "Qwen3-4B-Q4_0.gguf"
        Url = "https://huggingface.co/unsloth/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_0.gguf"
    },
    @{
        Name = "Qwen3-0.6B-Q4_0.gguf"
        Url = "https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_0.gguf"
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
        @'
locale: "uk"
candidate:
  name: ""
  title: ""
  years_experience: 0
  summary: ""
search:
  target_roles: []
  locations: []
  contract_type: "any"
compensation:
  min_rate: 0
  max_rate: 0
  rate_type: "daily"
  currency: ""
  legal_preferences: {}
skills:
  primary: []
  secondary: []
  certifications: []
domains:
  preferred: []
  excluded: []
proof_points: []
master_cv_path: "./data/master_cv.json"
job_boards: []
scoring:
  weights:
    skill_match: 0.35
    experience_match: 0.30
    rate_match: 0.20
    location_match: 0.15
  shortlist_threshold: 0.75
  method: "auto"
tailoring:
  ats_target_score: 80
  ats_retry_limit: 1
llm:
  provider: "llamacpp"
  triage_model: "qwen3-0.6b-q4_0"
  primary_model: "qwen3-4b-q4_0"
  base_url: "http://llm-primary:8080/v1"
  triage_base_url: "http://llm-triage:8081/v1"
  api_key_env: ""
  temperature: 0.3
  max_retries: 3
  track_costs: false
  monthly_budget: 0.0
  currency: ""
preferences:
  scrape_interval_hours: 4
  max_tailor_batch: 5
  follow_up_days: [5, 10, 15]
  archive_after_days: 30
outcome_learning:
  enabled: true
  minimum_total_applications: 15
  minimum_segment_size: 5
  maximum_score_adjustment: 0.10
  maximum_signal_adjustment: 0.04
  no_response_after_days: 35
  recency_half_life_days: 120
  enabled_signals: [source, role_family, seniority, working_pattern, employment_type, freshness]
  learning_since: null
'@ | Set-Content -Encoding UTF8 "data\profile.yaml"
    }
    Write-Warn "Complete onboarding in the browser or edit data\profile.yaml."
}

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
    } else {
        @'
# Hatch uses bundled Local AI (llama.cpp) by default — no API key required.
# To use a cloud provider instead, uncomment one of the keys below
# and select the provider during onboarding or in Settings:
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=AIza...

# Optional tuning
# SCRAPE_INTERVAL_HOURS=4
# SCORE_THRESHOLD=0.75
# LOG_LEVEL=INFO
'@ | Set-Content -Encoding UTF8 ".env"
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

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Equal {
    param($Expected, $Actual, [string]$Message)
    if ($Expected -ne $Actual) {
        throw "$Message Expected '$Expected' but got '$Actual'."
    }
}

function Assert-Contains {
    param([object[]]$Values, $Expected, [string]$Message)
    if ($Values -notcontains $Expected) {
        throw "$Message Missing '$Expected'. Values: $($Values -join ', ')"
    }
}

function Invoke-Test {
    param([string]$Name, [scriptblock]$Body)
    try {
        & $Body
        Write-Host "[PASS] $Name" -ForegroundColor Green
    } catch {
        Write-Host "[FAIL] $Name" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        throw
    }
}

$env:HATCH_INSTALL_TEST_MODE = "1"
. (Join-Path $RepoRoot "install.ps1")

Invoke-Test "preflight reports all prerequisite states instead of stopping at Docker" {
    $mock = @{
        platform = @{
            is_windows = $true
            caption = "Microsoft Windows 11 Pro"
            version = "10.0.26100"
            architecture = "x64"
            powershell_version = "5.1.26100.1"
            is_admin = $false
            restart_required = $false
            virtualization_enabled = $true
            wsl_installed = $true
            wsl2_available = $true
        }
        commands = @{
            docker = $false
            git = $false
            python = $true
            winget = $true
        }
        docker = @{
            desktop_installed = $false
            desktop_running = $false
            engine_ready = $false
            compose_available = $false
            linux_containers = $false
        }
        network = @{
            github = $true
            registry = $true
        }
        disk = @{
            install_free_gb = 40
            models_free_gb = 40
        }
        ports = @{
            frontend_available = $true
            backend_available = $true
        }
        filesystem = @{
            install_write = $true
            state_write = $true
        }
        install_state = @{
            status = "none"
        }
    }

    $result = Invoke-HatchPreflight -Mode "AiLater" -BackendProfile "core" -MockState $mock
    $ids = @($result.checks | ForEach-Object { $_.id })
    Assert-Contains $ids "docker.desktop.installed" "Docker Desktop check should be present."
    Assert-Contains $ids "docker.engine.ready" "Docker engine check should still be present."
    Assert-Contains $ids "git.available" "Git check should still be present."
    Assert-Contains $ids "ports.frontend" "Port check should still be present."

    $byId = @{}
    foreach ($check in $result.checks) { $byId[$check.id] = $check }
    Assert-Equal "fail" $byId["docker.desktop.installed"].status "Missing Docker Desktop should fail."
    Assert-Equal "blocked" $byId["docker.engine.ready"].status "Docker engine should be blocked when Docker Desktop is absent."
    Assert-Equal "fail" $byId["git.available"].status "Missing Git should fail."
    Assert-Equal $false $result.ready "Result should not be ready."
}

Invoke-Test "preflight emits stable JSON-ready schema and deterministic exit code" {
    $mock = @{
        platform = @{
            is_windows = $true
            caption = "Microsoft Windows 11 Pro"
            version = "10.0.26100"
            architecture = "x64"
            powershell_version = "7.5.0"
            is_admin = $false
            restart_required = $true
            virtualization_enabled = $true
            wsl_installed = $true
            wsl2_available = $true
        }
        commands = @{
            docker = $true
            git = $true
            python = $true
            winget = $true
        }
        docker = @{
            desktop_installed = $true
            desktop_running = $true
            engine_ready = $true
            compose_available = $true
            linux_containers = $true
        }
        network = @{
            github = $true
            registry = $true
        }
        disk = @{
            install_free_gb = 40
            models_free_gb = 40
        }
        ports = @{
            frontend_available = $true
            backend_available = $true
        }
        filesystem = @{
            install_write = $true
            state_write = $true
        }
        install_state = @{
            status = "none"
        }
    }

    $result = Invoke-HatchPreflight -Mode "AiLater" -BackendProfile "core" -MockState $mock
    $json = $result | ConvertTo-Json -Depth 8
    Assert-True ($json -match '"schema_version":') "JSON result should include schema_version."
    Assert-True ($json -match '"platform":') "JSON result should include platform."
    Assert-True ($json -match '"checks":') "JSON result should include checks."
    Assert-Equal 3 (Get-HatchInstallerExitCode -Result $result) "Restart-required result should use exit code 3."
}

Invoke-Test "redaction removes secret-like values from installer logs" {
    $text = "OPENAI_API_KEY=sk-live-secret PASSWORD=abc123 token: bearer-value normal text"
    $redacted = Redact-HatchLogText -Text $text
    Assert-True ($redacted -notmatch "sk-live-secret") "API key value should be redacted."
    Assert-True ($redacted -notmatch "abc123") "Password value should be redacted."
    Assert-True ($redacted -notmatch "bearer-value") "Token value should be redacted."
    Assert-True ($redacted -match "normal text") "Non-secret text should be preserved."
}

Invoke-Test "bootstrap cmd exists and declares local-or-remote pinned source contract" {
    $path = Join-Path $RepoRoot "install-hatch.cmd"
    Assert-True (Test-Path $path) "install-hatch.cmd should exist."
    $content = Get-Content $path -Raw
    Assert-True ($content -match "HATCH_REPO_REF") "Bootstrapper should centralise the repository reference."
    Assert-True ($content -match "install.ps1") "Bootstrapper should launch install.ps1."
    Assert-True ($content -match "pwsh.exe") "Bootstrapper should prefer PowerShell 7 when available."
    Assert-True ($content -match "powershell.exe") "Bootstrapper should fall back to Windows PowerShell 5.1."
}

Invoke-Test "hatch.ps1 resolves CLI from managed install config instead of wrapper directory only" {
    $content = Get-Content (Join-Path $RepoRoot "hatch.ps1") -Raw
    Assert-True ($content -match "install.json") "Wrapper should read managed install metadata."
    Assert-True ($content -match "source_dir") "Wrapper should use the managed source_dir."
    Assert-True ($content -match "scripts\\hatch_cli.py") "Wrapper should resolve the Python CLI inside the managed checkout."
}

Invoke-Test "check-only non-interactive run exits deterministically without cloning install directory" {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hatch-installer-test-$([guid]::NewGuid().ToString('N'))"
    $hatchHomePath = Join-Path $tempRoot "home"
    $install = Join-Path $tempRoot "Managed Hatch"
    New-Item -ItemType Directory -Force -Path $hatchHomePath | Out-Null
    $oldHome = $env:HATCH_HOME
    $oldTestMode = $env:HATCH_INSTALL_TEST_MODE
    try {
        $env:HATCH_HOME = $hatchHomePath
        Remove-Item Env:\HATCH_INSTALL_TEST_MODE -ErrorAction SilentlyContinue
        $expectedResult = Invoke-HatchPreflight -Mode "AiLater" -BackendProfile "core" -InstallDir $install
        $expectedExitCode = Get-HatchInstallerExitCode -Result $expectedResult
        $process = Start-Process -FilePath "pwsh" -ArgumentList @(
            "-NoLogo", "-NoProfile", "-File", (Join-Path $RepoRoot "install.ps1"),
            "-CheckOnly", "-NonInteractive", "-Json",
            "-InstallDir", $install,
            "-Mode", "ai-later",
            "-BackendProfile", "core"
        ) -Wait -PassThru -NoNewWindow
        Assert-Equal $expectedExitCode $process.ExitCode "CheckOnly should return the same exit code as the live preflight result for this host."
        Assert-True (-not (Test-Path $install)) "CheckOnly must not clone or create the install directory."
        Assert-True (Test-Path (Join-Path $hatchHomePath "installer\last-check.json")) "CheckOnly should persist the last preflight report."
    } finally {
        if ($oldHome) { $env:HATCH_HOME = $oldHome } else { Remove-Item Env:\HATCH_HOME -ErrorAction SilentlyContinue }
        if ($oldTestMode) { $env:HATCH_INSTALL_TEST_MODE = $oldTestMode } else { Remove-Item Env:\HATCH_INSTALL_TEST_MODE -ErrorAction SilentlyContinue }
        Remove-Item -Recurse -Force $tempRoot -ErrorAction SilentlyContinue
    }
}

Invoke-Test "copied hatch.ps1 wrapper runs CLI from configured source_dir with spaces" {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hatch-wrapper-test-$([guid]::NewGuid().ToString('N'))"
    $hatchHomePath = Join-Path $tempRoot "home"
    $managed = Join-Path $tempRoot "Managed Hatch Source"
    $scripts = Join-Path $managed "scripts"
    New-Item -ItemType Directory -Force -Path $scripts | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $hatchHomePath "config") | Out-Null
    @"
import sys
print("FAKE_CLI:" + " ".join(sys.argv[1:]))
"@ | Set-Content (Join-Path $scripts "hatch_cli.py")
    @{
        schema_version = 1
        managed = $true
        source_dir = $managed
    } | ConvertTo-Json | Set-Content (Join-Path $hatchHomePath "config\install.json")
    $oldHome = $env:HATCH_HOME
    try {
        $env:HATCH_HOME = $hatchHomePath
        $output = pwsh -NoLogo -NoProfile -File (Join-Path $RepoRoot "hatch.ps1") status
        Assert-True (($output -join "`n") -match "FAKE_CLI:status") "Wrapper should invoke the CLI from source_dir even when the path contains spaces."
    } finally {
        if ($oldHome) { $env:HATCH_HOME = $oldHome } else { Remove-Item Env:\HATCH_HOME -ErrorAction SilentlyContinue }
        Remove-Item -Recurse -Force $tempRoot -ErrorAction SilentlyContinue
    }
}

Remove-Item Env:\HATCH_INSTALL_TEST_MODE -ErrorAction SilentlyContinue

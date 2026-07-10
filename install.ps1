#Requires -Version 5.1
# Hatch guided installer for Windows PowerShell and PowerShell 7.
# Recommended Windows entry point: install-hatch.cmd

param (
    [string]$InstallDir = "$env:LOCALAPPDATA\Hatch",
    [string]$Mode,
    [string]$BackendProfile,
    [switch]$CheckOnly,
    [switch]$NonInteractive,
    [switch]$AutoInstallPrerequisites,
    [switch]$Resume,
    [switch]$Json,
    [switch]$VerboseLog
)

$ErrorActionPreference = "Stop"

$script:HatchInstaller = @{
    SchemaVersion = 1
    RepoUrl = "https://github.com/arvindsoni2/hatch.git"
    RawBaseUrl = "https://raw.githubusercontent.com/arvindsoni2/hatch"
    RepoRef = "main"
    FrontendPort = 3000
    BackendPort = 8000
    MinDiskCoreGb = 8
    MinDiskFullGb = 20
    ExitCodes = @{
        Success = 0
        PrerequisitesMissing = 2
        RestartRequired = 3
        Unsupported = 4
        ExistingInstallManualRecovery = 5
        NetworkFailure = 6
        DockerStartFailure = 7
        InvalidArguments = 8
        Unexpected = 10
    }
    WingetPackages = @{
        git = @{
            id = "Git.Git"
            name = "Git"
            publisher = "The Git Development Community"
        }
        python = @{
            id = "Python.Python.3.12"
            name = "Python 3.12"
            publisher = "Python Software Foundation"
        }
        docker = @{
            id = "Docker.DockerDesktop"
            name = "Docker Desktop"
            publisher = "Docker Inc."
        }
    }
}

function Write-Info { param([string]$Message) Write-Host "[hatch] $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "[hatch] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[hatch] $Message" -ForegroundColor Yellow }
function Write-FailMessage { param([string]$Message) Write-Host "[hatch] $Message" -ForegroundColor Red }

function Resolve-HatchInstallMode {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return "AiLater" }
    switch -Regex ($Value) {
        "^(?i:ai-?later|ailater)$" { return "AiLater" }
        "^(?i:cloud)$" { return "Cloud" }
        "^(?i:local)$" { return "Local" }
        "^(?i:advanced)$" { return "Advanced" }
        default { throw "Unsupported mode '$Value'. Use ai-later, cloud, local, or advanced." }
    }
}

function Resolve-HatchBackendProfile {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return "core" }
    switch -Regex ($Value) {
        "^(?i:core)$" { return "core" }
        "^(?i:browser)$" { return "browser" }
        "^(?i:local-?embeddings)$" { return "local-embeddings" }
        "^(?i:full)$" { return "full" }
        default { throw "Unsupported backend profile '$Value'. Use core, browser, local-embeddings, LocalEmbeddings, or full." }
    }
}

function Get-HatchHome {
    if ($env:HATCH_HOME) { return $env:HATCH_HOME }
    return (Join-Path $env:USERPROFILE ".hatch")
}

function Get-HatchInstallerDir {
    param([string]$HatchHome)
    return (Join-Path $HatchHome "installer")
}

function New-HatchCheck {
    param(
        [string]$Id,
        [ValidateSet("pass", "warning", "fail", "blocked", "skipped")]
        [string]$Status,
        [string]$Summary,
        [string]$Detail = "",
        [string]$ActionId = "",
        [string]$DocsAnchor = ""
    )
    [ordered]@{
        id = $Id
        status = $Status
        summary = $Summary
        detail = $Detail
        action_id = $ActionId
        docs_anchor = $DocsAnchor
    }
}

function Redact-HatchLogText {
    param([string]$Text)
    if ($null -eq $Text) { return "" }
    $redacted = $Text
    $redacted = [regex]::Replace($redacted, "(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*(`"[^`"]*`"|'[^']*'|\S+)", '$1=<redacted>')
    $redacted = [regex]::Replace($redacted, "(?i)(bearer)\s+[A-Za-z0-9._~+/\-=]+", '$1 <redacted>')
    $redacted = [regex]::Replace($redacted, "sk-[A-Za-z0-9._-]+", "sk-<redacted>")
    return $redacted
}

function Write-HatchInstallerLog {
    param([string]$LogPath, [string]$Message)
    if (-not $LogPath) { return }
    $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"), (Redact-HatchLogText $Message)
    Add-Content -Path $LogPath -Value $line
}

function Test-HatchCommand {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-HatchNativeCommand {
    param(
        [string[]]$Command,
        [int]$TimeoutSeconds = 10
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Command[0]
    for ($i = 1; $i -lt $Command.Count; $i++) {
        [void]$psi.ArgumentList.Add($Command[$i])
    }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $process = [System.Diagnostics.Process]::Start($psi)
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $process.Kill() } catch {}
        return @{ exit_code = 124; stdout = ""; stderr = "Timed out" }
    }
    return @{
        exit_code = $process.ExitCode
        stdout = $process.StandardOutput.ReadToEnd()
        stderr = $process.StandardError.ReadToEnd()
    }
}

function Test-HatchPortAvailable {
    param([int]$Port)
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        $listener.Stop()
        return $true
    } catch {
        return $false
    }
}

function Test-HatchNetworkEndpoint {
    param([string]$Uri)
    try {
        $request = [System.Net.WebRequest]::Create($Uri)
        $request.Method = "HEAD"
        $request.Timeout = 5000
        $response = $request.GetResponse()
        $response.Close()
        return $true
    } catch {
        return $false
    }
}

function Test-HatchRestartRequired {
    if (-not $IsWindows -and $PSVersionTable.PSVersion.Major -ge 6) { return $false }
    if ($env:HATCH_RESTART_REQUIRED -eq "1") { return $true }
    $keys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
    )
    foreach ($key in $keys) {
        if (Test-Path $key) { return $true }
    }
    return $false
}

function Get-HatchDiskFreeGb {
    param([string]$Path)
    try {
        $root = [System.IO.Path]::GetPathRoot((Resolve-Path -LiteralPath (Split-Path -Parent $Path) -ErrorAction SilentlyContinue))
        if (-not $root) { $root = [System.IO.Path]::GetPathRoot($Path) }
        $drive = Get-PSDrive -Name $root.TrimEnd(":\") -ErrorAction SilentlyContinue
        if ($drive) { return [math]::Round($drive.Free / 1GB, 2) }
    } catch {}
    return 0
}

function Get-HatchInstallStateStatus {
    param([string]$InstallDir)
    if (Test-Path (Join-Path $InstallDir ".git")) {
        $dirty = $false
        try {
            $status = Invoke-HatchNativeCommand -Command @("git", "-C", $InstallDir, "status", "--porcelain") -TimeoutSeconds 10
            $dirty = ($status.exit_code -eq 0 -and -not [string]::IsNullOrWhiteSpace($status.stdout))
        } catch {}
        if ($dirty) { return "dirty-managed" }
        return "managed"
    }
    if (Test-Path $InstallDir) { return "unmanaged" }
    return "none"
}

function Get-HatchPreflightState {
    param(
        [string]$InstallDir,
        [string]$Mode,
        [string]$BackendProfile
    )
    $dockerCommand = Test-HatchCommand "docker"
    $dockerInfo = @{ exit_code = 1; stdout = ""; stderr = "docker unavailable" }
    $dockerCompose = @{ exit_code = 1; stdout = ""; stderr = "docker unavailable" }
    if ($dockerCommand) {
        $dockerInfo = Invoke-HatchNativeCommand -Command @("docker", "info", "--format", "{{json .}}") -TimeoutSeconds 12
        $dockerCompose = Invoke-HatchNativeCommand -Command @("docker", "compose", "version") -TimeoutSeconds 12
    }

    $isWindowsHost = $false
    if ($PSVersionTable.PSVersion.Major -ge 6) {
        $isWindowsHost = [bool]$IsWindows
    } else {
        $isWindowsHost = ($env:OS -eq "Windows_NT")
    }

    $desktopInstalled = $false
    if ($isWindowsHost) {
        $desktopInstalled = [bool](Get-Command "Docker Desktop.exe" -ErrorAction SilentlyContinue)
        if (-not $desktopInstalled) {
            $desktopInstalled = Test-Path "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
        }
    }
    $desktopRunning = $false
    if ($isWindowsHost) {
        $desktopRunning = [bool](Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)
    }
    if ($desktopRunning) { $desktopInstalled = $true }
    if ($dockerInfo.exit_code -eq 0) { $desktopRunning = $true }

    $wslInstalled = $false
    $wsl2Available = $false
    if ($isWindowsHost -and (Test-HatchCommand "wsl")) {
        $wslInstalled = $true
        $wslStatus = Invoke-HatchNativeCommand -Command @("wsl", "--status") -TimeoutSeconds 10
        $wsl2Available = ($wslStatus.exit_code -eq 0)
    }

    $osDescription = $null
    try {
        if ($isWindowsHost) {
            $osDescription = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
        }
    } catch {}
    if (-not $osDescription) {
        try { $osDescription = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription } catch { $osDescription = [System.Environment]::OSVersion.VersionString }
    }
    $osArchitecture = $env:PROCESSOR_ARCHITECTURE
    try { $osArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() } catch {}

    $state = @{
        platform = @{
            is_windows = $isWindowsHost
            caption = $osDescription
            version = [System.Environment]::OSVersion.Version.ToString()
            architecture = $osArchitecture
            powershell_version = $PSVersionTable.PSVersion.ToString()
            is_admin = $false
            restart_required = Test-HatchRestartRequired
            virtualization_enabled = $true
            wsl_installed = $wslInstalled
            wsl2_available = $wsl2Available
        }
        commands = @{
            docker = $dockerCommand
            git = Test-HatchCommand "git"
            python = ((Test-HatchCommand "python") -or (Test-HatchCommand "py"))
            winget = Test-HatchCommand "winget"
        }
        docker = @{
            desktop_installed = $desktopInstalled
            desktop_running = $desktopRunning
            engine_ready = ($dockerInfo.exit_code -eq 0)
            compose_available = ($dockerCompose.exit_code -eq 0)
            linux_containers = ($dockerInfo.exit_code -eq 0 -and ($dockerInfo.stdout -match "(?i)OSType.*linux|linux"))
        }
        network = @{
            github = Test-HatchNetworkEndpoint "https://github.com"
            registry = Test-HatchNetworkEndpoint "https://ghcr.io"
        }
        disk = @{
            install_free_gb = Get-HatchDiskFreeGb -Path $InstallDir
            models_free_gb = Get-HatchDiskFreeGb -Path (Join-Path (Get-HatchHome) "models")
        }
        ports = @{
            frontend_available = Test-HatchPortAvailable -Port $script:HatchInstaller.FrontendPort
            backend_available = Test-HatchPortAvailable -Port $script:HatchInstaller.BackendPort
        }
        filesystem = @{
            install_write = Test-HatchDirectoryWritable -Path (Split-Path -Parent $InstallDir)
            state_write = Test-HatchDirectoryWritable -Path (Get-HatchInstallerDir -HatchHome (Get-HatchHome))
        }
        install_state = @{
            status = Get-HatchInstallStateStatus -InstallDir $InstallDir
        }
    }
    return $state
}

function Test-HatchDirectoryWritable {
    param([string]$Path)
    try {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
        $testPath = Join-Path $Path ".hatch-write-test-$([guid]::NewGuid().ToString('N'))"
        Set-Content -Path $testPath -Value "test"
        Remove-Item -Path $testPath -Force
        return $true
    } catch {
        return $false
    }
}

function Invoke-HatchPreflight {
    param(
        [string]$Mode = "AiLater",
        [string]$BackendProfile = "core",
        [string]$InstallDir = "$env:LOCALAPPDATA\Hatch",
        [hashtable]$MockState
    )

    $state = if ($MockState) { $MockState } else { Get-HatchPreflightState -InstallDir $InstallDir -Mode $Mode -BackendProfile $BackendProfile }
    $checks = New-Object System.Collections.ArrayList

    $platform = $state.platform
    [void]$checks.Add((New-HatchCheck "windows.version" ($(if ($platform.is_windows) { "pass" } else { "fail" })) $platform.caption "Hatch's guided installer currently supports Windows." "" "windows-version"))
    [void]$checks.Add((New-HatchCheck "powershell.runtime" ($(if ($platform.powershell_version -match "^(5\.1|[7-9]\.)") { "pass" } else { "fail" })) "PowerShell $($platform.powershell_version)" "Windows PowerShell 5.1 or supported PowerShell 7 is required." "" "powershell-not-found"))
    [void]$checks.Add((New-HatchCheck "process.architecture" ($(if ($platform.architecture -match "(?i)x64|x86_64|arm64") { "pass" } else { "fail" })) $platform.architecture "Hatch supports 64-bit Windows hosts."))
    [void]$checks.Add((New-HatchCheck "admin.elevation" "pass" "No permanent administrator session required" "Elevation is requested only for explicit prerequisite repair actions."))
    [void]$checks.Add((New-HatchCheck "virtualization.enabled" ($(if ($platform.virtualization_enabled) { "pass" } else { "fail" })) "Hardware virtualisation" "Docker Desktop requires virtualisation." "enable-virtualization" "virtualisation"))
    [void]$checks.Add((New-HatchCheck "wsl.installed" ($(if ($platform.wsl_installed) { "pass" } elseif (-not $state.docker.desktop_installed) { "blocked" } else { "fail" })) "WSL availability" "Docker Desktop on Windows may require WSL 2." "enable-wsl" "wsl-2-unavailable"))
    [void]$checks.Add((New-HatchCheck "wsl.version" ($(if ($platform.wsl2_available) { "pass" } elseif (-not $platform.wsl_installed) { "blocked" } else { "fail" })) "WSL 2 readiness" "WSL 2 must be available when Docker Desktop uses the WSL backend." "update-wsl" "wsl-2-unavailable"))

    [void]$checks.Add((New-HatchCheck "docker.cli.available" ($(if ($state.commands.docker) { "pass" } else { "fail" })) "Docker CLI" "Docker Desktop installs the Docker CLI." "install-docker-desktop" "windows-docker-desktop"))
    [void]$checks.Add((New-HatchCheck "docker.desktop.installed" ($(if ($state.docker.desktop_installed) { "pass" } else { "fail" })) "Docker Desktop" "Hatch uses Linux containers through Docker Desktop." "install-docker-desktop" "windows-docker-desktop"))
    [void]$checks.Add((New-HatchCheck "docker.desktop.running" ($(if ($state.docker.desktop_running) { "pass" } elseif (-not $state.docker.desktop_installed) { "blocked" } else { "fail" })) "Docker Desktop running" "Start Docker Desktop and wait until it reports Docker Engine is running." "start-docker-desktop" "docker-desktop-not-running"))
    [void]$checks.Add((New-HatchCheck "docker.engine.ready" ($(if ($state.docker.engine_ready) { "pass" } elseif (-not $state.docker.desktop_installed) { "blocked" } else { "fail" })) "Docker Engine" "Hatch confirms Docker readiness with docker info." "start-docker-desktop" "docker-engine-not-responding"))
    [void]$checks.Add((New-HatchCheck "docker.container_mode" ($(if ($state.docker.linux_containers) { "pass" } elseif (-not $state.docker.engine_ready) { "blocked" } else { "fail" })) "Linux container mode" "Switch Docker Desktop to Linux containers." "switch-linux-containers" "windows-containers-selected"))
    [void]$checks.Add((New-HatchCheck "docker.compose.available" ($(if ($state.docker.compose_available) { "pass" } elseif (-not $state.docker.engine_ready) { "blocked" } else { "fail" })) "Docker Compose v2" "Docker Compose v2 is required." "install-docker-desktop" "docker-compose-unavailable"))

    [void]$checks.Add((New-HatchCheck "git.available" ($(if ($state.commands.git) { "pass" } else { "fail" })) "Git" "Git is required to clone or update Hatch." "install-git" "windows-git"))
    [void]$checks.Add((New-HatchCheck "python.available" ($(if ($state.commands.python) { "pass" } else { "fail" })) "Python" "Python is required for the host hatch command wrapper." "install-python" "windows-python"))
    [void]$checks.Add((New-HatchCheck "winget.available" ($(if ($state.commands.winget) { "pass" } else { "warning" })) "Windows Package Manager" "winget is optional and only used after explicit consent." "" "winget-unavailable"))
    [void]$checks.Add((New-HatchCheck "network.github" ($(if ($state.network.github) { "pass" } else { "fail" })) "GitHub access" "Hatch source is downloaded from GitHub." "" "network-github"))
    [void]$checks.Add((New-HatchCheck "network.registry" ($(if ($state.network.registry) { "pass" } else { "fail" })) "Container registry access" "Docker images are pulled from container registries." "" "network-registry"))

    $requiredDisk = if ($BackendProfile -eq "full") { $script:HatchInstaller.MinDiskFullGb } else { $script:HatchInstaller.MinDiskCoreGb }
    [void]$checks.Add((New-HatchCheck "disk.core" ($(if ([double]$state.disk.install_free_gb -ge $requiredDisk) { "pass" } else { "fail" })) "$($state.disk.install_free_gb) GB free for install" "Hatch needs at least $requiredDisk GB free for the selected profile." "" "insufficient-disk-space"))
    [void]$checks.Add((New-HatchCheck "disk.local_ai" ($(if ($Mode -eq "Local") { if ([double]$state.disk.models_free_gb -ge 10) { "pass" } else { "fail" } } else { "skipped" })) "$($state.disk.models_free_gb) GB free for models" "Local AI requires additional model storage." "" "insufficient-disk-space"))
    [void]$checks.Add((New-HatchCheck "ports.frontend" ($(if ($state.ports.frontend_available) { "pass" } else { "fail" })) "Port 3000" "The frontend port must be available." "" "ports-already-in-use"))
    [void]$checks.Add((New-HatchCheck "ports.backend" ($(if ($state.ports.backend_available) { "pass" } else { "fail" })) "Port 8000" "The backend port must be available." "" "ports-already-in-use"))
    [void]$checks.Add((New-HatchCheck "install.existing_state" ($(switch ($state.install_state.status) { "unmanaged" { "fail" } "dirty-managed" { "fail" } default { "pass" } })) "Existing installation state" "Managed installs can be updated safely. Dirty or unmanaged directories need manual recovery." "" "installation-interrupted"))
    [void]$checks.Add((New-HatchCheck "filesystem.install_write" ($(if ($state.filesystem.install_write) { "pass" } else { "fail" })) "Install directory write access" "The installer needs write access to the install directory."))
    [void]$checks.Add((New-HatchCheck "filesystem.state_write" ($(if ($state.filesystem.state_write) { "pass" } else { "fail" })) "Hatch state directory write access" "The installer stores non-secret state under HATCH_HOME."))
    [void]$checks.Add((New-HatchCheck "windows.restart" ($(if ($platform.restart_required) { "fail" } else { "pass" })) "Restart state" "A Windows restart is required before continuing." "restart-windows" "restart-required"))

    $blocking = @($checks | Where-Object { $_.status -in @("fail", "blocked") })
    $restartRequired = [bool]$platform.restart_required
    return [ordered]@{
        schema_version = $script:HatchInstaller.SchemaVersion
        platform = "windows"
        ready = ($blocking.Count -eq 0)
        restart_required = $restartRequired
        selected_mode = $Mode
        backend_profile = $BackendProfile
        checks = @($checks)
    }
}

function Get-HatchInstallerExitCode {
    param([hashtable]$Result)
    if ($Result.ready) { return $script:HatchInstaller.ExitCodes.Success }
    if ($Result.restart_required) { return $script:HatchInstaller.ExitCodes.RestartRequired }
    $checks = @($Result.checks)
    if ($checks | Where-Object { $_.id -eq "windows.version" -and $_.status -eq "fail" }) { return $script:HatchInstaller.ExitCodes.Unsupported }
    if ($checks | Where-Object { $_.id -eq "install.existing_state" -and $_.status -eq "fail" }) { return $script:HatchInstaller.ExitCodes.ExistingInstallManualRecovery }
    if ($checks | Where-Object { $_.id -like "network.*" -and $_.status -eq "fail" }) { return $script:HatchInstaller.ExitCodes.NetworkFailure }
    return $script:HatchInstaller.ExitCodes.PrerequisitesMissing
}

function Format-HatchPreflightReport {
    param([hashtable]$Result)
    $lines = New-Object System.Collections.ArrayList
    [void]$lines.Add("Hatch installation readiness")
    [void]$lines.Add("")
    foreach ($check in $Result.checks) {
        $status = $check.status.ToUpperInvariant()
        [void]$lines.Add(("[{0}] {1,-32} {2}" -f $status, $check.id, $check.summary))
        if ($check.status -in @("fail", "blocked", "warning") -and $check.detail) {
            [void]$lines.Add(("       {0}" -f $check.detail))
        }
    }
    [void]$lines.Add("")
    if ($Result.ready) {
        [void]$lines.Add("Hatch is ready to install.")
    } else {
        $required = @($Result.checks | Where-Object { $_.status -in @("fail", "blocked") }).Count
        $warnings = @($Result.checks | Where-Object { $_.status -eq "warning" }).Count
        [void]$lines.Add("Hatch is not ready to install.")
        [void]$lines.Add("$required required actions and $warnings recommendations were found.")
    }
    return ($lines -join [Environment]::NewLine)
}

function Save-HatchInstallerState {
    param(
        [string]$InstallDir,
        [string]$Mode,
        [string]$BackendProfile,
        [string]$Phase,
        [int]$LastExitCode = 0
    )
    $hatchHomePath = Get-HatchHome
    $dir = Get-HatchInstallerDir -HatchHome $hatchHomePath
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $state = [ordered]@{
        schema_version = 1
        installer_ref = $script:HatchInstaller.RepoRef
        selected_install_dir = $InstallDir
        selected_ai_mode = $Mode
        selected_backend_profile = $BackendProfile
        completed_phases = @($Phase)
        pending_prerequisite_reason = $null
        updated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        last_failure_code = $LastExitCode
    }
    $state | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $dir "state.json")
}

function Save-HatchPreflightResult {
    param([hashtable]$Result)
    $dir = Get-HatchInstallerDir -HatchHome (Get-HatchHome)
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $Result | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $dir "last-check.json")
}

function Invoke-HatchWingetInstall {
    param([string]$PackageKey)
    $package = $script:HatchInstaller.WingetPackages[$PackageKey]
    if (-not $package) { throw "Unsupported package key: $PackageKey" }
    $command = "winget install --id $($package.id) --exact"
    Write-Host ""
    Write-Warn "Hatch can ask winget to install $($package.name) from $($package.publisher)."
    Write-Host "Command: $command"
    $answer = Read-Host "Run this command now? Type yes to continue"
    if ($answer -ne "yes") {
        Write-Warn "Skipped $($package.name) installation."
        return @{ attempted = $false; exit_code = $null }
    }
    $result = Invoke-HatchNativeCommand -Command @("winget", "install", "--id", $package.id, "--exact") -TimeoutSeconds 1800
    Write-Info "$($package.name) installation command completed with exit code $($result.exit_code). Rerun preflight before continuing."
    return @{ attempted = $true; exit_code = $result.exit_code }
}

function Invoke-HatchGuidedRemediation {
    param([hashtable]$Result)
    $packageActions = @($Result.checks | Where-Object { $_.action_id -in @("install-docker-desktop", "install-git", "install-python") })
    if ($packageActions.Count -eq 0) { return }
    if (-not (Test-HatchCommand "winget")) {
        Write-Warn "winget is unavailable. Open the troubleshooting guide and install prerequisites manually."
        return
    }
    Write-Host ""
    Write-Host "Guided prerequisite options:"
    Write-Host "1. Install supported missing prerequisites"
    Write-Host "2. Open setup instructions"
    Write-Host "3. Check again"
    Write-Host "4. Save report"
    Write-Host "5. Exit"
    $choice = Read-Host "Choose an option"
    if ($choice -ne "1") { return }
    $actions = @{}
    foreach ($check in $packageActions) {
        switch ($check.action_id) {
            "install-docker-desktop" { $actions["docker"] = $true }
            "install-git" { $actions["git"] = $true }
            "install-python" { $actions["python"] = $true }
        }
    }
    foreach ($key in $actions.Keys) {
        Invoke-HatchWingetInstall -PackageKey $key | Out-Null
    }
}

function Get-HatchBackendEnabled {
    param([string]$Profile)
    switch ($Profile) {
        "core" { return @() }
        "browser" { return @("browser") }
        "local-embeddings" { return @("local-embeddings") }
        "full" { return @("browser", "local-embeddings", "perception", "advanced-coach") }
    }
}

function Write-HatchBackendCapabilities {
    param([string]$Profile, [string]$HatchHome)
    $payload = [ordered]@{
        schema_version = 1
        profile = $Profile
        enabled = @(Get-HatchBackendEnabled $Profile)
        updated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        updated_by = "install"
    }
    $path = Join-Path $HatchHome "config\backend_capabilities.json"
    $payload | ConvertTo-Json -Depth 4 | Set-Content $path
}

function Get-HatchComposeArgsForBackendProfile {
    param([string]$Profile)
    $args = @("-f", "docker-compose.easy.yml")
    switch ($Profile) {
        "browser" { $args += @("-f", "docker-compose.browser.yml") }
        "local-embeddings" { $args += @("-f", "docker-compose.local-embeddings.yml") }
        "full" { $args += @("-f", "docker-compose.full.yml") }
    }
    return $args
}

function Invoke-HatchInstall {
    param(
        [string]$InstallDir,
        [string]$Mode,
        [string]$BackendProfile,
        [string]$LogPath
    )
    if (Test-Path (Join-Path $InstallDir ".git")) {
        Write-Info "Updating the existing managed install at $InstallDir"
        Write-HatchInstallerLog $LogPath "git -C $InstallDir pull --ff-only"
        git -C $InstallDir pull --ff-only
    } else {
        Write-Info "Cloning Hatch to $InstallDir"
        Write-HatchInstallerLog $LogPath "git clone $($script:HatchInstaller.RepoUrl) $InstallDir"
        git clone $script:HatchInstaller.RepoUrl $InstallDir
    }

    Set-Location $InstallDir
    $hatchHome = Get-HatchHome
    $env:HATCH_HOME = $hatchHome
    @("bin", "config", "models", "probe", "logs", "backups", "installer") | ForEach-Object {
        New-Item -ItemType Directory -Force -Path (Join-Path $hatchHome $_) | Out-Null
    }
    $installState = [ordered]@{
        schema_version = 1
        managed = $true
        source_dir = $InstallDir
        installed_mode = $Mode
        backend_capability_profile = $BackendProfile
    }
    $installState | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $hatchHome "config\install.json")
    Write-HatchBackendCapabilities $BackendProfile $hatchHome
    Copy-Item (Join-Path $InstallDir "hatch.ps1") (Join-Path $hatchHome "bin\hatch.ps1") -Force

    if (-not (Test-Path "data\profile.yaml")) {
        if (Test-Path "data\profile.yaml.example") {
            Copy-Item "data\profile.yaml.example" "data\profile.yaml"
        } else {
            throw "data\profile.yaml.example is missing. Re-clone Hatch before installing."
        }
        Write-Warn "Complete onboarding in the browser or edit data\profile.yaml."
    }
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
        } else {
            throw ".env.example is missing. Re-clone Hatch before installing."
        }
    }

    Write-Info "Building Hatch containers"
    $composeArgs = Get-HatchComposeArgsForBackendProfile $BackendProfile
    Write-HatchInstallerLog $LogPath "docker compose $($composeArgs -join ' ') up -d --build"
    docker compose @composeArgs up -d --build

    if ($Mode -eq "Local") {
        & (Join-Path $hatchHome "bin\hatch.ps1") probe
        Write-Warn "Local AI selected. Review model choices before running: hatch models install"
    } elseif ($Mode -eq "Cloud") {
        Write-Info "Choose a provider in Hatch, then run: hatch secrets set <provider>"
    }

    Save-HatchInstallerState -InstallDir $InstallDir -Mode $Mode -BackendProfile $BackendProfile -Phase "installed"
    Write-Host ""
    Write-Ok "Hatch is running at http://localhost:3000"
    Write-Host "  Experience: $Mode"
    Write-Host "  Backend capabilities: $BackendProfile"
    Write-Host "  AI configuration incomplete: $($Mode -eq 'AiLater')"
    Write-Host "  Next: Open Hatch and complete onboarding."
    Write-Host "  Diagnostics: $hatchHome\bin\hatch.ps1 doctor"
    Write-Host "  Log: $LogPath"
}

if ($env:HATCH_INSTALL_TEST_MODE -eq "1") {
    return
}

try {
    $resolvedMode = Resolve-HatchInstallMode $Mode
    $resolvedProfile = Resolve-HatchBackendProfile $BackendProfile
} catch {
    Write-FailMessage $_.Exception.Message
    exit $script:HatchInstaller.ExitCodes.InvalidArguments
}

$installerDir = Get-HatchInstallerDir -HatchHome (Get-HatchHome)
New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
$logPath = Join-Path $installerDir "install.log"
Write-HatchInstallerLog $logPath "Installer started. Mode=$resolvedMode BackendProfile=$resolvedProfile CheckOnly=$CheckOnly Resume=$Resume"

try {
    if ($Resume) {
        $statePath = Join-Path $installerDir "state.json"
        if (Test-Path $statePath) {
            $saved = Get-Content $statePath -Raw | ConvertFrom-Json
            if ($saved.selected_install_dir) { $InstallDir = [string]$saved.selected_install_dir }
            if ($saved.selected_ai_mode) { $resolvedMode = [string]$saved.selected_ai_mode }
            if ($saved.selected_backend_profile) { $resolvedProfile = [string]$saved.selected_backend_profile }
            Write-Info "Resuming guided install for $InstallDir"
        } else {
            Write-Warn "No compatible resume state was found. Running a fresh preflight."
        }
    }

    $preflight = Invoke-HatchPreflight -Mode $resolvedMode -BackendProfile $resolvedProfile -InstallDir $InstallDir
    Save-HatchPreflightResult -Result $preflight
    $exitCode = Get-HatchInstallerExitCode -Result $preflight

    if ($Json) {
        $preflight | ConvertTo-Json -Depth 8
    } else {
        Format-HatchPreflightReport -Result $preflight
    }

    if ($CheckOnly) {
        Save-HatchInstallerState -InstallDir $InstallDir -Mode $resolvedMode -BackendProfile $resolvedProfile -Phase "check-only" -LastExitCode $exitCode
        exit $exitCode
    }

    if (-not $preflight.ready) {
        Save-HatchInstallerState -InstallDir $InstallDir -Mode $resolvedMode -BackendProfile $resolvedProfile -Phase "preflight-failed" -LastExitCode $exitCode
        if ($AutoInstallPrerequisites) {
            Invoke-HatchGuidedRemediation -Result $preflight
            Write-Warn "Rerun install-hatch.cmd -CheckOnly or install.ps1 -CheckOnly after prerequisite actions complete."
        } elseif (-not $NonInteractive) {
            Invoke-HatchGuidedRemediation -Result $preflight
        }
        Write-Host "Log: $logPath"
        exit $exitCode
    }

    Invoke-HatchInstall -InstallDir $InstallDir -Mode $resolvedMode -BackendProfile $resolvedProfile -LogPath $logPath
    exit $script:HatchInstaller.ExitCodes.Success
} catch {
    Write-HatchInstallerLog $logPath $_.Exception.ToString()
    if ($Json) {
        [ordered]@{
            schema_version = $script:HatchInstaller.SchemaVersion
            platform = "windows"
            ready = $false
            error = (Redact-HatchLogText $_.Exception.Message)
            log_path = $logPath
        } | ConvertTo-Json -Depth 4
    } else {
        Write-FailMessage (Redact-HatchLogText $_.Exception.Message)
        Write-Host "Log: $logPath"
    }
    exit $script:HatchInstaller.ExitCodes.Unexpected
}

$ErrorActionPreference = "Stop"

function Get-HatchHome {
    if ($env:HATCH_HOME) { return $env:HATCH_HOME }
    return (Join-Path $env:USERPROFILE ".hatch")
}

function Get-HatchManagedRoot {
    $wrapperRoot = Split-Path -Parent $MyInvocation.ScriptName
    $hatchHome = Get-HatchHome
    $installConfig = Join-Path $hatchHome "config\install.json"

    if (Test-Path $installConfig) {
        try {
            $config = Get-Content $installConfig -Raw | ConvertFrom-Json
            if ($config.source_dir -and (Test-Path (Join-Path ([string]$config.source_dir) "scripts\hatch_cli.py"))) {
                return [string]$config.source_dir
            }
        } catch {
            Write-Warning "Could not read Hatch install metadata from $installConfig"
        }
    }

    if ($wrapperRoot -and (Test-Path (Join-Path $wrapperRoot "scripts\hatch_cli.py"))) {
        return $wrapperRoot
    }

    $parentRoot = Split-Path -Parent $wrapperRoot
    if ($parentRoot -and (Test-Path (Join-Path $parentRoot "scripts\hatch_cli.py"))) {
        return $parentRoot
    }

    throw "Could not locate scripts\hatch_cli.py. Run install-hatch.cmd -Resume, or set HATCH_HOME to the Hatch state directory that contains config\install.json."
}

$Root = Get-HatchManagedRoot
$Cli = Join-Path $Root "scripts\hatch_cli.py"
python $Cli @args

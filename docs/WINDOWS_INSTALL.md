# Windows Install And Troubleshooting

Hatch on Windows runs through Docker Desktop using Linux containers. The recommended installer is `install-hatch.cmd`, which launches `install.ps1` with either PowerShell 7 (`pwsh.exe`) or Windows PowerShell 5.1 (`powershell.exe`).

The default install uses the lightweight Hatch stack and does not download local AI models.

## Recommended Install

1. Download `install-hatch.cmd` from the Hatch repository.
2. Double-click it from File Explorer.
3. Review the consolidated readiness report.
4. Follow any required prerequisite actions.
5. Re-run the installer with `-Resume` after Docker, WSL, or a restart is complete.

Advanced terminal users may run:

```powershell
.\install-hatch.cmd -CheckOnly
.\install-hatch.cmd -Resume
.\install-hatch.cmd -Mode cloud -BackendProfile core
```

## Readiness Report

The installer checks all applicable prerequisites before stopping. Each check has one status:

- `pass`: ready
- `warning`: install can continue, but a limitation exists
- `fail`: install cannot continue
- `blocked`: the check could not run because another prerequisite failed
- `skipped`: not applicable to the selected mode/profile

Machine-readable output is available with:

```powershell
.\install-hatch.cmd -CheckOnly -Json
```

## Exit Codes

| Code | Meaning |
|---:|---|
| 0 | Success / ready |
| 2 | Prerequisites missing |
| 3 | Restart required |
| 4 | Unsupported platform/runtime |
| 5 | Existing installation requires manual recovery |
| 6 | Network or acquisition failure |
| 7 | Docker build/start failure |
| 8 | Invalid arguments or non-interactive decision missing |
| 10 | Unexpected internal installer failure |

## Logs And State

The installer stores non-secret state under:

```text
%USERPROFILE%\.hatch\installer\
```

Important files:

- `install.log`: timestamped installer log with secret-like values redacted
- `last-check.json`: last structured readiness report
- `state.json`: resumable installer state

The state files must not contain provider API keys, app-lock passwords, CV/profile contents, cookies, or other user secrets.

## Optional winget Assistance

When `winget` is available, Hatch can offer to run explicitly approved package installs after you choose the guided prerequisite-install option.

Current package IDs:

| Prerequisite | winget ID |
|---|---|
| Docker Desktop | `Docker.DockerDesktop` |
| Git | `Git.Git` |
| Python 3.12 | `Python.Python.3.12` |

Hatch prints the package name, publisher, ID, and command before running anything. A successful `winget` command only means the install command completed. Hatch reruns preflight before treating Docker or another prerequisite as ready.

## PowerShell Not Found

Windows PowerShell 5.1 is normally included on supported Windows systems. If neither `pwsh.exe` nor `powershell.exe` is available, install PowerShell from Microsoft and rerun `install-hatch.cmd`.

## Docker Desktop Not Installed

Install Docker Desktop, then rerun:

```powershell
.\install-hatch.cmd -Resume
```

If you use guided prerequisite repair, Hatch may offer:

```powershell
winget install --id Docker.DockerDesktop --exact
```

Docker may still require GUI setup, terms acceptance, WSL setup, sign-out, or a restart.

## Docker Desktop Installed But Not Running

Start Docker Desktop from the Start menu and wait until it reports that Docker Engine is running. Then rerun:

```powershell
.\install-hatch.cmd -CheckOnly
```

## Docker Stuck Starting

Open Docker Desktop and check whether it is waiting for licence acceptance, WSL setup, resource allocation, or a restart. Hatch does not treat Docker as ready until `docker info` and `docker compose version` succeed.

## WSL 2 Unavailable

Docker Desktop may require WSL 2 and the Virtual Machine Platform Windows feature. Hatch may show the exact command required, but it does not silently enable Windows features.

After enabling WSL or Virtual Machine Platform, restart Windows if requested, then run:

```powershell
.\install-hatch.cmd -Resume
```

## Windows Containers Selected

Hatch needs Linux containers. In Docker Desktop, switch to Linux containers, wait for Docker Engine to restart, and rerun preflight.

## Docker Compose Unavailable

Update or repair Docker Desktop so `docker compose version` succeeds.

## Restart Required

The installer exits with code `3` when Windows reports a pending restart. Restart Windows, then run:

```powershell
.\install-hatch.cmd -Resume
```

## Ports Already In Use

Hatch uses ports `3000` and `8000` by default. Stop the process using the port or change the deployment configuration before installing.

## Insufficient Disk Space

The lightweight/core install currently uses an explicit Hatch baseline of at least 8 GB free for the install path. The full backend profile uses a 20 GB baseline before model downloads. Local AI models require additional storage based on the selected model catalogue.

## Installation Interrupted

Run:

```powershell
.\install-hatch.cmd -Resume
```

The installer reloads non-secret state and reruns preflight rather than trusting stale results.

## Existing Dirty Or Unmanaged Install

If the install directory exists but is not a managed Hatch checkout, or if a managed checkout has uncommitted changes, the installer refuses destructive recovery. Move the directory, clean it manually, or choose a different `-InstallDir`.

## Save Or Share A Redacted Diagnostic Report

Use:

```powershell
.\install-hatch.cmd -CheckOnly -Json > hatch-install-check.json
```

Review the file before sharing it. The installer redacts secret-like log values, but you should still avoid sharing personal paths or environment details publicly.

## Requirement Provenance

Hatch separates hard minimums, supported baselines, recommendations, and estimates.

- PowerShell runtime support comes from Hatch policy: Windows PowerShell 5.1 and supported PowerShell 7.
- Docker Desktop and Linux-container requirements come from Hatch's Docker Compose architecture.
- Python is required by the host `hatch.ps1` wrapper and `scripts/hatch_cli.py`.
- Disk baselines are Hatch policy values for preflight only: 8 GB for core and 20 GB for full backend profile.
- Local AI model size and RAM guidance should be derived from `backend/app/config/model_catalog.json`.

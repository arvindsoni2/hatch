@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "HATCH_REPO_OWNER=arvindsoni2"
set "HATCH_REPO_NAME=hatch"
set "HATCH_REPO_REF=main"
set "HATCH_SCRIPT=install.ps1"
set "SCRIPT_DIR=%~dp0"
set "LOCAL_SCRIPT=%SCRIPT_DIR%%HATCH_SCRIPT%"
set "TEMP_SCRIPT="
set "LAUNCHED_FROM_EXPLORER=0"

echo %cmdcmdline% | find /I "/c" >nul
if %errorlevel%==0 set "LAUNCHED_FROM_EXPLORER=1"

where pwsh.exe >nul 2>nul
if %errorlevel%==0 (
  set "POWERSHELL_EXE=pwsh.exe"
) else (
  where powershell.exe >nul 2>nul
  if %errorlevel%==0 (
    set "POWERSHELL_EXE=powershell.exe"
  ) else (
    echo [hatch] No supported PowerShell runtime was found.
    echo [hatch] Windows PowerShell 5.1 is normally included with supported Windows versions.
    echo [hatch] Install PowerShell from: https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-windows
    if "%LAUNCHED_FROM_EXPLORER%"=="1" pause
    exit /b 4
  )
)

if exist "%LOCAL_SCRIPT%" (
  set "TARGET_SCRIPT=%LOCAL_SCRIPT%"
  echo [hatch] Running local installer: "%TARGET_SCRIPT%"
) else (
  set "SOURCE_URL=https://raw.githubusercontent.com/%HATCH_REPO_OWNER%/%HATCH_REPO_NAME%/%HATCH_REPO_REF%/%HATCH_SCRIPT%"
  set "TEMP_SCRIPT=%TEMP%\hatch-install-%RANDOM%-%RANDOM%.ps1"
  echo [hatch] Local install.ps1 not found beside install-hatch.cmd.
  echo [hatch] Downloading installer from: !SOURCE_URL!
  echo [hatch] Repository reference: %HATCH_REPO_REF%
  "%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%SOURCE_URL%' -OutFile '%TEMP_SCRIPT%' -UseBasicParsing -ErrorAction Stop; if (-not (Test-Path '%TEMP_SCRIPT%') -or (Get-Item '%TEMP_SCRIPT%').Length -le 0) { throw 'Downloaded installer is empty.' } } catch { Write-Error $_; exit 6 }"
  if not %errorlevel%==0 (
    echo [hatch] Could not download the Hatch installer.
    if exist "%TEMP_SCRIPT%" del /f /q "%TEMP_SCRIPT%" >nul 2>nul
    if "%LAUNCHED_FROM_EXPLORER%"=="1" pause
    exit /b 6
  )
  set "TARGET_SCRIPT=%TEMP_SCRIPT%"
  echo [hatch] Running downloaded installer: "%TARGET_SCRIPT%"
)

"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%TARGET_SCRIPT%" %*
set "EXIT_CODE=%errorlevel%"

if defined TEMP_SCRIPT (
  if exist "%TEMP_SCRIPT%" del /f /q "%TEMP_SCRIPT%" >nul 2>nul
)

if not "%EXIT_CODE%"=="0" (
  echo [hatch] Installer exited with code %EXIT_CODE%.
  if "%LAUNCHED_FROM_EXPLORER%"=="1" pause
)

exit /b %EXIT_CODE%

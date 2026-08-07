<#
  build_installer.ps1 — one-command build of the TE Measurement installer.

  Steps:
    1. Freeze the app with PyInstaller  -> dist\TE-Measurement\
    2. Compile the Inno Setup script    -> installer\Output\TE-Measurement-Setup-1.0.0.exe

  Run from anywhere:
    powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1

  Options:
    -SkipBuild   reuse an existing dist\TE-Measurement (only recompile the installer)
#>
param([switch]$SkipBuild)

$ErrorActionPreference = "Stop"
# Project root = parent of this script's folder
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "Project root: $Root" -ForegroundColor Cyan

# --- locate the venv python -------------------------------------------------
$Py = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }   # fall back to PATH python
Write-Host "Python: $Py"

# --- 1. regenerate icon (cheap, keeps it in sync) ---------------------------
& $Py "installer\make_icon.py"

# --- 2. PyInstaller ---------------------------------------------------------
if (-not $SkipBuild) {
    Write-Host "`n=== PyInstaller: freezing app ===" -ForegroundColor Green
    & $Py -m PyInstaller "TE-Measurement.spec" --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }
} else {
    Write-Host "Skipping PyInstaller (-SkipBuild)." -ForegroundColor Yellow
}

$AppExe = Join-Path $Root "dist\TE-Measurement\TE-Measurement.exe"
if (-not (Test-Path $AppExe)) { throw "Frozen app not found: $AppExe" }
Write-Host "Frozen app OK: $AppExe" -ForegroundColor Green

# --- 3. Inno Setup ----------------------------------------------------------
$Iscc = $null
foreach ($c in @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe")) {
    if (Test-Path $c) { $Iscc = $c; break }
}
# also try PATH
if (-not $Iscc) { $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue; if ($cmd) { $Iscc = $cmd.Source } }

if (-not $Iscc) {
    Write-Host "`nInno Setup (ISCC.exe) not found." -ForegroundColor Yellow
    Write-Host "The frozen app is ready in dist\TE-Measurement\, but the setup.exe was not built." -ForegroundColor Yellow
    Write-Host "Install Inno Setup 6 (free) from https://jrsoftware.org/isdl.php, then re-run:" -ForegroundColor Yellow
    Write-Host "    powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1 -SkipBuild" -ForegroundColor Yellow
    exit 2
}

Write-Host "`n=== Inno Setup: compiling installer ===" -ForegroundColor Green
Write-Host "ISCC: $Iscc"
& $Iscc "installer\TE-Measurement.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed (exit $LASTEXITCODE)" }

$Out = Join-Path $Root "installer\Output\TE-Measurement-Setup-1.0.0.exe"
Write-Host "`nDONE." -ForegroundColor Green
Write-Host "Installer: $Out" -ForegroundColor Green

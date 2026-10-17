# scripts/build_windows_exe.ps1
# Automated Windows Standalone Packaging Script for JASPER

[CmdletBinding()]
param (
    [switch]$InstallPyInstaller = $false,
    [switch]$DebugConsole = $false
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   JASPER Standalone Windows Executable Builder             " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Resolve Project Root
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot
Write-Host "[1/5] Working Directory: $ProjectRoot" -ForegroundColor Gray

# 2. Verify Python Virtual Environment
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtual environment not found at $PythonExe. Please initialize .venv first."
    exit 1
}
Write-Host "[2/5] Using Python: $PythonExe" -ForegroundColor Green

# 3. Verify PyInstaller Dependency
$hasPyinstaller = & $PythonExe -c "import PyInstaller; print('OK')" 2>$null
if ($LASTEXITCODE -ne 0 -or $hasPyinstaller -ne "OK") {
    if ($InstallPyInstaller) {
        Write-Host "Installing PyInstaller into virtual environment..." -ForegroundColor Yellow
        & $PythonExe -m pip install pyinstaller
    } else {
        Write-Host "PyInstaller is not installed in the local virtual environment." -ForegroundColor Yellow
        Write-Host "Run this script with -InstallPyInstaller to install automatically:" -ForegroundColor Yellow
        Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_exe.ps1 -InstallPyInstaller" -ForegroundColor Cyan
        exit 1
    }
}
Write-Host "[3/5] PyInstaller is ready." -ForegroundColor Green

# 4. Verify Icons and Assets
$IconIco = Join-Path $ProjectRoot "assets\jasper_icon.ico"
$IconPng = Join-Path $ProjectRoot "assets\jasper_icon.png"
if (-not (Test-Path $IconIco) -or -not (Test-Path $IconPng)) {
    Write-Host "Converting PNG icon to Windows ICO..." -ForegroundColor Yellow
    & $PythonExe -c "from PySide6.QtGui import QImage; img = QImage('assets/jasper_icon.png'); img.save('assets/jasper_icon.ico')"
}
Write-Host "[4/5] Verified application icon assets." -ForegroundColor Green

# 5. Compile Standalone Package
Write-Host "[5/5] Compiling JASPER executable via PyInstaller..." -ForegroundColor Cyan
$SpecFile = Join-Path $ProjectRoot "jasper.spec"

& $PythonExe -m PyInstaller $SpecFile --clean --noconfirm

$ExePath = Join-Path $ProjectRoot "dist\JASPER\JASPER.exe"
if (Test-Path $ExePath) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  BUILD SUCCESSFUL!                                          " -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "Standalone executable created at:" -ForegroundColor White
    Write-Host "  $ExePath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "You can distribute the entire 'dist\JASPER' folder as a portable standalone app." -ForegroundColor Gray
} else {
    Write-Error "Build finished but executable was not found at $ExePath."
    exit 1
}

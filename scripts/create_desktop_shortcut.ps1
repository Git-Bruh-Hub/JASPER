# scripts/create_desktop_shortcut.ps1
# Creates a 1-click Windows Desktop Shortcut for JASPER with live source execution and no terminal

[CmdletBinding()]
param (
    [switch]$AddToStartMenu = $false
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonwExe = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$IconPath = Join-Path $ProjectRoot "assets\jasper_icon.ico"

if (-not (Test-Path $PythonwExe)) {
    Write-Error "Virtual environment pythonw.exe not found at $PythonwExe."
    exit 1
}

# Verify / generate icon
if (-not (Test-Path $IconPath)) {
    $PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    & $PythonExe -c "from PySide6.QtGui import QImage; img = QImage('assets/jasper_icon.png'); img.save('assets/jasper_icon.ico')"
}

$WshShell = New-Object -ComObject WScript.Shell

# 1. Desktop Shortcut
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPath = Join-Path $DesktopPath "JASPER.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PythonwExe
$Shortcut.Arguments = "-m app.desktop"
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.IconLocation = "$IconPath,0"
$Shortcut.Description = "JASPER - Autonomous Desktop Assistant"
$Shortcut.Save()

Write-Host "Created Desktop Shortcut at: $ShortcutPath" -ForegroundColor Green

# 2. Local Project Directory Shortcut
$LocalShortcutPath = Join-Path $ProjectRoot "JASPER.lnk"
$LocalShortcut = $WshShell.CreateShortcut($LocalShortcutPath)
$LocalShortcut.TargetPath = $PythonwExe
$LocalShortcut.Arguments = "-m app.desktop"
$LocalShortcut.WorkingDirectory = $ProjectRoot
$LocalShortcut.IconLocation = "$IconPath,0"
$LocalShortcut.Description = "JASPER - Autonomous Desktop Assistant"
$LocalShortcut.Save()

Write-Host "Created Local Folder Shortcut at: $LocalShortcutPath" -ForegroundColor Green

# 3. Optional Start Menu Shortcut
if ($AddToStartMenu) {
    $StartMenuPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Programs)
    $StartMenuShortcutPath = Join-Path $StartMenuPath "JASPER.lnk"
    $StartMenuShortcut = $WshShell.CreateShortcut($StartMenuShortcutPath)
    $StartMenuShortcut.TargetPath = $PythonwExe
    $StartMenuShortcut.Arguments = "-m app.desktop"
    $StartMenuShortcut.WorkingDirectory = $ProjectRoot
    $StartMenuShortcut.IconLocation = "$IconPath,0"
    $StartMenuShortcut.Description = "JASPER - Autonomous Desktop Assistant"
    $StartMenuShortcut.Save()
    Write-Host "Created Start Menu Shortcut at: $StartMenuShortcutPath" -ForegroundColor Green
}

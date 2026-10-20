@echo off
rem JASPER 1-Click Windows Launcher (runs live source via windowless pythonw)
start "" ".\.venv\Scripts\pythonw.exe" -m app.desktop %*
exit /b 0

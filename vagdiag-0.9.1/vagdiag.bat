@echo off
rem SPDX-License-Identifier: GPL-3.0-or-later
rem Copyright (C) 2026 Nenveo
rem Startet die Oberflaeche ohne Konsolenfenster
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Zuerst installieren.bat ausfuehren.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m vagdiag %*

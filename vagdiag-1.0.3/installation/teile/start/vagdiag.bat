@echo off
rem SPDX-License-Identifier: GPL-3.0-or-later
rem Copyright (C) 2026 Nenveo
rem Startet die Oberflaeche ohne Konsolenfenster (legt der Installer in den Ordner vagdiag)
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Zuerst installation\installieren-windows-10-11.bat ausfuehren.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m vagdiag %*

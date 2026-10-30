@echo off
rem SPDX-License-Identifier: GPL-3.0-or-later
rem Copyright (C) 2026 Nenveo
rem Kommandozeile, z. B.:  vagdiag-cli.bat --adresse 01 fehler
rem Findet das Programm auch, wenn es aus einem anderen Ordner aufgerufen wird.
setlocal
set "PYTHONPATH=%~dp0.;%PYTHONPATH%"
"%~dp0.venv\Scripts\python.exe" -m vagdiag.cli %*

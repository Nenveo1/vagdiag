@echo off
rem SPDX-License-Identifier: GPL-3.0-or-later
rem Copyright (C) 2026 Nenveo
rem Kommandozeile, z. B.:  vagdiag-cli.bat --adresse 01 fehler
"%~dp0.venv\Scripts\python.exe" -m vagdiag.cli %*

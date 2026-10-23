@echo off
rem Kommandozeile, z. B.:  vagdiag-cli.bat --adresse 01 fehler
"%~dp0.venv\Scripts\python.exe" -m vagdiag.cli %*

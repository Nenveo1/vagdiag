@echo off
rem Einrichtung unter Windows 10/11: virtuelle Python-Umgebung mit den Paketen
setlocal
cd /d "%~dp0"

echo == Python-Umgebung anlegen (.venv)
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 goto kein_python

".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto altes_python

echo == Pakete installieren (PySide6, ftd2xx)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_fehler

echo.
echo Fertig. Kabel einstecken (Windows installiert den FTDI-Treiber selbst), dann:
echo   vagdiag.bat           Oberflaeche
echo   vagdiag-cli.bat -h    Kommandozeile
echo.
pause
exit /b 0

:kein_python
echo.
echo Python wurde nicht gefunden. Bitte Python 3.11 oder neuer von python.org
echo installieren (Haken bei "Add python.exe to PATH") und dieses Skript neu starten.
pause
exit /b 1

:altes_python
echo.
echo Python ist zu alt - bitte Python 3.11 oder neuer installieren (python.org).
rmdir /s /q .venv
pause
exit /b 1

:pip_fehler
echo.
echo Die Pakete liessen sich nicht installieren. Internetverbindung pruefen und
echo das Skript erneut starten.
pause
exit /b 1

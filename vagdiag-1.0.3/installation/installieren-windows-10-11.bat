@echo off
rem SPDX-License-Identifier: GPL-3.0-or-later
rem Copyright (C) 2026 Nenveo
rem vagdiag einrichten unter Windows 10 und Windows 11: virtuelle Python-Umgebung mit den
rem Paketen. Danach liegen vagdiag.bat (Oberflaeche) und vagdiag-cli.bat (Kommandozeile)
rem im Ordner vagdiag.
setlocal
cd /d "%~dp0.."
if not exist "vagdiag\__init__.py" goto kein_programm

echo == Python-Umgebung anlegen (.venv)
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv --clear .venv
) else (
    python -m venv --clear .venv
)
if errorlevel 1 goto kein_python

".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto altes_python

echo == Pakete installieren (PySide6, ftd2xx)
".venv\Scripts\python.exe" -m pip install --upgrade pip
rem Windows 11 hat die Build-Nummer 22000 oder hoeher. Unter Windows 10 bleibt PySide6
rem bei 6.12 - laut Qt die letzte Version fuer Windows 10.
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.getwindowsversion().build >= 22000 else 1)"
if errorlevel 1 goto windows_10
".venv\Scripts\python.exe" -m pip install -r installation\teile\requirements.txt
if errorlevel 1 goto pip_fehler
goto startdateien

:windows_10
".venv\Scripts\python.exe" -m pip install -r installation\teile\requirements.txt -c installation\teile\windows-10.txt
if errorlevel 1 goto pip_fehler

:startdateien
echo == Startdateien in den Ordner vagdiag legen
copy /y "installation\teile\start\vagdiag.bat" "vagdiag.bat" >nul
if errorlevel 1 goto kopier_fehler
copy /y "installation\teile\start\vagdiag-cli.bat" "vagdiag-cli.bat" >nul
if errorlevel 1 goto kopier_fehler
rem Reste einer frueheren Installation im Hauptordner (die Installer lagen dort) -
rem nach dem Entpacken ueber den alten Ordner wuerden sie nur verwirren
for %%d in (installieren.bat installieren.sh requirements.txt 70-kkl-ftdi.rules) do if exist "%%d" del /q "%%d"

rem Autostart beim Anmelden: fragen, Vorauswahl Nein. Eingerichtet wird er von vagdiag
rem selbst (python -m vagdiag.autostart, Eintrag unter HKCU\...\Run)
echo.
echo == Autostart
set "antwort="
set /p "antwort=vagdiag beim Anmelden automatisch starten? [j/N] "
if defined antwort set "antwort=%antwort:"=%"
if /i "%antwort%"=="j" goto autostart
if /i "%antwort%"=="ja" goto autostart
echo    Nein. Einschalten geht jederzeit in vagdiag: Datei, Beim Anmelden starten.
goto fertig

:autostart
".venv\Scripts\python.exe" -m vagdiag.autostart an
if errorlevel 1 echo    Ging nicht - einschalten in vagdiag: Datei, Beim Anmelden starten.

:fertig
echo.
echo Fertig. Kabel einstecken (Windows installiert den FTDI-Treiber selbst), dann im
echo Ordner vagdiag:
echo   vagdiag.bat           Oberflaeche
echo   vagdiag-cli.bat -h    Kommandozeile
echo.
pause
exit /b 0

:kein_programm
echo.
echo Im Ordner fehlt das Programm (Unterordner vagdiag). Die ZIP-Datei vollstaendig
echo entpacken und dieses Skript aus dem Ordner installation darin starten.
pause
exit /b 1

:kein_python
echo.
echo Die Python-Umgebung liess sich nicht anlegen. Ist Python 3.11 oder neuer von
echo python.org installiert (Haken bei "Add python.exe to PATH")? Laeuft vagdiag noch?
echo Dann vagdiag schliessen und dieses Skript neu starten.
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

:kopier_fehler
echo.
echo Die Startdateien liessen sich nicht in den Ordner vagdiag kopieren.
pause
exit /b 1

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# Ablauf der Einrichtung unter Alpine Linux, auch auf ARM (Paketverwaltung apk).
# Gestartet von installation/installieren-alpine.sh – nicht selbst starten.
set -u
HIER=$(cd "$(dirname "$0")/.." && pwd)
. "$HIER/teile/gemeinsam.sh"

anfang "Alpine Linux"

schritt "Pakete installieren (apk): python3, py3-pip, libusb"
als_root apk update || hinweis "Paketlisten nicht aktualisiert – es geht mit den vorhandenen weiter."
als_root apk add python3 py3-pip libusb || abbruch "apk konnte die Pakete nicht installieren."
# PySide6 steht im Paketquellen-Verzeichnis „community“; pip-Pakete gibt es für Alpine nicht
schritt "Oberfläche: py3-pyside6"
if ! als_root apk add py3-pyside6; then
    hinweis "py3-pyside6 nicht installiert – dann nur die Kommandozeile. Für die Oberfläche"
    hinweis "in /etc/apk/repositories die Zeile mit „community“ freischalten und das Skript"
    hinweis "noch einmal starten."
fi
python_waehlen || abbruch "vagdiag braucht Python 3.11 oder neuer."

venv_anlegen mit_system
pyftdi_installieren
oberflaeche_pruefen
udev_regel
gruppe_uucp
startdateien_legen
alte_dateien_entfernen
autostart_fragen
ende

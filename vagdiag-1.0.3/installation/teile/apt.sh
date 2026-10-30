# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# Ablauf der Einrichtung unter Debian, Ubuntu, Linux Mint und Armbian (Paketverwaltung apt).
# Gestartet von installation/installieren-debian-ubuntu-linuxmint-armbian.sh – nicht selbst starten.
set -u
HIER=$(cd "$(dirname "$0")/.." && pwd)
. "$HIER/teile/gemeinsam.sh"

anfang "Debian, Ubuntu, Linux Mint, Armbian"

schritt "Pakete installieren (apt): python3, python3-venv, libusb"
als_root apt-get update || hinweis "Paketlisten nicht aktualisiert – es geht mit den vorhandenen weiter."
als_root apt-get install python3 python3-venv libusb-1.0-0 ||
    abbruch "apt konnte die Pakete nicht installieren."

if ! python_waehlen; then
    # z. B. Ubuntu 22.04 und Linux Mint 21: Python 3.10 – Python 3.11 gibt es dort als Paket
    schritt "Python 3.11 nachinstallieren (das Python des Systems ist älter)"
    als_root apt-get install python3.11 python3.11-venv && python_waehlen ||
        abbruch "vagdiag braucht Python 3.11 oder neuer, und das System bietet keins an."
fi

# Oberfläche: PySide6 aus der Distribution, wenn es sie dort für dieses Python gibt (Debian 13,
# neuere Ubuntu und Mint) – sonst per pip
QT_SYSTEM=nein
if LC_ALL=C apt-cache policy python3-pyside6.qtwidgets 2>/dev/null | grep -q 'Candidate: [^(]'; then
    schritt "Oberfläche: PySide6 aus der Distribution (python3-pyside6.qtwidgets)"
    if als_root apt-get install python3-pyside6.qtwidgets && pyside_im_system; then
        QT_SYSTEM=ja
    else
        hinweis "Nicht verwendbar für Python $(python_version) – nehme PySide6 per pip."
    fi
fi
if [ "$QT_SYSTEM" = ja ]; then
    venv_anlegen mit_system
else
    venv_anlegen ohne_system
    schritt "Oberfläche: PySide6 per pip (dazu die Qt-Bibliothek libxcb-cursor0)"
    als_root apt-get install libxcb-cursor0 || hinweis "libxcb-cursor0 nicht installiert."
    pip_installieren "$PYSIDE" ||
        hinweis "PySide6 gibt es für dieses System nicht per pip – dann nur die Kommandozeile."
fi

pyftdi_installieren
oberflaeche_pruefen
udev_regel
gruppe_uucp
startdateien_legen
alte_dateien_entfernen
autostart_fragen
ende

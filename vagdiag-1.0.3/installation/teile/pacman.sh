# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# Ablauf der Einrichtung unter CachyOS, Arch Linux und Arch Linux ARM (Paketverwaltung pacman).
# Gestartet von installation/installieren-cachyos-archlinux-archlinuxarm.sh – nicht selbst starten.
set -u
HIER=$(cd "$(dirname "$0")/.." && pwd)
. "$HIER/teile/gemeinsam.sh"

anfang "CachyOS, Arch Linux, Arch Linux ARM"

# PySide6 aus der Distribution – auch auf 32-Bit-ARM (armv7h), wo es kein pip-Paket gibt
schritt "Pakete installieren (pacman): python, libusb, pyside6"
if ! als_root pacman -S --needed python libusb pyside6; then
    hinweis "pyside6 nicht installiert – dann nur die Kommandozeile."
    als_root pacman -S --needed python libusb ||
        abbruch "pacman konnte die Pakete nicht installieren. Das System aktualisieren (sudo pacman -Syu) und das Skript noch einmal starten."
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

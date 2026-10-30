#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# Einrichtung unter CachyOS/Arch: virtuelle Umgebung + udev-Regel
set -euo pipefail
cd "$(dirname "$0")"

echo "== Python-Umgebung anlegen (.venv)"
python -m venv .venv
if ! .venv/bin/pip install -r requirements.txt; then
    echo
    echo "PySide6 ließ sich per pip nicht installieren. Alternative:"
    echo "  sudo pacman -S pyside6"
    echo "  rm -rf .venv && python -m venv --system-site-packages .venv"
    echo "  .venv/bin/pip install pyftdi"
    exit 1
fi

echo "== udev-Regel für das KKL-Kabel (braucht sudo)"
sudo install -m 644 70-kkl-ftdi.rules /etc/udev/rules.d/70-kkl-ftdi.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

echo
echo "Fertig. Kabel einmal ab- und wieder anstecken, dann:"
echo "  ./vagdiag.sh           Oberfläche"
echo "  ./vagdiag-cli.sh -h    Kommandozeile"

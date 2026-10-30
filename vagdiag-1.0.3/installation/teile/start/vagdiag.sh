#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# Startet die Oberfläche (legt der Installer in den Ordner vagdiag). Geht mit ./vagdiag.sh, sh,
# bash, zsh und in der fish-Shell, dort auch mit „.“ oder „source“: Die zwei
# Befehle verstehen sh und fish gleichermaßen; fish startet die Datei mit sh neu.
test -z "$FISH_VERSION" || test -z "$status" || eval 'sh (status filename) $argv'
test -n "$FISH_VERSION" && test -n "$status" || eval '
cd "$(dirname "${BASH_SOURCE:-$0}")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "Zuerst das passende Skript aus dem Ordner installation ausführen." >&2
    exit 1
fi
exec .venv/bin/python -m vagdiag "$@"
'

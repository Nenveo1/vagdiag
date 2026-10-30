#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# Kommandozeile, z. B.:  ./vagdiag-cli.sh --adresse 01 fehler
# Findet das Programm auch, wenn es aus einem anderen Ordner aufgerufen wird (etwa als Dienst).
# Geht mit sh, bash, zsh und in der fish-Shell, dort auch mit „.“ oder „source“:
# Die zwei Befehle verstehen sh und fish gleichermaßen; fish startet die Datei mit sh neu.
test -z "$FISH_VERSION" || test -z "$status" || eval 'sh (status filename) $argv'
test -n "$FISH_VERSION" && test -n "$status" || eval '
HIER=$(dirname "${BASH_SOURCE:-$0}")
PYTHONPATH="$HIER${PYTHONPATH:+:$PYTHONPATH}" exec "$HIER/.venv/bin/python" -m vagdiag.cli "$@"
'

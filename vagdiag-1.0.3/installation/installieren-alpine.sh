#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# vagdiag einrichten unter Alpine Linux, auch auf ARM (Paketverwaltung apk).
# Im Ordner installation starten:  sh installieren-alpine.sh
# Geht auch mit ./…, bash, zsh und in der fish-Shell, dort auch mit „.“ oder „source“.
# Diese Datei startet nur den eigentlichen Ablauf (teile/apk.sh) mit sh. Ihre zwei
# Befehle verstehen sh und fish gleichermaßen: fish startet die Datei mit sh neu, sh führt
# den Ablauf aus.
test -z "$FISH_VERSION" || test -z "$status" || eval 'sh (status filename)'
test -n "$FISH_VERSION" && test -n "$status" || eval 'sh "$(dirname "${BASH_SOURCE:-$0}")/teile/apk.sh"'

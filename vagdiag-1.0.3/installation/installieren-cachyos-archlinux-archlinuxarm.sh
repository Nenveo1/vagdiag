#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# vagdiag einrichten unter CachyOS, Arch Linux und Arch Linux ARM (Paketverwaltung pacman).
# Im Ordner installation starten:  sh installieren-cachyos-archlinux-archlinuxarm.sh
# Geht auch mit ./…, bash, zsh und in der fish-Shell, dort auch mit „.“ oder „source“.
# Diese Datei startet nur den eigentlichen Ablauf (teile/pacman.sh) mit sh. Ihre zwei
# Befehle verstehen sh und fish gleichermaßen: fish startet die Datei mit sh neu, sh führt
# den Ablauf aus.
test -z "$FISH_VERSION" || test -z "$status" || eval 'sh (status filename)'
test -n "$FISH_VERSION" && test -n "$status" || eval 'sh "$(dirname "${BASH_SOURCE:-$0}")/teile/pacman.sh"'

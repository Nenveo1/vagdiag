#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# Kommandozeile, z. B.:  ./vagdiag-cli.sh --adresse 01 fehler
exec "$(dirname "$0")/.venv/bin/python" -m vagdiag.cli "$@"

#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# Startet die Oberfläche
cd "$(dirname "$0")"
exec .venv/bin/python -m vagdiag "$@"

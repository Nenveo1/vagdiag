#!/usr/bin/env bash
# Kommandozeile, z. B.:  ./vagdiag-cli.sh --adresse 01 fehler
exec "$(dirname "$0")/.venv/bin/python" -m vagdiag.cli "$@"

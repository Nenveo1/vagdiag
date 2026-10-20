#!/usr/bin/env bash
# Startet die Oberfläche
cd "$(dirname "$0")"
exec .venv/bin/python -m vagdiag "$@"

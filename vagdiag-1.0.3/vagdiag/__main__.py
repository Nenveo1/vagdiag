# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Start der Oberfläche:  python -m vagdiag
Der Autostart startet diese Datei direkt (python …/vagdiag/__main__.py, siehe autostart.py) –
dann nimmt sie den Ordner darüber in den Suchpfad, egal in welchem Ordner sie startet."""

import os
import sys


def _suchpfad() -> None:
    """Als Datei gestartet: statt des Paketordners den Ordner vagdiag darüber."""
    paket = os.path.dirname(os.path.abspath(__file__))
    if sys.path and os.path.abspath(sys.path[0] or ".") == paket:
        sys.path[0] = os.path.dirname(paket)
    else:
        sys.path.insert(0, os.path.dirname(paket))


def _melden(text: str) -> None:
    """Ohne Konsole (pythonw unter Windows) als Meldungsfenster, sonst als Text."""
    if sys.stdout is None and sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "vagdiag", 0x10)
            return
        except Exception:
            pass
    print(text)


def _starten() -> None:
    try:
        from vagdiag.gui import main
    except ImportError as exc:
        if "PySide6" not in str(exc):
            raise
        from vagdiag import einstellungen, sprache
        sprache.setzen(einstellungen.laden()["sprache"])
        _melden(sprache.t("Die Oberfläche braucht PySide6, und das fehlt hier. Das passende "
                          "Skript im Ordner installation richtet es ein, wo das System es "
                          "anbietet (siehe README).\nOhne Oberfläche geht es mit:  vagdiag-cli "
                          "--help"))
        sys.exit(1)
    main()


if not __package__:
    _suchpfad()
if __name__ == "__main__":
    _starten()

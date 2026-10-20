"""Ablageorte für Einstellungen, eigene Texte und Messdaten.

Linux:    ~/.config/vagdiag         Daten: ~/vagdiag-daten
Windows:  %APPDATA%\\vagdiag         Daten: %USERPROFILE%\\vagdiag-daten
Die Datenordner lassen sich in den Einstellungen ändern.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _konfig_ordner() -> Path:
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "vagdiag"
    return Path.home() / ".config" / "vagdiag"


KONFIG_ORDNER = _konfig_ordner()
DATEN_ORDNER = Path.home() / "vagdiag-daten"

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Lizenz und Hinweise: „Über vagdiag“ in der Oberfläche, --version und der Befehl lizenz in
der Kommandozeile (GPL Version 3, Abschnitt 5d: Urheber, keine Gewährleistung, Weitergabe
unter der Lizenz und wo der Lizenztext steht)."""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .sprache import t

COPYRIGHT = "Copyright (C) 2026 Nenveo"
SPDX = "GPL-3.0-or-later"
HAUPTORDNER = Path(__file__).resolve().parent.parent
LIZENZ_DATEI = HAUPTORDNER / "LICENSE"          # GPL Version 3, englisches Original
HINWEIS_DATEI = HAUPTORDNER / "NOTICE.txt"      # Zusatzerlaubnis (FTDI), fremde Bestandteile
GPL_URL = "https://www.gnu.org/licenses/gpl-3.0.html"


def kurz() -> list[str]:
    """Für --version und den Kopf von „Über vagdiag“."""
    return [
        f"vagdiag {__version__}",
        COPYRIGHT,
        t("Lizenz: GNU General Public License Version 3 oder (nach deiner Wahl) jede spätere "
          "Version (GPL-3.0-or-later). vagdiag ist freie Software: Du darfst es unter dieser "
          "Lizenz weitergeben und verändern."),
        t("vagdiag kommt OHNE JEDE GEWÄHRLEISTUNG – auch ohne die stillschweigende "
          "Gewährleistung der Marktreife oder der Verwendbarkeit für einen bestimmten Zweck. "
          "Benutzung auf eigene Gefahr."),
    ]


def hinweise() -> list[str]:
    """Zusatzerlaubnis, fremde Bestandteile und wo die vollständigen Texte stehen."""
    return [
        t("Zusätzliche Erlaubnis (GPL Abschnitt 7): vagdiag darf mit der D2XX-Bibliothek des "
          "FTDI-Treibers (Windows) verbunden weitergegeben werden – Wortlaut in NOTICE.txt."),
        t("Fremde Bestandteile: Texttabellen aus KLineKWP1281Lib (domnulvlad, GPL-3.0); "
          "Protokollbeschreibungen und Stellgliednamen nach kw1281test (Greg Menounos, MIT)."),
        t("Lizenztext: {lizenz} (sonst {url}). Hinweise: {hinweise}",
          lizenz=LIZENZ_DATEI, url=GPL_URL, hinweise=HINWEIS_DATEI),
    ]


def lizenztext() -> str:
    """Der vollständige Lizenztext – oder, falls die Datei fehlt, wo er steht."""
    try:
        return LIZENZ_DATEI.read_text(encoding="utf-8")
    except OSError:
        return t("Die Datei LICENSE fehlt. Der Lizenztext steht unter {url}", url=GPL_URL)


def hinweistext() -> str:
    """NOTICE.txt – oder ein kurzer Ersatz, falls die Datei fehlt."""
    try:
        return HINWEIS_DATEI.read_text(encoding="utf-8")
    except OSError:
        return "\n\n".join(kurz() + hinweise())

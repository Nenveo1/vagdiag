# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Scan: Steuergeräte nacheinander abfragen (nur lesen) – die üblichen Adressen oder
alle von 01 bis 7F.

Je Adresse: Verbindung aufbauen, Kennung, auf Wunsch Fehlerspeicher, trennen. Der
Ablauf selbst läuft in der Sitzung (DiagSession.scannen); hier stehen das Ergebnis
je Adresse und der Bericht als Text.
"""

from __future__ import annotations

import textwrap
import time
from dataclasses import dataclass

from . import __version__, adressen, geprueft, ident
from .fehler import Fehler
from .kw1281 import Verbindung
from .sprache import N_, datum_zeit, t

# Status je Adresse – intern deutsch, angezeigt mit t()
STATUS = {
    "gefunden": N_("gefunden"),
    "keine_antwort": N_("keine Antwort"),
    "gesperrt": N_("übersprungen (Airbag nicht freigegeben)"),
    "getrennt": N_("sofort getrennt (Airbag)"),
    "fehler": N_("Fehler beim Abfragen"),
    "uebersprungen": N_("übersprungen"),
}


@dataclass
class ScanEintrag:
    adresse: int
    status: str = "keine_antwort"
    verbindung: Verbindung | None = None
    fehler: list[Fehler] | None = None      # None = nicht gelesen
    meldung: str = ""

    @property
    def hinweis(self) -> str | None:
        """„Nicht geprüft“-Hinweis für ein gefundenes Steuergerät (None: geprüft)."""
        if self.status != "gefunden" or self.verbindung is None:
            return None
        return geprueft.hinweis(self.verbindung)

    @property
    def status_text(self) -> str:
        text = t(STATUS.get(self.status, self.status))
        if self.hinweis:
            text += " – " + t("nicht geprüft")
        return text

    @property
    def fehler_text(self) -> str:
        if self.fehler is None:
            return "–" if self.status == "gefunden" else ""
        return str(len(self.fehler))


def bericht(eintraege: list[ScanEintrag], sim: bool = False,
            abgebrochen: bool = False, alle: bool = False) -> list[str]:
    """Scan als Text: Übersicht, dann je gefundenem Steuergerät Kennung und Fehler.
    alle: Scan aller Adressen – die Adressen ohne Antwort stehen dann in einer Zeile."""
    gefunden = [e for e in eintraege if e.status == "gefunden"]
    zeilen = [t("vagdiag {version} – Scan vom {datum}", version=__version__,
                datum=datum_zeit(time.localtime()))
              + (" – " + t("alle Adressen 01–7F") if alle else "")
              + (" – " + t("SIMULATOR, keine echten Fahrzeugdaten") if sim else "")
              + (" – " + t("abgebrochen") if abgebrochen else ""),
              t("{gefunden} von {anzahl} Adressen antworten", gefunden=len(gefunden),
                anzahl=len(eintraege)), ""]
    stumm = [e for e in eintraege if e.status == "keine_antwort"]
    for e in eintraege:
        if alle and e.status == "keine_antwort":
            continue
        v = e.verbindung
        teil = f"  {v.teilenummer}  {v.bauteil}" if v is not None else ""
        fehler = (" – " + t("{anzahl} Fehler", anzahl=len(e.fehler))
                  if e.fehler is not None else "")
        zeilen.append(f"{adressen.text(e.adresse)}: {e.status_text}{fehler}{teil}")
    if alle and stumm:
        liste = ", ".join(f"{e.adresse:02X}" for e in stumm)
        zeilen += [""] + textwrap.wrap(t("Keine Antwort ({anzahl}): {liste}",
                                         anzahl=len(stumm), liste=liste), 78)
    for e in gefunden:
        zeilen += ["", "-" * 72]
        zeilen += ident.zeilen(e.verbindung, sim)
        if e.fehler is not None:
            zeilen.append("")
            if e.fehler:
                zeilen.append(t("{anzahl} Fehler gespeichert:", anzahl=len(e.fehler)))
                zeilen += ["  " + f.zeile() for f in e.fehler]
            else:
                zeilen.append(t("Kein Fehler gespeichert"))
        if e.meldung:
            zeilen.append(e.meldung)
    for e in eintraege:
        if e.status != "gefunden" and e.meldung:
            zeilen += ["", f"{adressen.text(e.adresse)}: {e.meldung}"]
    return zeilen

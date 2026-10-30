# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Texttabellen aus der freien Bibliothek KLineKWP1281Lib (domnulvlad, GPL-3.0).

Die Tabellen liegen als Textdateien in daten/klinekwp1281lib/ (Herkunft, Lizenz und
Umwandlung stehen im Kopf jeder Datei und in LIESMICH.txt dort):

  fehler       Klartexte der fünfstelligen VAG-Fehlercodes
  obd          Klartexte der OBD-II-Codes (P, C, B, U)
  fehlerarten  Fehlerarten (Statusbyte eines Fehlers ohne Bit 7)
  texte        Klartexte der Messwerte vom Typ 37 („Text aus Tabelle“)

vagdiag fragt sie erst, wenn weder eigene Texte (*.json im Einstellungsordner) noch die
eingebauten Texte von vagdiag etwas wissen – die haben immer Vorrang. Geladen wird eine
Tabelle beim ersten Bedarf. Fehlt ein Eintrag in der eingestellten Sprache, gilt der aus der
anderen Sprache (die englischen OBD-Texte sind weniger als die deutschen).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .sprache import englisch, t

log = logging.getLogger("vagdiag.proto")

ORDNER = Path(__file__).resolve().parent / "daten" / "klinekwp1281lib"
QUELLE = "KLineKWP1281Lib (domnulvlad, GPL-3.0) – https://github.com/domnulvlad/KLineKWP1281Lib"

_tabellen: dict[tuple[str, str], dict[int, str]] = {}
_sperre = threading.Lock()


def _laden(name: str, sprache: str) -> dict[int, str]:
    schluessel = (name, sprache)
    with _sperre:
        tabelle = _tabellen.get(schluessel)
        if tabelle is not None:
            return tabelle
        tabelle = {}
        datei = ORDNER / f"{name}_{sprache}.tsv"
        try:
            for zeile in datei.read_text(encoding="utf-8").splitlines():
                if not zeile or zeile.startswith("#"):
                    continue
                nummer, _, text = zeile.partition("\t")
                if text:
                    tabelle[int(nummer, 16)] = text
        except (OSError, ValueError) as exc:
            log.warning(t("Texttabelle nicht lesbar (%s): %s"), datei, exc)
        _tabellen[schluessel] = tabelle
        return tabelle


def nachschlagen(name: str, nummer: int) -> str | None:
    """Text aus der Tabelle name (fehler, obd, fehlerarten, texte) – in der eingestellten
    Sprache, sonst in der anderen; None, wenn die Nummer fehlt."""
    reihenfolge = ("en", "de") if englisch() else ("de", "en")
    for sprache in reihenfolge:
        text = _laden(name, sprache).get(nummer)
        if text:
            return text
    return None


def fehler(code: int) -> str | None:
    """Klartext eines fünfstelligen VAG-Fehlercodes."""
    return nachschlagen("fehler", code)


def obd(code: str) -> str | None:
    """Klartext eines OBD-II-Codes wie „P0102“ oder „U0101“."""
    if len(code) != 5 or code[0] not in "PCBU":
        return None
    try:
        nummer = ("PCBU".index(code[0]) << 14) | int(code[1:], 16)
    except ValueError:
        return None
    return nachschlagen("obd", nummer)


def fehlerart(nummer: int) -> str | None:
    """Fehlerart zum Statusbyte (ohne Bit 7 „sporadisch“)."""
    return nachschlagen("fehlerarten", nummer)


def klartext(nummer: int) -> str | None:
    """Klartext eines Messwerts vom Typ 37 (Nummer a·256 + b)."""
    return nachschlagen("texte", nummer)

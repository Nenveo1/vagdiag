"""Klartexte für Messwerte vom Typ 37 („Text aus Tabelle“).

Das Steuergerät schickt nur eine Textnummer; die Texte selbst stehen in der
Diagnosesoftware. Hier sind die Nummern eingetragen, die bei deinem Polo
vorkommen oder bei Motorsteuergeräten dieser Zeit üblich sind. Unbekannte
Nummern erscheinen als „Text Nr. N“.

Eigene Ergänzungen in ~/.config/vagdiag/texte.json, Nummer dezimal oder hex:
    {"31": "Öldruck 2 i. O.", "0x0105": "Klima ein"}
Eigene Einträge haben Vorrang (in beiden Sprachen).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .sprache import englisch, t

log = logging.getLogger("vagdiag.proto")

EIGENE_TEXTE = Path.home() / ".config" / "vagdiag" / "texte.json"

TEXTE: dict[int, str] = {
    0x0000: "–",                     # leeres Feld (Kombi Gruppe 002/003)
    0x0005: "Leerlauf",
    0x0006: "Teillast",
    0x0007: "Volllast",
    0x0008: "Anreicherung",
    0x0009: "Schub",
    0x001C: "Öldruck 1 < min",
    0x001D: "Öldruck 1 i. O.",
    0x001E: "Öldruck 2 < min",
    0x001F: "Öldruck 2 i. O.",       # Kombi Gruppe 001 bei laufendem Motor
    0x006B: "alte",                  # Kombi: Beschreibung von Anpassungskanal 09
    0x0095: "Kilometer-",
    0x00A7: "unbetätigt",            # ABS Gruppe 003: Bremslichtschalter
    0x00C1: "betätigt",
    0x0149: "stand in 10",
    0x014A: "km",
}

TEXTE_EN: dict[int, str] = {
    0x0000: "–",
    0x0005: "Idle",
    0x0006: "Part load",
    0x0007: "Full load",
    0x0008: "Enrichment",
    0x0009: "Overrun",
    0x001C: "Oil pressure 1 < min",
    0x001D: "Oil pressure 1 OK",
    0x001E: "Oil pressure 2 < min",
    0x001F: "Oil pressure 2 OK",
    0x006B: "old",
    0x0095: "Odometer",
    0x00A7: "not pressed",
    0x00C1: "pressed",
    0x0149: "reading in 10",
    0x014A: "km",
}

_eigene: dict[int, str] | None = None


def _nummer(schluessel: str) -> int:
    s = str(schluessel).strip().lower()
    return int(s, 16) if s.startswith("0x") else int(s)


def _eigene_texte() -> dict[int, str]:
    global _eigene
    if _eigene is None:
        _eigene = {}
        if EIGENE_TEXTE.exists():
            try:
                daten = json.loads(EIGENE_TEXTE.read_text(encoding="utf-8"))
                _eigene = {_nummer(k): str(v) for k, v in daten.items()}
                log.info(t("%d eigene Klartexte geladen"), len(_eigene))
            except (OSError, ValueError, AttributeError) as exc:
                log.warning(t("Eigene Klartexte nicht lesbar (%s): %s"), EIGENE_TEXTE, exc)
    return _eigene


def neu_laden() -> None:
    """Nach einer Änderung an texte.json (und für Tests)."""
    global _eigene
    _eigene = None


def text(nummer: int) -> str:
    """Klartext in der eingestellten Sprache (eigene Texte haben Vorrang)."""
    eigen = _eigene_texte().get(nummer)
    if eigen is not None:
        return eigen
    if englisch() and nummer in TEXTE_EN:
        return TEXTE_EN[nummer]
    if nummer in TEXTE:
        return TEXTE[nummer]
    return t("Text Nr. {nummer}", nummer=nummer)

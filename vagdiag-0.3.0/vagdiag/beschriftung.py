"""Bezeichnungen der Anzeigefelder in Messwertgruppen.

Die Steuergeräte schicken nur Rohwerte mit Formeltyp – was ein Feld
bedeutet, steht in der Diagnosesoftware. Eingetragen sind die Gruppen, die
an deinem Polo gelesen wurden (Motor ME7.5.10, Kombi, ABS). Damit nichts
Falsches dransteht, gilt eine Belegung nur, wenn die Einheiten aller
benannten Felder zur gelesenen Gruppe passen. Sonst bleibt das Feld ohne
Namen.

Eigene Bezeichnungen in ~/.config/vagdiag/beschriftungen.json – Adresse
(hex) → Gruppe → bis zu vier Namen (null = kein Name), z. B.
    {"01": {"3": ["Motordrehzahl", "Saugrohrdruck", "Drosselklappe", "Zündwinkel"]},
     "25": {"2": ["Start erlaubt", "Motor-SG antwortet", "Schlüssel lesbar",
                  "angelernte Schlüssel"]}}
Eigene Bezeichnungen haben Vorrang und werden nicht geprüft.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .kw1281 import Verbindung
from .messwerte import Messwert

log = logging.getLogger("vagdiag.proto")

EIGENE_DATEI = Path.home() / ".config" / "vagdiag" / "beschriftungen.json"


@dataclass(frozen=True)
class Feld:
    name: str
    einheiten: tuple[str, ...]   # erwartete Einheit(en) des Feldes


def _f(name: str, *einheiten: str) -> Feld:
    return Feld(name, einheiten)


@dataclass(frozen=True)
class Belegung:
    adresse: int
    gruppen: dict[int, tuple[Feld | None, ...]]
    kennung: str = ""            # muss in Teilenummer/Bauteil vorkommen ("" = jedes Gerät)


DREHZAHL = _f("Motordrehzahl", "/min")

BELEGUNGEN: list[Belegung] = [
    # Motor ME7.5 – Gruppen 001, 002 und 004 an deinem 6K0906032M geprüft
    Belegung(0x01, {
        1: (DREHZAHL, _f("Kühlmitteltemperatur", "°C"), _f("Lambdaregelung", "%"),
            _f("Grundeinstellungsbedingungen", "")),
        2: (DREHZAHL, _f("Motorlast", "%"), _f("Einspritzzeit", "ms"),
            _f("Saugrohrdruck", "mbar")),
        4: (DREHZAHL, _f("Bordspannung", "V"), _f("Kühlmitteltemperatur", "°C"),
            _f("Ansauglufttemperatur", "°C")),
    }, kennung="ME7.5"),
    # Kombiinstrument – an deinem TRW-Kombi geprüft, bei VDO-Kombis gleich aufgebaut
    Belegung(0x17, {
        1: (_f("Geschwindigkeit", "km/h"), DREHZAHL, _f("Öldruckschalter", ""),
            _f("Uhrzeit", "")),
        2: (_f("Kilometerstand", "km"), _f("Tankinhalt", "l"), _f("Tankgeber", "Ω"), None),
        3: (_f("Kühlmitteltemperatur", "°C"), None, None),
    }),
    # ABS – Raddrehzahlen
    Belegung(0x03, {
        1: (_f("Rad vorn links", "km/h"), _f("Rad vorn rechts", "km/h"),
            _f("Rad hinten links", "km/h"), _f("Rad hinten rechts", "km/h")),
    }),
]

_eigene: dict[int, dict[int, list]] | None = None


def _eigene_bezeichnungen() -> dict[int, dict[int, list]]:
    global _eigene
    if _eigene is None:
        _eigene = {}
        if EIGENE_DATEI.exists():
            try:
                daten = json.loads(EIGENE_DATEI.read_text(encoding="utf-8"))
                for adresse, gruppen in daten.items():
                    _eigene[int(str(adresse), 16)] = {
                        int(g): [None if n is None else str(n) for n in namen][:4]
                        for g, namen in gruppen.items()}
                log.info("Eigene Feldbezeichnungen geladen: %s", EIGENE_DATEI)
            except (OSError, ValueError, AttributeError, TypeError) as exc:
                log.warning("Eigene Feldbezeichnungen nicht lesbar (%s): %s",
                            EIGENE_DATEI, exc)
                _eigene = {}
    return _eigene


def neu_laden() -> None:
    """Nach einer Änderung an beschriftungen.json (und für Tests)."""
    global _eigene
    _eigene = None


def _passt(felder: Sequence[Feld | None], werte: Sequence[Messwert]) -> bool:
    benannt = [(i, f) for i, f in enumerate(felder) if f is not None]
    if not benannt or len(werte) <= max(i for i, _ in benannt):
        return False
    return all(werte[i].einheit in f.einheiten for i, f in benannt)


def namen(verbindung: Verbindung | None, gruppe: int,
          werte: Sequence[Messwert]) -> list[str]:
    """Namen der Felder einer gelesenen Gruppe ("" = unbekannt)."""
    ergebnis = [""] * len(werte)
    if verbindung is None:
        return ergebnis
    eigen = _eigene_bezeichnungen().get(verbindung.adresse, {}).get(gruppe)
    if eigen is not None:
        for i, name in enumerate(eigen[:len(werte)]):
            ergebnis[i] = name or ""
        return ergebnis
    kennung = f"{verbindung.teilenummer} {verbindung.bauteil}"
    for belegung in BELEGUNGEN:
        felder = belegung.gruppen.get(gruppe)
        if (belegung.adresse != verbindung.adresse or felder is None
                or (belegung.kennung and belegung.kennung not in kennung)):
            continue
        if _passt(felder, werte):
            for i, feld in enumerate(felder[:len(werte)]):
                ergebnis[i] = feld.name if feld else ""
            return ergebnis
    return ergebnis


def mit_namen(namen_: Sequence[str], werte: Sequence[Messwert]) -> list[str]:
    """„Bordspannung = 13,86 V“ – oder nur der Wert, wenn kein Name bekannt ist."""
    return [f"{n} = {w.text}" if n else w.text for n, w in zip(namen_, werte)]

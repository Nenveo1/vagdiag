# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Bezeichnungen der Anzeigefelder in Messwertgruppen.

Die Steuergeräte schicken nur Rohwerte mit Formeltyp – was ein Feld
bedeutet, steht in der Diagnosesoftware. Eingetragen sind Gruppen, die an
einem Testfahrzeug (Polo 6KV: Motor ME7.5.10, Kombi, ABS) geprüft wurden. Damit nichts
Falsches dransteht, gilt eine Belegung nur, wenn die Einheiten aller
benannten Felder zur gelesenen Gruppe passen. Sonst bleibt das Feld ohne
Namen.

Geprüft ist eine Belegung nur an den Steuergeräten in Belegung.geprueft (Teilenummer).
An anderen Geräten derselben Art stehen die Namen mit dem Zusatz „(nicht geprüft)“ –
intern bleiben sie gleich (Feldname merkt sich, ob geprüft). Die Erklärung des Bitfelds
in Gruppe 001 gilt nur am 6K0 906 032 M.

Eigene Bezeichnungen in beschriftungen.json im Einstellungsordner – Adresse
(hex), wahlweise mit Teilenummer („01:036906034AM“ gilt nur für dieses Gerät und hat
Vorrang vor „01“) → Gruppe → bis zu vier Namen (null = kein Name), z. B.
    {"01": {"3": ["Motordrehzahl", "Saugrohrdruck", "Drosselklappe", "Zündwinkel"]},
     "25": {"2": ["Start erlaubt", "Motor-SG antwortet", "Schlüssel lesbar",
                  "angelernte Schlüssel"]}}
Eigene Bezeichnungen haben Vorrang und werden nicht geprüft.

Intern bleiben die Namen deutsch (der Fahrtenschreiber wertet nach ihnen
aus); angezeigt werden sie mit anzeige() in der eingestellten Sprache.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Sequence

from . import geprueft as geprueft_
from .kw1281 import Verbindung
from .messwerte import Messwert
from .pfade import KONFIG_ORDNER
from .sprache import N_, t

log = logging.getLogger("vagdiag.proto")

EIGENE_DATEI = KONFIG_ORDNER / "beschriftungen.json"


@dataclass(frozen=True)
class Feld:
    name: str
    einheiten: tuple[str, ...]   # erwartete Einheit(en) des Feldes


def _f(name: str, *einheiten: str) -> Feld:
    return Feld(N_(name), einheiten)


@dataclass(frozen=True)
class Belegung:
    adresse: int
    gruppen: dict[int, tuple[Feld | None, ...]]
    kennung: str = ""            # muss in Teilenummer/Bauteil vorkommen ("" = jedes Gerät)
    geprueft: tuple[str, ...] = ()   # Teilenummern (ohne Leerzeichen), an denen geprüft


class Feldname(str):
    """Feldname (intern deutsch) mit dem Merker, ob seine Belegung an diesem Steuergerät
    geprüft ist. Vergleicht sich wie ein gewöhnlicher Text."""
    geprueft: bool = True

    def __new__(cls, text: str, geprueft: bool = True) -> "Feldname":
        name = super().__new__(cls, text)
        name.geprueft = geprueft
        return name


DREHZAHL = _f("Motordrehzahl", "/min")
ME75_GEPRUEFT = "6K0906032M"     # Motor des Testfahrzeugs

BELEGUNGEN: list[Belegung] = [
    # Motor ME7.5 – Gruppen 001 bis 005 an einem 6K0 906 032 M geprüft (005 mit den
    # Fahrdaten vom 20.10.2026: Tempo wie Kombi und ABS)
    Belegung(0x01, {
        1: (DREHZAHL, _f("Kühlmitteltemperatur", "°C"), _f("Lambdaregelung", "%"),
            _f("Grundeinstellungsbedingungen", "")),
        2: (DREHZAHL, _f("Motorlast", "%"), _f("Einspritzzeit", "ms"),
            _f("Saugrohrdruck", "mbar")),
        3: (DREHZAHL, _f("Saugrohrdruck", "mbar"), _f("Drosselklappenwinkel", "%"),
            _f("Zündwinkel", "° v.OT", "° n.OT")),
        4: (DREHZAHL, _f("Bordspannung", "V"), _f("Kühlmitteltemperatur", "°C"),
            _f("Ansauglufttemperatur", "°C")),
        5: (DREHZAHL, _f("Motorlast", "%"), _f("Fahrgeschwindigkeit", "km/h"),
            _f("Lastzustand", "")),
    }, kennung="ME7.5", geprueft=(ME75_GEPRUEFT,)),
    # Kombiinstrument – an einem TRW-Kombi (6K9 920 806) geprüft, VDO-Kombis ähnlich
    Belegung(0x17, {
        1: (_f("Geschwindigkeit", "km/h"), DREHZAHL, _f("Öldruckschalter", ""),
            _f("Uhrzeit", "")),
        2: (_f("Kilometerstand", "km"), _f("Tankinhalt", "l"), _f("Tankgeber", "Ω"), None),
        3: (_f("Kühlmitteltemperatur", "°C"), None, None),
    }, geprueft=("6K9920806",)),
    # ABS – Raddrehzahlen und Bremslichtschalter, an einem 6X0 907 379 B geprüft
    Belegung(0x03, {
        1: (_f("Rad vorn links", "km/h"), _f("Rad vorn rechts", "km/h"),
            _f("Rad hinten links", "km/h"), _f("Rad hinten rechts", "km/h")),
        3: (_f("Bremslichtschalter", ""),),
    }, geprueft=("6X0907379B",)),
]

# Bitfeld der ME7.5 in Gruppe 001, Feld 4 – aus aufgezeichneten Fahrdaten des
# 6K0 906 032 M abgeleitet (Stellen von rechts gezählt, 1 = Bedingung erfüllt)
ME75_BITS = {
    1: N_("Kühlmittel über 80 °C"),
    2: N_("Drehzahl unter 2000/min"),
    4: N_("Lambdaregelung aktiv"),
}


def bitfeld_bekannt(teilenummer: str | None) -> bool:
    """Gilt die Erklärung des Bitfelds (Gruppe 001, Feld 4) für dieses Motorsteuergerät?
    Nur am geprüften 6K0 906 032 M (und am Simulator, der ihn nachbildet)."""
    return geprueft_.vorbild(teilenummer) == ME75_GEPRUEFT


def bitfeld_erklaerung(verbindung: Verbindung | None, gruppe: int, feld: int,
                       bits: str | None = None) -> str:
    """Erklärung der bekannten Stellen des ME7.5-Bitfelds (sonst "")."""
    if (verbindung is None or verbindung.adresse != 0x01 or gruppe != 1 or feld != 4
            or not bitfeld_bekannt(verbindung.teilenummer)):
        return ""
    zeilen = []
    for stelle, text in ME75_BITS.items():
        zustand = ""
        if bits and len(bits) >= stelle and bits[-stelle] in "01":
            zustand = " – " + (t("ja") if bits[-stelle] == "1" else t("nein"))
        zeilen.append(t("{stelle}. Stelle von rechts: {text}", stelle=stelle, text=t(text))
                      + zustand)
    return "\n".join(zeilen)

_eigene: dict[tuple[int, str], dict[int, list]] | None = None


def _eigene_bezeichnungen() -> dict[tuple[int, str], dict[int, list]]:
    """(Adresse, Teilenummer oder "") → Gruppe → Namen."""
    global _eigene
    if _eigene is None:
        _eigene = {}
        if EIGENE_DATEI.exists():
            try:
                daten = json.loads(EIGENE_DATEI.read_text(encoding="utf-8"))
                for schluessel, gruppen in daten.items():
                    adresse, _, teil = str(schluessel).partition(":")
                    _eigene[(int(adresse.strip(), 16), geprueft_.teilenummer_normal(teil))] = {
                        int(g): [None if n is None else str(n) for n in namen][:4]
                        for g, namen in gruppen.items()}
                log.info(t("Eigene Feldbezeichnungen geladen: %s"), EIGENE_DATEI)
            except (OSError, ValueError, AttributeError, TypeError) as exc:
                log.warning(t("Eigene Feldbezeichnungen nicht lesbar (%s): %s"),
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
    """Namen der Felder einer gelesenen Gruppe ("" = unbekannt), intern deutsch –
    zum Anzeigen anzeige() verwenden. Jeder Name ist ein Feldname: Er weiß, ob seine
    Belegung an diesem Steuergerät geprüft ist."""
    ergebnis: list[str] = [""] * len(werte)
    if verbindung is None:
        return ergebnis
    eigene = _eigene_bezeichnungen()
    teil = geprueft_.vorbild(verbindung.teilenummer)
    eigen = None
    for schluessel in ((verbindung.adresse, teil), (verbindung.adresse, "")):
        eigen = eigene.get(schluessel, {}).get(gruppe)
        if eigen is not None:
            break
    if eigen is not None:
        for i, name in enumerate(eigen[:len(werte)]):
            ergebnis[i] = Feldname(name) if name else ""
        return ergebnis
    kennung = f"{verbindung.teilenummer} {verbindung.bauteil}"
    for belegung in BELEGUNGEN:
        felder = belegung.gruppen.get(gruppe)
        if (belegung.adresse != verbindung.adresse or felder is None
                or (belegung.kennung and belegung.kennung not in kennung)):
            continue
        if _passt(felder, werte):
            geprueft = teil in belegung.geprueft
            for i, feld in enumerate(felder[:len(werte)]):
                ergebnis[i] = Feldname(feld.name, geprueft) if feld else ""
            return ergebnis
    return ergebnis


def anzeige(name: str) -> str:
    """Feldname in der eingestellten Sprache (eigene Namen bleiben, wie sie sind) – mit
    „(nicht geprüft)“, wenn seine Belegung an diesem Steuergerät nicht geprüft ist."""
    if not name:
        return ""
    text = t(name)
    if not getattr(name, "geprueft", True):
        text += " " + t("(nicht geprüft)")
    return text


def mit_namen(namen_: Sequence[str], werte: Sequence[Messwert]) -> list[str]:
    """„Bordspannung = 13,86 V“ – oder nur der Wert, wenn kein Name bekannt ist."""
    return [f"{anzeige(n)} = {w.text}" if n else w.text for n, w in zip(namen_, werte)]

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

Gruppe 000 (zehn Rohwerte) hat Namen für vier Felder – nur am 6K0 906 032 M:
Dort laufen sie im Log vom 28.10.2026 in 144 Durchläufen mit benannten Feldern aus Gruppe
001 und 002 mit (Feld 1 Kühlmitteltemperatur, 2 Motorlast, 3 Drehzahl, 8 Lambdaregelung)
und stehen an denselben Stellen wie in der Gruppenübersicht des Audi-Reparaturleitfadens
für Motronic. Bei anderen Motronic-Versionen ist die Reihenfolge eine andere, deshalb gelten
sie nirgends sonst. Die Namen tragen „(Rohwert)“, damit nichts, was nach Namen auswertet
(Fahrtenschreiber, Live-Anzeige), einen Rohwert für den umgerechneten Wert hält;
rohwert_text() rechnet um.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Sequence

from . import geprueft as geprueft_
from .kw1281 import Verbindung
from .messwerte import ROHWERT, Messwert
from .pfade import KONFIG_ORDNER
from .sprache import N_, einheit, t, zahl

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
    # Airbag – Gruppe 001 nach dem Reparaturleitfaden des Polo 6N (Messwertblock
    # lesen, Anzeigegruppe 001). Am 1J0 909 609 Q zeigten alle vier Felder „richtig“ – die
    # Reihenfolge lässt sich am Auto deshalb nicht nachprüfen; die Namen stehen darum auch
    # dort mit „(nicht geprüft)“. Nur an Airbag-Steuergeräten 1J0 909 609 (andere
    # Generationen belegen anders).
    Belegung(0x15, {
        1: (_f("Zündpille Fahrerairbag (N95)", ""), _f("Zündpille Beifahrerairbag (N131)", ""),
            _f("Zündpille Gurtstraffer Fahrer (N153)", ""),
            _f("Zündpille Gurtstraffer Beifahrer (N154)", "")),
    }, kennung="1J0909609", geprueft=()),
]


@dataclass(frozen=True)
class Rohfeld:
    """Ein benanntes Feld der Gruppe 000 und wie sein Rohwert umzurechnen ist."""
    name: str
    umrechnen: Callable[[int], float]
    einheit: str
    stellen: int = 0


# Gruppe 000 am 6K0 906 032 M – Umrechnung wie das Feld derselben Größe in Gruppe 001/002
# (Typ 5 mit a=10, Typ 33 mit a=133, Typ 1 mit a=200, Typ 20 mit a=100)
ROHWERTE_ME75 = {
    1: Rohfeld(N_("Kühlmitteltemperatur (Rohwert)"), lambda r: r - 100, "°C"),
    2: Rohfeld(N_("Motorlast (Rohwert)"), lambda r: r * 100 / 133, "%", 1),
    3: Rohfeld(N_("Motordrehzahl (Rohwert)"), lambda r: r * 40, "/min"),
    8: Rohfeld(N_("Lambdaregelung (Rohwert)"), lambda r: (r - 128) * 100 / 128, "%", 1),
}


def _rohfelder(verbindung: Verbindung | None) -> dict[int, Rohfeld]:
    if (verbindung is None or verbindung.adresse != 0x01
            or geprueft_.vorbild(verbindung.teilenummer) != ME75_GEPRUEFT):
        return {}
    return ROHWERTE_ME75


def rohwert_umgerechnet(verbindung: Verbindung | None, feld: int,
                        roh: int) -> tuple[float, str, int] | None:
    """Gruppe 000: (Wert, Einheit, Nachkommastellen) eines benannten Felds – None, wenn das
    Feld an diesem Steuergerät keinen geprüften Namen hat."""
    rf = _rohfelder(verbindung).get(feld)
    if rf is None:
        return None
    return float(rf.umrechnen(roh)), rf.einheit, rf.stellen


def rohwert_text(verbindung: Verbindung | None, feld: int, roh: int) -> str | None:
    """Gruppe 000: der umgerechnete Wert eines benannten Felds („21 °C“) – None, wenn das
    Feld an diesem Steuergerät keinen geprüften Namen hat."""
    umgerechnet = rohwert_umgerechnet(verbindung, feld, roh)
    if umgerechnet is None:
        return None
    wert, einheit_, stellen = umgerechnet
    return f"{zahl(wert, stellen)} {einheit(einheit_)}"

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
    if gruppe == 0:
        rohfelder = _rohfelder(verbindung)
        for i, m in enumerate(werte):
            rf = rohfelder.get(m.feld)
            if rf is not None and m.typ == ROHWERT:
                ergebnis[i] = Feldname(rf.name)
        return ergebnis
    kennung = f"{verbindung.teilenummer} {verbindung.bauteil}"
    for belegung in BELEGUNGEN:
        felder = belegung.gruppen.get(gruppe)
        if (belegung.adresse != verbindung.adresse or felder is None
                or (belegung.kennung and belegung.kennung not in kennung
                    and belegung.kennung not in teil)):
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


def mit_namen(namen_: Sequence[str], werte: Sequence[Messwert],
              verbindung: Verbindung | None = None) -> list[str]:
    """„Bordspannung = 13,86 V“ – oder nur der Wert, wenn kein Name bekannt ist. Bei
    Rohwerten der Gruppe 000 mit Namen dahinter der umgerechnete Wert:
    „Kühlmitteltemperatur (Rohwert) = 121 (21 °C)“."""
    texte = []
    for n, w in zip(namen_, werte):
        text = w.text
        if n and w.typ == ROHWERT:
            umgerechnet = rohwert_text(verbindung, w.feld, w.b)
            if umgerechnet:
                text += f" ({umgerechnet})"
        texte.append(f"{anzeige(n)} = {text}" if n else text)
    return texte

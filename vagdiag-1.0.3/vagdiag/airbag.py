# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Vorsicht beim Airbag-Steuergerät (Adresse 15).

Ross-Tech (VCDS) warnt vor einem Firmwarefehler in Airbag-Steuergeräten
6Q0 909 605 A (Golf/Jetta/Beetle 2000–2001 und ähnliche SEAT/Škoda): Bei
Störungen in der Kommunikation können sie den Fehler 65535 („interner
Steuergerätefehler“) speichern. Der lässt sich nicht löschen, die
Airbaglampe bleibt an, das Steuergerät muss getauscht werden. Mit einfachen
KKL-Kabeln ist das wahrscheinlicher als mit Ross-Techs eigenen Interfaces.
Andere Teilenummern gelten als unbedenklich.

Deshalb verbindet vagdiag nur nach ausdrücklicher Freigabe mit Adresse 15
(Rückfrage in der Oberfläche, --mit-airbag auf der Kommandozeile) und
beendet die Verbindung sofort sauber, wenn sich ein betroffenes Gerät meldet.
Geschrieben wird beim Airbag ohnehin nichts – nur Kennung und Fehlerspeicher.

vagdiag prüft das bei jeder Verbindung, egal welche Adresse gereizt wurde:
Verfälscht eine Störung die Reizung, kann ein anderes Steuergerät antworten. Meldet sich
dabei ein Airbag (oder ein betroffenes Gerät), beendet vagdiag die Verbindung sofort nach
der Kennung.

Quelle: https://www.ross-tech.com/vag-com/vw_issues.php
"""

from __future__ import annotations

import re

from .kw1281 import DiagError
from .sprache import N_, t

ADRESSE = 0x15

# Teilenummer (ohne Leerzeichen/Striche) → Grund
RISIKO = {
    "6Q0909605A": N_("bekannter Firmwarefehler: kann bei Störungen in der Kommunikation den "
                     "nicht löschbaren Fehler 65535 speichern – die Airbaglampe bleibt dann "
                     "an und das Steuergerät muss getauscht werden"),
}


class AirbagGesperrt(DiagError):
    """Verbindung zum Airbag-Steuergerät wurde nicht freigegeben."""


class AirbagRisiko(DiagError):
    """Airbag-Steuergerät mit bekanntem Firmwarefehler – Verbindung beendet."""


class AirbagFremd(AirbagRisiko):
    """Unter einer anderen Adresse als 15 hat sich ein Airbag gemeldet – Verbindung beendet."""


# Woran man ein Airbag-Steuergerät an der Kennung erkennt (wie in stellglied.py): Mitte der
# VAG-Teilenummer 909 5xx/6xx oder 959 655, oder „AIRBAG“ im Namen
_TEILE = re.compile(r"^[0-9A-Z]{3}(?:909[56]\d\d|959655)")
_WORT = re.compile(r"(?<![A-Z])AIRBAG(?![A-Z])")


def normiert(teilenummer: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(teilenummer).upper())


def risiko(teilenummer: str) -> str | None:
    """Grund, warum dieses Airbag-Steuergerät nicht gelesen werden sollte."""
    nummer = normiert(teilenummer)
    for teil, grund in RISIKO.items():
        if nummer.startswith(teil):
            return t(grund)
    return None


def ist_airbag(teilenummer: str, bauteil: str) -> bool:
    return bool(_TEILE.match(normiert(teilenummer))
                or _WORT.search(f"{teilenummer} {bauteil}".upper()))


def pruefen(adresse: int, teilenummer: str, bauteil: str) -> None:
    """Läuft direkt nach der Kennung jedes Steuergeräts, vor jeder weiteren Anfrage. Eine
    Ausnahme beendet die Verbindung sofort (sauber, mit Endeblock)."""
    grund = risiko(teilenummer)
    if grund:
        raise AirbagRisiko(risiko_text(teilenummer, grund))
    if adresse != ADRESSE and ist_airbag(teilenummer, bauteil):
        raise AirbagFremd(t(
            "Unter Adresse {adresse:02X} hat sich ein Airbag-Steuergerät gemeldet ({kennung}) – "
            "vermutlich eine gestörte Reizung. vagdiag hat sofort getrennt; den Airbag liest es "
            "nur unter Adresse 15 nach Rückfrage.",
            adresse=adresse, kennung=f"{teilenummer} {bauteil}".strip()))


def hinweis() -> str:
    """Text der Rückfrage vor dem Verbinden."""
    return t("Manche Airbag-Steuergeräte (6Q0 909 605 A, Golf/Jetta/Beetle 2000–2001, ähnliche "
             "SEAT/Škoda) speichern bei Störungen in der Kommunikation einen Fehler, der sich "
             "nicht löschen lässt – die Airbaglampe bleibt dann an, das Steuergerät muss getauscht "
             "werden. Mit einfachen KKL-Kabeln ist das wahrscheinlicher.\n\n"
             "vagdiag liest beim Airbag nur Kennung und Fehlerspeicher und trennt sofort, wenn "
             "sich ein solches Gerät meldet. Während der Verbindung kann die Airbaglampe leuchten.")


def gesperrt_text() -> str:
    return t("Airbag-Steuergerät (Adresse 15) nicht freigegeben – vorher bestätigen "
             "(Oberfläche: Rückfrage, Kommandozeile: --mit-airbag).")


def risiko_text(teilenummer: str, grund: str) -> str:
    return t("Airbag-Steuergerät {teilenummer}: {grund}. vagdiag hat die Verbindung sofort "
             "beendet und liest dieses Gerät nicht.", teilenummer=teilenummer, grund=grund)

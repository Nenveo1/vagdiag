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


def normiert(teilenummer: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(teilenummer).upper())


def risiko(teilenummer: str) -> str | None:
    """Grund, warum dieses Airbag-Steuergerät nicht gelesen werden sollte."""
    nummer = normiert(teilenummer)
    for teil, grund in RISIKO.items():
        if nummer.startswith(teil):
            return t(grund)
    return None


def hinweis() -> str:
    """Text der Rückfrage vor dem Verbinden."""
    return t("Bestimmte Airbag-Steuergeräte (6Q0 909 605 A, Golf/Jetta/Beetle 2000–2001 "
             "und ähnliche SEAT/Škoda) haben einen Firmwarefehler: Bei Störungen in der "
             "Kommunikation können sie einen Fehler speichern, der sich nicht löschen lässt. "
             "Die Airbaglampe bleibt dann an, das Steuergerät muss getauscht werden. Mit "
             "einfachen KKL-Kabeln ist das wahrscheinlicher.\n\n"
             "vagdiag liest beim Airbag nur Kennung und Fehlerspeicher und beendet die "
             "Verbindung sofort, wenn sich ein betroffenes Gerät meldet. Andere "
             "Teilenummern gelten als unbedenklich.\n\n"
             "Während der Verbindung kann die Airbaglampe leuchten – nach dem Trennen geht "
             "sie wieder aus.")


def gesperrt_text() -> str:
    return t("Airbag-Steuergerät (Adresse 15) nicht freigegeben – vorher bestätigen "
             "(Oberfläche: Rückfrage, Kommandozeile: --mit-airbag).")


def risiko_text(teilenummer: str, grund: str) -> str:
    return t("Airbag-Steuergerät {teilenummer}: {grund}. vagdiag hat die Verbindung sofort "
             "beendet und liest dieses Gerät nicht.", teilenummer=teilenummer, grund=grund)

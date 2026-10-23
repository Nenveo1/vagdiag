"""Sprache der Oberfläche und aller Ausgaben: Deutsch (Standard) oder Englisch.

Die Texte stehen im Programm auf Deutsch und laufen beim Anzeigen durch t();
die englischen Fassungen stehen in sprache_en.py. Was dort nicht steht
(z. B. eigene Feldbezeichnungen aus beschriftungen.json), bleibt unverändert.

    t("Keine Antwort von Adresse {adresse:02X}.", adresse=0x01)
    N_("Motorelektronik")   # nur vormerken – übersetzt wird beim Anzeigen mit t()

Gesetzt wird die Sprache beim Programmstart aus den Einstellungen
(„sprache“: "de" oder "en"); auf der Kommandozeile geht auch --sprache en.
Zahlen folgen der Sprache: 13,86 V auf Deutsch, 13.86 V auf Englisch – auch
in den CSV-Dateien (Deutsch: Semikolon und Dezimalkomma, Englisch: Komma
und Dezimalpunkt).
"""

from __future__ import annotations

import time

from .sprache_en import EN

SPRACHEN = {"de": "Deutsch", "en": "English"}
STANDARD = "de"

_aktuell = STANDARD

# Einheiten, die auf Englisch anders geschrieben werden
EINHEITEN_EN = {
    "° v.OT": "° BTDC",
    "° n.OT": "° ATDC",
    "°KW": "°CA",
    "Monate": "months",
}


def setzen(code: str | None) -> str:
    """Sprache umstellen ("de" oder "en"); Unbekanntes ergibt Deutsch."""
    global _aktuell
    code = str(code or STANDARD).strip().lower()[:2]
    _aktuell = code if code in SPRACHEN else STANDARD
    return _aktuell


def aktuell() -> str:
    return _aktuell


def englisch() -> bool:
    return _aktuell == "en"


def N_(text: str) -> str:
    """Text zum Übersetzen vormerken (für Tabellen, die beim Import entstehen)."""
    return text


def t(text: str, /, **werte) -> str:
    """Text in der eingestellten Sprache, Platzhalter wie bei str.format."""
    if _aktuell == "en":
        text = EN.get(text, text)
    return text.format(**werte) if werte else text


def zahl(wert: float, stellen: int = 0) -> str:
    """Zahl mit Dezimalkomma (Deutsch) bzw. Dezimalpunkt (Englisch)."""
    text = f"{wert:.{stellen}f}"
    return text.replace(".", ",") if _aktuell == "de" else text


def tausender(wert: float) -> str:
    """Ganze Zahl mit Tausenderpunkt (12.345) bzw. -komma (12,345)."""
    text = f"{wert:,.0f}"
    return text.replace(",", ".") if _aktuell == "de" else text


def einheit(text: str) -> str:
    return EINHEITEN_EN.get(text, text) if _aktuell == "en" else text


def ja_nein(wert) -> str:
    return t("ja") if wert else t("nein")


def datum_zeit(zeit: time.struct_time) -> str:
    return time.strftime("%d.%m.%Y, %H:%M" if _aktuell == "de" else "%Y-%m-%d %H:%M", zeit)


def csv_trenner() -> str:
    """Spaltentrenner der CSV-Dateien – passend zum Dezimalzeichen."""
    return ";" if _aktuell == "de" else ","

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Umrechnung der Messwerte (KW1281 und KWP2000).

Fast jedes Anzeigefeld eines Messwertblocks kommt als drei Bytes: Formeltyp, a, b.
Einige Typen sind länger: 5F (Text mit Längenbyte), 76 (Bytes mit Längenbyte),
3F (Text bis zum Ende der Antwort) und A0 (sechs Bytes, Einheit und Kommastelle
stehen mit im Feld) – beschrieben in der freien Bibliothek KLineKWP1281Lib.
Lässt sich ein Feld nicht sicher abgrenzen (Typ ohne bekanntes Format oder
unvollständig), zeigt vagdiag den Rest der Gruppe ab dort roh, statt die
folgenden Bytes falsch einzuteilen.

Die Formeln sind herstellerweit gleich. Abgeglichen mit Daten eines Polo 6KV
und mit KLineKWP1281Lib. Für unbekannte Typen wird der Rohwert angezeigt, und
zu jedem Wert bleibt der Rohwert sichtbar. vagdiag kennt alle Typen der
Bibliothek bis B5 (dazu 6F und 79–B5) – auch die, die nur im Kopf-Rumpf-Format
vorkommen.

Kopf + Rumpf: Manche KW1281-Steuergeräte schicken eine Gruppe zuerst als Kopf (Block 02:
je Feld Formeltyp, a und eine Tabelle) und danach nur noch den Rumpf (Block F4: je Feld
das Byte b). Die Typen 8B, 8C und 93 rechnen b über die 17 Stützstellen der Tabelle um,
8D wählt mit b einen Text aus einer Liste im Kopf (kopf_auswerten, rumpf_auswerten).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Union

from . import texte
from .sprache import N_, einheit as einheit_anzeige, t, zahl

Zahl = Callable[[int, int], float]
Text = Callable[[int, int], str]
Einheit = Union[str, Callable[[int, int], str]]


def _s8(b: int) -> int:
    return b - 256 if b >= 128 else b


def _s16(a: int, b: int) -> int:
    v = a * 256 + b
    return v - 65536 if v >= 32768 else v


def _div(x: float, y: float) -> float:
    return x / y if y else float("nan")


def _zeichen(x: int) -> str:
    return chr(x) if 0x20 <= x < 0x7F else "?"


def _hex(daten: bytes) -> str:
    return " ".join(f"{b:02X}" for b in daten)


def _text(daten: bytes) -> str:
    """Text eines langen Felds: endet wie ein C-Text beim ersten Nullbyte; Zeichen außerhalb
    von ASCII werden zu „?“ (die Zeichentabelle des Steuergeräts ist nicht bekannt)."""
    ende = daten.find(0)
    if ende >= 0:
        daten = daten[:ende]
    return "".join(_zeichen(b) for b in daten).strip()


# Zündwinkel: Betrag anzeigen, Richtung in der Einheit (v.OT = vor OT)
def _zw4_einheit(a: int, b: int) -> str:
    return "° v.OT" if b < 127 else "° n.OT"


def _zw27_einheit(a: int, b: int) -> str:
    return "° v.OT" if b > 128 else "° n.OT"


def _zw83_einheit(a: int, b: int) -> str:
    # wie in KLineKWP1281Lib: negativ = vor OT
    return "° v.OT" if a * b * 0.5 - 30 < 0 else "° n.OT"


SCHALTER_UNBENUTZT = "·"


def _schalter(a: int, b: int) -> str:
    """Schalterstellungen (Typ 10 und 88): a sagt, welche der acht Stellen benutzt sind,
    b ihren Zustand. Unbenutzte Stellen stehen als „·“ da – als 0 sähen sie aus wie ein
    ausgeschalteter Schalter (KLineKWP1281Lib lässt sie leer)."""
    return "".join(("1" if b & bit else "0") if a & bit else SCHALTER_UNBENUTZT
                   for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01))


def _datum(a: int, b: int) -> str:
    """Typ 7F: Datum in zwei Bytes – Jahr 2000 + (b & 7F), Monat aus den unteren drei Bits
    von a und Bit 7 von b, Tag aus den oberen fünf Bits von a (wie KLineKWP1281Lib)."""
    jahr = 2000 + (b & 0x7F)
    monat = ((a & 0x07) << 1) | (b >> 7)
    tag = a >> 3
    return f"{jahr:04d}-{monat:02d}-{tag:02d}"


# Typ: (Funktion, Einheit). Zahlen-Typen liefern float, Text-Typen str.
ZAHL_TYPEN: dict[int, tuple[Zahl, Einheit]] = {
    1: (lambda a, b: 0.2 * a * b, "/min"),
    2: (lambda a, b: 0.002 * a * b, "%"),
    3: (lambda a, b: 0.002 * a * b, "°"),
    4: (lambda a, b: (127 - b) * 0.01 * a, _zw4_einheit),     # + = vor OT
    5: (lambda a, b: a * (b - 100) * 0.1, "°C"),
    6: (lambda a, b: 0.001 * a * b, "V"),
    7: (lambda a, b: 0.01 * a * b, "km/h"),
    8: (lambda a, b: 0.1 * a * b, ""),
    9: (lambda a, b: (b - 127) * 0.02 * a, "°"),
    11: (lambda a, b: 0.0001 * a * (b - 128) + 1, ""),
    12: (lambda a, b: 0.001 * a * b, "Ω"),
    13: (lambda a, b: (b - 127) * 0.001 * a, "mm"),
    14: (lambda a, b: 0.005 * a * b, "bar"),
    15: (lambda a, b: 0.01 * a * b, "ms"),
    18: (lambda a, b: 0.04 * a * b, "mbar"),
    19: (lambda a, b: 0.01 * a * b, "l"),
    20: (lambda a, b: a * (b - 128) / 128, "%"),
    21: (lambda a, b: 0.001 * a * b, "V"),
    22: (lambda a, b: 0.001 * a * b, "ms"),
    23: (lambda a, b: b / 256 * a, "%"),
    24: (lambda a, b: 0.001 * a * b, "A"),
    25: (lambda a, b: (256 * b + a) / 180, "g/s"),
    26: (lambda a, b: b - a, "°C"),
    27: (lambda a, b: (b - 128) * 0.01 * a, _zw27_einheit),   # + = vor OT
    28: (lambda a, b: b - a, ""),
    30: (lambda a, b: b * a / 12, "°"),
    31: (lambda a, b: b * a / 2560, ""),
    32: (lambda a, b: _s8(b), ""),
    33: (lambda a, b: _div(100 * b, a), "%"),
    34: (lambda a, b: (b - 128) * 0.01 * a, "KW"),
    35: (lambda a, b: 0.01 * a * b, "l/h"),
    36: (lambda a, b: (a * 256 + b) * 10, "km"),
    38: (lambda a, b: (b - 128) * 0.001 * a, "°KW"),
    39: (lambda a, b: a * b / 255, "mg/Hub"),
    40: (lambda a, b: (a * 255 + b - 4000) * 0.1, "A"),
    41: (lambda a, b: a * 255 + b, "Ah"),
    42: (lambda a, b: (a * 255 + b - 4000) * 0.1, "kW"),
    43: (lambda a, b: (a * 255 + b) * 0.1, "V"),
    45: (lambda a, b: 0.1 * a * b, "l/100km"),
    46: (lambda a, b: (a * 256 + b - 32768) * 0.00275, "°KW"),
    47: (lambda a, b: (b - 128) * a, "ms"),
    48: (lambda a, b: a * 255 + b, ""),
    49: (lambda a, b: a * b * 0.025, "mg/Hub"),
    50: (lambda a, b: _div((b - 128) * 100, a), "mbar"),
    51: (lambda a, b: (b - 128) * a / 255, "mg/Hub"),
    52: (lambda a, b: (b - 50) * a * 0.02, "Nm"),
    53: (lambda a, b: ((b - 128) * 256 + a) / 180, "g/s"),
    54: (lambda a, b: a * 256 + b, ""),
    55: (lambda a, b: a * b * 0.005, "s"),
    56: (lambda a, b: a * 256 + b, "WSC"),
    57: (lambda a, b: a * 256 + b + 65536, "WSC"),
    58: (lambda a, b: _s8(b) * 1.023, "/s"),
    59: (lambda a, b: (a * 256 + b) / 32768, ""),
    60: (lambda a, b: (a * 256 + b) / 100, "s"),
    61: (lambda a, b: _div(b - 128, a), ""),
    62: (lambda a, b: a * b * 256 / 1000, "s"),
    64: (lambda a, b: a + b, "Ω"),
    65: (lambda a, b: (b - 127) * a * 0.01, "mm"),
    66: (lambda a, b: a * b / 512, "V"),
    67: (lambda a, b: _s16(a, b) * 2.5, "°"),
    68: (lambda a, b: _s16(a, b) * 0.1358, "°/s"),
    69: (lambda a, b: _s16(a, b) * 0.3255, "bar"),
    70: (lambda a, b: _s16(a, b) * 0.192, "m/s²"),
    71: (lambda a, b: a * b, "cm"),
    72: (lambda a, b: (a * 255 + b * (211 - a)) / 4080, "V"),
    73: (lambda a, b: a * b * 0.01, "Ω"),
    74: (lambda a, b: 0.1 * a * b, "Monate"),
    75: (lambda a, b: a * 256 + b, ""),
    76: (lambda a, b: a * 255 + b, "kΩ"),
    77: (lambda a, b: (255 * a + b * 60) / 4080, "V"),
    78: (lambda a, b: _s8(b) * 1.819, "/s"),
    79: (lambda a, b: b, ""),
    80: (lambda a, b: (a * 256 + b) / 100, "kΩ"),
    81: (lambda a, b: _s16(a, b) * 0.04375, "°"),
    82: (lambda a, b: _s16(a, b) * 0.00981, "m/s²"),
    83: (lambda a, b: _s16(a, b) * 0.01, "bar"),
    84: (lambda a, b: _s16(a, b) * 0.0973, "m/s²"),
    85: (lambda a, b: _s16(a, b) * 0.002865, "°/s"),
    86: (lambda a, b: 0.1 * a * b, "A"),
    87: (lambda a, b: a * (b - 128) * 0.1, "°/s"),
    88: (lambda a, b: 0.01 * a * b, "kΩ"),
    89: (lambda a, b: a * 256 + b, "h"),
    90: (lambda a, b: 0.1 * a * b, "kg"),
    91: (lambda a, b: a * (b - 128) * 0.1, "°"),
    92: (lambda a, b: a * b, "km"),
    93: (lambda a, b: (b - 128) * a * 0.001, "Nm"),
    94: (lambda a, b: a * (b - 128) * 0.1, "Nm"),
    96: (lambda a, b: 0.1 * a * b, "mbar"),
    97: (lambda a, b: (b - a) * 5, "°C"),
    98: (lambda a, b: 0.1 * a * b, "/km"),
    99: (lambda a, b: _s16(a, b), ""),
    100: (lambda a, b: 0.1 * a * b, "bar"),
    101: (lambda a, b: 0.001 * a * b, "l/mm"),
    102: (lambda a, b: 0.1 * a * b, "mm"),
    103: (lambda a, b: a + b * 0.05, "V"),
    104: (lambda a, b: (b - 128) * a * 0.2, "ml"),
    105: (lambda a, b: (b - 128) * a * 0.01, "m"),
    106: (lambda a, b: (b - 128) * a * 0.1, "km/h"),
    112: (lambda a, b: (b - 128) * a * 0.001, "°"),
    113: (lambda a, b: (b - 128) * a * 0.01, ""),
    114: (lambda a, b: (b - 128) * a, "m"),
    115: (lambda a, b: _s16(a, b), "W"),
    116: (lambda a, b: _s16(a, b), "/min"),
    117: (lambda a, b: (b - 64) * a * 0.01, "°C"),
    119: (lambda a, b: 0.01 * a * b, "%"),
    120: (lambda a, b: 1.41 * a * b, "°"),
    # die übrigen Typen aus KLineKWP1281Lib (a = erstes, b = zweites Byte).
    # Ohne Angabe der Bibliothek, was der Wert bedeutet, bleibt die Einheit leer.
    0x6F: (lambda a, b: 0x6F0000 | (a << 8) | b, "km"),     # so in der Bibliothek
    0x79: (lambda a, b: (b * 256 + a) * 0.5, ""),
    0x7A: (lambda a, b: (b * 256 + a - 32768) * 0.01, ""),
    0x7C: (lambda a, b: 0.1 * a * b, "mA"),
    0x7D: (lambda a, b: a - b, "dB"),
    0x7E: (lambda a, b: 0.1 * a * b, ""),
    0x80: (lambda a, b: a * b, "/min"),
    0x81: (lambda a, b: a * b / 256, "%"),
    0x82: (lambda a, b: a * b / 2560, "A"),
    0x83: (lambda a, b: a * b * 0.5 - 30, _zw83_einheit),
    0x84: (lambda a, b: a * b * 0.5, "°"),
    0x85: (lambda a, b: a * b / 256, "V"),
    0x86: (lambda a, b: a * b, "km/h"),
    0x87: (lambda a, b: a * b, ""),
    0x89: (lambda a, b: 0.01 * a * b, "ms"),
    0x8A: (lambda a, b: 0.001 * a * b, "V"),
    0x8F: (lambda a, b: (b - 128) * a * 0.01, "°"),
    0x90: (lambda a, b: 0.01 * a * b, "l/h"),
    0x91: (lambda a, b: 0.01 * a * b, "l/100km"),
    0x92: (lambda a, b: 1 + (b - 128) * a * 0.0001, ""),
    0x94: (lambda a, b: (b - 128) * a * 0.25, ""),
    0x95: (lambda a, b: (b - 100) * a * 0.1, "°C"),
    0x96: (lambda a, b: (256 * b + a) / 180, "g/s"),
    0x97: (lambda a, b: (b - 128) * a * 0.01, "°KW"),
    0x98: (lambda a, b: a * b * 0.025, "mg/Hub"),
    0x99: (lambda a, b: (b - 128) * a / 255, "mg/Hub"),
    0x9A: (lambda a, b: a * b, "°"),
    0x9B: (lambda a, b: a * b * 0.01 - 90, "°"),
    0x9C: (lambda a, b: a * 256 + b, "cm"),
    0x9D: (lambda a, b: _s16(a, b), "cm"),
    0x9E: (lambda a, b: (a * 256 + b) * 0.01, "km/h"),
    0x9F: (lambda a, b: ((b - 127) * 256 + a) * 0.1, "°C"),
    0xA2: (lambda a, b: a * b * 0.448, "°"),
    0xA3: (lambda a, b: a + b / 100, "h"),
    0xA4: (lambda a, b: b - 100 if 100 < b <= 200 else b, "%"),
    0xA5: (lambda a, b: b * 256 + a - 32768, "mA"),
    0xA6: (lambda a, b: _s16(a, b) * 2.5, "°/s"),
    0xA7: (lambda a, b: a * b * 0.001, "mΩ"),
    0xA8: (lambda a, b: (256 * a + b) * 0.01, "%"),
    0xA9: (lambda a, b: a * b + 200, "mV"),
    0xAA: (lambda a, b: a * b / 2560, "g"),
    0xAB: (lambda a, b: a * b / 2560, "g"),
    0xAC: (lambda a, b: a * b, "mg/km"),
    0xAD: (lambda a, b: a * b * 0.1, "mg/s"),
    0xAE: (lambda a, b: a * b * 0.01, "l/1000km"),
    0xAF: (lambda a, b: a * b * 0.005, "bar"),
    0xB0: (lambda a, b: a * b * 0.1, "ppm"),
    0xB1: (lambda a, b: (a - 128) * 256 + b, "Nm"),
    0xB2: (lambda a, b: ((a - 128) * 256 + b) * 6 / 51, "°/s"),
    0xB3: (lambda a, b: (a * 256 + b) * 10, ""),
    0xB4: (lambda a, b: a * b / 256, "kg/h"),
    0xB5: (lambda a, b: a * b * 0.001, "mg/s"),
}

# Klartext aus der Texttabelle (Nummer a·256 + b): Typ 37 (25 hex) und 7B
KLARTEXT_TYPEN = frozenset({37, 0x7B})

TEXT_TYPEN: dict[int, Text] = {
    10: lambda a, b: N_("warm") if b else N_("kalt"),
    16: _schalter,
    17: lambda a, b: (_zeichen(a) + _zeichen(b)).strip(),   # " 1" → "1"
    29: lambda a, b: N_("Kennfeld 1") if b < a else N_("Kennfeld 2"),
    37: lambda a, b: texte.text(a * 256 + b),     # Klartext oder „Text Nr. N“
    44: lambda a, b: f"{a:02d}:{b:02d}",
    107: lambda a, b: f"{a:02X} {b:02X}",
    0x7B: lambda a, b: texte.text(a * 256 + b),
    0x7F: _datum,
    0x88: _schalter,
    0x8E: lambda a, b: (_zeichen(a) + _zeichen(b)).strip(),
    0xA1: lambda a, b: f"{a:08b} {b:08b}",
}

# Typen, bei denen a = b = FF „kein gültiger Wert“ bedeutet
FFFF_UNGUELTIG = {36}
# Gruppe 000: zehn Rohwerte 0–255 ohne Formeltyp (Antwort F4) – eigener Typ, damit sie nie
# mit einem umgerechneten Wert verwechselt werden
ROHWERT = -1
# Rest einer Gruppe, der sich nicht sicher in Felder teilen ließ – wird nur roh gezeigt
ROH_REST = -2

# Typen, deren Feld nicht drei Bytes lang ist (Aufbau wie in KLineKWP1281Lib)
TEXT_MIT_LAENGE = 0x5F    # Typ, Länge, Zeichen
HEX_MIT_LAENGE = 0x76     # Typ, Länge, Bytes (hex angezeigt)
TEXT_BIS_ENDE = 0x3F      # Typ, dann Zeichen bis zum Ende der Antwort (immer das letzte Feld)
VARIABLE_EINHEIT = 0xA0   # Typ und fünf Bytes a b c d e – Einheit und Kommastelle in d und e
LANGE_TYPEN = {TEXT_MIT_LAENGE, HEX_MIT_LAENGE, TEXT_BIS_ENDE, VARIABLE_EINHEIT}
# Typen, deren Länge nicht bekannt ist: ab dort lässt sich eine Gruppe nicht sicher teilen
FORMAT_UNBEKANNT = {0x00, 0x6C, 0x6D, 0x6E}
LETZTE_FORMEL = 0xB5      # höhere Typen gibt es laut KLineKWP1281Lib nicht

# Nur im Kopf-Rumpf-Format: Wert über die 17 Stützstellen einer Tabelle aus dem Kopf
# (8B Drehzahl × a, 8C Temperatur − a, 93 Neigung − a) bzw. Text aus einer Liste (8D)
KOPF_TABELLE = {0x8B: "/min", 0x8C: "°C", 0x93: "%"}
KOPF_TEXTLISTE = 0x8D
KOPF_STUETZSTELLEN = 17
KOPF_TYPEN = frozenset({*KOPF_TABELLE, KOPF_TEXTLISTE})

# Typ A0: Einheit in den unteren sechs Bits von e, Vorsatz (k, m, µ) in den oberen zwei
A0_VORSATZ = ("", "k", "m", "µ")
A0_EINHEITEN = {
    0x01: "V", 0x02: "Vss", 0x03: "A", 0x04: "Ah", 0x05: "Ω", 0x06: "W", 0x07: "W/m²",
    0x08: "W/cm²", 0x09: "Wh", 0x0A: "Ws", 0x0B: "m", 0x0C: "m/s", 0x0D: "m/s²", 0x0E: "cm",
    0x0F: "km/h", 0x10: "l", 0x11: "l/100km", 0x12: "l/mm", 0x13: "l/h", 0x14: "l/km",
    0x15: "s", 0x16: "h", 0x17: "Monate", 0x18: "g", 0x19: "g/s", 0x1A: "mg/Hub", 0x1B: "Nm",
    0x1C: "N", 0x1D: "bar", 0x1E: "°", 0x1F: "<°", 0x20: "°C", 0x21: "°F", 0x22: "°/s",
    0x24: "/min", 0x25: "%", 0x26: "KW", 0x27: "KW", 0x28: "/s", 0x29: "Imp", 0x2A: "dB",
}
A0_ZUENDWINKEL = 0x23     # Richtung im Vorzeichenbit von d: gesetzt = vor OT, Wert bleibt positiv

# Text-Typen mit festen (übersetzbaren) Texten; Typ 37 holt seinen Text beim
# Anzeigen aus texte.py, damit er der eingestellten Sprache folgt
UEBERSETZT = {10, 29}

# Typen, bei denen a das untere Byte eines 16-Bit-Werts ist (b das obere): Die Auflösung steckt
# in a – nach b gerundet zeigte Typ 25 sonst 1,51 g/s als „2 g/s“.
UNTEN_A = frozenset({25, 53, 0x79, 0x7A, 0x96, 0x9F, 0xA5})


def _nachkommastellen(funktion: Zahl, a: int, b: int, typ: int | None = None) -> int:
    """Stellen passend zur Auflösung: Schrittweite eines Rohwert-Schritts – in b, bei den
    Typen aus UNTEN_A in a."""
    try:
        v1 = funktion(a, b)
        if typ in UNTEN_A:
            v2 = funktion(a + 1 if a < 255 else a - 1, b)
        else:
            v2 = funktion(a, b + 1 if b < 255 else b - 1)
    except (ArithmeticError, ValueError):
        return 1
    schritt = abs(v2 - v1)
    if schritt == 0 or math.isnan(schritt):
        return 1
    # + 1e-9 gleicht Rundungsrauschen aus (0.0999… soll 1 Stelle ergeben)
    return max(0, min(3, -math.floor(math.log10(schritt) + 1e-9)))


def zahl_deutsch(wert: float, stellen: int) -> str:
    """Zahl in der eingestellten Sprache (Name aus der Zeit vor der Übersetzung)."""
    return zahl(wert, stellen)


@dataclass
class Messwert:
    feld: int
    typ: int
    a: int
    b: int
    zahl: float | None = None      # Zahlenwert (für Min/Max und CSV)
    textwert: str | None = None    # bei Text-Typen
    einheit: str = ""
    stellen: int = 1
    gueltig: bool = True
    daten: bytes = b""             # Inhalt langer Felder (5F, 76, 3F, A0) und roher Rest

    @property
    def bekannt(self) -> bool:
        return (self.typ in ZAHL_TYPEN or self.typ in TEXT_TYPEN or self.typ == ROHWERT
                or self.typ in LANGE_TYPEN or self.typ in KOPF_TYPEN)

    @property
    def textnummer(self) -> int | None:
        """Nummer des Klartexts bei Typ 37 und 7B (sprachunabhängig, für Auswertungen)."""
        return self.a * 256 + self.b if self.typ in KLARTEXT_TYPEN else None

    @property
    def wert_text(self) -> str:
        """Nur der Wert, ohne Einheit – in der eingestellten Sprache."""
        if not self.gueltig:
            return t("kein Wert")
        if self.typ == ROH_REST:
            return t("roh: {hex}", hex=_hex(self.daten))
        if self.typ in KLARTEXT_TYPEN:
            return texte.text(self.a * 256 + self.b)
        if self.textwert is not None:
            return t(self.textwert) if self.typ in UEBERSETZT else self.textwert
        if self.zahl is None:
            return t("Typ {typ}: {a}/{b}", typ=self.typ, a=self.a, b=self.b)
        if math.isnan(self.zahl):
            return "—"
        if self.zuendwinkel:      # Richtung steckt in der Einheit
            return zahl(abs(self.zahl), self.stellen)
        return zahl(self.zahl, self.stellen)

    @property
    def zuendwinkel(self) -> bool:
        """Zündwinkel mit der Richtung (vor/nach OT) in der Einheit: Zahl ohne Vorzeichen."""
        return self.typ in (4, 27) or self.einheit in ("° v.OT", "° n.OT")

    @property
    def einheit_text(self) -> str:
        """Einheit, wie sie angezeigt wird (z. B. „° v.OT“ → „° BTDC“ auf Englisch)."""
        return einheit_anzeige(self.einheit)

    @property
    def text(self) -> str:
        if not self.gueltig:
            return t("kein Wert (FF FF)")
        if self.zahl is None and self.textwert is None:
            return self.wert_text
        return f"{self.wert_text} {self.einheit_text}".strip()

    @property
    def roh(self) -> str:
        if self.typ == ROHWERT:
            return t("Rohwert {wert} (hex {wert:02X}) ohne Umrechnung", wert=self.b)
        if self.typ == ROH_REST:
            erstes = self.daten[0] if self.daten else 0
            if erstes in FORMAT_UNBEKANNT or erstes > LETZTE_FORMEL:
                return t("Typ {typ} hat kein bekanntes Format – Rest der Gruppe roh "
                         "({anzahl} Bytes): {hex}", typ=erstes, anzahl=len(self.daten),
                         hex=_hex(self.daten))
            return t("Feld unvollständig – Rest der Gruppe roh ({anzahl} Bytes): {hex}",
                     anzahl=len(self.daten), hex=_hex(self.daten))
        if self.typ in LANGE_TYPEN:
            return t("Typ {typ}, {anzahl} Bytes: {hex}", typ=self.typ, anzahl=len(self.daten),
                     hex=_hex(self.daten))
        roh = t("Typ {typ}, a={a}, b={b}", typ=self.typ, a=self.a, b=self.b)
        if self.typ in KLARTEXT_TYPEN:
            roh += " " + t("(Text Nr. {nummer})", nummer=self.a * 256 + self.b)
        elif self.typ in KOPF_TYPEN:
            roh += " " + t("(mit Tabelle aus dem Gruppenkopf)")
        return roh


def umrechnen(feld: int, typ: int, a: int, b: int) -> Messwert:
    if typ in FFFF_UNGUELTIG and a == 0xFF and b == 0xFF:
        einheit = ZAHL_TYPEN[typ][1]
        return Messwert(feld, typ, a, b, None, None,
                        einheit if isinstance(einheit, str) else "", 0, gueltig=False)
    if typ in TEXT_TYPEN:
        return Messwert(feld, typ, a, b, None, TEXT_TYPEN[typ](a, b), "", 0)
    eintrag = ZAHL_TYPEN.get(typ)
    if eintrag is None:
        return Messwert(feld, typ, a, b)
    funktion, einheit = eintrag
    try:
        wert = float(funktion(a, b))
    except (ArithmeticError, ValueError):
        wert = float("nan")
    if callable(einheit):
        einheit = einheit(a, b)
    return Messwert(feld, typ, a, b, wert, None, einheit,
                    _nachkommastellen(funktion, a, b, typ))


class MinMax:
    """Kleinster und größter Wert je Anzeigefeld, z. B. für die Bordspannung
    beim Anlassen."""

    def __init__(self):
        self._werte: dict[object, list] = {}

    def zuruecksetzen(self, schluessel=None) -> None:
        if schluessel is None:
            self._werte.clear()
        else:
            self._werte.pop(schluessel, None)

    def erfassen(self, schluessel, m: Messwert) -> None:
        if not m.gueltig or m.zahl is None or math.isnan(m.zahl):
            return
        eintrag = self._werte.get(schluessel)
        if eintrag is None or eintrag[3] != m.einheit:
            self._werte[schluessel] = [m.zahl, m.zahl, m.stellen, m.einheit]
        else:
            eintrag[0] = min(eintrag[0], m.zahl)
            eintrag[1] = max(eintrag[1], m.zahl)

    def werte(self, schluessel) -> tuple[float, float] | None:
        eintrag = self._werte.get(schluessel)
        return (eintrag[0], eintrag[1]) if eintrag else None

    def text(self, schluessel) -> str:
        eintrag = self._werte.get(schluessel)
        if not eintrag:
            return ""
        klein, gross, stellen, einheit = eintrag
        return t("min {klein} · max {gross} {einheit}", klein=zahl(klein, stellen),
                 gross=zahl(gross, stellen), einheit=einheit_anzeige(einheit)).strip()


def rohwerte_auswerten(daten: bytes) -> list[Messwert]:
    """Gruppe 000 (Antwort F4): je Byte ein Rohwert 0–255 – meist zehn. Was sie bedeuten,
    steht im Reparaturleitfaden des Steuergeräts; vagdiag rechnet nichts um."""
    return [Messwert(i + 1, ROHWERT, 0, b, float(b), None, "", 0) for i, b in enumerate(daten)]


def _feldlaenge(daten: bytes, i: int) -> int | None:
    """Länge des Felds ab daten[i] samt Typbyte, None wenn sie sich nicht bestimmen lässt."""
    typ = daten[i]
    if typ in FORMAT_UNBEKANNT or typ > LETZTE_FORMEL:
        return None
    if typ in (TEXT_MIT_LAENGE, HEX_MIT_LAENGE):
        return 2 + daten[i + 1] if i + 1 < len(daten) else None
    if typ == TEXT_BIS_ENDE:
        return len(daten) - i
    if typ == VARIABLE_EINHEIT:
        return 6
    return 3


def felder_teilen(daten: bytes) -> tuple[list[bytes], bytes]:
    """Nutzdaten eines Messwertblocks in Felder (je mit Typbyte). Was sich nicht sicher
    abgrenzen lässt – Typ ohne bekanntes Format oder unvollständiges Feld –, kommt ab dort
    als Rest zurück."""
    daten = bytes(daten)
    felder: list[bytes] = []
    i = 0
    while i < len(daten):
        laenge = _feldlaenge(daten, i)
        if laenge is None or i + laenge > len(daten):
            return felder, daten[i:]
        felder.append(daten[i:i + laenge])
        i += laenge
    return felder, b""


def sauber_teilbar(daten: bytes, nur_dreier: bool = False) -> bool:
    """Lassen sich die Daten ohne Rest in Felder teilen? nur_dreier: und sind es lauter
    gewöhnliche Felder zu drei Bytes (keines der langen Formate 5F, 76, 3F, A0)?"""
    felder, rest = felder_teilen(daten)
    return not rest and (not nur_dreier or not any(f[0] in LANGE_TYPEN for f in felder))


def _variable_einheit(feld: int, daten: bytes) -> Messwert:
    """Typ A0: Wert = a · (b·256 + c) · (d & 0F) · 10^−((d >> 4) & 7); Bit 7 von d ist das
    Vorzeichen, e enthält Einheit und Vorsatz (wie in KLineKWP1281Lib)."""
    a, b, c, d, e = daten
    nummer = e & 0x3F
    wort = b * 256 + c
    if d & 0x80 and nummer != A0_ZUENDWINKEL:
        wort = -wort
    schritt = a * (d & 0x0F) * 10.0 ** -((d >> 4) & 7)
    if nummer == A0_ZUENDWINKEL:
        einheit = "° v.OT" if d & 0x80 else "° n.OT"
    else:
        einheit = A0_EINHEITEN.get(nummer, "")
    if einheit:
        einheit = A0_VORSATZ[e >> 6] + einheit
    # Kommastellen passend zur Auflösung – hier bis zu sieben, das Feld nennt sie selbst
    if schritt:
        stellen = max(0, min(7, -math.floor(math.log10(schritt) + 1e-9)))
    else:
        stellen = (d >> 4) & 7
    return Messwert(feld, VARIABLE_EINHEIT, 0, 0, float(wort * schritt), None, einheit,
                    stellen, daten=bytes(daten))


def feld_auswerten(nummer: int, feld: bytes) -> Messwert:
    """Ein Feld aus felder_teilen() als Messwert."""
    typ = feld[0]
    if typ == VARIABLE_EINHEIT:
        return _variable_einheit(nummer, feld[1:])
    if typ in (TEXT_MIT_LAENGE, HEX_MIT_LAENGE, TEXT_BIS_ENDE):
        inhalt = bytes(feld[1:] if typ == TEXT_BIS_ENDE else feld[2:])
        text = _hex(inhalt) if typ == HEX_MIT_LAENGE else _text(inhalt)
        return Messwert(nummer, typ, 0, 0, None, text, "", 0, daten=inhalt)
    return umrechnen(nummer, typ, feld[1], feld[2])


def gruppe_auswerten(daten: bytes) -> list[Messwert]:
    """Nutzdaten eines Messwertblocks (Titel E7) in Messwerte – bei KW1281 meist vier.
    Ein Rest, der sich nicht sicher teilen ließ, steht als letztes Feld roh dabei."""
    felder, rest = felder_teilen(daten)
    werte = [feld_auswerten(i + 1, f) for i, f in enumerate(felder)]
    if rest:
        werte.append(Messwert(len(werte) + 1, ROH_REST, 0, 0, None, None, "", 0,
                              daten=rest))
    return werte


# ---------------------------------------------------------------- Kopf + Rumpf
@dataclass(frozen=True)
class KopfFeld:
    """Ein Feld aus dem Gruppenkopf (Block 02): Formeltyp, Byte a und die Tabelle."""
    typ: int
    a: int
    tabelle: bytes = b""


def kopf_auswerten(daten: bytes) -> list[KopfFeld] | None:
    """Gruppenkopf: je Feld Typ, a, Länge der Tabelle, Tabelle (wie KLineKWP1281Lib).
    None, wenn er sich nicht vollständig so lesen lässt – oder eine Tabelle für 8B, 8C und
    93 nicht genau 17 Stützstellen hat, für 8D leer ist."""
    daten = bytes(daten)
    felder: list[KopfFeld] = []
    i = 0
    while i < len(daten):
        if i + 3 > len(daten):
            return None
        typ, a, laenge = daten[i], daten[i + 1], daten[i + 2]
        tabelle = daten[i + 3:i + 3 + laenge]
        if len(tabelle) != laenge:
            return None
        if typ in KOPF_TABELLE and laenge != KOPF_STUETZSTELLEN:
            return None
        if typ == KOPF_TEXTLISTE and laenge == 0:
            return None
        felder.append(KopfFeld(typ, a, tabelle))
        i += 3 + laenge
    return felder or None


def _c_teilen(x: int, y: int) -> int:
    """Ganzzahlige Division, die wie in C zur Null hin abschneidet."""
    q = abs(x) // y
    return q if x >= 0 else -q


def _tabellenwert(feld: int, k: KopfFeld, b: int) -> Messwert:
    """8B, 8C, 93: b läuft über die 17 Stützstellen (je 16 Schritte), dazwischen gerade
    verbunden – ganzzahlig wie in KLineKWP1281Lib. 8B mal a, 8C und 93 minus a."""
    schritte = len(k.tabelle) - 1                       # 16
    i = min(b // schritte, schritte - 1)
    basis = k.tabelle[i]
    wert = basis + _c_teilen((k.tabelle[i + 1] - basis) * (b % schritte), schritte)
    wert = wert * k.a if k.typ == 0x8B else wert - k.a
    return Messwert(feld, k.typ, k.a, b, float(wert), None, KOPF_TABELLE[k.typ], 0)


def _textliste(feld: int, k: KopfFeld, b: int) -> Messwert:
    """8D: Texte im Kopf, getrennt durch 03; b wählt einen davon (fehlt er: leer)."""
    texte_ = k.tabelle.split(b"\x03")
    if texte_ and texte_[-1] == b"" and k.tabelle.endswith(b"\x03"):
        texte_ = texte_[:-1]
    text = _text(texte_[b]) if b < len(texte_) else ""
    return Messwert(feld, k.typ, k.a, b, None, text, "", 0, daten=bytes(k.tabelle))


def rumpf_auswerten(kopf: list[KopfFeld], rumpf: bytes) -> list[Messwert]:
    """Rumpf (Block F4, je Feld ein Byte b) mit dem gespeicherten Kopf zu Messwerten. Lange
    Formate (5F, 76, 3F, A0) gibt es hier nicht – sie und unbekannte Typen bleiben roh."""
    werte: list[Messwert] = []
    for i, (k, b) in enumerate(zip(kopf, bytes(rumpf))):
        if k.typ in KOPF_TABELLE:
            werte.append(_tabellenwert(i + 1, k, b))
        elif k.typ == KOPF_TEXTLISTE:
            werte.append(_textliste(i + 1, k, b))
        elif k.typ in LANGE_TYPEN or k.typ in FORMAT_UNBEKANNT or k.typ > LETZTE_FORMEL:
            werte.append(Messwert(i + 1, k.typ, k.a, b))
        else:
            werte.append(umrechnen(i + 1, k.typ, k.a, b))
    return werte

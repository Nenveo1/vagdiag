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
zu jedem Wert bleibt der Rohwert sichtbar.
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
}

TEXT_TYPEN: dict[int, Text] = {
    10: lambda a, b: N_("warm") if b else N_("kalt"),
    16: lambda a, b: format(b & a, "08b"),
    17: lambda a, b: (_zeichen(a) + _zeichen(b)).strip(),   # " 1" → "1"
    29: lambda a, b: N_("Kennfeld 1") if b < a else N_("Kennfeld 2"),
    37: lambda a, b: texte.text(a * 256 + b),     # Klartext oder „Text Nr. N“
    44: lambda a, b: f"{a:02d}:{b:02d}",
    107: lambda a, b: f"{a:02X} {b:02X}",
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


def _nachkommastellen(funktion: Zahl, a: int, b: int) -> int:
    """Stellen passend zur Auflösung: Schrittweite eines Rohwert-Schritts."""
    try:
        v1 = funktion(a, b)
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
                or self.typ in LANGE_TYPEN)

    @property
    def textnummer(self) -> int | None:
        """Nummer des Klartexts bei Typ 37 (sprachunabhängig, für Auswertungen)."""
        return self.a * 256 + self.b if self.typ == 37 else None

    @property
    def wert_text(self) -> str:
        """Nur der Wert, ohne Einheit – in der eingestellten Sprache."""
        if not self.gueltig:
            return t("kein Wert")
        if self.typ == ROH_REST:
            return t("roh: {hex}", hex=_hex(self.daten))
        if self.typ == 37:
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
        if self.typ == 37:
            roh += " " + t("(Text Nr. {nummer})", nummer=self.a * 256 + self.b)
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
                    _nachkommastellen(funktion, a, b))


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

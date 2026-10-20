"""Umrechnung der KW1281-Messwerte.

Jedes Anzeigefeld eines Messwertblocks kommt als drei Bytes: Formeltyp, a, b.
Die Formeln sind herstellerweit gleich. Abgeglichen mit den Daten deines
Polos und mit der freien Bibliothek KLineKWP1281Lib (nur als Referenz für die
Formeln genutzt). Für unbekannte Typen wird der Rohwert angezeigt, und zu
jedem Wert bleibt der Rohwert sichtbar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Union

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
    39: (lambda a, b: a * b / 255, "mg/h"),
    40: (lambda a, b: (a * 255 + b - 4000) * 0.1, "A"),
    41: (lambda a, b: a * 255 + b, "Ah"),
    42: (lambda a, b: (a * 255 + b - 4000) * 0.1, "kW"),
    43: (lambda a, b: (a * 255 + b) * 0.1, "V"),
    45: (lambda a, b: 0.1 * a * b, "l/100km"),
    46: (lambda a, b: (a * 256 + b - 32768) * 0.00275, "°KW"),
    47: (lambda a, b: (b - 128) * a, "ms"),
    48: (lambda a, b: a * 255 + b, ""),
    49: (lambda a, b: a * b * 0.025, "mg/h"),
    50: (lambda a, b: _div((b - 128) * 100, a), "mbar"),
    51: (lambda a, b: (b - 128) * a / 255, "mg/h"),
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
    10: lambda a, b: "warm" if b else "kalt",
    16: lambda a, b: format(b & a, "08b"),
    17: lambda a, b: _zeichen(a) + _zeichen(b),
    29: lambda a, b: "Kennfeld 1" if b < a else "Kennfeld 2",
    37: lambda a, b: f"Text Nr. {a * 256 + b}",   # Texttabelle des Steuergeräts fehlt noch
    44: lambda a, b: f"{a:02d}:{b:02d}",
    107: lambda a, b: f"{a:02X} {b:02X}",
}

# Typen, bei denen a = b = FF „kein gültiger Wert“ bedeutet
FFFF_UNGUELTIG = {36}


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
    return f"{wert:.{stellen}f}".replace(".", ",")


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

    @property
    def bekannt(self) -> bool:
        return self.typ in ZAHL_TYPEN or self.typ in TEXT_TYPEN

    @property
    def wert_text(self) -> str:
        """Nur der Wert, ohne Einheit."""
        if not self.gueltig:
            return "kein Wert"
        if self.textwert is not None:
            return self.textwert
        if self.zahl is None:
            return f"Typ {self.typ}: {self.a}/{self.b}"
        if math.isnan(self.zahl):
            return "—"
        if self.typ in (4, 27):   # Zündwinkel: Richtung steckt in der Einheit
            return zahl_deutsch(abs(self.zahl), self.stellen)
        return zahl_deutsch(self.zahl, self.stellen)

    @property
    def text(self) -> str:
        if not self.gueltig:
            return "kein Wert (FF FF)"
        if self.zahl is None and self.textwert is None:
            return self.wert_text
        return f"{self.wert_text} {self.einheit}".strip()

    @property
    def roh(self) -> str:
        return f"Typ {self.typ}, a={self.a}, b={self.b}"


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
        return (f"min {zahl_deutsch(klein, stellen)} · max {zahl_deutsch(gross, stellen)} "
                f"{einheit}").strip()


def gruppe_auswerten(daten: bytes) -> list[Messwert]:
    """Nutzdaten eines Messwertblocks (Titel E7) in bis zu 4 Messwerte."""
    werte = []
    for i in range(0, len(daten) - 2, 3):
        werte.append(umrechnen(i // 3 + 1, daten[i], daten[i + 1], daten[i + 2]))
    return werte

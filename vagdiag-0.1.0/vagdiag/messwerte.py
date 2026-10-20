"""Umrechnung der KW1281-Messwerte.

Jedes Anzeigefeld eines Messwertblocks kommt als drei Bytes: Formeltyp, a, b.
Die Formeln sind herstellerweit gleich. Für Typen, die (noch) nicht in der
Tabelle stehen, wird der Rohwert angezeigt. Zu jedem Wert bleibt der Rohwert
sichtbar, damit sich eine falsche Formel sofort erkennen lässt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Union

Wert = Union[float, str, None]


def _div(x: float, y: float) -> float:
    return x / y if y else float("nan")


def _zuendwinkel(mitte: int):
    def f(a: int, b: int) -> str:
        w = (b - mitte) * 0.01 * a
        return f"{abs(w):.1f} ° {'v.OT' if w >= 0 else 'n.OT'}"
    return f


# typ: (Funktion(a, b) -> Zahl oder Text, Einheit)
FORMELN: dict[int, tuple[Callable[[int, int], Wert], str]] = {
    1: (lambda a, b: 0.2 * a * b, "/min"),
    2: (lambda a, b: 0.002 * a * b, "%"),
    3: (lambda a, b: 0.002 * a * b, "°"),
    4: (_zuendwinkel(127), ""),
    5: (lambda a, b: a * (b - 100) * 0.1, "°C"),
    6: (lambda a, b: 0.001 * a * b, "V"),
    7: (lambda a, b: 0.01 * a * b, "km/h"),
    8: (lambda a, b: 0.1 * a * b, ""),
    9: (lambda a, b: (b - 127) * 0.02 * a, "°"),
    10: (lambda a, b: "kalt" if b == 0 else "warm", ""),
    11: (lambda a, b: 0.0001 * a * (b - 128) + 1, ""),
    12: (lambda a, b: 0.001 * a * b, "Ω"),
    13: (lambda a, b: (b - 127) * 0.001 * a, "mm"),
    14: (lambda a, b: 0.005 * a * b, "bar"),
    15: (lambda a, b: 0.01 * a * b, "ms"),
    16: (lambda a, b: format(b, "08b"), ""),
    17: (lambda a, b: chr(a) + chr(b), ""),
    18: (lambda a, b: 0.04 * a * b, "mbar"),
    19: (lambda a, b: 0.01 * a * b, "l"),
    20: (lambda a, b: a * (b - 128) / 128, "%"),
    21: (lambda a, b: 0.001 * a * b, "V"),
    22: (lambda a, b: 0.001 * a * b, "ms"),
    23: (lambda a, b: b / 256 * a, "%"),
    24: (lambda a, b: 0.001 * a * b, "A"),
    25: (lambda a, b: b * 1.421 + a / 182, "g/s"),
    27: (_zuendwinkel(128), ""),
    31: (lambda a, b: b / 2560 * a, "°C"),
    33: (lambda a, b: 100 * b / a if a else 100 * b, "%"),
    34: (lambda a, b: (b - 128) * 0.01 * a, "kW"),
    35: (lambda a, b: 0.01 * a * b, "l/h"),
    36: (lambda a, b: a * 2560 + b * 10, "km"),
    38: (lambda a, b: (b - 128) * 0.001 * a, "°KW"),
    39: (lambda a, b: b / 256 * a, "mg/h"),
    40: (lambda a, b: b * 0.1 + 25.5 * a - 400, "A"),
    41: (lambda a, b: b + a * 255, "Ah"),
    42: (lambda a, b: b * 0.1 + 25.5 * a - 400, "kW"),
    43: (lambda a, b: b * 0.1 + 25.5 * a, "V"),
    44: (lambda a, b: f"{a:02d}:{b:02d}", "h:min"),
    47: (lambda a, b: (b - 128) * a, "ms"),
    48: (lambda a, b: b + a * 255, ""),
    49: (lambda a, b: b / 4 * a * 0.1, "mg/h"),
    50: (lambda a, b: _div(b - 128, 0.01 * a), "mbar"),
    51: (lambda a, b: (b - 128) / 255 * a, "mg/h"),
    52: (lambda a, b: b * 0.02 * a - a, "Nm"),
    53: (lambda a, b: (b - 128) * 1.4222 + 0.006 * a, "g/s"),
    54: (lambda a, b: a * 256 + b, ""),
    55: (lambda a, b: a * b / 200, "s"),
    56: (lambda a, b: a * 256 + b, "WSC"),
    57: (lambda a, b: a * 256 + b + 65536, "WSC"),
    59: (lambda a, b: (a * 256 + b) / 32768, ""),
    60: (lambda a, b: (a * 256 + b) * 0.01, "s"),
    61: (lambda a, b: _div(b - 128, a), ""),
    62: (lambda a, b: 0.256 * a * b, "S"),
    64: (lambda a, b: a + b, "Ω"),
    65: (lambda a, b: 0.01 * a * (b - 127), "mm"),
    66: (lambda a, b: a * b / 511.12, "V"),
}


def _nachkommastellen(funktion: Callable[[int, int], Wert], a: int, b: int) -> int:
    """Stellen passend zur Auflösung: Schrittweite eines Rohwert-Schritts."""
    try:
        v1 = funktion(a, b)
        v2 = funktion(a, b + 1 if b < 255 else b - 1)
    except (ArithmeticError, ValueError):
        return 1
    if not isinstance(v1, (int, float)) or not isinstance(v2, (int, float)):
        return 0
    schritt = abs(v2 - v1)
    if schritt == 0 or math.isnan(schritt):
        return 1
    # + 1e-9 gleicht Rundungsrauschen aus (0.0999… soll 1 Stelle ergeben)
    return max(0, min(3, -math.floor(math.log10(schritt) + 1e-9)))


@dataclass
class Messwert:
    feld: int
    typ: int
    a: int
    b: int
    wert: Wert
    einheit: str
    stellen: int = 1

    @property
    def bekannt(self) -> bool:
        return self.typ in FORMELN

    @property
    def text(self) -> str:
        if self.wert is None:
            return f"Typ {self.typ}: {self.a}/{self.b}"
        if isinstance(self.wert, str):
            wert = self.wert
        elif math.isnan(self.wert):
            wert = "—"
        else:
            wert = f"{self.wert:.{self.stellen}f}"
        return f"{wert} {self.einheit}".strip()

    @property
    def roh(self) -> str:
        return f"Typ {self.typ}, a={self.a}, b={self.b}"


def umrechnen(feld: int, typ: int, a: int, b: int) -> Messwert:
    eintrag = FORMELN.get(typ)
    if eintrag is None:
        return Messwert(feld, typ, a, b, None, "")
    funktion, einheit = eintrag
    try:
        wert = funktion(a, b)
    except (ArithmeticError, ValueError):
        wert = float("nan")
    return Messwert(feld, typ, a, b, wert, einheit,
                    _nachkommastellen(funktion, a, b))


def gruppe_auswerten(daten: bytes) -> list[Messwert]:
    """Nutzdaten eines Messwertblocks (Titel E7) in bis zu 4 Messwerte."""
    werte = []
    for i in range(0, len(daten) - 2, 3):
        werte.append(umrechnen(i // 3 + 1, daten[i], daten[i + 1], daten[i + 2]))
    return werte

"""Fehlercodes: Klartexte, Fehlerart und Umrechnung in OBD-II-P-Codes.

Die eingebauten Texte stehen in fehlercodes.py (fünfstellige VAG-Codes, VAG-eigene
P1-Codes und genormte P0-Codes) – nur, was sicher stimmt, auf Deutsch und Englisch.
Eigene Texte lassen sich ergänzen in fehlertexte.json im Einstellungsordner (siehe
pfade.py), z. B.
    {"16486": "Luftmassenmesser: Signal zu klein", "P0171": "Gemisch zu mager"}
Eigene Texte gelten in beiden Sprachen und haben Vorrang.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .fehlercodes import SAE_P, VAG, VAG_P
from .pfade import KONFIG_ORDNER
from .sprache import englisch, t

log = logging.getLogger("vagdiag.proto")

EIGENE_TEXTE = KONFIG_ORDNER / "fehlertexte.json"

FEHLERARTEN = {
    0: "",
    1: "Signal Kurzschluss nach Plus",
    2: "Signal Kurzschluss nach Masse",
    3: "kein Signal",
    4: "mechanischer Fehler",
    5: "Eingang offen",
    6: "Signal zu groß",
    7: "Signal zu klein",
    8: "Regelgrenze überschritten",
    9: "Adaptionsgrenze überschritten",
    10: "Adaptionsgrenze nicht erreicht",
    11: "Regelgrenze nicht erreicht",
    12: "Adaptionsgrenze (mul) überschritten",
    13: "Adaptionsgrenze (mul) nicht erreicht",
    14: "Adaptionsgrenze (add) überschritten",
    15: "Adaptionsgrenze (add) nicht erreicht",
    16: "Signal außerhalb der Toleranz",
    17: "Regeldifferenz",
    18: "oberer Grenzwert",
    19: "unterer Grenzwert",
    20: "Störung in Grundeinstellung",
    21: "Druckaufbauzeit vorn zu lang",
    22: "Druckabbauzeit vorn zu lang",
    23: "Druckaufbauzeit hinten zu lang",
    24: "Druckabbauzeit hinten zu lang",
    25: "unbekannter Schaltzustand",
    26: "Ausgang offen",
    27: "unplausibles Signal",
    28: "Kurzschluss nach Plus",
    29: "Kurzschluss nach Masse",
    30: "Unterbrechung/Kurzschluss nach Plus",
    31: "Unterbrechung/Kurzschluss nach Masse",
    32: "Widerstand zu groß",
    33: "Widerstand zu klein",
    34: "keine Grundeinstellung",
    35: "",          # bei EOBD-Codes: Text steht im Fehlercode selbst
    36: "Unterbrechung",
    37: "defekt",
}

FEHLERARTEN_EN = {
    0: "",
    1: "Signal Shorted to Plus",
    2: "Signal Shorted to Ground",
    3: "No Signal",
    4: "Mechanical Malfunction",
    5: "Input Open",
    6: "Signal too High",
    7: "Signal too Low",
    8: "Control Limit Surpassed",
    9: "Adaptation Limit Surpassed",
    10: "Adaptation Limit Not Reached",
    11: "Control Limit Not Reached",
    12: "Adaptation Limit (Mul) Exceeded",
    13: "Adaptation Limit (Mul) Not Reached",
    14: "Adaptation Limit (Add) Exceeded",
    15: "Adaptation Limit (Add) Not Reached",
    16: "Signal Outside Specifications",
    17: "Control Difference",
    18: "Upper Limit",
    19: "Lower Limit",
    20: "Malfunction in Basic Setting",
    21: "Front Pressure Build-up Time too Long",
    22: "Front Pressure Reducing Time too Long",
    23: "Rear Pressure Build-up Time too Long",
    24: "Rear Pressure Reducing Time too Long",
    25: "Unknown Switch Condition",
    26: "Output Open",
    27: "Implausible Signal",
    28: "Short to Plus",
    29: "Short to Ground",
    30: "Open or Short to Plus",
    31: "Open or Short to Ground",
    32: "Resistance too High",
    33: "Resistance too Low",
    34: "No Basic Setting",
    35: "",
    36: "Open Circuit",
    37: "Defective",
}

# Klartexte: fehlercodes.py (deutsch und englisch nebeneinander); hier nach Sprache getrennt
VAG_TEXTE = {code: texte[0] for code, texte in VAG.items()}
VAG_TEXTE_EN = {code: texte[1] for code, texte in VAG.items()}
P_TEXTE = {code: texte[0] for code, texte in {**SAE_P, **VAG_P}.items()}
P_TEXTE_EN = {code: texte[1] for code, texte in {**SAE_P, **VAG_P}.items()}


def p_code(code: int) -> str | None:
    """VAG-Code der EOBD-Steuergeräte in den OBD-II-P-Code umrechnen.

    16384–17383 entsprechen P0000–P0999, 17408–18407 entsprechen P1000–P1999.
    """
    if 16384 <= code <= 17383:
        return f"P{code - 16384:04d}"
    if 17408 <= code <= 18407:
        return f"P{code - 16408:04d}"
    return None


_eigene: dict[str, str] | None = None


def _eigene_texte() -> dict[str, str]:
    global _eigene
    if _eigene is None:
        _eigene = {}
        if EIGENE_TEXTE.exists():
            try:
                daten = json.loads(EIGENE_TEXTE.read_text(encoding="utf-8"))
                _eigene = {str(k).upper(): str(v) for k, v in daten.items()}
                log.info(t("%d eigene Fehlertexte geladen"), len(_eigene))
            except (OSError, ValueError) as exc:
                log.warning(t("Eigene Fehlertexte nicht lesbar (%s): %s"), EIGENE_TEXTE, exc)
    return _eigene


def eigene_beschreibung(code: int) -> str | None:
    """Eigener Text aus fehlertexte.json für einen fünfstelligen Code (oder None)."""
    eigene = _eigene_texte()
    for schluessel in (f"{code:05d}", str(code)):
        if schluessel in eigene:
            return eigene[schluessel]
    return None


def vag_text(code: int) -> str | None:
    """Eingebauter Klartext für einen fünfstelligen VAG-Code (oder None)."""
    return (VAG_TEXTE_EN if englisch() else VAG_TEXTE).get(code)


@dataclass
class Fehler:
    code: int
    status: int

    @property
    def fehlerart(self) -> int:
        return self.status & 0x7F

    @property
    def sporadisch(self) -> bool:
        return bool(self.status & 0x80)

    @property
    def code_text(self) -> str:
        return f"{self.code:05d}"

    @property
    def p_code(self) -> str | None:
        return p_code(self.code)

    @property
    def beschreibung(self) -> str:
        eigene = _eigene_texte()
        pc = self.p_code
        for schluessel in (self.code_text, str(self.code), pc):
            if schluessel and schluessel.upper() in eigene:
                return eigene[schluessel.upper()]
        vag, p_texte = (VAG_TEXTE_EN, P_TEXTE_EN) if englisch() else (VAG_TEXTE, P_TEXTE)
        if self.code in vag:
            return vag[self.code]
        if pc and pc in p_texte:
            return p_texte[pc]
        return t("(kein Klartext hinterlegt)")

    @property
    def fehlerart_text(self) -> str:
        """Wie VCDS: Fehlerart-Nummer, -10 bei sporadisch, dazu Klartext."""
        nummer = f"{self.fehlerart:02d}-{'10' if self.sporadisch else '00'}"
        text = (FEHLERARTEN_EN if englisch() else FEHLERARTEN).get(self.fehlerart, "")
        return f"{nummer} {text}".strip()

    def zeile(self) -> str:
        teile = [self.code_text]
        if self.p_code:
            teile.append(self.p_code)
        teile.append(self.beschreibung)
        teile.append(self.fehlerart_text)
        if self.sporadisch:
            teile.append(t("sporadisch"))
        return " – ".join(teile)

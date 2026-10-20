"""Fehlercodes: Klartexte, Fehlerart und Umrechnung in OBD-II-P-Codes.

Die eingebaute Liste ist bewusst klein und enthält nur Texte, die sicher
stimmen. Eigene Texte lassen sich ergänzen in
~/.config/vagdiag/fehlertexte.json, z. B.
    {"16486": "Luftmassenmesser: Signal zu klein", "P0171": "Gemisch zu mager"}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("vagdiag.proto")

EIGENE_TEXTE = Path.home() / ".config" / "vagdiag" / "fehlertexte.json"

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

# Herstellerspezifische VAG-Codes (5-stellig)
VAG_TEXTE = {
    513: "Motordrehzahlgeber (G28)",
    515: "Hallgeber (G40)",
    522: "Kühlmitteltemperaturgeber (G62)",
    525: "Lambdasonde (G39)",
    532: "Versorgungsspannung B+",
    668: "Versorgungsspannung Klemme 30",
    771: "Geber für Kraftstoffvorratsanzeige (G)",
    779: "Außentemperaturfühler (G17)",
    1128: "Lesespule Wegfahrsperre (D2)",
    1176: "Schlüssel (Wegfahrsperre)",
    1177: "Motorsteuergerät (Wegfahrsperre)",
    17978: "Motorsteuergerät durch Wegfahrsperre gesperrt",
    18010: "Spannungsversorgung Klemme 30: Spannung zu klein",
    18020: "Motorsteuergerät falsch codiert",
    65535: "Steuergerät defekt (interner Speicherfehler)",
}

# Genormte OBD-II-Codes (SAE J2012), eigene deutsche Formulierung
P_TEXTE = {
    "P0100": "Luftmassenmesser: Stromkreis",
    "P0101": "Luftmassenmesser: Bereich/Funktion",
    "P0102": "Luftmassenmesser: Signal zu klein",
    "P0103": "Luftmassenmesser: Signal zu groß",
    "P0105": "Saugrohrdruck-/Höhengeber: Stromkreis",
    "P0106": "Saugrohrdruck-/Höhengeber: Bereich/Funktion",
    "P0107": "Saugrohrdruck-/Höhengeber: Signal zu klein",
    "P0108": "Saugrohrdruck-/Höhengeber: Signal zu groß",
    "P0110": "Ansauglufttemperaturgeber: Stromkreis",
    "P0111": "Ansauglufttemperaturgeber: Bereich/Funktion",
    "P0112": "Ansauglufttemperaturgeber: Signal zu klein",
    "P0113": "Ansauglufttemperaturgeber: Signal zu groß",
    "P0115": "Kühlmitteltemperaturgeber: Stromkreis",
    "P0116": "Kühlmitteltemperaturgeber: Bereich/Funktion",
    "P0117": "Kühlmitteltemperaturgeber: Signal zu klein",
    "P0118": "Kühlmitteltemperaturgeber: Signal zu groß",
    "P0120": "Drosselklappen-/Pedalwertgeber A: Stromkreis",
    "P0121": "Drosselklappen-/Pedalwertgeber A: Bereich/Funktion",
    "P0122": "Drosselklappen-/Pedalwertgeber A: Signal zu klein",
    "P0123": "Drosselklappen-/Pedalwertgeber A: Signal zu groß",
    "P0125": "Kühlmitteltemperatur zu niedrig für Lambdaregelung",
    "P0130": "Lambdasonde vor Kat (Bank 1, Sonde 1): Stromkreis",
    "P0131": "Lambdasonde vor Kat (Bank 1, Sonde 1): Spannung zu niedrig",
    "P0132": "Lambdasonde vor Kat (Bank 1, Sonde 1): Spannung zu hoch",
    "P0133": "Lambdasonde vor Kat (Bank 1, Sonde 1): reagiert zu langsam",
    "P0134": "Lambdasonde vor Kat (Bank 1, Sonde 1): keine Aktivität",
    "P0135": "Lambdasonde vor Kat (Bank 1, Sonde 1): Heizung Stromkreis",
    "P0136": "Lambdasonde nach Kat (Bank 1, Sonde 2): Stromkreis",
    "P0137": "Lambdasonde nach Kat (Bank 1, Sonde 2): Spannung zu niedrig",
    "P0138": "Lambdasonde nach Kat (Bank 1, Sonde 2): Spannung zu hoch",
    "P0139": "Lambdasonde nach Kat (Bank 1, Sonde 2): reagiert zu langsam",
    "P0140": "Lambdasonde nach Kat (Bank 1, Sonde 2): keine Aktivität",
    "P0141": "Lambdasonde nach Kat (Bank 1, Sonde 2): Heizung Stromkreis",
    "P0170": "Gemischaufbereitung Bank 1: Fehlfunktion",
    "P0171": "Gemisch Bank 1 zu mager",
    "P0172": "Gemisch Bank 1 zu fett",
    "P0300": "Verbrennungsaussetzer erkannt (mehrere/zufällige Zylinder)",
    "P0301": "Verbrennungsaussetzer Zylinder 1",
    "P0302": "Verbrennungsaussetzer Zylinder 2",
    "P0303": "Verbrennungsaussetzer Zylinder 3",
    "P0304": "Verbrennungsaussetzer Zylinder 4",
    "P0320": "Drehzahlgeber/Zündung Eingang: Stromkreis",
    "P0321": "Drehzahlgeber/Zündung Eingang: Bereich/Funktion",
    "P0322": "Drehzahlgeber/Zündung Eingang: kein Signal",
    "P0325": "Klopfsensor 1: Stromkreis",
    "P0327": "Klopfsensor 1: Signal zu klein",
    "P0328": "Klopfsensor 1: Signal zu groß",
    "P0335": "Kurbelwellengeber: Stromkreis",
    "P0336": "Kurbelwellengeber: Bereich/Funktion",
    "P0340": "Nockenwellengeber: Stromkreis",
    "P0341": "Nockenwellengeber: Bereich/Funktion",
    "P0400": "Abgasrückführung: Durchfluss",
    "P0410": "Sekundärluftsystem",
    "P0420": "Katalysator Bank 1: Wirkungsgrad unter Schwellwert",
    "P0440": "Kraftstoffverdunstungs-Rückhaltesystem: Fehlfunktion",
    "P0441": "Kraftstoffverdunstungs-Rückhaltesystem: falscher Spüldurchfluss",
    "P0443": "Magnetventil Aktivkohlebehälter: Stromkreis",
    "P0444": "Magnetventil Aktivkohlebehälter: Stromkreis offen",
    "P0445": "Magnetventil Aktivkohlebehälter: Kurzschluss",
    "P0500": "Geschwindigkeitsgeber: Fehlfunktion",
    "P0501": "Geschwindigkeitsgeber: Bereich/Funktion",
    "P0505": "Leerlaufregelung: Fehlfunktion",
    "P0506": "Leerlaufdrehzahl niedriger als erwartet",
    "P0507": "Leerlaufdrehzahl höher als erwartet",
    "P0560": "Bordnetzspannung: Fehlfunktion",
    "P0562": "Bordnetzspannung zu niedrig",
    "P0563": "Bordnetzspannung zu hoch",
    "P0601": "Steuergerät: Prüfsummenfehler im Speicher",
    "P0602": "Steuergerät: Programmierfehler",
    "P0603": "Steuergerät: Fehler im Dauerspeicher",
    "P0604": "Steuergerät: RAM-Fehler",
    "P0605": "Steuergerät: ROM-Fehler",
}


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
                log.info("%d eigene Fehlertexte geladen", len(_eigene))
            except (OSError, ValueError) as exc:
                log.warning("Eigene Fehlertexte nicht lesbar (%s): %s", EIGENE_TEXTE, exc)
    return _eigene


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
        if self.code in VAG_TEXTE:
            return VAG_TEXTE[self.code]
        if pc and pc in P_TEXTE:
            return P_TEXTE[pc]
        return "(kein Klartext hinterlegt)"

    @property
    def fehlerart_text(self) -> str:
        """Wie VCDS: Fehlerart-Nummer, -10 bei sporadisch, dazu Klartext."""
        nummer = f"{self.fehlerart:02d}-{'10' if self.sporadisch else '00'}"
        text = FEHLERARTEN.get(self.fehlerart, "")
        return f"{nummer} {text}".strip()

    def zeile(self) -> str:
        teile = [self.code_text]
        if self.p_code:
            teile.append(self.p_code)
        teile.append(self.beschreibung)
        teile.append(self.fehlerart_text)
        if self.sporadisch:
            teile.append("sporadisch")
        return " – ".join(teile)

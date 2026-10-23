"""Fehlercodes: Klartexte, Fehlerart und Umrechnung in OBD-II-P-Codes.

Die eingebaute Liste ist bewusst klein und enthält nur Texte, die sicher
stimmen – auf Deutsch und Englisch. Eigene Texte lassen sich ergänzen in
fehlertexte.json im Einstellungsordner (siehe pfade.py), z. B.
    {"16486": "Luftmassenmesser: Signal zu klein", "P0171": "Gemisch zu mager"}
Eigene Texte gelten in beiden Sprachen.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

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

VAG_TEXTE_EN = {
    513: "Engine Speed Sensor (G28)",
    515: "Hall Sender (G40)",
    522: "Coolant Temperature Sensor (G62)",
    525: "Oxygen (Lambda) Sensor (G39)",
    532: "Supply Voltage B+",
    668: "Supply Voltage Terminal 30",
    771: "Fuel Level Sensor (G)",
    779: "Outside Air Temperature Sensor (G17)",
    1128: "Immobilizer Read Coil (D2)",
    1176: "Key (Immobilizer)",
    1177: "Engine Control Module (Immobilizer)",
    17978: "Engine Control Module Locked by Immobilizer",
    18010: "Power Supply Terminal 30: Voltage too Low",
    18020: "Engine Control Module Incorrectly Coded",
    65535: "Internal Control Module Memory Error",
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

P_TEXTE_EN = {
    "P0100": "Mass Air Flow Sensor: Circuit",
    "P0101": "Mass Air Flow Sensor: Range/Performance",
    "P0102": "Mass Air Flow Sensor: Signal too Low",
    "P0103": "Mass Air Flow Sensor: Signal too High",
    "P0105": "Manifold Absolute Pressure/Barometric Sensor: Circuit",
    "P0106": "Manifold Absolute Pressure/Barometric Sensor: Range/Performance",
    "P0107": "Manifold Absolute Pressure/Barometric Sensor: Signal too Low",
    "P0108": "Manifold Absolute Pressure/Barometric Sensor: Signal too High",
    "P0110": "Intake Air Temperature Sensor: Circuit",
    "P0111": "Intake Air Temperature Sensor: Range/Performance",
    "P0112": "Intake Air Temperature Sensor: Signal too Low",
    "P0113": "Intake Air Temperature Sensor: Signal too High",
    "P0115": "Coolant Temperature Sensor: Circuit",
    "P0116": "Coolant Temperature Sensor: Range/Performance",
    "P0117": "Coolant Temperature Sensor: Signal too Low",
    "P0118": "Coolant Temperature Sensor: Signal too High",
    "P0120": "Throttle/Pedal Position Sensor A: Circuit",
    "P0121": "Throttle/Pedal Position Sensor A: Range/Performance",
    "P0122": "Throttle/Pedal Position Sensor A: Signal too Low",
    "P0123": "Throttle/Pedal Position Sensor A: Signal too High",
    "P0125": "Coolant Temperature too Low for Closed Loop Control",
    "P0130": "Oxygen Sensor before Catalyst (Bank 1, Sensor 1): Circuit",
    "P0131": "Oxygen Sensor before Catalyst (Bank 1, Sensor 1): Low Voltage",
    "P0132": "Oxygen Sensor before Catalyst (Bank 1, Sensor 1): High Voltage",
    "P0133": "Oxygen Sensor before Catalyst (Bank 1, Sensor 1): Slow Response",
    "P0134": "Oxygen Sensor before Catalyst (Bank 1, Sensor 1): No Activity",
    "P0135": "Oxygen Sensor before Catalyst (Bank 1, Sensor 1): Heater Circuit",
    "P0136": "Oxygen Sensor after Catalyst (Bank 1, Sensor 2): Circuit",
    "P0137": "Oxygen Sensor after Catalyst (Bank 1, Sensor 2): Low Voltage",
    "P0138": "Oxygen Sensor after Catalyst (Bank 1, Sensor 2): High Voltage",
    "P0139": "Oxygen Sensor after Catalyst (Bank 1, Sensor 2): Slow Response",
    "P0140": "Oxygen Sensor after Catalyst (Bank 1, Sensor 2): No Activity",
    "P0141": "Oxygen Sensor after Catalyst (Bank 1, Sensor 2): Heater Circuit",
    "P0170": "Fuel Trim Bank 1: Malfunction",
    "P0171": "System too Lean (Bank 1)",
    "P0172": "System too Rich (Bank 1)",
    "P0300": "Random/Multiple Cylinder Misfire Detected",
    "P0301": "Cylinder 1 Misfire Detected",
    "P0302": "Cylinder 2 Misfire Detected",
    "P0303": "Cylinder 3 Misfire Detected",
    "P0304": "Cylinder 4 Misfire Detected",
    "P0320": "Ignition/Distributor Engine Speed Input: Circuit",
    "P0321": "Ignition/Distributor Engine Speed Input: Range/Performance",
    "P0322": "Ignition/Distributor Engine Speed Input: No Signal",
    "P0325": "Knock Sensor 1: Circuit",
    "P0327": "Knock Sensor 1: Signal too Low",
    "P0328": "Knock Sensor 1: Signal too High",
    "P0335": "Crankshaft Position Sensor: Circuit",
    "P0336": "Crankshaft Position Sensor: Range/Performance",
    "P0340": "Camshaft Position Sensor: Circuit",
    "P0341": "Camshaft Position Sensor: Range/Performance",
    "P0400": "Exhaust Gas Recirculation: Flow",
    "P0410": "Secondary Air Injection System",
    "P0420": "Catalyst System Efficiency below Threshold (Bank 1)",
    "P0440": "Evaporative Emission System: Malfunction",
    "P0441": "Evaporative Emission System: Incorrect Purge Flow",
    "P0443": "EVAP Purge Control Valve: Circuit",
    "P0444": "EVAP Purge Control Valve: Circuit Open",
    "P0445": "EVAP Purge Control Valve: Circuit Shorted",
    "P0500": "Vehicle Speed Sensor: Malfunction",
    "P0501": "Vehicle Speed Sensor: Range/Performance",
    "P0505": "Idle Air Control System: Malfunction",
    "P0506": "Idle Speed Lower than Expected",
    "P0507": "Idle Speed Higher than Expected",
    "P0560": "System Voltage: Malfunction",
    "P0562": "System Voltage Low",
    "P0563": "System Voltage High",
    "P0601": "Control Module: Memory Checksum Error",
    "P0602": "Control Module: Programming Error",
    "P0603": "Control Module: Keep Alive Memory Error",
    "P0604": "Control Module: RAM Error",
    "P0605": "Control Module: ROM Error",
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

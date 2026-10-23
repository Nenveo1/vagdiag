"""Stellglieddiagnose: Nummern und Namen der Stellglieder.

Bei der Stellglieddiagnose meldet ein Steuergerät jedes Stellglied mit einer Nummer aus
derselben Liste wie die fünfstelligen VAG-Fehlercodes (z. B. 00662 = Drehzahlmesser).
01195 (hex 04AB) und 00000 bedeuten „Ende“.

Die eingebauten Namen stammen aus Beobachtungen, die das freie Programm kw1281test
(MIT-Lizenz, Greg Menounos und Mitwirkende) veröffentlicht hat: Kombiinstrument
(KW1281) und Diesel-Motorsteuergeräte EDC15/EDC16 (KWP2000). Unbekannte Nummern zeigt
vagdiag ohne Namen; eigene Namen lassen sich wie Fehlertexte in fehlertexte.json im
Einstellungsordner eintragen, z. B. {"01247": "Magnetventil Aktivkohlebehälter"}.

Bremsen, Airbag, Wegfahrsperre und Lenkung steuert vagdiag nie an (GESPERRT, und nach der
Kennung auch unter anderer Adresse) – das prüfen die Schreibsperren in kw1281.py und
kwp2000.py vor jedem Block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .fehler import eigene_beschreibung, vag_text
from .sprache import N_, englisch, t

ENDE = (0x04AB, 0x0000)

# Steuergeräte, deren Stellglieder vagdiag nie ansteuert
GESPERRT = {
    0x03: N_("Bremsenelektronik"),
    0x15: N_("Airbag"),
    0x23: N_("Bremskraftverstärker"),
    0x25: N_("Wegfahrsperre"),
    0x44: N_("Lenkhilfe"),
    0x53: N_("Parkbremse"),
}

# Woran man Airbag, Bremsen, Wegfahrsperre und Lenkung an der Kennung erkennt – falls sich so
# ein Gerät unter einer anderen Adresse meldet (etwa wenn eine Störung die Reizung verfälscht
# hat): Mitte der VAG-Teilenummer (909 6xx/959 655 Airbag, 907 379/614 xxx ABS/ESP,
# 907 801 Parkbremse, 953 2xx Wegfahrsperre, 423 xxx/909 144 Lenkung) und Wörter im Namen.
# Ein Kombi mit eingebauter Wegfahrsperre bleibt erlaubt.
_TEILE = re.compile(r"^[0-9A-Z]{3}(?:909[56]\d\d|909144|959655|907379|907801|614\d{3}|"
                    r"9532[3-5]\d|423\d{3})")
_WOERTER = re.compile(r"(?<![A-Z])(?:AIRBAG|ABS|ESP|EDS|ASR|EPS|LENKHILFE|LENKUNG)(?![A-Z])")


def gesperrt_nach_kennung(teilenummer: str, bauteil: str) -> str | None:
    """Grund, warum dieses Gerät nach seiner Kennung keine Expertenfunktion bekommt."""
    teil = re.sub(r"[\s.-]", "", (teilenummer or "").upper())
    text = f"{teilenummer} {bauteil}".upper()
    if _TEILE.match(teil) or _WOERTER.search(text):
        return t("Das Steuergerät meldet sich als „{kennung}“ – das sieht nach Airbag, Bremsen, "
                 "Wegfahrsperre oder Lenkung aus. Expertenfunktionen sind dort gesperrt, egal "
                 "unter welcher Adresse.", kennung=f"{teilenummer} {bauteil}".strip())
    return None


# Nummer → (deutsch, englisch)
TEXTE: dict[int, tuple[str, str]] = {
    # Kombiinstrument (KW1281)
    0x01F5: ("Warnleuchte Ölstand", "Oil level warning light"),
    0x01F6: ("Kontrollleuchte Wegfahrsperre", "Immobilizer warning light"),
    0x0272: ("Glühzeit-Kontrollleuchte", "Glow plug warning light"),
    0x0295: ("Kühlmitteltemperaturanzeige", "Coolant temperature gauge"),
    0x0296: ("Drehzahlmesser", "Rev counter"),
    0x0297: ("Geschwindigkeitsmesser", "Speedometer"),
    0x0298: ("Kraftstoffvorratsanzeige", "Fuel gauge"),
    0x0299: ("Gurtwarnleuchte", "Seat belt warning light"),
    0x029A: ("Gong", "Gong"),
    0x02F2: ("Warnleuchte Kühlmitteltemperatur", "Coolant temperature warning light"),
    0x02F3: ("Warnleuchte Öldruck", "Oil pressure warning light"),
    0x031E: ("Segmenttest der Anzeigen", "Display segment test"),
    0x03FF: ("Summer", "Chime"),
    0x0416: ("Warnleuchte Bremsbeläge", "Brake pad warning light"),
    0x0417: ("Warnleuchte Bremse", "Brake warning light"),
    0x043A: ("Warnleuchte Kraftstoffreserve", "Low fuel warning light"),
    0x043B: ("Warnleuchte Waschwasserstand", "Low washer fluid warning light"),
    # Diesel-Motorsteuergeräte EDC15/EDC16 (KWP2000)
    0x0243: ("Magnetventil Ladedruckbegrenzung (N75)", "Boost pressure control valve (N75)"),
    0x04EE: ("Magnetventil Ladedruckbegrenzung (N75)", "Boost pressure control valve (N75)"),
    0x0270: ("Abschaltung Klimakompressor", "A/C compressor cut-off"),
    0x02EE: ("Abgaswarnleuchte (K83)", "Malfunction indicator lamp (K83)"),
    0x1690: ("Abgaswarnleuchte", "Malfunction indicator lamp"),
    0x46B4: ("Abgaswarnleuchte", "Malfunction indicator lamp"),
    0x0403: ("Ventil Abgasrückführung", "EGR valve"),
    0x04F1: ("Ventil Abgasrückführung", "EGR valve"),
    0x0480: ("Kühlerlüfter 1", "Radiator fan 1"),
    0x09E6: ("Kühlerlüfter 1", "Radiator fan 1"),
    0x04A9: ("Relais Zusatzheizung Kühlmittel (kleine Leistung)",
             "Coolant heater relay (low output)"),
    0x3003: ("Relais Zusatzheizung Kühlmittel (kleine Leistung)",
             "Coolant heater relay (low output)"),
    0x04AA: ("Relais Zusatzheizung Kühlmittel (große Leistung)",
             "Coolant heater relay (high output)"),
    0x3005: ("Relais Zusatzheizung Kühlmittel (große Leistung)",
             "Coolant heater relay (high output)"),
    0x04D5: ("Kraftstoffabschaltventil (N109)", "Fuel shut-off valve (N109)"),
    0x04F2: ("Relais Glühkerzen (J52)", "Glow plug relay (J52)"),
    0x04F5: ("Ventil Spritzbeginn (N108)", "Injection timing valve (N108)"),
    0x0684: ("Steuergerät Glühzeit", "Glow plug control module"),
    0x42AC: ("Steuergerät Glühzeit", "Glow plug control module"),
    0x09E8: ("Umschaltventil Kühler Abgasrückführung", "EGR cooler bypass valve"),
    0x1495: ("Umschaltventil Kühler Abgasrückführung", "EGR cooler bypass valve"),
    0x1616: ("Glühzeit-Kontrollleuchte", "Glow plug warning light"),
    0x162D: ("Kontrollleuchte Partikelfilter", "Particulate filter warning light"),
    0x3100: ("Saugrohrklappe", "Intake manifold flap"),
    0x4C64: ("Saugrohrklappe", "Intake manifold flap"),
    0x3372: ("Drallklappen-Steller", "Swirl flap actuator"),
    0x4808: ("Drallklappen-Steller", "Swirl flap actuator"),
    # Ende der Stellglieddiagnose
    0x04AB: ("Ende", "End"),
    0x0000: ("Ende", "End"),
}

# Namen, die nur der Simulator meldet (Nummern ab F000) – eingetragen von sim.py
SIMULATOR: dict[int, tuple[str, str]] = {}


def name(code: int) -> str:
    """Name eines Stellglieds in der eingestellten Sprache – eigene Texte haben Vorrang."""
    for text in (eigene_beschreibung(code), vag_text(code)):
        if text:
            return text
    for tabelle in (TEXTE, SIMULATOR):
        if code in tabelle:
            return tabelle[code][1 if englisch() else 0]
    return t("(kein Klartext hinterlegt)")


@dataclass
class Stellglied:
    code: int
    roh: bytes = b""            # Antwortdaten des Steuergeräts (fürs Protokoll)

    @property
    def code_text(self) -> str:
        return f"{self.code:05d}"

    @property
    def name(self) -> str:
        return name(self.code)

    @property
    def ende(self) -> bool:
        return self.code in ENDE

    @property
    def text(self) -> str:
        return f"{self.code_text} – {self.name}"

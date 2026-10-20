"""Kilometerstand aus dem Kombiinstrument lesen – nur lesen.

Viele VAG-Kombis dieser Zeit melden ihn in Messwertgruppe 002, Feld 1. Dein
TRW-Kombi schickt dort FF FF („kein Wert“). Dann wird Anpassungskanal 09
gelesen: Bei vielen VAG-Kombis steht dort der Kilometerstand in
10-km-Schritten. Ob ein bestimmtes Kombi das genauso macht, zeigt nur der
Vergleich mit seiner Anzeige – deshalb gilt dieser Wert als unbestätigt.

Geschrieben wird nichts: Den Kilometerstand zu verändern ist nicht
vorgesehen (und in Deutschland nach § 22b StVG verboten).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .kw1281 import KW1281, Nak, NotAvailable, Stoerung
from .sprache import t, tausender

KANAL = 9
SCHRITT_KM = 10


def km_text(km: int) -> str:
    """12.345 km (Deutsch) bzw. 12,345 km (Englisch)."""
    return tausender(km) + " km"


km_deutsch = km_text   # alter Name


@dataclass
class Kilometerstand:
    km: int | None
    quelle: str = ""
    rohwert: str = ""
    bestaetigt: bool = False          # aus einem Feld mit der Einheit km
    geprueft: list[str] = field(default_factory=list)

    @property
    def zeilen(self) -> list[str]:
        if self.km is None:
            zeilen = [t("Das Kombi liefert den Kilometerstand weder in Messwertgruppe 002 noch "
                        "in Anpassungskanal {kanal:02d}.", kanal=KANAL)]
        else:
            zeilen = [t("Kilometerstand: {km}", km=km_text(self.km)),
                      t("Quelle: {quelle}", quelle=self.quelle)
                      + (" – " + t("Rohwert {rohwert}", rohwert=self.rohwert)
                         if self.rohwert else "")]
            if not self.bestaetigt:
                zeilen += ["", t("Unbestätigt: Bei vielen VAG-Kombis steht in Kanal {kanal:02d} "
                                 "der Kilometerstand in {schritt}-km-Schritten. Bitte mit der "
                                 "Anzeige im Kombi vergleichen.", kanal=KANAL,
                                 schritt=SCHRITT_KM)]
        if self.geprueft:
            zeilen += ["", t("Geprüft:")] + [f"  – {g}" for g in self.geprueft]
        return zeilen


def _wiederholt(funktion, versuche: int = 3):
    for versuch in range(1, versuche + 1):
        try:
            return funktion()
        except Stoerung:
            if versuch == versuche:
                raise


def lesen(proto: KW1281) -> Kilometerstand:
    """Erst Messwertgruppe 002, dann Anpassungskanal 09."""
    geprueft: list[str] = []
    try:
        werte = _wiederholt(lambda: proto.gruppe_lesen(2))
    except (Nak, NotAvailable):
        geprueft.append(t("Messwertgruppe 002: nicht vorhanden"))
    else:
        feld_km = next((w for w in werte if w.einheit == "km"), None)
        if feld_km is None:
            geprueft.append(t("Messwertgruppe 002: kein Feld mit Kilometern"))
        elif not feld_km.gueltig or feld_km.zahl is None:
            geprueft.append(t("Messwertgruppe 002, Feld {feld}: kein Wert (FF FF)",
                              feld=feld_km.feld))
        else:
            return Kilometerstand(int(round(feld_km.zahl)),
                                  t("Messwertgruppe 002, Feld {feld}", feld=feld_km.feld),
                                  feld_km.roh, True, geprueft)
    try:
        anpassung = _wiederholt(lambda: proto.anpassung_lesen(KANAL))
    except (Nak, NotAvailable) as exc:
        geprueft.append(str(exc))
        return Kilometerstand(None, geprueft=geprueft)
    if anpassung.wert == 0xFFFF:
        beschreibung = (" – " + t("das Kombi beschreibt den Kanal als „{text}“",
                                  text=anpassung.beschreibung)
                        if anpassung.beschreibung else "")
        geprueft.append(t("Anpassungskanal {kanal:02d}: kein Wert (FF FF)", kanal=KANAL)
                        + beschreibung)
        return Kilometerstand(None, geprueft=geprueft)
    return Kilometerstand(anpassung.wert * SCHRITT_KM,
                          t("Anpassungskanal {kanal:02d}", kanal=KANAL),
                          f"{anpassung.wert} (hex {anpassung.hex}) × {SCHRITT_KM} km",
                          False, geprueft)

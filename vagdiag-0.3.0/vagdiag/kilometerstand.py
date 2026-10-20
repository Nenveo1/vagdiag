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

from .kw1281 import KW1281, Nak, NotAvailable

KANAL = 9
SCHRITT_KM = 10


def km_deutsch(km: int) -> str:
    return f"{km:,}".replace(",", ".") + " km"


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
            zeilen = ["Das Kombi liefert den Kilometerstand weder in Messwertgruppe 002 "
                      f"noch in Anpassungskanal {KANAL:02d}."]
        else:
            zeilen = [f"Kilometerstand: {km_deutsch(self.km)}",
                      f"Quelle: {self.quelle}" + (f" – Rohwert {self.rohwert}"
                                                  if self.rohwert else "")]
            if not self.bestaetigt:
                zeilen += ["", f"Unbestätigt: Bei vielen VAG-Kombis steht in Kanal {KANAL:02d} "
                               f"der Kilometerstand in {SCHRITT_KM}-km-Schritten. Bitte mit der "
                               "Anzeige im Kombi vergleichen."]
        if self.geprueft:
            zeilen += ["", "Geprüft:"] + [f"  – {g}" for g in self.geprueft]
        return zeilen


def lesen(proto: KW1281) -> Kilometerstand:
    """Erst Messwertgruppe 002, dann Anpassungskanal 09."""
    geprueft: list[str] = []
    try:
        werte = proto.gruppe_lesen(2)
    except (Nak, NotAvailable):
        geprueft.append("Messwertgruppe 002: nicht vorhanden")
    else:
        feld_km = next((w for w in werte if w.einheit == "km"), None)
        if feld_km is None:
            geprueft.append("Messwertgruppe 002: kein Feld mit Kilometern")
        elif not feld_km.gueltig or feld_km.zahl is None:
            geprueft.append(f"Messwertgruppe 002, Feld {feld_km.feld}: kein Wert (FF FF)")
        else:
            return Kilometerstand(int(round(feld_km.zahl)),
                                  f"Messwertgruppe 002, Feld {feld_km.feld}",
                                  feld_km.roh, True, geprueft)
    try:
        anpassung = proto.anpassung_lesen(KANAL)
    except (Nak, NotAvailable) as exc:
        geprueft.append(str(exc))
        return Kilometerstand(None, geprueft=geprueft)
    if anpassung.wert == 0xFFFF:
        geprueft.append(f"Anpassungskanal {KANAL:02d}: kein Wert (FF FF)")
        return Kilometerstand(None, geprueft=geprueft)
    return Kilometerstand(anpassung.wert * SCHRITT_KM, f"Anpassungskanal {KANAL:02d}",
                          f"{anpassung.wert} (hex {anpassung.hex}) × {SCHRITT_KM} km",
                          False, geprueft)

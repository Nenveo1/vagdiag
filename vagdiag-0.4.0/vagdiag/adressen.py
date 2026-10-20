"""Übliche Steuergeräte-Adressen (hexadezimal, wie in VCDS geschrieben)."""

from .sprache import N_, t

ADRESSEN = {
    0x01: N_("Motorelektronik"),
    0x02: N_("Getriebeelektronik"),
    0x03: N_("Bremsenelektronik (ABS)"),
    0x08: N_("Klima-/Heizungselektronik"),
    0x15: N_("Airbag"),
    0x16: N_("Lenkradelektronik"),
    0x17: N_("Schalttafeleinsatz (Kombi)"),
    0x25: N_("Wegfahrsperre"),
    0x35: N_("Zentralverriegelung"),
    0x45: N_("Innenraumüberwachung"),
    0x46: N_("Komfortsystem"),
    0x55: N_("Leuchtweitenregulierung"),
    0x56: N_("Radio"),
}


def name(adresse: int) -> str:
    return t(ADRESSEN.get(adresse, N_("unbekanntes Steuergerät")))


def text(adresse: int) -> str:
    return f"{adresse:02X} – {name(adresse)}"

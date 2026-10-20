"""Übliche Steuergeräte-Adressen (hexadezimal, wie in VCDS geschrieben)."""

ADRESSEN = {
    0x01: "Motorelektronik",
    0x02: "Getriebeelektronik",
    0x03: "Bremsenelektronik (ABS)",
    0x08: "Klima-/Heizungselektronik",
    0x15: "Airbag",
    0x16: "Lenkradelektronik",
    0x17: "Schalttafeleinsatz (Kombi)",
    0x25: "Wegfahrsperre",
    0x35: "Zentralverriegelung",
    0x45: "Innenraumüberwachung",
    0x46: "Komfortsystem",
    0x55: "Leuchtweitenregulierung",
    0x56: "Radio",
}


def name(adresse: int) -> str:
    return ADRESSEN.get(adresse, "unbekanntes Steuergerät")


def text(adresse: int) -> str:
    return f"{adresse:02X} – {name(adresse)}"

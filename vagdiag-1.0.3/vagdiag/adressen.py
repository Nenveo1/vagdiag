# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Steuergeräte-Adressen (hexadezimal, wie in VCDS geschrieben).

ADRESSEN sind die üblichen – die Liste links und der normale Scan. WEITERE nennt
Adressen, die es in manchen Autos zusätzlich gibt (Namen nach den Übersichten von
Ross-Tech); der Scan aller Adressen fragt jede von 01 bis 7F ab – außer denen in
UEBERSPRINGEN.
"""

from .sprache import N_, t

ADRESSEN = {
    0x01: N_("Motorelektronik"),
    0x02: N_("Getriebeelektronik"),
    0x03: N_("Bremsenelektronik (ABS)"),
    0x08: N_("Klima-/Heizungselektronik"),
    0x09: N_("Zentralelektrik"),
    0x15: N_("Airbag"),
    0x16: N_("Lenkradelektronik"),
    0x17: N_("Schalttafeleinsatz (Kombi)"),
    0x19: N_("Diagnose-Interface Datenbus (Gateway)"),
    0x25: N_("Wegfahrsperre"),
    0x35: N_("Zentralverriegelung"),
    0x45: N_("Innenraumüberwachung"),
    0x46: N_("Komfortsystem"),
    0x55: N_("Leuchtweitenregulierung"),
    0x56: N_("Radio"),
}

WEITERE = {
    0x05: N_("Zugang/Startberechtigung"),
    0x06: N_("Sitzverstellung Beifahrerseite"),
    0x07: N_("Bedieneinheit vorn"),
    0x0E: N_("Mediaplayer 1"),
    0x0F: N_("Digitalradio"),
    0x11: N_("Motorelektronik 2"),
    0x13: N_("Abstandsregelung"),
    0x18: N_("Zusatzheizung"),
    0x1E: N_("Mediaplayer 2"),
    0x22: N_("Allradelektronik"),
    0x23: N_("Bremskraftverstärker"),
    0x28: N_("Klimaanlage hinten"),
    0x29: N_("Licht links"),
    0x33: N_("OBD-II (allgemein)"),
    0x34: N_("Niveauregulierung"),
    0x36: N_("Sitzverstellung Fahrerseite"),
    0x37: N_("Navigation"),
    0x39: N_("Licht rechts"),
    0x3D: N_("Sonderfunktion"),
    0x42: N_("Türelektronik Fahrerseite"),
    0x44: N_("Lenkhilfe"),
    0x47: N_("Soundsystem"),
    0x4F: N_("Zentralelektrik 2"),
    0x52: N_("Türelektronik Beifahrerseite"),
    0x53: N_("Parkbremse"),
    0x57: N_("TV-Tuner"),
    0x5F: N_("Informationselektronik"),
    0x61: N_("Batterieregelung"),
    0x62: N_("Tür hinten links"),
    0x65: N_("Reifendruckkontrolle"),
    0x67: N_("Sprachbedienung"),
    0x68: N_("Wischer"),
    0x69: N_("Anhängerfunktion"),
    0x6E: N_("Bedieneinheit Dach"),
    0x72: N_("Tür hinten rechts"),
    0x75: N_("Telematik"),
    0x76: N_("Einparkhilfe"),
    0x77: N_("Telefon"),
    0x7C: N_("Radio (Werksmodus)"),
}

# Beim Scan aller Adressen nie gereizt
UEBERSPRINGEN = {
    0x33: N_("OBD-II-Adresse (allgemeine Abgasdiagnose, kein eigenes Steuergerät)"),
    0x7C: N_("Werksmodus des Radios"),
}


def alle() -> list[int]:
    """Alle Adressen 01 bis 7F (die übersprungenen fragt der Scan nicht ab)."""
    return list(range(0x01, 0x80))


def name(adresse: int) -> str:
    return t(ADRESSEN.get(adresse) or WEITERE.get(adresse) or N_("unbekanntes Steuergerät"))


def text(adresse: int) -> str:
    return f"{adresse:02X} – {name(adresse)}"

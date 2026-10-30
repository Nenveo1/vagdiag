# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""An welchen Steuergeräten vagdiag geprüft ist – und der Hinweis an allen anderen.

Geprüft heißt: am Testfahrzeug (Polo 6KV, 12/2000) verbunden, gelesen und mit der Anzeige
im Auto verglichen. Entschieden wird nach der Teilenummer (ohne Leerzeichen, Punkte und
Striche), nicht nach dem Auto: Dasselbe Steuergerät in einem anderen Auto gilt als geprüft,
ein anderes Steuergerät im Testfahrzeug nicht.

vagdiag sperrt an ungeprüften Steuergeräten nichts – es zeigt nur den Hinweis: über den
Reitern, in der Identifikation (und damit in Berichten und im Scan) und in jeder Rückfrage
vor dem Löschen des Fehlerspeichers und vor Expertenfunktionen. Gesperrt bleibt nur, was
ein Steuergerät falsch verstehen könnte (siehe experte.py und die Schreibsperren).
"""

from __future__ import annotations

import re

from .sprache import N_, t

# normalisierte Teilenummer → was es ist (Anzeige mit t())
GEPRUEFT: dict[str, str] = {
    "6K0906032M": N_("Motorelektronik ME7.5.10"),
    "6K9920806": N_("Kombiinstrument TRW"),
    "6X0907379B": N_("ABS"),
    "6X0953257": N_("Wegfahrsperre"),
    "1J0909609Q": N_("Airbag"),
    "6N0909901": N_("Gateway K<->CAN"),
}

# Die Simulatoren bilden die geprüften Geräte nach und gelten wie sie; die KWP2000-Simulatoren
# (…KWP, SIMKWP2000) haben kein geprüftes Vorbild
SIMULATOR_VORBILD = {
    "SIM906032": "6K0906032M",
    "SIM920806": "6K9920806",
    "SIM907379": "6X0907379B",
    "SIM953257": "6X0953257",
    "SIM959655": "1J0909609Q",
}

HINWEIS = N_("An diesem Steuergerät ist vagdiag nicht geprüft – Feldnamen und Erklärungen "
             "können abweichen.")
HINWEIS_OHNE_KENNUNG = N_("Dieses Steuergerät hat keine Teilenummer geschickt – vagdiag kann "
                          "nicht erkennen, ob es hier geprüft ist. Feldnamen und Erklärungen "
                          "können abweichen.")


def teilenummer_normal(teilenummer: str | None) -> str:
    """„6X0 907 379 B“ → „6X0907379B“."""
    return re.sub(r"[\s.\-]", "", (teilenummer or "").upper())


def vorbild(teilenummer: str | None) -> str:
    """Normalisierte Teilenummer – beim Simulator die des Geräts, das er nachbildet."""
    nummer = teilenummer_normal(teilenummer)
    return SIMULATOR_VORBILD.get(nummer, nummer)


def ist_geprueft(teilenummer: str | None) -> bool:
    return vorbild(teilenummer) in GEPRUEFT


def hinweis_teilenummer(teilenummer: str | None) -> str | None:
    """Hinweistext für ein Steuergerät mit dieser Teilenummer – None, wenn es geprüft ist."""
    if not teilenummer_normal(teilenummer):
        return t(HINWEIS_OHNE_KENNUNG)
    return None if ist_geprueft(teilenummer) else t(HINWEIS)


def hinweis(verbindung) -> str | None:
    """Hinweis für eine Verbindung (kw1281.Verbindung) – None ohne Verbindung oder wenn das
    Steuergerät geprüft ist."""
    if verbindung is None:
        return None
    return hinweis_teilenummer(verbindung.teilenummer)


def hinweis_kennung(kennung: tuple) -> str | None:
    """Wie hinweis(), für eine Kennung (Adresse, Teilenummer, Bauteil)."""
    if len(kennung) != 3:
        return None
    return hinweis_teilenummer(kennung[1])


def liste() -> str:
    """Die geprüften Steuergeräte als eine Zeile, z. B. für Tooltips."""
    return ", ".join(f"{nummer} ({t(name)})" for nummer, name in GEPRUEFT.items())

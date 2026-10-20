"""Identifikation eines Steuergeräts als Textzeilen (Oberfläche und Kommandozeile)."""

from __future__ import annotations

from . import adressen, sprache
from .kw1281 import Verbindung
from .sprache import N_, t

BREITE = 15


def zeilen(v: Verbindung, sim: bool = False) -> list[str]:
    """Identifikation wie in VCDS, Bezeichnungen bündig."""
    def zeile(name: str, wert) -> str:
        return f"{t(name):<{BREITE}}{wert}"

    ergebnis = [
        zeile(N_("Adresse:"), adressen.text(v.adresse)),
        zeile(N_("Protokoll:"), t("{protokoll} (Keyword {keyword})", protokoll=v.protokoll,
                                  keyword=v.keyword)),
        zeile(N_("Baudrate:"), v.baud),
        zeile(N_("Kabel-Echo:"), sprache.ja_nein(v.echo)),
        "",
        zeile(N_("Teilenummer:"), v.teilenummer),
        zeile(N_("Bauteil:"), v.bauteil),
    ]
    if v.codierung is not None:
        ergebnis.append(zeile(N_("Codierung:"), f"{v.codierung:0{v.codierung_stellen}d}"))
    if v.werkstattcode is not None:
        ergebnis.append(zeile(N_("Werkstattcode:"), f"{v.werkstattcode:05d}"))
    if v.zusatzkennung:
        ergebnis.append(zeile(N_("Zusatzkennung:"), v.zusatzkennung))
    for z in v.zusatzdaten:
        ergebnis.append(zeile(N_("Zusatzdaten:"), z))
    if sim:
        ergebnis += ["", t("(Simulator – keine echten Fahrzeugdaten)")]
    return ergebnis

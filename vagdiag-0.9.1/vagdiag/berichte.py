# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Was die Reiter zeigen, als Textdatei: Identifikation, Fehlerspeicher und die gelesenen
Anpassungskanäle (den Scan schreibt scan.bericht). Nur Text aus Daten, die vagdiag schon
gelesen hat – zum Speichern wird nichts mehr an das Steuergerät gesendet.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import __version__, geprueft, ident
from .experte import kennung_text
from .fehler import Fehler
from .kw1281 import Verbindung
from .sprache import datum_zeit, t


def kopf(titel: str, sim: bool) -> list[str]:
    """Erste Zeile wie beim Scan-Bericht: Programm, Inhalt, Datum – und ob Simulator."""
    return [t("vagdiag {version} – {titel} vom {datum}", version=__version__, titel=titel,
              datum=datum_zeit(time.localtime()))
            + (" – " + t("SIMULATOR, keine echten Fahrzeugdaten") if sim else "")]


def dateiname(art: str, adresse: int | None, sim: bool) -> str:
    """z. B. ident-17-20261022-081500.txt, im Simulator mit „sim-“ davor."""
    teil = f"-{adresse:02X}" if adresse is not None else ""
    return time.strftime(("sim-" if sim else "") + f"{art}{teil}-%Y%m%d-%H%M%S.txt")


def identifikation(v: Verbindung, sim: bool) -> list[str]:
    return kopf(t("Identifikation"), sim) + [""] + ident.zeilen(v, sim)


def _hinweis(kennung: tuple) -> list[str]:
    """Hinweis „nicht geprüft“ unter der Kennung – leer bei geprüften Steuergeräten."""
    hinweis = geprueft.hinweis_kennung(kennung)
    return [hinweis] if hinweis else []


def fehlerspeicher(kennung: tuple, fehler: list[Fehler], gelesen: str, sim: bool) -> list[str]:
    zeilen = kopf(t("Fehlerspeicher"), sim)
    zeilen += [kennung_text(kennung)] + _hinweis(kennung)
    zeilen += [t("gelesen um {uhrzeit}", uhrzeit=gelesen), ""]
    if fehler:
        zeilen.append(t("{anzahl} Fehler gespeichert:", anzahl=len(fehler)))
        zeilen += ["  " + f.zeile() for f in fehler]
    else:
        zeilen.append(t("Kein Fehler gespeichert"))
    return zeilen


@dataclass
class AnpassungsZeile:
    """Eine Zeile im Reiter Anpassung – so, wie sie dort steht."""
    kanal: int
    wert: str
    hex: str
    hinweis: str
    gelesen: str


def anpassung(kennung: tuple, zeilen_tabelle: list[AnpassungsZeile], sim: bool) -> list[str]:
    zeilen = kopf(t("Anpassungskanäle"), sim)
    zeilen += [kennung_text(kennung)] + _hinweis(kennung)
    zeilen += [t("Nur gelesen – vagdiag hat dabei nichts geändert."), ""]
    spalten = [t("Kanal"), t("Wert"), t("Hex"), t("Gelesen"), t("Hinweis")]
    breite = [max(7, len(spalten[0]) + 2), 9, 8, 10]
    zeilen.append("".join(f"{s:<{b}}" for s, b in zip(spalten, breite)) + spalten[4])
    for z in sorted(zeilen_tabelle, key=lambda z: z.kanal):
        werte = [f"{z.kanal:02d}", z.wert, z.hex, z.gelesen]
        zeilen.append(("".join(f"{w:<{b - 1}} " for w, b in zip(werte, breite))
                       + z.hinweis).rstrip())
    if not zeilen_tabelle:
        zeilen.append(t("Keine Kanäle gelesen."))
    return zeilen

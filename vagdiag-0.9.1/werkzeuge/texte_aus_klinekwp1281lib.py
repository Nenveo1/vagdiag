#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Wandelt die Texttabellen der Bibliothek KLineKWP1281Lib in die Datendateien von vagdiag.

    python3 werkzeuge/texte_aus_klinekwp1281lib.py <Pfad zu KLineKWP1281Lib/src>

Gelesen werden die deutschen und englischen C-Header (Fehlercodes, OBD-Codes, Fehlerarten,
Klartexte der Messwerte). Geschrieben wird je Tabelle und Sprache eine Textdatei nach
vagdiag/daten/klinekwp1281lib/: eine Zeile je Eintrag, Schlüssel (hex) und Text durch einen
Tabulator getrennt. Die Texte bleiben inhaltlich unverändert; umgewandelt wird nur die
Schreibweise (Windows-1252 → UTF-8, geschütztes Leerzeichen → Leerzeichen, weiches
Trennzeichen entfernt, Leerraum am Rand und doppelte Leerzeichen entfernt).

Die Tabellen stehen unter der GPL-3.0 (Lizenzdatei der Bibliothek, ohne „or later“) –
die erzeugten Dateien tragen deshalb „GPL-3.0-only“ und den Hinweis auf die Herkunft.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ZIEL = Path(__file__).resolve().parent.parent / "vagdiag" / "daten" / "klinekwp1281lib"

# Datei in der Bibliothek, Name der Konstanten, Zieldatei, Beschreibung
TABELLEN = [
    ("fault_code_description_{sprache}.h", "KWP_FAULT_", "fehler",
     "Fehlercodes (fünfstellige VAG-Codes), Schlüssel = Code"),
    ("OBD_fault_code_description_{sprache}.h", "OBD2_FAULT_", "obd",
     "OBD-II-Codes, Schlüssel = genormte Zwei-Byte-Darstellung (SAE J2012: Bits 15–14 "
     "P/C/B/U, danach vier Ziffern)"),
    ("fault_code_elaboration_{sprache}.h", "KWP_ELAB_", "fehlerarten",
     "Fehlerarten (Statusbyte ohne Bit 7)"),
    ("text_table_{sprache}.h", "KWP_TEXT_", "texte",
     "Klartexte der Messwerte vom Typ 37 (25 hex), Schlüssel = a·256 + b"),
]
SPRACHEN = {"de": "DE", "en": "EN"}

_ZEILE = re.compile(r'^const char (\w+)\[\] PROGMEM = (.*);\s*$')
_TEIL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _c_text(literale: str) -> str:
    """Aneinandergereihte C-Zeichenketten ("a" "\\xE4" "b") in einen Text."""
    roh = bytearray()
    for teil in _TEIL.findall(literale):
        i = 0
        while i < len(teil):
            zeichen = teil[i]
            if zeichen != "\\":
                roh += zeichen.encode("latin-1")
                i += 1
                continue
            folge = teil[i + 1]
            if folge == "x":
                roh.append(int(teil[i + 2:i + 4], 16))
                i += 4
            elif folge in "\"'\\":
                roh += folge.encode("ascii")
                i += 2
            else:
                raise ValueError(f"unbekannte Escape-Folge \\{folge} in {literale!r}")
    text = roh.decode("cp1252").replace(" ", " ").replace("­", "")
    return re.sub(r" {2,}", " ", text).strip()


def tabelle_lesen(datei: Path, vorsilbe: str) -> dict[int, str]:
    eintraege: dict[int, str] = {}
    for zeile in datei.read_text(encoding="latin-1").splitlines():
        treffer = _ZEILE.match(zeile)
        if not treffer or not treffer.group(1).startswith(vorsilbe):
            continue
        schluessel = int(treffer.group(1)[len(vorsilbe):], 16)
        eintraege[schluessel] = _c_text(treffer.group(2))
    return eintraege


def kopf(name: str, beschreibung: str, quelle: str, stand: str) -> str:
    return (f"# {name}: {beschreibung}\n"
            f"# Aus KLineKWP1281Lib {stand} (https://github.com/domnulvlad/KLineKWP1281Lib), "
            f"Datei src/{quelle}\n"
            "# Copyright (C) domnulvlad und Mitwirkende der Bibliothek\n"
            "# SPDX-License-Identifier: GPL-3.0-only\n"
            f"# Umgewandelt für vagdiag am {time.strftime('%Y-%m-%d')} (nur die Schreibweise, "
            "siehe werkzeuge/texte_aus_klinekwp1281lib.py)\n")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    quelle = Path(argv[1])
    stand = "unbekannte Version"
    eigenschaften = quelle.parent / "library.properties"
    if eigenschaften.exists():
        for zeile in eigenschaften.read_text(encoding="utf-8").splitlines():
            if zeile.startswith("version="):
                stand = zeile.split("=", 1)[1].strip()
    ZIEL.mkdir(parents=True, exist_ok=True)
    for muster, vorsilbe, name, beschreibung in TABELLEN:
        for sprache, endung in SPRACHEN.items():
            datei = quelle / muster.format(sprache=endung)
            eintraege = tabelle_lesen(datei, vorsilbe)
            ziel = ZIEL / f"{name}_{sprache}.tsv"
            with open(ziel, "w", encoding="utf-8", newline="\n") as aus:
                aus.write(kopf(name, beschreibung, datei.name, stand))
                for schluessel in sorted(eintraege):
                    aus.write(f"{schluessel:04X}\t{eintraege[schluessel]}\n")
            print(f"{ziel.name}: {len(eintraege)} Einträge")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

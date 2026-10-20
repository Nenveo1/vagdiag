"""Dauerhafte Einstellungen in einstellungen.json (Ordner siehe pfade.py).

Enthält Sprache, Ablageorte für Protokolle und Messwert-Aufzeichnungen, ob
überhaupt Dateien geschrieben werden (Standard: nein), die Optionen des
Fahrtenschreibers und die zuletzt funktionierende Baudrate je Steuergerät
(spart beim nächsten Verbinden den Fehlversuch).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from .pfade import DATEN_ORDNER, KONFIG_ORDNER
from .sprache import t

log = logging.getLogger("vagdiag.proto")

DATEI = KONFIG_ORDNER / "einstellungen.json"

VERSION = 2

STANDARD = {
    "version": VERSION,
    "sprache": "de",             # "de" oder "en"
    "log_datei": False,          # Protokolldatei schreiben (sonst nur im Speicher)
    "log_ordner": str(DATEN_ORDNER / "logs"),
    "csv_ordner": str(DATEN_ORDNER / "messwerte"),
    "csv_automatisch": False,    # Messwertblöcke automatisch als CSV aufzeichnen
    "neu_verbinden": True,       # bei Abbruch während der Messung neu verbinden
    "baudraten": {},             # "01": 10400, "03": 9600 …
    # Fahrtenschreiber
    "fahrt_motor_gruppen": "1,2,3,4,5",
    "fahrt_kombi_alle": 180,     # Sekunden zwischen zwei Besuchen beim Kombi (0 = nie)
    "fahrt_abs_alle": 300,       # … beim ABS (0 = nie)
    "fahrt_besuch": 6,           # Sekunden je Besuch
    "fahrt_pruefung": True,      # Start- und Abschlussprüfung
}

_sperre = threading.Lock()
_cache: dict | None = None


def _anpassen(daten: dict) -> dict:
    """Einstellungen älterer Versionen übernehmen.

    Bis 0.3 wurde jede Einstellung mitgespeichert, auch unveränderte
    Standardwerte – „csv_automatisch: true“ steht deshalb in fast jeder alten
    Datei. Seit 0.4 ist die automatische CSV-Aufzeichnung standardmäßig aus;
    der alte Wert wird darum nicht übernommen.
    """
    if int(daten.get("version", 1) or 1) < 2:
        daten.pop("csv_automatisch", None)
    daten["version"] = VERSION
    return daten


def laden() -> dict:
    global _cache
    with _sperre:
        if _cache is None:
            daten = {}
            if DATEI.exists():
                try:
                    daten = json.loads(DATEI.read_text(encoding="utf-8"))
                    if not isinstance(daten, dict):
                        raise ValueError(t("kein JSON-Objekt"))
                except (OSError, ValueError) as exc:
                    log.warning(t("Einstellungen nicht lesbar (%s) – nehme Standardwerte"), exc)
                    daten = {}
            _cache = {**STANDARD, **_anpassen(daten)}
            _cache["baudraten"] = dict(_cache.get("baudraten") or {})
        return dict(_cache)


def speichern(**aenderungen) -> dict:
    """Einzelne Werte ändern und sofort speichern."""
    global _cache
    aktuell = laden()
    aktuell.update(aenderungen)
    with _sperre:
        _cache = aktuell
        try:
            DATEI.parent.mkdir(parents=True, exist_ok=True)
            tmp = DATEI.with_suffix(".tmp")
            tmp.write_text(json.dumps(aktuell, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, DATEI)
        except OSError as exc:
            log.warning(t("Einstellungen konnten nicht gespeichert werden: %s"), exc)
    return dict(aktuell)


def ordner(name: str) -> Path:
    """'log_ordner' oder 'csv_ordner' – wird bei Bedarf angelegt."""
    pfad = Path(os.path.expanduser(laden()[name]))
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def baud_fuer(adresse: int) -> int | None:
    wert = laden()["baudraten"].get(f"{adresse:02X}")
    return int(wert) if wert else None


def baud_merken(adresse: int, baud: int) -> None:
    baudraten = laden()["baudraten"]
    if baudraten.get(f"{adresse:02X}") != baud:
        baudraten[f"{adresse:02X}"] = baud
        speichern(baudraten=baudraten)


def _zuruecksetzen_fuer_tests(datei: Path) -> None:
    global DATEI, _cache
    DATEI = datei
    _cache = None

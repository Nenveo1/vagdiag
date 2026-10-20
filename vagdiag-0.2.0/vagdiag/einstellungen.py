"""Dauerhafte Einstellungen in ~/.config/vagdiag/einstellungen.json.

Enthält die Ablageorte für Protokolle und Messwert-Aufzeichnungen, die
Aufzeichnungs-Optionen und die zuletzt funktionierende Baudrate je
Steuergerät (spart beim nächsten Verbinden den Fehlversuch).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("vagdiag.proto")

DATEI = Path.home() / ".config" / "vagdiag" / "einstellungen.json"
DATEN_ORDNER = Path.home() / "vagdiag-daten"

STANDARD = {
    "log_ordner": str(DATEN_ORDNER / "logs"),
    "csv_ordner": str(DATEN_ORDNER / "messwerte"),
    "csv_automatisch": True,     # Messwerte immer aufzeichnen
    "neu_verbinden": True,       # bei Abbruch während der Messung neu verbinden
    "baudraten": {},             # "01": 10400, "03": 9600 …
}

_sperre = threading.Lock()
_cache: dict | None = None


def laden() -> dict:
    global _cache
    with _sperre:
        if _cache is None:
            daten = {}
            if DATEI.exists():
                try:
                    daten = json.loads(DATEI.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    log.warning("Einstellungen nicht lesbar (%s) – nehme Standardwerte", exc)
            _cache = {**STANDARD, **daten}
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
            log.warning("Einstellungen konnten nicht gespeichert werden: %s", exc)
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

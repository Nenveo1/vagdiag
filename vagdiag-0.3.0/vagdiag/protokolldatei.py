"""Protokolldatei mit allen Bytes – das ist, was ich zur Fehlersuche brauche.

Der Ablageort kommt aus den Einstellungen (Standard: ~/vagdiag-daten/logs)
und lässt sich während des Laufs umstellen.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from . import einstellungen

_datei_handler: logging.FileHandler | None = None
_formatierer = None


class RelativeZeit(logging.Formatter):
    """Millisekunden seit Programmstart – wichtig, um Timing-Probleme zu sehen."""

    def __init__(self):
        super().__init__()
        self.start = time.time()

    def format(self, record: logging.LogRecord) -> str:
        ms = (record.created - self.start) * 1000
        kanal = record.name.split(".")[-1]
        text = f"{ms:10.1f} ms  {kanal:5s}  {record.getMessage()}"
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


def _neuer_dateiname(ordner: Path) -> Path:
    return ordner / time.strftime("vagdiag-%Y%m%d-%H%M%S.log")


def einrichten(datei: Path | None = None, konsole: bool = False,
               bytes_in_konsole: bool = False, ordner: Path | None = None) -> Path:
    """Logging für 'vagdiag' einrichten. Gibt den Pfad der Protokolldatei zurück.

    datei:  fester Dateiname (CLI --log); sonst neuer Name im Ordner.
    ordner: Ordner für diesen Lauf; sonst der aus den Einstellungen.
    """
    global _datei_handler, _formatierer
    if datei is None:
        ziel = Path(ordner).expanduser() if ordner else einstellungen.ordner("log_ordner")
        ziel.mkdir(parents=True, exist_ok=True)
        datei = _neuer_dateiname(ziel)
    datei = Path(datei).expanduser()
    datei.parent.mkdir(parents=True, exist_ok=True)

    wurzel = logging.getLogger("vagdiag")
    wurzel.setLevel(logging.DEBUG)
    for h in list(wurzel.handlers):
        wurzel.removeHandler(h)

    _formatierer = RelativeZeit()
    _datei_handler = logging.FileHandler(datei, encoding="utf-8")
    _datei_handler.setLevel(logging.DEBUG)
    _datei_handler.setFormatter(_formatierer)
    wurzel.addHandler(_datei_handler)

    if konsole:
        k = logging.StreamHandler()
        k.setFormatter(_formatierer)
        k.setLevel(logging.DEBUG)
        if not bytes_in_konsole:
            k.addFilter(lambda r: r.name != "vagdiag.bytes")
        wurzel.addHandler(k)

    from . import __version__
    wurzel.info("vagdiag %s – Protokoll gestartet %s", __version__,
                time.strftime("%Y-%m-%d %H:%M:%S"))
    return datei


def aktuelle_datei() -> Path | None:
    return Path(_datei_handler.baseFilename) if _datei_handler else None


def ordner_wechseln(neuer_ordner: Path) -> Path:
    """Ab sofort in eine neue Datei im neuen Ordner schreiben."""
    global _datei_handler
    neuer_ordner = Path(neuer_ordner).expanduser()
    neuer_ordner.mkdir(parents=True, exist_ok=True)
    neu = _neuer_dateiname(neuer_ordner)
    wurzel = logging.getLogger("vagdiag")
    alt = _datei_handler
    if alt is not None:
        wurzel.info("Protokoll wird fortgesetzt in %s", neu)
    handler = logging.FileHandler(neu, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_formatierer or RelativeZeit())
    wurzel.addHandler(handler)
    if alt is not None:
        wurzel.removeHandler(alt)
        alt.close()
        wurzel.info("Fortsetzung des Protokolls aus %s", alt.baseFilename)
    _datei_handler = handler
    return neu

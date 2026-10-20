"""Protokolldatei mit allen Bytes – das ist, was ich zur Fehlersuche brauche."""

from __future__ import annotations

import logging
import time
from pathlib import Path

LOG_ORDNER = Path.home() / ".local" / "share" / "vagdiag" / "logs"


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


def einrichten(datei: Path | None = None, konsole: bool = False,
               bytes_in_konsole: bool = False) -> Path:
    """Logging für 'vagdiag' einrichten. Gibt den Pfad der Protokolldatei zurück."""
    if datei is None:
        LOG_ORDNER.mkdir(parents=True, exist_ok=True)
        datei = LOG_ORDNER / time.strftime("vagdiag-%Y%m%d-%H%M%S.log")
    datei = Path(datei)
    datei.parent.mkdir(parents=True, exist_ok=True)

    wurzel = logging.getLogger("vagdiag")
    wurzel.setLevel(logging.DEBUG)
    for h in list(wurzel.handlers):
        wurzel.removeHandler(h)

    formatierer = RelativeZeit()

    datei_handler = logging.FileHandler(datei, encoding="utf-8")
    datei_handler.setLevel(logging.DEBUG)
    datei_handler.setFormatter(formatierer)
    wurzel.addHandler(datei_handler)

    if konsole:
        k = logging.StreamHandler()
        k.setFormatter(formatierer)
        k.setLevel(logging.DEBUG)
        if not bytes_in_konsole:
            k.addFilter(lambda r: r.name != "vagdiag.bytes")
        wurzel.addHandler(k)

    from . import __version__
    wurzel.info("vagdiag %s – Protokoll gestartet %s", __version__,
                time.strftime("%Y-%m-%d %H:%M:%S"))
    return datei

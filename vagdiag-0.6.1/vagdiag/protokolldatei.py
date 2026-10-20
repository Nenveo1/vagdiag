"""Protokoll des Datenverkehrs – das brauche ich zur Fehlersuche.

Standardmäßig wird keine Datei geschrieben (Einstellung „log_datei“). Die
letzten Zeilen (mit allen Bytes) hält das Programm trotzdem im Speicher; bei
einem Problem lassen sie sich nachträglich speichern (Oberfläche: Datei →
Protokoll speichern …). Mit eingeschalteter Protokolldatei landet alles
sofort in einer Datei im Log-Ordner (Standard: ~/vagdiag-daten/logs).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path

from . import einstellungen
from .sprache import t

PUFFER_ZEILEN = 256_000     # mit allen Bytes etwa die letzten 35 Minuten (rund 8 MB als Datei)

_datei_handler: logging.FileHandler | None = None
_puffer: "Puffer | None" = None
_formatierer: "RelativeZeit | None" = None
_sperre = threading.Lock()


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


class Puffer(logging.Handler):
    """Die letzten Protokollzeilen im Speicher – auch ohne Protokolldatei.

    Die erste Zeile (Version und Startzeit) bleibt immer erhalten, auch wenn ältere
    Zeilen schon verdrängt sind."""

    def __init__(self, zeilen: int = PUFFER_ZEILEN):
        super().__init__(logging.DEBUG)
        self.zeilen: deque[str] = deque(maxlen=zeilen)
        self.kopf: str | None = None
        self.verdraengt = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            zeile = self.format(record)
            if self.kopf is None:
                self.kopf = zeile
            if len(self.zeilen) == self.zeilen.maxlen:
                self.verdraengt += 1
            self.zeilen.append(zeile)
        except Exception:   # Protokollieren darf die Diagnose nie stören
            self.handleError(record)

    def kopie(self) -> list[str]:
        """Alle Zeilen – unter der Sperre, weil andere Threads weiter protokollieren.
        Sind ältere schon verdrängt: erst die Kopfzeile, dann ein Hinweis darauf."""
        with self.lock:
            zeilen = list(self.zeilen)
            if self.verdraengt and self.kopf is not None:
                zeilen[:0] = [self.kopf, t("(ältere Zeilen nicht mehr im Speicher)")]
            return zeilen


def _neuer_dateiname(ordner: Path) -> Path:
    return ordner / time.strftime("vagdiag-%Y%m%d-%H%M%S.log")


def _kopfzeile() -> str:
    from . import __version__
    return t("vagdiag {version} – Protokoll gestartet {zeit}", version=__version__,
             zeit=time.strftime("%Y-%m-%d %H:%M:%S"))


def einrichten(datei: Path | None = None, konsole: bool = False,
               bytes_in_konsole: bool = False, ordner: Path | None = None,
               schreiben: bool | None = None) -> Path | None:
    """Logging für 'vagdiag' einrichten. Gibt die Protokolldatei zurück
    (None, wenn keine geschrieben wird).

    datei:     feste Protokolldatei (wird immer geschrieben)
    ordner:    Ordner für diesen Lauf statt dem aus den Einstellungen
    schreiben: True/False erzwingt bzw. verbietet die Datei; None = Einstellung
    """
    global _puffer, _formatierer, _datei_handler
    wurzel = logging.getLogger("vagdiag")
    wurzel.setLevel(logging.DEBUG)
    for h in list(wurzel.handlers):
        wurzel.removeHandler(h)
        if h is _datei_handler:
            h.close()
    _datei_handler = None

    _formatierer = RelativeZeit()
    _puffer = Puffer()
    _puffer.setFormatter(_formatierer)
    wurzel.addHandler(_puffer)

    if konsole:
        k = logging.StreamHandler()
        k.setFormatter(_formatierer)
        k.setLevel(logging.DEBUG)
        if not bytes_in_konsole:
            k.addFilter(lambda r: r.name != "vagdiag.bytes")
        wurzel.addHandler(k)

    if schreiben is None:
        schreiben = bool(einstellungen.laden().get("log_datei"))
    wurzel.info("%s", _kopfzeile())
    if datei is not None or schreiben:
        datei_einschalten(datei, ordner)
    return aktuelle_datei()


def _handler(pfad: Path) -> logging.FileHandler:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(pfad, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_formatierer or RelativeZeit())
    return handler


def datei_einschalten(datei: Path | None = None, ordner: Path | None = None) -> Path:
    """Ab sofort in eine Datei schreiben. Was schon im Speicher steht, kommt
    mit hinein – so fehlt der Anfang der Sitzung nicht."""
    global _datei_handler
    if datei is None:
        ziel = Path(ordner).expanduser() if ordner else einstellungen.ordner("log_ordner")
        datei = _neuer_dateiname(ziel)
    datei = Path(datei).expanduser()
    wurzel = logging.getLogger("vagdiag")
    with _sperre:
        alt = _datei_handler
        handler = _handler(datei)
        if alt is None and _puffer is not None:
            bisher = _puffer.kopie()
            if bisher:
                handler.stream.write("\n".join(bisher) + "\n")
                handler.flush()
        wurzel.addHandler(handler)
        _datei_handler = handler
        if alt is not None:
            wurzel.removeHandler(alt)
            alt.close()
    wurzel.info(t("Protokolldatei: %s"), datei)
    return datei


def datei_ausschalten() -> None:
    """Keine Datei mehr schreiben (der Speicher läuft weiter)."""
    global _datei_handler
    wurzel = logging.getLogger("vagdiag")
    with _sperre:
        alt = _datei_handler
        _datei_handler = None
    if alt is not None:
        wurzel.info(t("Protokolldatei geschlossen: %s"), alt.baseFilename)
        wurzel.removeHandler(alt)
        alt.close()


def aktuelle_datei() -> Path | None:
    handler = _datei_handler
    return Path(handler.baseFilename) if handler else None


def ordner_wechseln(neuer_ordner: Path) -> Path | None:
    """Ab sofort in eine neue Datei im neuen Ordner schreiben – nur wenn
    überhaupt eine Protokolldatei geschrieben wird."""
    if _datei_handler is None:
        return None
    alt = aktuelle_datei()
    wurzel = logging.getLogger("vagdiag")
    neu = _neuer_dateiname(Path(neuer_ordner).expanduser())
    wurzel.info(t("Protokoll wird fortgesetzt in %s"), neu)
    datei_einschalten(neu)
    wurzel.info(t("Fortsetzung des Protokolls aus %s"), alt)
    return neu


def puffer_zeilen() -> list[str]:
    return _puffer.kopie() if _puffer is not None else []


def speichern(ziel: Path | None = None) -> Path:
    """Die Zeilen aus dem Speicher in eine Datei schreiben (Standard: neue
    Datei im Log-Ordner)."""
    if ziel is None:
        ziel = _neuer_dateiname(einstellungen.ordner("log_ordner"))
    ziel = Path(ziel).expanduser()
    ziel.parent.mkdir(parents=True, exist_ok=True)
    zeilen = puffer_zeilen()
    ziel.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    logging.getLogger("vagdiag").info(t("Protokoll gespeichert: %s"), ziel)
    return ziel

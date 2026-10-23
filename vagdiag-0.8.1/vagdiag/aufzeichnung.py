"""Messwerte als CSV aufzeichnen. Auf Deutsch mit Semikolon und Dezimalkomma
(passt für LibreOffice/Excel mit deutscher Einstellung), auf Englisch mit
Komma und Dezimalpunkt.

Jede Zeile wird sofort geschrieben, damit bei einem Absturz nichts fehlt.
Verbindungsabbrüche und Neuverbindungen stehen als eigene Zeilen in der
Datei, damit Lücken in den Daten erkennbar sind.
"""

from __future__ import annotations

import csv
import logging
import threading
import time
from pathlib import Path

from . import einstellungen
from .beschriftung import anzeige
from .messwerte import Messwert
from .sprache import N_, csv_trenner, einheit, t, zahl

log = logging.getLogger("vagdiag.proto")

KOPF = [N_("Zeit"), N_("Sekunden"), N_("Gruppe"),
        N_("Feld 1"), N_("Einheit 1"), N_("Feld 2"), N_("Einheit 2"),
        N_("Feld 3"), N_("Einheit 3"), N_("Feld 4"), N_("Einheit 4"), N_("Ereignis")]


def _zahl(m: Messwert) -> str:
    """Zahlen ohne Einheit (Dezimalzeichen der Sprache), sonst der Text."""
    if m.gueltig and m.zahl is not None and m.zahl == m.zahl:  # nicht NaN
        wert = abs(m.zahl) if m.typ in (4, 27) else m.zahl
        return zahl(wert, m.stellen)
    return m.wert_text


def zeitstempel(start: float) -> list[str]:
    """Uhrzeit mit Millisekunden und Sekunden seit Beginn der Aufzeichnung."""
    jetzt = time.time()
    zeit = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(jetzt))
    trenner = "," if csv_trenner() == ";" else "."
    zeit += f"{trenner}{int(jetzt * 1000) % 1000:03d}"
    return [zeit, zahl(time.monotonic() - start, 3)]


class CsvAufzeichnung:
    def __init__(self, pfad: Path):
        self.pfad = Path(pfad)
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        # mit BOM, damit Excel die Umlaute erkennt; LibreOffice kommt mit beidem zurecht
        self._datei = open(self.pfad, "w", newline="", encoding="utf-8-sig")
        self._csv = csv.writer(self._datei, delimiter=csv_trenner())
        self._csv.writerow([t(k) for k in KOPF])
        self._datei.flush()
        self._start = time.monotonic()
        self._sperre = threading.Lock()   # Ereignisse kommen aus dem Diagnose-Thread
        self.zeilen = 0
        self._beschriftet: set[int] = set()
        log.info(t("Messwerte werden aufgezeichnet: %s"), self.pfad)

    @classmethod
    def neu(cls, adresse: int, ordner: Path | None = None,
            sim: bool = False) -> "CsvAufzeichnung":
        """Neue Datei im CSV-Ordner. Simulator-Dateien beginnen mit „sim-“,
        damit sie nicht mit echten Messungen verwechselt werden."""
        ziel = Path(ordner).expanduser() if ordner else einstellungen.ordner("csv_ordner")
        vorsilbe = "sim-" if sim else ""
        name = time.strftime(f"{vorsilbe}messwerte-{adresse:02X}-%Y%m%d-%H%M%S.csv")
        aufzeichnung = cls(ziel / name)
        if sim:
            aufzeichnung.ereignis(t("Simulator – keine echten Fahrzeugdaten"))
        return aufzeichnung

    def _zeit(self) -> list[str]:
        return zeitstempel(self._start)

    def messwerte(self, gruppe: int, werte: list[Messwert],
                  namen: list[str] | None = None) -> None:
        """Eine Zeile mit den Werten einer Gruppe. Beim ersten Auftreten einer
        Gruppe stehen die Feldnamen (falls bekannt) als Ereigniszeile davor."""
        if namen and any(namen) and gruppe not in self._beschriftet:
            self._beschriftet.add(gruppe)
            self.ereignis(t("Gruppe {gruppe:03d}:", gruppe=gruppe) + " " + " | ".join(
                anzeige(n) or t("Feld {nummer}", nummer=i + 1) for i, n in enumerate(namen)))
        felder: list[str] = []
        for i in range(4):
            if i < len(werte):
                felder += [_zahl(werte[i]), einheit(werte[i].einheit)]
            else:
                felder += ["", ""]
        self._schreiben(self._zeit() + [f"{gruppe:03d}"] + felder + [""])

    def ereignis(self, text: str) -> None:
        self._schreiben(self._zeit() + [""] + [""] * 8 + [text])

    def _schreiben(self, zeile: list[str]) -> None:
        with self._sperre:
            if self._datei.closed:
                return
            self._csv.writerow(zeile)
            self._datei.flush()
            self.zeilen += 1

    def schliessen(self) -> None:
        with self._sperre:
            if self._datei.closed:
                return
            self._datei.close()
        log.info(t("Aufzeichnung beendet (%d Zeilen): %s"), self.zeilen, self.pfad)

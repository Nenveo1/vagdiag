# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Ringspeicher des passiven Fahrtenschreibers – wie bei einer Dashcam.

Der Fahrtenschreiber schreibt wie sonst auch, nur nicht in eine Datei, sondern in Stücke von
etwa einer Minute Fahrzeit (`stueck-000001.csv` …) im Ordner `passiv` unter dem CSV-Ordner
(Simulator: `passiv-sim`). Ist mehr als die gewählte Zeitspanne beisammen, wird das älteste
Stück gelöscht. Die Stücke bleiben auf der Platte: Nach einem Neustart des Rechners – also
bei der nächsten Fahrt – geht es mit ihnen weiter.

Fahrzeit ist nur die Zeit mit Messwerten (Zündung an): Zwischen zwei Messwertzeilen zählt
höchstens LUECKE_MAX Sekunden. Steht das Auto mit ausgeschalteter Zündung, kommt keine
Fahrzeit dazu – überschrieben wird dann nichts.

Jede Zeile eines Stücks hat die Spalten der Fahrt-CSV und dahinter zwei interne: die
Fahrzeit im Stück (Sekunden, immer mit Punkt) und – für die Zusammenfassung – die Werte
sprachunabhängig als JSON (interne Feldnamen, Zahl, Text, Klartext-Nummer). Beim Export
fallen die beiden weg.

exportieren() setzt die Stücke zu einer Datei mit genau der gewählten Zeitspanne zusammen
(die Spalte Sekunden zählt dann die Fahrzeit ab Beginn der Datei) und liefert die Werte für
die Zusammenfassung dieser Zeitspanne. Wurde zwischendurch die Sprache umgestellt, werden
Zahlen, Einheiten und Phasen älterer Stücke umgeschrieben; Notizen bleiben, wie sie sind.

Nur ein vagdiag darf in einen Ringspeicher schreiben (Sperrdatei) – z. B. nicht zugleich
der automatisch gestartete Fahrtenschreiber und die Oberfläche.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import einstellungen
from .kw1281 import DiagError
from .sprache import EINHEITEN_EN, N_, VORSAETZE, csv_trenner, englisch, t, zahl
from .sprache_en import EN

log = logging.getLogger("vagdiag.proto")

# Zeitspannen (Sekunden Fahrzeit) – Name für die Kommandozeile, Text für die Anzeige
FENSTER: list[tuple[int, str, str]] = [
    (300, "5min", N_("5 Minuten")), (1200, "20min", N_("20 Minuten")),
    (3600, "1h", N_("1 Stunde")), (18000, "5h", N_("5 Stunden")),
]
STANDARD_FENSTER = 1200
STUECK = 60.0                 # Fahrzeit je Stück (s)
LUECKE_MAX = 10.0             # so viel zählt eine Pause zwischen zwei Messwertzeilen höchstens
SICHTBAR = 14                 # Spalten der Fahrt-CSV (fahrtenschreiber.KOPF)
INTERN = ["Fahrzeit", "intern"]

# Kennzeichen im internen Feld
DATEN = "D"                   # Messwertzeile: [D, Phase, [Zahl | [Text, Klartext-Nr.] | null …]]
BESCHRIFTUNG = "L"            # Feldnamen: [L, Adresse, Gruppe, Teilenummer, [Namen …]]
LAUF = "R"                    # „Fahrtenschreiber gestartet“ – hier beginnt ein neuer Lauf
FEHLERSPEICHER = "F"          # Ergebnis eines Fehlerspeichers
EREIGNIS = "E"                # Markierung (F9, Enter)
UNERREICHBAR = "U"            # Steuergerät nicht erreicht
ZUENDUNG = "Z"                # Zündung aus / wieder an
SICHERUNG = "S"               # Zeitspanne gesichert

_STUECK_NAME = re.compile(r"^stueck-(\d+)\.csv$")
_ZAHL_DE = re.compile(r"^-?\d+(,\d+)?$")
_ZAHL_EN = re.compile(r"^-?\d+(\.\d+)?$")
# Phasen der Fahrt-CSV (wie fahrtenschreiber.START …) – zum Umschreiben älterer Stücke
PHASEN = (N_("Start"), N_("Fahrt"), N_("Ereignis"), N_("Ende"), N_("Abschluss"), N_("Fertig"))


class RingBelegt(DiagError):
    """Ein anderes vagdiag schreibt gerade in diesen Ringspeicher."""


def fenster_text(sekunden: float) -> str:
    for wert, _, text in FENSTER:
        if wert == int(sekunden):
            return t(text)
    if sekunden < 120:
        return t("{sekunden} s", sekunden=zahl(sekunden, 0))
    return t("{minuten} min", minuten=zahl(sekunden / 60, 0))


def fenster_aus_name(name: str) -> int:
    """„20min“, „1h“ … (auch „20“ = Minuten) → Sekunden; ValueError bei Unbekanntem."""
    name = name.strip().lower().replace(" ", "")
    for wert, kurz, _ in FENSTER:
        if name in (kurz, kurz.replace("min", ""), f"{wert // 60}min", f"{wert}s"):
            return wert
    raise ValueError(name)


def ordner(basis: Path | str | None = None, sim: bool = False) -> Path:
    """Ordner des Ringspeichers: passiv (Simulator: passiv-sim) unter dem CSV-Ordner."""
    wurzel = Path(basis).expanduser() if basis else einstellungen.ordner("csv_ordner")
    return wurzel / ("passiv-sim" if sim else "passiv")


# ---------------------------------------------------------------- Stücke
@dataclass
class Stueck:
    nummer: int
    pfad: Path
    fahrzeit: float = 0.0


def _lesen(pfad: Path) -> tuple[bool, list[list[str]]]:
    """Zeilen eines Stücks (ohne Kopf) und ob es deutsch geschrieben ist (Semikolon)."""
    text = pfad.read_text(encoding="utf-8-sig", errors="replace")
    erste, _, rest = text.partition("\n")
    deutsch = ";" in erste
    zeilen = [z for z in csv.reader(io.StringIO(rest), delimiter=";" if deutsch else ",")
              if len(z) == SICHTBAR + len(INTERN)]
    return deutsch, zeilen


def _fahrzeit(zeile: list[str]) -> float | None:
    try:
        return float(zeile[SICHTBAR])
    except (ValueError, IndexError):
        return None


def _dateien(pfad: Path) -> list[Stueck]:
    liste = []
    for datei in pfad.glob("stueck-*.csv"):
        treffer = _STUECK_NAME.match(datei.name)
        if treffer:
            liste.append(Stueck(int(treffer.group(1)), datei))
    return sorted(liste, key=lambda s: s.nummer)


def _gelesen(pfad: Path) -> list[tuple[Stueck, bool, list[list[str]]]]:
    """Jedes Stück einmal gelesen: (Stück mit Fahrzeit, deutsch?, Zeilen)."""
    ergebnis = []
    for stueck in _dateien(pfad):
        try:
            deutsch, zeilen = _lesen(stueck.pfad)
        except FileNotFoundError:
            continue          # gerade gelöscht (ein anderes vagdiag schreibt)
        except OSError as exc:
            log.warning(t("Ringspeicher: %s nicht lesbar (%s)"), stueck.pfad, exc)
            continue
        for zeile in zeilen:
            wert = _fahrzeit(zeile)
            if wert is not None:
                stueck.fahrzeit = max(stueck.fahrzeit, wert)
        ergebnis.append((stueck, deutsch, zeilen))
    return ergebnis


def vorhanden(pfad: Path) -> bool:
    """Liegt in diesem Ordner ein Ringspeicher (mindestens ein Stück)?"""
    return Path(pfad).is_dir() and bool(_dateien(Path(pfad)))


def stuecke(pfad: Path) -> list[Stueck]:
    """Alle Stücke im Ordner, älteste zuerst – mit ihrer Fahrzeit (letzte Zeile)."""
    return [stueck for stueck, _, _ in _gelesen(pfad)]


# ---------------------------------------------------------------- Sperre
class Sperre:
    """Sperrdatei: Nur ein vagdiag schreibt in einen Ringspeicher. Endet das Programm (auch
    durch einen Absturz), gibt das Betriebssystem die Sperre frei."""

    def __init__(self, pfad: Path):
        self.pfad = pfad / "belegt.sperre"
        self._datei = open(self.pfad, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self._datei.seek(0)
                msvcrt.locking(self._datei.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._datei.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._datei.close()
            raise RingBelegt(t("In den Ringspeicher {ordner} schreibt gerade ein anderes vagdiag "
                               "(z. B. der automatisch gestartete Fahrtenschreiber).",
                               ordner=pfad)) from exc

    def freigeben(self) -> None:
        if self._datei.closed:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._datei.seek(0)
                msvcrt.locking(self._datei.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._datei.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._datei.close()


# ---------------------------------------------------------------- Schreiben
class Ring:
    """Schreibt Zeilen in Stücke, beginnt nach STUECK Sekunden Fahrzeit ein neues und löscht
    die ältesten, solange auch ohne sie die Zeitspanne voll ist."""

    def __init__(self, pfad: Path, fenster: float, kopf: list[str]):
        self.ordner = Path(pfad)
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.fenster = float(fenster)
        self._kopf = list(kopf) + INTERN
        self._sperre = Sperre(self.ordner)
        try:
            self.stuecke = stuecke(self.ordner)
        except OSError:
            self._sperre.freigeben()
            raise
        self.fahrzeit = 0.0                      # im laufenden Stück
        self._datei = None
        self._csv = None
        self.aktuell: Stueck | None = None
        self.neues_stueck()

    @property
    def fahrzeit_gesamt(self) -> float:
        return sum(s.fahrzeit for s in self.stuecke)

    def neues_stueck(self) -> None:
        self._schliessen_datei()
        nummer = self.stuecke[-1].nummer + 1 if self.stuecke else 1
        self.aktuell = Stueck(nummer, self.ordner / f"stueck-{nummer:06d}.csv")
        self.stuecke.append(self.aktuell)
        self.fahrzeit = 0.0
        self._datei = open(self.aktuell.pfad, "w", newline="", encoding="utf-8-sig")
        self._csv = csv.writer(self._datei, delimiter=csv_trenner())
        self._csv.writerow(self._kopf)
        self._datei.flush()
        self._aufraeumen()

    @staticmethod
    def zaehlt(sekunden: float) -> float:
        """Wie viel Fahrzeit eine Pause zwischen zwei Messwertzeilen zählt."""
        return max(0.0, min(LUECKE_MAX, sekunden))

    def fahrzeit_buchen(self, sekunden: float) -> None:
        """Fahrzeit seit der letzten Messwertzeile. Wäre das Stück danach voll, beginnt
        vorher ein neues – so steht die Fahrzeit jedes Stücks in seiner letzten Zeile."""
        dauer = self.zaehlt(sekunden)
        if self.fahrzeit > 0 and self.fahrzeit + dauer >= STUECK:
            self.neues_stueck()
        self.fahrzeit += dauer
        self.aktuell.fahrzeit = self.fahrzeit

    def schreiben(self, zeile: list[str], intern) -> None:
        if self._datei is None or self._datei.closed:
            return
        self._csv.writerow(list(zeile) + [f"{self.fahrzeit:.3f}",
                                          json.dumps(intern, ensure_ascii=False,
                                                     separators=(",", ":"))
                                          if intern else ""])
        self._datei.flush()

    def _aufraeumen(self) -> None:
        """Älteste Stücke löschen, solange die übrigen die Zeitspanne noch füllen. Das
        laufende Stück bleibt immer."""
        while (len(self.stuecke) > 1
               and self.fahrzeit_gesamt - self.stuecke[0].fahrzeit >= self.fenster):
            alt = self.stuecke.pop(0)
            try:
                alt.pfad.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:       # z. B. unter Windows gerade geöffnet
                log.warning(t("Ringspeicher: %s nicht gelöscht (%s)"), alt.pfad, exc)

    def _schliessen_datei(self) -> None:
        if self._datei is not None and not self._datei.closed:
            self._datei.close()

    def schliessen(self) -> None:
        self._schliessen_datei()
        self._sperre.freigeben()


# ---------------------------------------------------------------- Export
@dataclass
class Daten:
    """Eine Messwertzeile aus dem Ringspeicher – für die Zusammenfassung."""
    zeit: float                  # Fahrzeit ab Beginn der Zeitspanne (s)
    adresse: int
    gruppe: int
    phase: str                   # intern (deutsch)
    teil: str
    felder: list                 # [[Name, Zahl, Text, Nummer], …]
    lauf: int


@dataclass
class Notiz:
    zeit: str                    # Uhrzeit-Spalte, wie sie in der Datei steht
    art: str
    text: str
    adresse: int | None


@dataclass
class Auszug:
    pfad: Path | None
    zeilen: int = 0
    fahrzeit: float = 0.0        # Fahrzeit in der Datei (höchstens die Zeitspanne)
    von: str = ""
    bis: str = ""
    laeufe: int = 0
    daten: list[Daten] = field(default_factory=list)
    notizen: list[Notiz] = field(default_factory=list)


def _phase_intern(text: str) -> str:
    for phase in PHASEN:
        if text in (phase, EN.get(phase)):
            return phase
    return text


def _einheit_umschreiben(text: str, nach_englisch: bool) -> str:
    if nach_englisch:
        if text in EINHEITEN_EN:
            return EINHEITEN_EN[text]
        if text[:1] in VORSAETZE and text[1:] in EINHEITEN_EN:
            return text[:1] + EINHEITEN_EN[text[1:]]
        return text
    rueck = {en: de for de, en in EINHEITEN_EN.items()}
    if text in rueck:
        return rueck[text]
    if text[:1] in VORSAETZE and text[1:] in rueck:
        return text[:1] + rueck[text[1:]]
    return text


def _umschreiben(zeile: list[str], deutsch: bool) -> list[str]:
    """Sichtbare Spalten eines Stücks aus der anderen Sprache in die eingestellte."""
    zeile = list(zeile)
    if deutsch:
        zeile[0] = zeile[0][:19] + zeile[0][19:].replace(",", ".")
    else:
        zeile[0] = zeile[0][:19] + zeile[0][19:].replace(".", ",")
    zeile[4] = t(_phase_intern(zeile[4])) if zeile[4] else ""
    for i in (5, 7, 9, 11):
        wert = zeile[i]
        if deutsch and _ZAHL_DE.match(wert):
            zeile[i] = wert.replace(",", ".")
        elif not deutsch and _ZAHL_EN.match(wert):
            zeile[i] = wert.replace(".", ",")
        zeile[i + 1] = _einheit_umschreiben(zeile[i + 1], nach_englisch=deutsch)
    return zeile


def auszug_lesen(pfad: Path, fenster: float) -> tuple[list, Auszug]:
    """Die Zeilen der letzten `fenster` Sekunden Fahrzeit (sichtbare Spalten, in der
    eingestellten Sprache, Sekunden = Fahrzeit ab Beginn) und ihre Daten."""
    gelesen = _gelesen(pfad)
    gesamt = sum(s.fahrzeit for s, _, _ in gelesen)
    beginn = max(0.0, gesamt - fenster)
    auszug = Auszug(None, fahrzeit=min(gesamt, fenster))
    ausgabe: list[list[str]] = []
    beschriftungen: dict[tuple[int, int], list[str]] = {}      # zuletzt gesehen
    namen: dict[tuple[int, int], tuple[str, list]] = {}        # (Teilenummer, interne Namen)
    beschriftet: set[tuple[int, int]] = set()                  # schon ausgegeben
    versatz = 0.0
    lauf = 0
    englisch_jetzt = englisch()
    for stueck, deutsch, zeilen in gelesen:
        anders = deutsch == englisch_jetzt                     # Stück in der anderen Sprache
        for roh in zeilen:
            f = _fahrzeit(roh)
            if f is None:
                continue
            intern = []
            if roh[SICHTBAR + 1]:
                try:
                    intern = json.loads(roh[SICHTBAR + 1])
                except ValueError:
                    intern = []
            art = intern[0] if intern else ""
            if art == LAUF:
                lauf += 1
            zeile = _umschreiben(roh[:SICHTBAR], deutsch) if anders else list(roh[:SICHTBAR])
            if art == BESCHRIFTUNG and len(intern) >= 3:
                beschriftungen[(intern[1], intern[2])] = zeile
                if len(intern) >= 5:
                    namen[(intern[1], intern[2])] = (intern[3], intern[4])
            zeit = versatz + f
            if zeit < beginn:
                continue
            zeile[1] = zahl(zeit - beginn, 3)
            if art == BESCHRIFTUNG:
                if (intern[1], intern[2]) in beschriftet:
                    continue
                beschriftet.add((intern[1], intern[2]))
            elif art == DATEN and len(intern) >= 3:
                try:
                    schluessel = (int(roh[2], 16), int(roh[3]))
                except ValueError:
                    continue
                if schluessel not in beschriftet and schluessel in beschriftungen:
                    beschriftet.add(schluessel)
                    vorher = list(beschriftungen[schluessel])
                    vorher[0], vorher[1] = zeile[0], zeile[1]
                    ausgabe.append(vorher)
                teil, feldnamen = namen.get(schluessel, ("", []))
                felder = []
                for i, wert in enumerate(intern[2]):
                    name = feldnamen[i] if i < len(feldnamen) else ""
                    if isinstance(wert, list) and len(wert) >= 2:
                        felder.append([name, None, wert[0], wert[1]])
                    else:
                        felder.append([name, wert, "", None])
                auszug.daten.append(Daten(zeit - beginn, schluessel[0], schluessel[1],
                                          intern[1], teil, felder, lauf))
            elif art:
                try:
                    adresse = int(roh[2], 16) if roh[2] else None
                except ValueError:
                    adresse = None
                auszug.notizen.append(Notiz(zeile[0], art, zeile[13], adresse))
            ausgabe.append(zeile)
        versatz += stueck.fahrzeit
    if ausgabe:
        auszug.von, auszug.bis = ausgabe[0][0], ausgabe[-1][0]
    auszug.zeilen = len(ausgabe)
    auszug.laeufe = len({d.lauf for d in auszug.daten})
    return ausgabe, auszug


def exportieren(pfad: Path, fenster: float, ziel: Path, kopf: list[str]) -> Auszug:
    """Die letzten `fenster` Sekunden Fahrzeit als eine CSV-Datei (`kopf`: sichtbare
    Spaltennamen in der eingestellten Sprache). Lässt sich das Ziel nicht ersetzen (unter
    Windows z. B. in Excel geöffnet), entsteht eine Datei mit Uhrzeit im Namen."""
    zeilen, auszug = auszug_lesen(pfad, fenster)
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_name(ziel.name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as datei:
        schreiber = csv.writer(datei, delimiter=csv_trenner())
        schreiber.writerow(kopf)
        schreiber.writerows(zeilen)
    try:
        os.replace(tmp, ziel)
    except OSError as exc:
        ersatz = ziel.with_name(ziel.stem + time.strftime("-%Y%m%d-%H%M%S") + ziel.suffix)
        log.warning(t("%s lässt sich nicht ersetzen (%s) – gespeichert als %s"), ziel, exc,
                    ersatz)
        os.replace(tmp, ersatz)
        ziel = ersatz
    auszug.pfad = ziel
    log.info(t("Ringspeicher exportiert: %s (%d Zeilen, %.0f s Fahrzeit)"), ziel, auszug.zeilen,
             auszug.fahrzeit)
    return auszug

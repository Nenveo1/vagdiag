# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Fahrtenschreiber: die wichtigen Messwerte einer ganzen Fahrt in einer Datei.

Über die K-Leitung spricht das Programm immer nur mit einem Steuergerät.
Der Fahrtenschreiber wechselt deshalb selbst:

  Startprüfung  Tankinhalt im Stand (Kombi), Fehlerspeicher aller Steuergeräte – die
                Wegfahrsperre zuerst (beim Anlassen ist ihre Sitzung längst vorbei),
                der Motor zuletzt: Die Verbindung zu ihm bleibt offen, die Aufzeichnung
                beginnt sofort.
  Fahrt         Motorsteuergerät durchgehend. Solange der Motor steht, nur
                Gruppe 004 – so wird die Bordspannung beim Anlassen möglichst
                oft gelesen. Die Aufforderung „jetzt Motor starten“ kommt erst, wenn die
                ersten Motorwerte da sind; lief er da schon, steht in der Zusammenfassung,
                dass das Anlassen fehlt. In festen Abständen kurze Besuche beim Kombi
                (Tempo, Tank) und beim ABS (Raddrehzahlen, Bremslichtschalter).
                Das ABS nur im Stillstand: Manche ABS-Steuergeräte (z. B. Mark 20 IE)
                nehmen eine Verbindung nur an, wenn das Auto steht – danach
                antworten sie auch beim Anfahren weiter.
  Ereignis      Markierung und sofort der Fehlerspeicher des Motors, der des ABS
                beim nächsten Halt – für den Moment, in dem eine Warnlampe angeht.
  Abschluss     Tankinhalt im Stand, Fehlerspeicher aller Steuergeräte. Antwortet
                keins (Zündung schon aus), wartet der Fahrtenschreiber eine Weile,
                ob sie wieder eingeschaltet wird.

Alles landet in einer CSV-Datei (Format wie bei den Messwerten, siehe
aufzeichnung.py). Am Ende entsteht eine Zusammenfassung als Textdatei
daneben. Der Fahrtenschreiber schreibt immer – dafür wird er gestartet.

Das Airbag-Steuergerät (15) wird nur gelesen, wenn es in der Sitzung
freigegeben ist (siehe airbag.py), sonst steht es als „nicht gelesen“ in der
Zusammenfassung.

Passiv (FahrtPlan.passiv = Zeitspanne in Sekunden): wie eine Dashcam. Statt
einer Datei je Fahrt ein Ringspeicher (ringspeicher.py), der immer die letzten 5 min, 20 min,
1 h oder 5 h Fahrzeit enthält – über Fahrten und Neustarts des Rechners hinweg. Am Ende
jedes Laufs entsteht daraus fahrt-passiv.csv mit genau dieser Zeitspanne, die
Zusammenfassung gilt ebenso für sie. Ein Ereignis (F9, Enter) sichert die Zeitspanne
zusätzlich in eine eigene Datei, die nie überschrieben wird. Ohne Kabel wartet der passive
Fahrtenschreiber still darauf (etwa beim automatischen Start nach dem Anmelden).

Der Ablauf läuft im Diagnose-Thread der DiagSession (siehe session.py).
"""

from __future__ import annotations

import csv
import logging
import queue
import statistics
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from . import adressen, airbag, beschriftung, einstellungen, ringspeicher
from .aufzeichnung import _zahl, zeitstempel
from .kline import KLineError
from .kw1281 import (Abgebrochen, DiagError, Nak, NoResponse, NotAvailable, NotConnected,
                     ProtocolError)
from .messwerte import Messwert
from .port import PortError, fehlertext, kabelfehler
from .sprache import N_, csv_trenner, datum_zeit, einheit, t, tausender, zahl

if TYPE_CHECKING:
    from .session import DiagSession

log = logging.getLogger("vagdiag.proto")

LEITUNG = (ProtocolError, NotConnected, KLineError, PortError)

# Phasen – intern immer deutsch, angezeigt und in der CSV in der eingestellten Sprache
START, FAHRT, EREIGNIS, ENDE = N_("Start"), N_("Fahrt"), N_("Ereignis"), N_("Ende")
ABSCHLUSS, FERTIG = N_("Abschluss"), N_("Fertig")

BREMSE_BETAETIGT = 0x00C1     # Klartext-Nummer „betätigt“ (ABS Gruppe 003)
BESUCH_LUECKE = 5.0           # s ohne Wert vom ABS: ab hier zählt es als neuer Besuch
ANLASS_NACHLAUF = 5.0         # s nach dem Anspringen: Spannung zählt noch zum Anlassen
LAMBDA_WARM_AB = 60.0         # °C: ab hier sagt die Lambdaregelung etwas über das Gemisch
KURZNAMEN = {0x17: N_("Kombi"), 0x03: N_("ABS")}
WEGFAHRSPERRE = 0x25
KABEL_PAUSE = 3.0             # s zwischen zwei Versuchen, ein fehlendes Kabel zu öffnen


# ---------------------------------------------------------------- Ablaufplan
@dataclass
class Besuch:
    adresse: int
    gruppen: tuple[int, ...]
    alle_sekunden: float      # Abstand zwischen zwei Besuchen
    dauer: float              # so lange werden die Gruppen gelesen


@dataclass
class FahrtPlan:
    motor: int = 0x01
    motor_gruppen: tuple[int, ...] = (1, 2, 3, 4, 5)
    anlass_gruppe: int = 4                       # solange der Motor steht
    besuche: list[Besuch] = field(default_factory=lambda: [
        Besuch(0x17, (1, 2, 3), 180, 6),
        Besuch(0x03, (1, 3), 300, 6)])
    pruefung: bool = True                        # Start- und Abschlussprüfung
    fehlerspeicher: tuple[int, ...] = (0x01, 0x03, 0x17, 0x25)
    mit_airbag: bool = False                     # Airbag (15) nur auf ausdrücklichen Wunsch
    ereignis_fehlerspeicher: tuple[int, ...] = (0x01, 0x03)
    stand_adresse: int = 0x17                    # Tankinhalt im Stand
    stand_gruppe: int = 2
    stand_dauer: float = 10.0
    motor_laeuft_ab: float = 400                 # /min
    volle_runde_nach: float = 10.0               # s Motorlauf, bis alle Gruppen dran sind
    bauds: tuple[int, ...] = (10400, 9600)
    nur_im_stand: tuple[int, ...] = (0x03,)      # nur bei Tempo 0 ansprechen (ABS)
    stand_frisch: float = 4.0                    # so alt darf der Tempo-Wert dafür sein (s)
    stand_bestaetigt: float = 1.0                # erst nach zwei Werten 0 km/h, so weit
                                                 # auseinander (s), gilt das Auto als stehend
    zuendung_warten: float = 60.0                # Prüfungen: so lange auf die Zündung warten
    passiv: float | None = None                  # Ringspeicher: Zeitspanne in s

    def pruef_adressen(self) -> tuple[int, ...]:
        """Steuergeräte, deren Fehlerspeicher Start- und Abschlussprüfung lesen."""
        adressen_ = [a for a in self.fehlerspeicher if a != airbag.ADRESSE]
        if self.mit_airbag:
            adressen_.append(airbag.ADRESSE)
        return tuple(sorted(adressen_))

    @classmethod
    def aus_einstellungen(cls) -> "FahrtPlan":
        werte = einstellungen.laden()
        plan = cls()
        gruppen = _gruppenliste(werte.get("fahrt_motor_gruppen", "1,2,3,4,5"))
        if gruppen:
            plan.motor_gruppen = gruppen
        plan.besuche = [
            Besuch(0x17, (1, 2, 3), float(werte.get("fahrt_kombi_alle", 180)),
                   float(werte.get("fahrt_besuch", 6))),
            Besuch(0x03, (1, 3), float(werte.get("fahrt_abs_alle", 300)),
                   float(werte.get("fahrt_besuch", 6)))]
        plan.besuche = [b for b in plan.besuche if b.alle_sekunden > 0]
        plan.pruefung = bool(werte.get("fahrt_pruefung", True))
        return plan


def _gruppenliste(text: str) -> tuple[int, ...]:
    gruppen = []
    for teil in str(text).replace(";", ",").replace(" ", ",").split(","):
        if teil.strip():
            try:
                g = int(teil)
            except ValueError:
                continue
            if 0 <= g <= 255 and g not in gruppen:
                gruppen.append(g)
    return tuple(gruppen)


# ---------------------------------------------------------------- Datei
KOPF = [N_("Zeit"), N_("Sekunden"), N_("Steuergerät"), N_("Gruppe"), N_("Phase"),
        N_("Feld 1"), N_("Einheit 1"), N_("Feld 2"), N_("Einheit 2"),
        N_("Feld 3"), N_("Einheit 3"), N_("Feld 4"), N_("Einheit 4"), N_("Ereignis")]


class FahrtDatei:
    """Eine CSV-Datei für die ganze Fahrt, jede Zeile sofort geschrieben."""

    def __init__(self, pfad: Path):
        self.pfad = Path(pfad)
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        # mit BOM, damit Excel die Umlaute erkennt; LibreOffice kommt mit beidem zurecht
        self._datei = open(self.pfad, "w", newline="", encoding="utf-8-sig")
        self._csv = csv.writer(self._datei, delimiter=csv_trenner())
        self._csv.writerow([t(k) for k in KOPF])
        self._datei.flush()
        self._start = time.monotonic()
        self._sperre = threading.Lock()
        self._beschriftet: set[tuple[int, int]] = set()
        self.zeilen = 0

    @classmethod
    def neu(cls, ordner: Path | None = None, sim: bool = False) -> "FahrtDatei":
        ziel = Path(ordner).expanduser() if ordner else einstellungen.ordner("csv_ordner")
        name = time.strftime(("sim-" if sim else "") + "fahrt-%Y%m%d-%H%M%S.csv")
        return cls(ziel / name)

    def _zeit(self) -> list[str]:
        return zeitstempel(self._start)

    def messwerte(self, adresse: int, gruppe: int, phase: str, werte: list[Messwert],
                  namen: list[str], teil: str = "") -> None:
        schluessel = (adresse, gruppe)
        if any(namen) and schluessel not in self._beschriftet:
            self._beschriftet.add(schluessel)
            self.ereignis(f"{adresse:02X}/{gruppe:03d}: " + " | ".join(
                beschriftung.anzeige(n) or t("Feld {nummer}", nummer=i + 1)
                for i, n in enumerate(namen)), adresse, phase,
                [ringspeicher.BESCHRIFTUNG, adresse, gruppe, teil or "", [str(n) for n in namen]])
        felder: list[str] = []
        for i in range(4):
            felder += ([_zahl(werte[i]), einheit(werte[i].einheit)] if i < len(werte)
                       else ["", ""])
        self._schreiben(self._zeit() + [f"{adresse:02X}", f"{gruppe:03d}", t(phase)]
                        + felder + [""], self._intern(phase, teil, werte, namen))

    def _intern(self, phase: str, teil: str, werte: list[Messwert], namen: list[str]):
        """Sprachunabhängige Werte für den Ringspeicher – die normale Fahrt-CSV braucht sie
        nicht."""
        return None

    def ereignis(self, text: str, adresse: int | None = None, phase: str = "",
                 art=None) -> None:
        """art: Kennzeichen der Notiz für den Ringspeicher (ringspeicher.FEHLERSPEICHER …)."""
        self._schreiben(self._zeit() + [f"{adresse:02X}" if adresse is not None else "",
                                        "", t(phase) if phase else ""] + [""] * 8 + [text],
                        art if isinstance(art, list) else [art] if art else None)

    def _schreiben(self, zeile: list[str], intern=None) -> None:
        with self._sperre:
            if self._datei.closed:
                return
            self._csv.writerow(zeile)
            self._datei.flush()
            self.zeilen += 1

    def schliessen(self) -> None:
        with self._sperre:
            if not self._datei.closed:
                self._datei.close()


class RingDatei(FahrtDatei):
    """Wie FahrtDatei, aber in den Ringspeicher des passiven Fahrtenschreibers: Nach etwa
    einer Minute Fahrzeit beginnt ein neues Stück (mit den Feldnamen vorweg), die ältesten
    fallen weg, sobald mehr als die Zeitspanne beisammen ist."""

    def __init__(self, ordner: Path, fenster: float, uhr=time.monotonic):
        self.ring = ringspeicher.Ring(ordner, fenster, [t(k) for k in KOPF])
        self.pfad = self.ring.ordner
        self._uhr = uhr
        self._start = uhr()
        self._sperre = threading.Lock()
        self._beschriftet: set[tuple[int, int]] = set()
        self._letzte_daten: float | None = None
        self.zeilen = 0

    @property
    def fahrzeit_gesamt(self) -> float:
        return self.ring.fahrzeit_gesamt

    def _zeit(self) -> list[str]:
        uhrzeit, _ = zeitstempel(self._start)
        return [uhrzeit, zahl(self._uhr() - self._start, 3)]

    def messwerte(self, adresse: int, gruppe: int, phase: str, werte: list[Messwert],
                  namen: list[str], teil: str = "") -> None:
        jetzt = self._uhr()
        if self._letzte_daten is not None:
            with self._sperre:
                stueck = self.ring.aktuell
                self.ring.fahrzeit_buchen(jetzt - self._letzte_daten)
                if self.ring.aktuell is not stueck:
                    self._beschriftet.clear()      # Feldnamen am Anfang jedes Stücks
        self._letzte_daten = jetzt
        super().messwerte(adresse, gruppe, phase, werte, namen, teil)

    def _intern(self, phase: str, teil: str, werte: list[Messwert], namen: list[str]):
        # je Feld die Zahl – nur wo keine ist, Text und Klartext-Nummer (Bitfeld, Klartext);
        # Namen und Teilenummer stehen einmal in der Zeile mit den Feldnamen
        felder = []
        for m in werte:
            if m.gueltig and m.zahl is not None and m.zahl == m.zahl:
                felder.append(round(m.zahl, 6))
            elif m.gueltig and m.zahl is None:
                felder.append([m.wert_text, m.textnummer])
            else:
                felder.append(None)
        return [ringspeicher.DATEN, phase, felder]

    def _schreiben(self, zeile: list[str], intern=None) -> None:
        with self._sperre:
            self.ring.schreiben(zeile, intern)
            self.zeilen += 1

    def schliessen(self) -> None:
        with self._sperre:
            self.ring.schliessen()


# ---------------------------------------------------------------- Sammeln
@dataclass
class Probe:
    t: float          # Sekunden seit Beginn
    phase: str
    zahl: float | None
    text: str
    nummer: int | None = None     # Klartext-Nummer (Typ 37), sprachunabhängig


class Sammler:
    """Werte nach (Adresse, Feldname) für die Zusammenfassung."""

    def __init__(self):
        self.reihen: dict[tuple[int, str], list[Probe]] = {}

    def add(self, adresse: int, name: str, zeit: float, phase: str, m: Messwert) -> None:
        if not name:
            return
        wert = m.zahl if (m.gueltig and m.zahl is not None and m.zahl == m.zahl) else None
        self.reihen.setdefault((adresse, name), []).append(
            Probe(zeit, phase, wert, m.wert_text, m.textnummer))

    def probe(self, adresse: int, name: str, probe: Probe) -> None:
        if name:
            self.reihen.setdefault((adresse, name), []).append(probe)

    def zahlen(self, adresse: int, name: str, phase: str | None = None,
               ab: float | None = None) -> list[float]:
        return [p.zahl for p in self.reihen.get((adresse, name), [])
                if p.zahl is not None and (phase is None or p.phase == phase)
                and (ab is None or p.t >= ab)]

    def proben(self, adresse: int, name: str) -> list[Probe]:
        return self.reihen.get((adresse, name), [])


# ---------------------------------------------------------------- Ergebnis
@dataclass
class Zusammenfassung:
    zeilen: list[str]
    csv_datei: Path
    txt_datei: Path | None
    abgebrochen: bool = False
    sicherungen: list[Path] = field(default_factory=list)     # passiv: mit F9 gesichert


def _z(wert: float, stellen: int = 0) -> str:
    return zahl(wert, stellen)


def _fehlertext(ergebnis) -> str:
    if isinstance(ergebnis, str):
        return ergebnis
    if not ergebnis:
        return t("kein Fehler")
    return (t("{anzahl} Fehler:", anzahl=len(ergebnis)) + " "
            + " | ".join(f.zeile() for f in ergebnis))


# ---------------------------------------------------------------- Ablauf
class Fahrtenschreiber:
    def __init__(self, sitzung: "DiagSession", plan: FahrtPlan, ordner: Path | None = None,
                 sim: bool = False, marken: "queue.Queue | None" = None,
                 ende: threading.Event | None = None):
        self.s = sitzung
        self.plan = plan
        self.sim = sim
        self.ordner = ordner
        self.passiv = plan.passiv
        self.datei = (RingDatei(ringspeicher.ordner(ordner, sim), plan.passiv) if plan.passiv
                      else FahrtDatei.neu(ordner, sim))
        self.sicherungen: list[Path] = []          # passiv: mit F9 gesicherte Zeitspannen
        self.marken = marken if marken is not None else queue.Queue()
        self.ende = ende if ende is not None else threading.Event()
        self.sammler = Sammler()
        self.beginn = time.monotonic()
        self.beginn_wand = time.localtime()
        self.fehler: dict[str, dict[int, object]] = {}      # Phase → Adresse → Liste/Text
        self.ereignisse: list[tuple[str, str, dict[int, object]]] = []
        self.unerreichbar: list[tuple[int, str, float | None]] = []
        self.stoerungen = 0
        self.besuche = 0
        self.motor_zeit = 0.0           # Sekunden mit Verbindung zum Motor
        self.letztes_tempo: float | None = None
        self.tempo_zeit: float | None = None        # wann letztes_tempo gemessen wurde
        self._stand_seit: float | None = None       # erster Wert 0 km/h in Folge
        self._stand_werte = 0                       # … und wie viele seitdem
        self._verlust_offen = False                 # Motor verloren – Störung oder Zündung aus?
        self.zuendung_aus_fahrt: list[tuple[str, str]] = []   # (von, bis) während der Fahrt
        self.kabel_weg: list[tuple[str, str]] = []            # (von, bis): Kabel nicht erreichbar
        self.letzte_drehzahl: float | None = None
        self.motor_laeuft_seit: float | None = None
        self.motorstarts: list[float] = []          # Anspringen, Sekunden seit Start (_t)
        self._motor_aus_gesehen = False             # erst danach ist „Motor läuft“ ein Start
        self._aufgefordert = False                  # „jetzt Motor starten“ schon gesagt
        self.anlassen_verpasst = False              # Motor lief schon beim ersten Messwert
        self.besuche_je: dict[int, int] = {}
        self.zuendung_aus: set[str] = set()         # Prüfungen, bei denen die Zündung aus war
        self._offen: dict[int, list[dict[int, object]]] = {}   # Fehlerspeicher fürs Ereignis fehlt
        self._nachholen_ab = 0.0
        self._tempo_hinweis = False
        self.abgebrochen = False
        self.fahrt_beginn: float | None = None      # Sekunden seit Start (_t)
        self.fahrt_ende: float | None = None
        self._fehlende: dict[int, set[int]] = {}           # Adresse → Gruppen ohne Antwort
        self._bestaetigt: dict[int, set[int]] = {}
        self.teilenummern: dict[int, str] = {}             # Adresse → Teilenummer
        self._phase = START

    # ------------------------------------------------------------ Helfer
    def _t(self) -> float:
        return time.monotonic() - self.beginn

    def _status(self, phase: str, text: str) -> None:
        """phase: interner Name (START, FAHRT …); im Ereignis steht er übersetzt."""
        self._phase = phase
        log.info(t("Fahrtenschreiber – %s: %s"), t(phase), text)
        daten = {"phase": t(phase), "text": text, "zeilen": self.datei.zeilen,
                 "datei": str(self.datei.pfad), "dauer": self._t()}
        if self.passiv:
            daten["ring"] = (self.datei.fahrzeit_gesamt, self.passiv)
        self.s._melden("fahrt", daten)

    def _notiz(self, text: str, adresse: int | None = None, art: str | None = None) -> None:
        """Ereignis in die CSV, in die Oberfläche – und ins Protokoll, damit beide
        dasselbe erzählen. art: Kennzeichen für den Ringspeicher (ringspeicher.EREIGNIS …)."""
        self.datei.ereignis(text, adresse, self._phase, art)
        log.info(t("Fahrtenschreiber – Notiz: %s"), text)
        self.s._melden("fahrt_notiz", f"{time.strftime('%H:%M:%S')}  {text}")

    def _pruefe_abbruch(self) -> None:
        if self.s._abbruch.is_set():
            raise Abgebrochen(t("Abgebrochen"))

    def _warten(self, sekunden: float) -> None:
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            self._pruefe_abbruch()
            if self.ende.is_set():
                return
            time.sleep(min(0.1, max(0.0, ende - time.monotonic())))

    def _pause(self, sekunden: float) -> None:
        """Warten, abbrechbar – anders als _warten auch, wenn die Fahrt schon endet."""
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            self._pruefe_abbruch()
            time.sleep(min(0.1, max(0.0, ende - time.monotonic())))

    def _simulator(self, name: str) -> None:
        """Fahrprofil des Simulators steuern (parken/losfahren) – sonst nichts."""
        if self.sim:
            self.s._port_oeffnen()      # der Simulator entsteht erst mit dem Port
            aufruf = getattr(self.s._port, name, None)
            if callable(aufruf):
                aufruf()

    def _versuch(self, adresse: int) -> DiagError | None:
        """Verbinden; None bei Erfolg, sonst der Fehler (ohne ihn festzuhalten)."""
        self._pruefe_abbruch()
        try:
            self.s._verbinden(adresse, self.plan.bauds)
            return None
        except Abgebrochen:
            raise
        except DiagError as exc:
            return exc

    def _unerreichbar(self, adresse: int, fehler: DiagError) -> None:
        tempo = self.letztes_tempo
        self.unerreichbar.append((adresse, time.strftime("%H:%M:%S"), tempo))
        zusatz = (", " + t("Tempo zuletzt {tempo:.0f} km/h", tempo=tempo)
                  if tempo is not None else "")
        self._notiz(t("{steuergeraet} nicht erreichbar ({fehler})",
                      steuergeraet=adressen.text(adresse), fehler=fehler) + zusatz, adresse,
                    ringspeicher.UNERREICHBAR)

    def _verbinden(self, adresse: int) -> bool:
        fehler = self._versuch(adresse)
        if fehler is None:
            return True
        self._unerreichbar(adresse, fehler)
        return False

    def _trennen(self) -> None:
        try:
            self.s._trennen()
        except (DiagError, KLineError, PortError) as exc:
            log.debug(t("Trennen: %s"), exc)

    # ------------------------------------------------------------ Kabel
    def _kabel_weg(self, phase: str, fehler: PortError) -> str:
        """Kabel nicht erreichbar (gezogen, Rechner im Ruhezustand): einmal notieren – kein
        Fehler am Auto, keine Störung. Ergebnis: Uhrzeit für _kabel_zurueck."""
        self._notiz(t("Kabel nicht erreichbar – vagdiag wartet darauf ({fehler})",
                      fehler=fehlertext(fehler)), art=ringspeicher.UNERREICHBAR)
        self._status(phase, t("Warte auf das Kabel …"))
        return time.strftime("%H:%M:%S")

    def _kabel_zurueck(self, seit: str) -> None:
        self.kabel_weg.append((seit, time.strftime("%H:%M:%S")))
        self._notiz(t("Kabel wieder da (weg seit {uhrzeit})", uhrzeit=seit))

    def _kabel_abwarten(self) -> bool:
        """Passiv, vor dem Start: das Kabel öffnen – fehlt es (etwa beim automatischen Start
        nach dem Anmelden) oder hängt es nach dem Ruhezustand, still warten, bis es da ist.
        False: Ende, bevor das Kabel kam."""
        seit: str | None = None
        while True:
            self._pruefe_abbruch()
            if self.ende.is_set():
                if seit is not None:
                    self.kabel_weg.append((seit, "–"))
                return False
            try:
                self.s._port_oeffnen()
                self.s._port.purge_rx()        # nach dem Ruhezustand öffnet port.py neu
            except PortError as exc:
                if seit is None:
                    seit = self._kabel_weg(START, exc)
                self._pause(KABEL_PAUSE)
                continue
            if seit is not None:
                self._kabel_zurueck(seit)
            return True

    def _lesen(self, adresse: int, gruppe: int, phase: str) -> list[Messwert] | None:
        """Eine Gruppe lesen und festhalten. None = gibt es nicht."""
        proto = self.s._proto_pruefen()
        try:
            werte = self.s._wiederholt(lambda: proto.gruppe_lesen(gruppe))
        except (Nak, NotAvailable):
            if gruppe not in self._bestaetigt.get(adresse, set()):
                self._fehlende.setdefault(adresse, set()).add(gruppe)
                self._notiz(t("{adresse:02X}/{gruppe:03d} gibt es nicht – wird übersprungen",
                              adresse=adresse, gruppe=gruppe), adresse)
            return None
        self._bestaetigt.setdefault(adresse, set()).add(gruppe)
        verbindung = self.s._proto.verbindung if self.s._proto else None
        if verbindung is not None:
            self.teilenummern[adresse] = verbindung.teilenummer
        namen = beschriftung.namen(verbindung, gruppe, werte)
        self.datei.messwerte(adresse, gruppe, phase, werte, namen,
                             verbindung.teilenummer if verbindung is not None else "")
        zeit = self._t()
        for name, m in zip(namen, werte):
            self.sammler.add(adresse, name, zeit, phase, m)
            if m.zahl is None or not m.gueltig:
                continue
            if name in ("Fahrgeschwindigkeit", "Geschwindigkeit"):
                self._tempo_merken(m.zahl)
            elif name == "Motordrehzahl" and adresse == self.plan.motor:
                self.letzte_drehzahl = m.zahl
        if adresse == 0x03 and gruppe == 1:
            raeder = [m.zahl for m in werte if m.zahl is not None and m.einheit == "km/h"]
            if raeder:
                self._tempo_merken(max(raeder))
        self.s._melden("fahrt_werte", {"adresse": adresse, "gruppe": gruppe,
                                       "werte": werte, "namen": namen})
        return werte

    def _fehler_lesen(self, adresse: int, phase: str, ziel: dict[int, object]) -> None:
        try:
            liste = self.s._proto_pruefen().fehler_lesen()
            ziel[adresse] = liste
        except (Nak, NotAvailable) as exc:
            ziel[adresse] = t("nicht lesbar ({fehler})", fehler=exc)
        except LEITUNG as exc:
            ziel[adresse] = t("nicht lesbar ({fehler})", fehler=exc)
        self._notiz(t("Fehlerspeicher {steuergeraet}: {ergebnis}",
                      steuergeraet=adressen.text(adresse), ergebnis=_fehlertext(ziel[adresse])),
                    adresse, ringspeicher.FEHLERSPEICHER)
        offen = self._offen.pop(adresse, [])
        if offen:
            wann = (t("bei der Abschlussprüfung gelesen") if phase == ENDE else
                    t("im Stand gelesen um {uhrzeit}", uhrzeit=time.strftime("%H:%M:%S")))
            for ergebnisse in offen:
                ergebnisse[adresse] = f"{_fehlertext(ziel[adresse])} ({wann})"

    # ------------------------------------------------------------ Stillstand
    def _tempo_merken(self, tempo: float) -> None:
        jetzt = time.monotonic()
        if tempo < 1:
            if self._stand_seit is None:
                self._stand_seit, self._stand_werte = jetzt, 0
            self._stand_werte += 1
        else:
            self._stand_seit, self._stand_werte = None, 0
        self.letztes_tempo = tempo
        self.tempo_zeit = jetzt

    def _steht(self) -> bool:
        """Steht das Auto? Nur mit frischem Tempo-Wert (Motor-Gruppe 005, Kombi, ABS) – und
        erst, wenn mindestens zwei Werte über stand_bestaetigt Sekunden hinweg 0 km/h zeigen:
        Beim Anfahren meldete der Motor schon einmal 0 km/h, als es wieder losging (das ABS
        nahm die Verbindung dann nicht mehr an)."""
        return (self.letztes_tempo is not None and self.letztes_tempo < 1
                and self.tempo_zeit is not None
                and time.monotonic() - self.tempo_zeit <= self.plan.stand_frisch
                and self._stand_seit is not None and self._stand_werte >= 2
                and self.tempo_zeit - self._stand_seit >= self.plan.stand_bestaetigt)

    def _darf(self, adresse: int) -> bool:
        return adresse not in self.plan.nur_im_stand or self._steht()

    def _nachholen(self) -> None:
        """Fehlerspeicher für Ereignisse, die nur im Stand lesbar sind."""
        for adresse in list(self._offen):
            self._pruefe_abbruch()
            if not self._steht() or self.ende.is_set():
                return
            self._status(FAHRT, t("Halt – lese den Fehlerspeicher von {steuergeraet} nach …",
                                  steuergeraet=adressen.text(adresse)))
            self._trennen()
            if not self._verbinden(adresse):
                self._nachholen_ab = time.monotonic() + 30
                return
            try:
                self._fehler_lesen(adresse, EREIGNIS, {})
            except LEITUNG as exc:
                self.stoerungen += 1
                self._notiz(t("Störung bei {adresse:02X}: {fehler}", adresse=adresse,
                              fehler=exc), adresse)
                self._nachholen_ab = time.monotonic() + 30
            self._trennen()

    # ------------------------------------------------------------ Prüfungen
    def _erste_verbindung(self, phase: str, erste: int) -> bool | None:
        """Erste Verbindung einer Prüfung, mit Blick auf die Zündung.

        True:  mit `erste` verbunden.
        False: `erste` antwortet nicht, die Zündung ist aber an (der Motor antwortet).
        None:  kein Steuergerät antwortet, auch nicht nach zuendung_warten Sekunden –
               die Zündung ist aus."""
        warten_bis = time.monotonic() + self.plan.zuendung_warten
        hinweis = False
        while True:
            self._status(phase, t("verbinde mit {steuergeraet} …",
                                  steuergeraet=adressen.text(erste)))
            fehler = self._versuch(erste)
            if fehler is None:
                if hinweis:
                    self._notiz(t("Zündung ist wieder an – die Prüfung läuft"))
                return True
            if not isinstance(fehler, NoResponse):
                self._unerreichbar(erste, fehler)       # antwortet, ist aber nicht lesbar
                return False
            if erste != self.plan.motor:
                fehler_motor = self._versuch(self.plan.motor)
                if not isinstance(fehler_motor, NoResponse):
                    self._unerreichbar(erste, fehler)   # Zündung an, nur `erste` fehlt
                    return False
            if (phase == START and self.ende.is_set()) or time.monotonic() >= warten_bis:
                return None
            if not hinweis:
                hinweis = True
                self._notiz(t("Keine Antwort – ist die Zündung aus? Bitte einschalten (Motor "
                              "nicht starten). vagdiag wartet bis zu {sekunden:.0f} s.",
                              sekunden=self.plan.zuendung_warten))
            self._status(phase, t("Zündung aus? Bitte einschalten – warte noch {rest:.0f} s …",
                                  rest=max(0.0, warten_bis - time.monotonic())))
            self._pause(2.0)

    def _reihenfolge(self, phase: str) -> list[int]:
        """Abschluss: zuerst das Kombi (Tankinhalt im Stand), dann die übrigen. Start: die
        Wegfahrsperre zuerst – wird gleich danach angelassen, ist ihre Diagnose-Sitzung
        längst vorbei –, der Motor zuletzt: Seine Verbindung bleibt danach offen."""
        lesen = self.plan.pruef_adressen()
        alle = [self.plan.stand_adresse] + [a for a in lesen if a != self.plan.stand_adresse]
        if phase != START:
            return alle
        zuerst = [a for a in alle if a == WEGFAHRSPERRE]
        zuletzt = [a for a in alle if a == self.plan.motor]
        return zuerst + [a for a in alle if a not in zuerst and a not in zuletzt] + zuletzt

    def _pruefung(self, phase: str) -> None:
        """Tankinhalt im Stand und Fehlerspeicher aller Steuergeräte."""
        ergebnisse = self.fehler.setdefault(phase, {})
        lesen = self.plan.pruef_adressen()
        reihenfolge = self._reihenfolge(phase)
        erste = self._erste_verbindung(phase, reihenfolge[0])
        if erste is None:
            self.zuendung_aus.add(phase)
            self._notiz(t("Zündung aus – {phase} nicht möglich", phase=t(phase)),
                        art=ringspeicher.ZUENDUNG)
            for adresse in lesen:
                ergebnisse[adresse] = t("nicht geprüft (Zündung aus)")
            return
        for i, adresse in enumerate(reihenfolge):
            self._pruefe_abbruch()
            if phase == START and self.ende.is_set():
                return
            if adresse == airbag.ADRESSE and not self.s.airbag_freigegeben:
                ergebnisse[adresse] = t("nicht gelesen (Airbag nicht freigegeben)")
                continue
            if i == 0 and not erste:
                if adresse in lesen:
                    ergebnisse[adresse] = t("nicht erreichbar")
                continue
            schon_da = self.s.verbunden and self.s._letzte_adresse == adresse
            if not schon_da:
                self._status(phase, t("verbinde mit {steuergeraet} …",
                                      steuergeraet=adressen.text(adresse)))
                if not self._verbinden(adresse):
                    if adresse in lesen:
                        ergebnisse[adresse] = t("nicht erreichbar")
                    continue
            try:
                if adresse == self.plan.stand_adresse:
                    self._status(phase, t("Tankinhalt im Stand ({dauer:.0f} s) …",
                                          dauer=self.plan.stand_dauer))
                    ende = time.monotonic() + self.plan.stand_dauer
                    while time.monotonic() < ende:
                        self._pruefe_abbruch()
                        if self._lesen(adresse, self.plan.stand_gruppe, phase) is None:
                            break
                if adresse in lesen:
                    self._fehler_lesen(adresse, phase, ergebnisse)
            except LEITUNG as exc:
                self.stoerungen += 1
                self._notiz(t("Störung bei {adresse:02X}: {fehler}", adresse=adresse,
                              fehler=exc), adresse)
                if adresse in lesen and adresse not in ergebnisse:
                    ergebnisse[adresse] = t("nicht lesbar ({fehler})", fehler=exc)
            if (phase == START and adresse == self.plan.motor and i == len(reihenfolge) - 1
                    and self.s.verbunden and self.s._letzte_adresse == adresse):
                continue        # Motor bleibt verbunden – die Aufzeichnung beginnt sofort
            self._trennen()

    # ------------------------------------------------------------ Fahrt
    def _motor_verbinden(self) -> bool:
        """So lange versuchen, bis der Motor antwortet (oder Ende/Abbruch).

        Antwortet er gar nicht (keine Reaktion auf die Reizung), ist meist die Zündung aus –
        das zählt nicht als Störung, steht aber mit Uhrzeit in der Zusammenfassung. Bricht
        der Aufbau mittendrin ab, ist es eine Störung. Eine vorher verlorene Verbindung
        (_verlust_offen) zählt als Störung, wenn der Motor ohne Pause wieder antwortet.
        Ist das Kabel nicht erreichbar, wartet er still darauf (_kabel_weg)."""
        aus_seit: str | None = None
        kabel_seit: str | None = None
        while True:
            self._pruefe_abbruch()
            if self.ende.is_set():
                if aus_seit is not None:
                    self.zuendung_aus_fahrt.append((aus_seit, "–"))
                if kabel_seit is not None:
                    self.kabel_weg.append((kabel_seit, "–"))
                self._verlust_offen = False
                return False
            if kabel_seit is None:
                self._status(FAHRT, t("verbinde mit {steuergeraet} …",
                                      steuergeraet=adressen.text(self.plan.motor)))
            try:
                self.s._verbinden(self.plan.motor, self.plan.bauds)
            except Abgebrochen:
                raise
            except (DiagError, PortError) as exc:
                grund = kabelfehler(exc)
                if grund is not None:
                    if kabel_seit is None:
                        kabel_seit = self._kabel_weg(FAHRT, grund)
                    self._verlust_offen = False     # das Kabel, nicht das Auto
                    self._warten(KABEL_PAUSE)
                    continue
                if kabel_seit is not None:          # Kabel wieder da, das Auto antwortet
                    self._kabel_zurueck(kabel_seit)
                    kabel_seit = None
                if not isinstance(exc, NoResponse):
                    self.stoerungen += 1
                    self._notiz(t("Verbindungsaufbau zum Motor gestört: {fehler}", fehler=exc),
                                self.plan.motor)
                    self._verlust_offen = False         # schon gezählt
                    self._warten(0.5)
                    continue
                if aus_seit is None:
                    aus_seit = time.strftime("%H:%M:%S")
                    self._notiz(t("Motor antwortet nicht ({fehler}) – Zündung aus?",
                                  fehler=exc), self.plan.motor, ringspeicher.ZUENDUNG)
                self._verlust_offen = False         # Zündung aus, keine Störung
                self._warten(0.5)
                continue
            if kabel_seit is not None:
                self._kabel_zurueck(kabel_seit)
            if aus_seit is not None:
                bis = time.strftime("%H:%M:%S")
                self.zuendung_aus_fahrt.append((aus_seit, bis))
                self._notiz(t("Motor antwortet wieder – die Zündung war vermutlich von "
                              "{von} bis {bis} aus", von=aus_seit, bis=bis), self.plan.motor,
                            ringspeicher.ZUENDUNG)
            elif self._verlust_offen:
                self.stoerungen += 1
            self._verlust_offen = False
            return True

    def _motor_gruppen(self) -> list[int]:
        gruppen = [g for g in self.plan.motor_gruppen
                   if g not in self._fehlende.get(self.plan.motor, set())]
        laeuft = (self.motor_laeuft_seit is not None
                  and time.monotonic() - self.motor_laeuft_seit >= self.plan.volle_runde_nach)
        if not laeuft and self.plan.anlass_gruppe in gruppen:
            return [self.plan.anlass_gruppe]     # Anlassen nicht verpassen
        return gruppen

    def _fahrt(self) -> None:
        self.fahrt_beginn = self._t()
        try:
            self._fahrt_schleife()
        finally:
            self.fahrt_ende = self._t()

    def _fahrt_schleife(self) -> None:
        self._status(FAHRT, t("Aufzeichnung läuft"))
        self._notiz(t("Fahrt beginnt"))
        naechster = {b.adresse: None for b in self.plan.besuche}
        index = 0
        # aus der Startprüfung noch mit dem Motor verbunden: ab jetzt zählt die Motorzeit
        verbunden_seit: float | None = (time.monotonic() if self.s.verbunden and
                                        self.s._letzte_adresse == self.plan.motor else None)

        def motor_zeit_buchen() -> None:
            nonlocal verbunden_seit
            if verbunden_seit is not None:
                self.motor_zeit += time.monotonic() - verbunden_seit
                verbunden_seit = None

        while True:
            self._pruefe_abbruch()
            if self.ende.is_set():
                break
            # Markierungen haben Vorrang
            try:
                marke = self.marken.get_nowait()
            except queue.Empty:
                marke = None
            if marke is not None:
                motor_zeit_buchen()
                self._ereignis(marke)
                continue
            # Besuche erst, wenn der Motor läuft – und vor dem Neuverbinden zum Motor,
            # damit nach einem Besuch nicht erst der Motor und gleich wieder der nächste kommt
            jetzt = time.monotonic()
            motor_an = self.motor_laeuft_seit is not None
            for b in self.plan.besuche:
                if not motor_an:
                    naechster[b.adresse] = None
                elif naechster[b.adresse] is None:
                    naechster[b.adresse] = jetzt + b.alle_sekunden
            faellig = [b for b in self.plan.besuche
                       if naechster[b.adresse] is not None and jetzt >= naechster[b.adresse]]
            wartet = [b for b in faellig if not self._darf(b.adresse)]
            faellig = [b for b in faellig if b not in wartet]
            if wartet and not self._tempo_hinweis and (
                    self.tempo_zeit is None or jetzt - self.tempo_zeit > 60):
                self._tempo_hinweis = True
                self._notiz(t("{steuergeraet} wird nur im Stand besucht – das Tempo ist aber "
                              "unbekannt (eine Motor-Gruppe mit dem Tempo mitlesen, bei ME7 "
                              "die 005)", steuergeraet=adressen.text(wartet[0].adresse)))
            if faellig:
                # im Stand zuerst die Steuergeräte, die nur dann antworten; sonst das am
                # längsten fällige
                b = min(faellig, key=lambda b: (b.adresse not in self.plan.nur_im_stand,
                                                naechster[b.adresse]))
                motor_zeit_buchen()
                self._besuch(b)
                naechster[b.adresse] = time.monotonic() + b.alle_sekunden
                continue
            if self._offen and self._steht() and time.monotonic() >= self._nachholen_ab:
                motor_zeit_buchen()
                self._nachholen()
                continue
            if not self.s.verbunden or self.s._letzte_adresse != self.plan.motor:
                motor_zeit_buchen()
                if not self._motor_verbinden():
                    break
                verbunden_seit = time.monotonic()
                self._status(FAHRT, t("Aufzeichnung läuft"))
            gruppen = self._motor_gruppen()
            if not gruppen:
                self._warten(1.0)
                continue
            gruppe = gruppen[index % len(gruppen)]
            index += 1
            try:
                werte = self._lesen(self.plan.motor, gruppe, FAHRT)
            except LEITUNG as exc:
                # Störung oder Zündung aus? Das zeigt erst der nächste Verbindungsaufbau.
                self._verlust_offen = True
                self._notiz(t("Verbindung zum Motor verloren: {fehler}", fehler=exc),
                            self.plan.motor)
                continue
            self._motorzustand()
            if werte is not None and not self._aufgefordert:
                self._auffordern()
        motor_zeit_buchen()

    def _auffordern(self) -> None:
        """Nach den ersten Motorwerten: jetzt anlassen – oder festhalten, dass er schon lief
        (dann fehlt das Anlassen in der Aufzeichnung)."""
        self._aufgefordert = True
        if self.motor_laeuft_seit is not None:
            self.anlassen_verpasst = True
            self._notiz(t("Der Motor lief schon beim ersten Messwert – das Anlassen ist nicht "
                          "aufgezeichnet"), self.plan.motor)
            return
        self._notiz(t("Aufzeichnung läuft – jetzt Motor starten und losfahren"))
        self._status(FAHRT, t("Aufzeichnung läuft – jetzt Motor starten und losfahren"))

    def _motorzustand(self) -> None:
        n = self.letzte_drehzahl
        if n is None:
            return
        if n >= self.plan.motor_laeuft_ab:
            if self.motor_laeuft_seit is None:
                self.motor_laeuft_seit = time.monotonic()
                if self._motor_aus_gesehen:     # lief er schon, gab es kein Anlassen zu sehen
                    self.motorstarts.append(self._t())
                self._notiz(t("Motor läuft"))
                if self._aufgefordert:          # „jetzt Motor starten“ ist erledigt
                    self._status(FAHRT, t("Aufzeichnung läuft"))
        else:
            self._motor_aus_gesehen = True
            if self.motor_laeuft_seit is not None:
                self.motor_laeuft_seit = None
                self._notiz(t("Motor steht"))

    def _besuch(self, b: Besuch) -> None:
        self.besuche += 1
        self.besuche_je[b.adresse] = self.besuche_je.get(b.adresse, 0) + 1
        self._status(FAHRT, t("kurzer Besuch bei {steuergeraet} …",
                              steuergeraet=adressen.text(b.adresse)))
        self._trennen()
        if not self._verbinden(b.adresse):
            return
        gruppen = [g for g in b.gruppen if g not in self._fehlende.get(b.adresse, set())]
        ende = time.monotonic() + b.dauer
        i = 0
        try:
            if b.adresse in self._offen:        # Fehlerspeicher für ein Ereignis nachholen
                self._fehler_lesen(b.adresse, EREIGNIS, {})
            while gruppen and time.monotonic() < ende:
                self._pruefe_abbruch()
                if self.ende.is_set():
                    break
                g = gruppen[i % len(gruppen)]
                i += 1
                if self._lesen(b.adresse, g, FAHRT) is None:
                    gruppen.remove(g)
        except LEITUNG as exc:
            self.stoerungen += 1
            self._notiz(t("Störung bei {adresse:02X}: {fehler}", adresse=b.adresse, fehler=exc),
                        b.adresse)
        self._trennen()

    def _ereignis(self, marke: tuple[float, str]) -> None:
        zeitpunkt, text = marke
        uhrzeit = time.strftime("%H:%M:%S", time.localtime(zeitpunkt))
        self._status(EREIGNIS, t("{text} – lese Fehlerspeicher …", text=text))
        self._notiz(t("EREIGNIS ({text}) um {uhrzeit}", text=text, uhrzeit=uhrzeit),
                    art=ringspeicher.EREIGNIS)
        ergebnisse: dict[int, object] = {}
        self.ereignisse.append((uhrzeit, text, ergebnisse))
        for adresse in self.plan.ereignis_fehlerspeicher:
            self._pruefe_abbruch()
            if not self._darf(adresse):
                # z. B. ABS: antwortet nur im Stand – beim nächsten Halt nachlesen
                ergebnisse[adresse] = t("wird beim nächsten Halt gelesen")
                self._offen.setdefault(adresse, []).append(ergebnisse)
                self._notiz(t("{steuergeraet}: Fehlerspeicher wird beim nächsten Halt gelesen "
                              "(antwortet nur im Stand)", steuergeraet=adressen.text(adresse)),
                            adresse)
                continue
            schon_da = self.s.verbunden and self.s._letzte_adresse == adresse
            if not schon_da:
                self._trennen()
                if not self._verbinden(adresse):
                    ergebnisse[adresse] = t("nicht erreichbar")
                    continue
            # zuerst ein Satz Messwerte (Spannung beim Motor), dann der Fehlerspeicher
            try:
                if adresse == self.plan.motor and 4 in self.plan.motor_gruppen:
                    self._lesen(adresse, 4, EREIGNIS)
                self._fehler_lesen(adresse, EREIGNIS, ergebnisse)
            except LEITUNG as exc:
                self.stoerungen += 1
                ergebnisse.setdefault(adresse, t("nicht lesbar ({fehler})", fehler=exc))
                self._notiz(t("Störung bei {adresse:02X}: {fehler}", adresse=adresse,
                              fehler=exc), adresse)
        if self.passiv:
            self._sichern()
        self._status(FAHRT, t("Aufzeichnung läuft"))

    def _sichern(self) -> None:
        """Passiv: die Zeitspanne bis jetzt als eigene Datei, die nie überschrieben wird."""
        self._status(EREIGNIS, t("sichere die Zeitspanne …"))
        try:
            ergebnis = passiv_exportieren(self.ordner, self.passiv, self.sim, gesichert=True,
                                          plan=self.plan)
        except OSError as exc:
            self._notiz(t("Zeitspanne nicht gesichert: {fehler}", fehler=exc))
            return
        self.sicherungen.append(ergebnis.csv_datei)
        self._notiz(t("Zeitspanne gesichert: {pfad}", pfad=ergebnis.csv_datei),
                    art=ringspeicher.SICHERUNG)

    # ------------------------------------------------------------ Gesamtablauf
    def ausfuehren(self) -> Zusammenfassung:
        try:
            return self._ausfuehren()
        except BaseException:
            # unerwartet beendet (z. B. Kabel gezogen): Datei schließen – beim Ringspeicher
            # auch seine Sperre, sonst ginge im selben Programm kein neuer Lauf
            self.datei.schliessen()
            raise

    def _ausfuehren(self) -> Zusammenfassung:
        self._notiz(t("Fahrtenschreiber gestartet") + (
            " " + t("(Simulator – keine echten Fahrzeugdaten)") if self.sim else "")
            + (" – " + t("passiv, Zeitspanne {zeitspanne}",
                         zeitspanne=ringspeicher.fenster_text(self.passiv))
               if self.passiv else ""), art=ringspeicher.LAUF)
        try:
            # passiv (auch automatisch gestartet): ohne Kabel still warten statt abbrechen
            kabel = not self.passiv or self._kabel_abwarten()
            if kabel and self.plan.pruefung:
                # im Simulator steht das Auto zur Prüfung – wie im echten Leben
                self._simulator("fahrzeug_parken")
                self._status(START, t("Startprüfung: Tankinhalt im Stand, Fehlerspeicher"))
                self._pruefung(START)
            if kabel and not self.ende.is_set():    # beim Beenden vor der Fahrt: Schluss
                if self.plan.pruefung:
                    self._notiz(t("Startprüfung fertig"))
                    self._simulator("fahrzeug_losfahren")
                self._fahrt()
                # im Simulator fährt das Profil sonst weiter – zur Abschlussprüfung steht er
                self._simulator("fahrzeug_parken")
                if self.plan.pruefung:
                    self._status(ABSCHLUSS, t("Abschlussprüfung – Zündung noch an lassen"))
                    self._pruefung(ENDE)
                for adresse, offen in self._offen.items():
                    for ergebnisse in offen:
                        ergebnisse[adresse] = t("nicht gelesen (kein Halt mehr)")
                self._offen.clear()
        except Abgebrochen:
            self.abgebrochen = True
            self._notiz(t("Fahrtenschreiber abgebrochen"))
        finally:
            self._trennen()
        self._notiz(t("Fahrtenschreiber beendet"))
        if self.passiv:
            return self._passiv_beenden()
        zeilen = self.zusammenfassung()
        self.datei.schliessen()
        txt = self.datei.pfad.with_name(self.datei.pfad.stem + t("-zusammenfassung") + ".txt")
        try:
            txt.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        except OSError as exc:
            log.warning(t("Zusammenfassung nicht gespeichert: %s"), exc)
            txt = None
        self._status(FERTIG, t("Fahrtenschreiber beendet"))
        return Zusammenfassung(zeilen, self.datei.pfad, txt, self.abgebrochen)

    def _passiv_beenden(self) -> Zusammenfassung:
        """Ringspeicher schließen, die Zeitspanne als fahrt-passiv.csv mit Zusammenfassung."""
        self.datei.schliessen()
        nachtrag = ((["", t("Während der Fahrt gesichert:")]
                     + [f"  {p}" for p in self.sicherungen]) if self.sicherungen else [])
        try:
            ergebnis = passiv_exportieren(self.ordner, self.passiv, self.sim, gesichert=False,
                                          plan=self.plan, abgebrochen=self.abgebrochen,
                                          nachtrag=nachtrag)
        except OSError as exc:
            log.warning(t("Zeitspanne nicht exportiert: %s"), exc)
            zeilen = [t("Zeitspanne nicht exportiert: {fehler}", fehler=exc),
                      t("Der Ringspeicher bleibt erhalten: {ordner}", ordner=self.datei.pfad)]
            ergebnis = Zusammenfassung(zeilen + nachtrag, self.datei.pfad, None,
                                       self.abgebrochen)
        ergebnis.sicherungen = list(self.sicherungen)
        self._status(FERTIG, t("Fahrtenschreiber beendet"))
        return ergebnis

    # ------------------------------------------------------------ Auswertung
    def zusammenfassung(self) -> list[str]:
        s = self.sammler
        dauer = self._t()
        z = [t("Fahrt vom {datum} – Dauer {minuten:.0f} min", datum=datum_zeit(self.beginn_wand),
               minuten=dauer / 60)
             + (" – " + t("SIMULATOR, keine echten Fahrzeugdaten") if self.sim else "")
             + (" – " + t("abgebrochen") if self.abgebrochen else ""),
             t("Datei: {pfad}", pfad=self.datei.pfad), ""]
        if self.fahrt_beginn is not None:
            fahrt_dauer = max(1e-9, (self.fahrt_ende or dauer) - self.fahrt_beginn)
            besuche = []
            for b in self.plan.besuche:
                name = t(KURZNAMEN[b.adresse]) if b.adresse in KURZNAMEN else f"{b.adresse:02X}"
                text = f"{name} {self.besuche_je.get(b.adresse, 0)}"
                if b.adresse in self.plan.nur_im_stand:
                    text += " " + t("(nur im Stand)")
                besuche.append(text)
            z.append(t("Motordaten: {anteil:.0f} % der Fahrzeit · Besuche: {besuche} · "
                       "Störungen: {stoerungen}",
                       anteil=min(100.0, self.motor_zeit / fahrt_dauer * 100),
                       besuche=", ".join(besuche) or "–", stoerungen=self.stoerungen))
            if self.zuendung_aus_fahrt:
                z.append(t("Zündung zwischendurch aus (keine Störung): {zeiten}",
                           zeiten=", ".join(f"{von}–{bis}" for von, bis in
                                            self.zuendung_aus_fahrt)))
        if self.kabel_weg:
            z.append(t("Kabel zwischendurch nicht erreichbar: {zeiten}",
                       zeiten=", ".join(f"{von}–{bis}" for von, bis in self.kabel_weg)))

        # Fehlerspeicher
        z += ["", t("Fehlerspeicher")]
        for phase in (START, ENDE):
            ergebnisse = self.fehler.get(phase)
            if phase in self.zuendung_aus:
                z.append(f"  {t(phase)}: " + t("nicht geprüft – die Zündung war aus"))
            elif ergebnisse:
                z.append(f"  {t(phase)}: " + " · ".join(
                    f"{a:02X} {_fehlertext(e)}" for a, e in sorted(ergebnisse.items())))
        for uhrzeit, text, ergebnisse in self.ereignisse:
            z.append("  " + t("Ereignis {uhrzeit} ({text}):", uhrzeit=uhrzeit, text=text) + " "
                     + (" · ".join(f"{a:02X} {_fehlertext(e)}" for a, e in ergebnisse.items())
                        or "–"))
        if not self.fehler and not self.ereignisse:
            z.append("  " + t("nicht gelesen"))

        z += auswertung(s, self.plan, dauer, self.motorstarts, self.anlassen_verpasst,
                        self.teilenummern, ENDE in self.zuendung_aus)

        if self.unerreichbar:
            z += ["", t("Nicht erreicht:")]
            for adresse, uhrzeit, tempo in self.unerreichbar:
                zusatz = (" " + t("bei etwa {tempo:.0f} km/h", tempo=tempo)
                          if tempo is not None else "")
                z.append(f"  {uhrzeit} {adressen.text(adresse)}{zusatz}")
        return z


def auswertung(s: Sammler, plan: FahrtPlan, dauer: float, motorstarts: list[float],
               anlassen_verpasst: bool, teilenummern: dict[int, str],
               ende_zuendung_aus: bool = False) -> list[str]:
    """Die Werte-Teile der Zusammenfassung (Kühlmittel, Spannung, Drehzahl, Lambda, Tempo,
    Tank, Bremse) – für eine Fahrt und für die Zeitspanne des passiven Fahrtenschreibers."""
    M, K, A = plan.motor, 0x17, 0x03
    z: list[str] = []
    # Kühlmittel
    kmt = s.zahlen(M, "Kühlmitteltemperatur")
    if kmt:
        proben = [p for p in s.proben(M, "Kühlmitteltemperatur") if p.zahl is not None]
        warm_ab = next((p.t for p in proben if p.zahl >= 70), None)
        zeile = t("Kühlmittel (Motor): Anfang {anfang} °C, höchstens {hoechstens} °C",
                  anfang=_z(proben[0].zahl), hoechstens=_z(max(kmt)))
        if warm_ab is not None:
            warm = [p.zahl for p in proben if p.t >= warm_ab]
            zeile += ", " + t("nach dem Warmlaufen {von}–{bis} °C (Median {median} °C)",
                              von=_z(min(warm)), bis=_z(max(warm)),
                              median=_z(statistics.median(warm)))
        z += ["", zeile]
        # die Bedeutung der Stellen ist nur am 6K0 906 032 M geprüft
        bits = [p.text for p in s.proben(M, "Grundeinstellungsbedingungen")
                if p.phase == FAHRT and len(p.text) == 8 and set(p.text) <= {"0", "1"}
                and beschriftung.bitfeld_bekannt(teilenummern.get(M))]
        if bits:
            anteil = sum(1 for b in bits if b[-1] == "1") / len(bits) * 100
            z.append("  " + t("Merker „Kühlmittel über 80 °C“ (Gruppe 001): {anteil:.0f} % "
                              "der Zeit", anteil=anteil))
        if warm_ab is not None and max(kmt) < 85 and dauer > 900:
            z.append("  " + t("Hinweis: Nach über 15 Minuten nie 85 °C erreicht – "
                              "Thermostat beobachten."))
    kombi_kmt = s.zahlen(K, "Kühlmitteltemperatur", FAHRT)
    if kombi_kmt:
        z.append(t("Kühlmittel (Kombi, während der Fahrt): {von}–{bis} °C",
                   von=_z(min(kombi_kmt)), bis=_z(max(kombi_kmt))))

    # Spannung
    u_proben = [p for p in s.proben(M, "Bordspannung") if p.zahl is not None]
    if u_proben:
        # Drehzahl aus derselben Abfrage (Gruppe 004 enthält beide)
        n_bei = {p.t: p.zahl for p in s.proben(M, "Motordrehzahl")}
        grenze = plan.motor_laeuft_ab

        def gerade_angesprungen(zeit: float) -> bool:
            # die ersten Sekunden nach dem Anspringen gehören noch zum Anlassen
            return any(-1.0 <= zeit - start < ANLASS_NACHLAUF for start in motorstarts)

        anlassen = [p.zahl for p in u_proben if 0 < (n_bei.get(p.t) or 0) < grenze
                    or ((n_bei.get(p.t) or 0) >= grenze and gerade_angesprungen(p.t))]
        laufend = [p.zahl for p in u_proben if (n_bei.get(p.t) or 0) >= grenze
                   and not gerade_angesprungen(p.t)]
        stehend = [p.zahl for p in u_proben if n_bei.get(p.t) == 0]
        teile = []
        if stehend:
            teile.append(t("Motor aus {spannung} V", spannung=_z(statistics.median(stehend), 2)))
        if anlassen:
            teile.append(t("beim Anlassen min. {spannung} V", spannung=_z(min(anlassen), 2)))
        elif anlassen_verpasst:
            teile.append(t("Anlassen nicht aufgezeichnet (Motor lief schon beim ersten "
                           "Messwert)"))
        if laufend:
            teile.append(t("bei laufendem Motor Median {median} V ({von}–{bis} V)",
                           median=_z(statistics.median(laufend), 2),
                           von=_z(min(laufend), 2), bis=_z(max(laufend), 2)))
        if teile:
            z.append(t("Bordspannung:") + " " + " · ".join(teile))

    iat = s.zahlen(M, "Ansauglufttemperatur")
    if iat:
        z.append(t("Ansauglufttemperatur: {von}–{bis} °C", von=_z(min(iat)), bis=_z(max(iat))))
    n_alle = [n for n in s.zahlen(M, "Motordrehzahl", FAHRT)
              if n >= plan.motor_laeuft_ab]
    if n_alle:
        z.append(t("Drehzahl: höchstens {hoechstens}/min, Median {median}/min",
                   hoechstens=tausender(max(n_alle)),
                   median=tausender(statistics.median(n_alle))))
    # Lambdaregelung erst mit warmem Motor – direkt nach dem Kaltstart schwingt der
    # Regler weit aus, das sagt nichts über das Gemisch
    kmt_bei = {p.t: p.zahl for p in s.proben(M, "Kühlmitteltemperatur")
               if p.zahl is not None}
    lam = [p.zahl for p in s.proben(M, "Lambdaregelung")
           if p.phase == FAHRT and p.zahl not in (None, 0)
           and (kmt_bei.get(p.t) or 0) >= LAMBDA_WARM_AB]
    if len(lam) >= 5:
        reihe = sorted(lam)
        z.append(t("Lambdaregelung (warmer Motor): Mittel {mittel} %, meist {p5} bis {p95} %, "
                   "äußerste Werte {von} bis {bis} %",
                   mittel=_z(statistics.mean(lam), 1),
                   p5=_z(reihe[int(0.05 * (len(reihe) - 1))], 1),
                   p95=_z(reihe[int(round(0.95 * (len(reihe) - 1)))], 1),
                   von=_z(reihe[0], 1), bis=_z(reihe[-1], 1)))

    # Tempo – jede Quelle für sich (Motor-Gruppe 005, Kombi, ABS-Räder); das ABS nur,
    # wenn es auch beim Fahren besucht wird – im Stand gelesen sagt es nichts
    tempo = []
    for adresse, name, quelle in ((M, "Fahrgeschwindigkeit", N_("Motorsteuergerät")),
                                  (K, "Geschwindigkeit", N_("Kombi")),
                                  (A, "Rad vorn links", N_("ABS"))):
        if adresse in plan.nur_im_stand:
            continue
        v = s.zahlen(adresse, name, FAHRT)
        if v:
            tempo.append(f"{t(quelle)} {_z(max(v))} km/h")
    if tempo:
        z.append(t("Tempo höchstens:") + " " + " · ".join(tempo))

    # Tank
    teile = []
    for phase, titel in ((START, N_("Stand am Anfang")), (FAHRT, N_("während der Fahrt")),
                         (ENDE, N_("Stand am Ende"))):
        liter = s.zahlen(K, "Tankinhalt", phase)
        ohm = s.zahlen(K, "Tankgeber", phase)
        if liter:
            text = f"{t(titel)} {_z(statistics.median(liter))} l"
            if ohm:
                text += f" ({_z(statistics.median(ohm))} Ω)"
            if phase == FAHRT:
                text += ", " + t("Median aus {anzahl} Werten", anzahl=len(liter))
            teile.append(text)
    if teile and ende_zuendung_aus:
        teile.append(t("Stand am Ende nicht gemessen (Zündung aus)"))
    if teile:
        z += ["", t("Tankanzeige:") + " " + " · ".join(teile)]

    # Bremse (nach der Klartext-Nummer – unabhängig von der Sprache), je Besuch: im Stand
    # steht der Fuß oft die ganze Zeit auf der Bremse
    proben = s.proben(A, "Bremslichtschalter")
    if proben:
        besuche: list[list[int | None]] = []
        for vorher, p in zip([None] + proben[:-1], proben):
            if vorher is None or p.t - vorher.t > BESUCH_LUECKE:
                besuche.append([])
            besuche[-1].append(p.nummer)
        betaetigt = sum(1 for b in besuche if BREMSE_BETAETIGT in b)
        z.append(t("Bremslichtschalter (ABS-Besuche): {anzahl} Werte, bei {betaetigt} von "
                   "{besuche} Besuchen betätigt", anzahl=len(proben), betaetigt=betaetigt,
                   besuche=len(besuche)))

    return z


# ---------------------------------------------------------------- passiv
def _export_ziel(ordner, sim: bool, gesichert: bool) -> Path:
    basis = Path(ordner).expanduser() if ordner else einstellungen.ordner("csv_ordner")
    vorsilbe = "sim-" if sim else ""
    if gesichert:
        return basis / time.strftime(vorsilbe + "fahrt-passiv-gesichert-%Y%m%d-%H%M%S.csv")
    return basis / (vorsilbe + "fahrt-passiv.csv")


def passiv_exportieren(ordner, fenster: float, sim: bool = False, gesichert: bool = True,
                       plan: FahrtPlan | None = None, abgebrochen: bool = False,
                       nachtrag: list[str] | None = None) -> Zusammenfassung:
    """Die letzten `fenster` Sekunden Fahrzeit aus dem Ringspeicher als CSV-Datei mit
    Zusammenfassung daneben. gesichert: eigene Datei mit Datum und Uhrzeit im Namen (nie
    überschrieben), sonst fahrt-passiv.csv (bei jedem Ende neu)."""
    auszug = ringspeicher.exportieren(ringspeicher.ordner(ordner, sim), fenster,
                                      _export_ziel(ordner, sim, gesichert), [t(k) for k in KOPF])
    zeilen = (fenster_zusammenfassung(auszug, plan or FahrtPlan(), fenster, sim, abgebrochen)
              + list(nachtrag or []))
    txt = auszug.pfad.with_name(auszug.pfad.stem + t("-zusammenfassung") + ".txt")
    try:
        txt.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning(t("Zusammenfassung nicht gespeichert: %s"), exc)
        txt = None
    return Zusammenfassung(zeilen, auszug.pfad, txt, abgebrochen)


def _datum(spalte: str) -> str:
    """Uhrzeit-Spalte der CSV („2026-10-28 14:03:22,123“) → „28.10.2026, 14:03“."""
    try:
        return datum_zeit(time.strptime(spalte[:19], "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return spalte


def fenster_zusammenfassung(auszug: ringspeicher.Auszug, plan: FahrtPlan, fenster: float,
                            sim: bool = False, abgebrochen: bool = False) -> list[str]:
    """Zusammenfassung der Zeitspanne – aus den Daten im Ringspeicher, auch über mehrere
    Fahrten: Fehlerspeicher und Ereignisse im Zeitraum, dann die Werte wie bei einer Fahrt."""
    z = [t("Passiver Fahrtenschreiber – die letzten {zeitspanne} Fahrzeit",
           zeitspanne=ringspeicher.fenster_text(fenster))
         + (" – " + t("SIMULATOR, keine echten Fahrzeugdaten") if sim else "")
         + (" – " + t("abgebrochen") if abgebrochen else "")]
    if auszug.daten:
        z.append(t("Zeitraum: {von} bis {bis} · Fahrzeit {minuten} min · Fahrten: {fahrten}",
                   von=_datum(auszug.von), bis=_datum(auszug.bis),
                   minuten=_z(auszug.fahrzeit / 60, 1), fahrten=auszug.laeufe))
        if auszug.fahrzeit < fenster - ringspeicher.STUECK:
            z.append(t("Die Zeitspanne ist noch nicht voll."))
    else:
        z.append(t("Im Ringspeicher sind noch keine Messwerte."))
    z += [t("Datei: {pfad}", pfad=auszug.pfad), "", t("Fehlerspeicher und Ereignisse im Zeitraum")]
    notizen = [n for n in auszug.notizen
               if n.art in (ringspeicher.FEHLERSPEICHER, ringspeicher.EREIGNIS)]
    z += [f"  {n.zeit[11:19]}  {n.text}" for n in notizen] or ["  " + t("keine")]

    s = Sammler()
    teilenummern: dict[int, str] = {}
    motorstarts: list[float] = []
    drehzahl_vorher: dict[int, float] = {}            # Lauf → letzte Drehzahl
    for d in auszug.daten:
        if d.teil:
            teilenummern[d.adresse] = d.teil
        for feld in d.felder:
            if len(feld) < 4:
                continue
            name, wert, text, nummer = feld[:4]
            s.probe(d.adresse, name, Probe(d.zeit, d.phase, wert, text, nummer))
            if d.adresse == plan.motor and name == "Motordrehzahl" and wert is not None:
                vorher = drehzahl_vorher.get(d.lauf)
                if vorher is not None and vorher < plan.motor_laeuft_ab <= wert:
                    motorstarts.append(d.zeit)
                drehzahl_vorher[d.lauf] = wert
    z += auswertung(s, plan, auszug.fahrzeit, motorstarts, False, teilenummern)
    unerreichbar = [n for n in auszug.notizen if n.art == ringspeicher.UNERREICHBAR]
    if unerreichbar:
        z += ["", t("Nicht erreicht:")] + [f"  {n.zeit[11:19]}  {n.text}" for n in unerreichbar]
    return z

"""Fahrtenschreiber: die wichtigen Messwerte einer ganzen Fahrt in einer Datei.

Über die K-Leitung spricht das Programm immer nur mit einem Steuergerät.
Der Fahrtenschreiber wechselt deshalb selbst:

  Startprüfung  Tankinhalt im Stand (Kombi), Fehlerspeicher aller Steuergeräte
  Fahrt         Motorsteuergerät durchgehend. Solange der Motor steht, nur
                Gruppe 004 – so wird die Bordspannung beim Anlassen möglichst
                oft gelesen. In festen Abständen kurze Besuche beim Kombi
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

from . import adressen, airbag, beschriftung, einstellungen
from .aufzeichnung import _zahl, zeitstempel
from .kline import KLineError
from .kw1281 import (Abgebrochen, DiagError, Nak, NoResponse, NotAvailable, NotConnected,
                     ProtocolError)
from .messwerte import Messwert
from .port import PortError
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
    zuendung_warten: float = 60.0                # Prüfungen: so lange auf die Zündung warten

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
                  namen: list[str]) -> None:
        schluessel = (adresse, gruppe)
        if any(namen) and schluessel not in self._beschriftet:
            self._beschriftet.add(schluessel)
            self.ereignis(f"{adresse:02X}/{gruppe:03d}: " + " | ".join(
                beschriftung.anzeige(n) or t("Feld {nummer}", nummer=i + 1)
                for i, n in enumerate(namen)), adresse, phase)
        felder: list[str] = []
        for i in range(4):
            felder += ([_zahl(werte[i]), einheit(werte[i].einheit)] if i < len(werte)
                       else ["", ""])
        self._schreiben(self._zeit() + [f"{adresse:02X}", f"{gruppe:03d}", t(phase)]
                        + felder + [""])

    def ereignis(self, text: str, adresse: int | None = None, phase: str = "") -> None:
        self._schreiben(self._zeit() + [f"{adresse:02X}" if adresse is not None else "",
                                        "", t(phase) if phase else ""] + [""] * 8 + [text])

    def _schreiben(self, zeile: list[str]) -> None:
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
        self.datei = FahrtDatei.neu(ordner, sim)
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
        self.letzte_drehzahl: float | None = None
        self.motor_laeuft_seit: float | None = None
        self.motorstarts: list[float] = []          # Anspringen, Sekunden seit Start (_t)
        self._motor_aus_gesehen = False             # erst danach ist „Motor läuft“ ein Start
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
        self._phase = START

    # ------------------------------------------------------------ Helfer
    def _t(self) -> float:
        return time.monotonic() - self.beginn

    def _status(self, phase: str, text: str) -> None:
        """phase: interner Name (START, FAHRT …); im Ereignis steht er übersetzt."""
        self._phase = phase
        log.info(t("Fahrtenschreiber – %s: %s"), t(phase), text)
        self.s._melden("fahrt", {"phase": t(phase), "text": text, "zeilen": self.datei.zeilen,
                                 "datei": str(self.datei.pfad), "dauer": self._t()})

    def _notiz(self, text: str, adresse: int | None = None) -> None:
        self.datei.ereignis(text, adresse, self._phase)
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
                      steuergeraet=adressen.text(adresse), fehler=fehler) + zusatz, adresse)

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
        namen = beschriftung.namen(verbindung, gruppe, werte)
        self.datei.messwerte(adresse, gruppe, phase, werte, namen)
        zeit = self._t()
        for name, m in zip(namen, werte):
            self.sammler.add(adresse, name, zeit, phase, m)
            if m.zahl is None or not m.gueltig:
                continue
            if name in ("Fahrgeschwindigkeit", "Geschwindigkeit"):
                self.letztes_tempo = m.zahl
                self.tempo_zeit = time.monotonic()
            elif name == "Motordrehzahl" and adresse == self.plan.motor:
                self.letzte_drehzahl = m.zahl
        if adresse == 0x03 and gruppe == 1:
            raeder = [m.zahl for m in werte if m.zahl is not None and m.einheit == "km/h"]
            if raeder:
                self.letztes_tempo = sum(raeder) / len(raeder)
                self.tempo_zeit = time.monotonic()
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
                    adresse)
        offen = self._offen.pop(adresse, [])
        if offen:
            wann = (t("bei der Abschlussprüfung gelesen") if phase == ENDE else
                    t("im Stand gelesen um {uhrzeit}", uhrzeit=time.strftime("%H:%M:%S")))
            for ergebnisse in offen:
                ergebnisse[adresse] = f"{_fehlertext(ziel[adresse])} ({wann})"

    # ------------------------------------------------------------ Stillstand
    def _steht(self) -> bool:
        """Steht das Auto? Nur mit frischem Tempo-Wert (Motor-Gruppe 005, Kombi, ABS)."""
        return (self.letztes_tempo is not None and self.letztes_tempo < 1
                and self.tempo_zeit is not None
                and time.monotonic() - self.tempo_zeit <= self.plan.stand_frisch)

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

    def _pruefung(self, phase: str) -> None:
        """Tankinhalt im Stand und Fehlerspeicher aller Steuergeräte."""
        ergebnisse = self.fehler.setdefault(phase, {})
        lesen = self.plan.pruef_adressen()
        reihenfolge = [self.plan.stand_adresse] + [a for a in lesen
                                                   if a != self.plan.stand_adresse]
        erste = self._erste_verbindung(phase, reihenfolge[0])
        if erste is None:
            self.zuendung_aus.add(phase)
            self._notiz(t("Zündung aus – {phase} nicht möglich", phase=t(phase)))
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
            self._trennen()

    # ------------------------------------------------------------ Fahrt
    def _motor_verbinden(self) -> bool:
        """So lange versuchen, bis der Motor antwortet (oder Ende/Abbruch)."""
        while True:
            self._pruefe_abbruch()
            if self.ende.is_set():
                return False
            self._status(FAHRT, t("verbinde mit {steuergeraet} …",
                                  steuergeraet=adressen.text(self.plan.motor)))
            try:
                self.s._verbinden(self.plan.motor, self.plan.bauds)
                return True
            except Abgebrochen:
                raise
            except DiagError as exc:
                log.info(t("Motor nicht erreichbar: %s"), exc)
                self._warten(0.5)

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
        verbunden_seit: float | None = None

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
                self._lesen(self.plan.motor, gruppe, FAHRT)
            except LEITUNG as exc:
                self.stoerungen += 1
                self._notiz(t("Verbindung zum Motor verloren: {fehler}", fehler=exc),
                            self.plan.motor)
                continue
            self._motorzustand()
        motor_zeit_buchen()

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
        self._notiz(t("EREIGNIS ({text}) um {uhrzeit}", text=text, uhrzeit=uhrzeit))
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
        self._status(FAHRT, t("Aufzeichnung läuft"))

    # ------------------------------------------------------------ Gesamtablauf
    def ausfuehren(self) -> Zusammenfassung:
        self._notiz(t("Fahrtenschreiber gestartet") + (
            " " + t("(Simulator – keine echten Fahrzeugdaten)") if self.sim else ""))
        try:
            if self.plan.pruefung:
                # im Simulator steht das Auto zur Prüfung – wie im echten Leben
                self._simulator("fahrzeug_parken")
                self._status(START, t("Startprüfung: Tankinhalt im Stand, Fehlerspeicher"))
                self._pruefung(START)
            if not self.ende.is_set():      # beim Beenden während der Startprüfung: Schluss
                if self.plan.pruefung:
                    self._notiz(t("Startprüfung fertig – Motor starten und losfahren"))
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

    # ------------------------------------------------------------ Auswertung
    def zusammenfassung(self) -> list[str]:
        s = self.sammler
        M, K, A = self.plan.motor, 0x17, 0x03
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

        # Fehlerspeicher
        z += ["", t("Fehlerspeicher")]
        for phase in (START, ENDE):
            ergebnisse = self.fehler.get(phase)
            if phase in self.zuendung_aus:
                z.append(f"  {t(phase)}: " + t("nicht geprüft – die Zündung war aus"))
            elif ergebnisse:
                z.append(f"  {t(phase)}: " + " · ".join(
                    f"{a:02X} {_fehlertext(e)}" for a, e in ergebnisse.items()))
        for uhrzeit, text, ergebnisse in self.ereignisse:
            z.append("  " + t("Ereignis {uhrzeit} ({text}):", uhrzeit=uhrzeit, text=text) + " "
                     + (" · ".join(f"{a:02X} {_fehlertext(e)}" for a, e in ergebnisse.items())
                        or "–"))
        if not self.fehler and not self.ereignisse:
            z.append("  " + t("nicht gelesen"))

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
            bits = [p.text for p in s.proben(M, "Grundeinstellungsbedingungen")
                    if p.phase == FAHRT and len(p.text) == 8 and set(p.text) <= {"0", "1"}]
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
            grenze = self.plan.motor_laeuft_ab

            def gerade_angesprungen(zeit: float) -> bool:
                # die ersten Sekunden nach dem Anspringen gehören noch zum Anlassen
                return any(-1.0 <= zeit - start < ANLASS_NACHLAUF for start in self.motorstarts)

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
                  if n >= self.plan.motor_laeuft_ab]
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
            if adresse in self.plan.nur_im_stand:
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
        if teile and ENDE in self.zuendung_aus:
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

        if self.unerreichbar:
            z += ["", t("Nicht erreicht:")]
            for adresse, uhrzeit, tempo in self.unerreichbar:
                zusatz = (" " + t("bei etwa {tempo:.0f} km/h", tempo=tempo)
                          if tempo is not None else "")
                z.append(f"  {uhrzeit} {adressen.text(adresse)}{zusatz}")
        return z

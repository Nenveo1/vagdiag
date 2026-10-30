# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Diagnose-Sitzung in einem eigenen Thread.

Alle Zugriffe auf das Kabel laufen nacheinander in einem Arbeits-Thread. Ist
gerade nichts zu tun, hält er die Verbindung mit ACK-Blöcken am Leben – sonst
legt das Steuergerät nach gut einer Sekunde auf. Die Oberfläche bekommt
Ergebnisse als concurrent.futures.Future und Ereignisse über einen Callback:

  "verbunden"       Verbindung      (auch nach automatischem Neuverbinden)
  "getrennt"        {"grund": str, "neu_verbinden": bool}
  "neu_verbinden"   Versuchsnummer
  "baud"            (adresse, baud) – funktionierende Baudrate merken
  "suche"           (gruppe, Messwerte oder None) während der Gruppensuche
  "anpassung_suche" (kanal, Anpassung oder None) während der Kanalsuche
  "fahrt"           {"phase", "text", "zeilen", "datei", "dauer"} – Fahrtenschreiber
  "fahrt_werte"     {"adresse", "gruppe", "werte", "namen"} – jede gelesene Gruppe
  "fahrt_notiz"     Text – Ereigniszeile des Fahrtenschreibers
  "scan"            {"index", "anzahl", "adresse", "eintrag"} – Scan; eintrag ist None,
                    solange die Adresse gerade abgefragt wird (siehe scan.py)
  "grundeinstellung" {"gruppe", "werte", "sekunden", "dauer", "status"} – Expertenmodus
  "stellglied"      {"schritt", "stellglied", "gleich", "kwp2000", "adresse", "hoechstens"}
                    – jedes Stellglied der Stellglieddiagnose (Expertenmodus); hoechstens:
                    so viele Sekunden bleibt es ohne „Weiter“ angesteuert
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from concurrent.futures import Future
from typing import Callable, Sequence

from . import adressen, airbag, obd2
from . import experte as expertenfunktionen
from . import kilometerstand as km_lesen
from .scan import ScanEintrag
from .fahrtenschreiber import Fahrtenschreiber, FahrtPlan, Zusammenfassung
from .kline import KLine, KLineError
from .kwp2000 import FAST_INIT_ADRESSE
from .kw1281 import (KW1281, Abgebrochen, Anpassung, DiagError, Nak, NoResponse,
                     NotAvailable, NotConnected, ProtocolError, Stoerung, Timing, Verbindung)
from .port import PortError, RawPort
from .sprache import t

log = logging.getLogger("vagdiag.proto")

Ereignis = Callable[[str, object], None]


class DiagSession:
    def __init__(self, port_fabrik: Callable[[], RawPort], timing: Timing | None = None,
                 keepalive: float = 0.5, ereignis: Ereignis | None = None,
                 baudraten: dict[int, int] | None = None):
        self._port_fabrik = port_fabrik
        self.timing = timing or Timing()
        self.keepalive = keepalive
        self._ereignis = ereignis or (lambda art, daten: None)
        self.baudraten = baudraten if baudraten is not None else {}
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._lauf, name="diag", daemon=True)
        self._abbruch = threading.Event()
        self._port: RawPort | None = None
        self._kline: KLine | None = None
        self._proto: KW1281 | None = None
        self._letzte_adresse: int | None = None
        self._letzte_bauds: tuple[int, ...] = (10400, 9600)
        self._verloren_um = -1e9
        self._verloren_adresse: int | None = None   # Steuergerät des letzten Abbruchs/Fehlversuchs
        self._getrennt_um = -1e9
        self._eilig = False       # Neuverbinden während einer Messung (siehe _pause_vor_reizung)
        self._laeuft = False
        self._fahrt_ende = threading.Event()
        self._fahrt_marken: queue.Queue = queue.Queue()
        self.fahrt_laeuft = False
        # Adresse 15 (Airbag) nur nach ausdrücklicher Freigabe – siehe airbag.py
        self.airbag_freigegeben = False
        # Motor (01): zuerst den KWP2000-Fast-Init probieren (sonst nur 5-Baud-Reizung)
        self._fast_init = False
        self._fast_init_klappt: dict[int, bool] = {}
        # Expertenmodus: nur dann dürfen Expertenfunktionen schreiben (siehe experte.py)
        self._experte = False
        self._stellglied_befehle: queue.Queue = queue.Queue()   # „weiter“ / „ende“
        # Stellglieddiagnose: so lange bleibt ein Stellglied höchstens ohne „Weiter“ an
        self.stellglied_schritt_max = expertenfunktionen.SCHRITT_MAX

    # ------------------------------------------------------------ Steuerung
    def start(self) -> "DiagSession":
        # Hält ein anderer Thread (Oberfläche, Protokolldatei) gerade den Python-Interpreter,
        # bekommt ihn der Diagnose-Thread spätestens nach 1 ms statt nach 5 ms zurück – bei
        # KW1281 wartet das Steuergerät nur wenige Dutzend Millisekunden auf das nächste Byte
        if sys.getswitchinterval() > 0.001:
            sys.setswitchinterval(0.001)
        self._laeuft = True
        self._thread.start()
        return self

    def schliessen(self, warten: float = 4.0) -> None:
        if not self._laeuft:
            return
        self._abbruch.set()
        self._q.put(None)
        self._thread.join(warten)
        self._laeuft = False

    def abbrechen(self) -> None:
        """Laufendes Neuverbinden oder eine Gruppensuche abbrechen."""
        self._abbruch.set()

    @property
    def fast_init(self) -> bool:
        return self._fast_init

    @fast_init.setter
    def fast_init(self, an: bool) -> None:
        """Beim Motor zuerst den Fast-Init probieren. Hat er einmal nicht geantwortet,
        die normale Reizung aber geklappt, lässt die Sitzung ihn danach weg – bis die
        Einstellung geändert wird."""
        if bool(an) != self._fast_init:
            self._fast_init_klappt.clear()
        self._fast_init = bool(an)

    @property
    def experte(self) -> bool:
        return self._experte

    @experte.setter
    def experte(self, an: bool) -> None:
        """Expertenmodus der Sitzung. Aus: kein Block, der etwas ändert, verlässt vagdiag
        (außer „Fehlerspeicher löschen“). An: nur die Expertenfunktionen, jede mit
        ihrer eigenen Freigabe."""
        if bool(an) != self._experte:
            log.warning(t("Expertenmodus %s"), t("an") if an else t("aus"))
        self._experte = bool(an)
        if self._proto is not None:
            self._proto.experte = self._experte

    def airbag_freigeben(self, an: bool = True) -> None:
        """Verbindungen zum Airbag-Steuergerät (Adresse 15) erlauben."""
        self.airbag_freigegeben = an

    @property
    def verbunden(self) -> bool:
        return bool(self._proto and self._proto.verbunden)

    @property
    def verbindung(self) -> Verbindung | None:
        return self._proto.verbindung if self.verbunden else None

    def ausfuehren(self, funktion: Callable, *args) -> Future:
        """Funktion im Arbeits-Thread ausführen."""
        future: Future = Future()
        self._q.put((future, funktion, args))
        return future

    # ------------------------------------------------------------ Aufträge
    def verbinden(self, adresse: int, bauds: Sequence[int] = (10400, 9600),
                  fast_init: bool | None = None) -> Future:
        """fast_init: None = Einstellung der Sitzung (self.fast_init) beibehalten."""
        self._abbruch.clear()
        if fast_init is not None:
            self.fast_init = fast_init
        return self.ausfuehren(self._verbinden, adresse, tuple(bauds))

    def trennen(self) -> Future:
        return self.ausfuehren(self._trennen)

    def fehler_lesen(self) -> Future:
        return self.ausfuehren(lambda: self._proto_pruefen().fehler_lesen())

    def fehler_loeschen(self, kennung: tuple | None = None) -> Future:
        """Fehlerspeicher löschen – mit `kennung` nur, wenn noch genau das Steuergerät
        verbunden ist, für das der Benutzer zugestimmt hat."""
        return self.ausfuehren(self._fehler_loeschen, kennung)

    def _fehler_loeschen(self, kennung: tuple | None):
        proto = self._proto_pruefen()
        if kennung is not None and (proto.verbindung is None
                                    or proto.verbindung.kennung != tuple(kennung)):
            jetzt = proto.verbindung.kennung if proto.verbindung is not None else ()
            raise expertenfunktionen.Nichts(t(
                "Inzwischen ist ein anderes Steuergerät verbunden ({jetzt} statt {vorher}) – "
                "nichts gelöscht.", jetzt=expertenfunktionen.kennung_text(jetzt),
                vorher=expertenfunktionen.kennung_text(tuple(kennung))))
        return proto.fehler_loeschen()

    def gruppe_lesen(self, gruppe: int, neu_verbinden: bool = False) -> Future:
        """Messwertgruppe lesen. Mit neu_verbinden=True wird nach einem
        Verbindungsabbruch automatisch neu verbunden und erneut gelesen
        (bis es klappt oder abbrechen() aufgerufen wird)."""
        return self.ausfuehren(self._gruppe_lesen, gruppe, neu_verbinden)

    def messung_starten(self) -> None:
        """Vor einer neuen Messreihe: einen früheren Abbruch vergessen."""
        self._abbruch.clear()

    def gruppen_suchen(self, von: int = 0, bis: int = 255) -> Future:
        """Alle Gruppen von–bis lesen (nur lesen), Gruppe 000 eingeschlossen – bei KWP2000
        gibt es sie nicht, dann fehlt sie einfach im Ergebnis."""
        self._abbruch.clear()
        return self.ausfuehren(self._gruppen_suchen, von, bis)

    def anpassung_lesen(self, kanal: int) -> Future:
        """Einen Anpassungskanal lesen (nur lesen, Kanal 00 nie)."""
        return self.ausfuehren(
            lambda: self._wiederholt(lambda: self._proto_pruefen().anpassung_lesen(kanal)))

    def anpassungen_suchen(self, von: int = 1, bis: int = 99) -> Future:
        self._abbruch.clear()
        return self.ausfuehren(self._anpassungen_suchen, von, bis)

    def fahrt_starten(self, plan: FahrtPlan | None = None, ordner=None,
                      sim: bool = False) -> Future:
        """Fahrtenschreiber starten. Läuft, bis fahrt_beenden() (mit
        Abschlussprüfung) oder abbrechen() (sofort) aufgerufen wird.
        Ergebnis: Zusammenfassung."""
        self._abbruch.clear()
        self._fahrt_ende.clear()
        while not self._fahrt_marken.empty():
            self._fahrt_marken.get_nowait()
        return self.ausfuehren(self._fahrt, plan or FahrtPlan(), ordner, sim)

    def fahrt_beenden(self) -> None:
        """Fahrt beenden – die Abschlussprüfung läuft noch."""
        self._fahrt_ende.set()

    def fahrt_ereignis(self, text: str = "Markierung") -> None:
        """Markierung setzen; der Fehlerspeicher des Motors wird sofort gelesen, der des
        ABS beim nächsten Halt (siehe fahrtenschreiber.py)."""
        self._fahrt_marken.put((time.time(), text))

    def _fahrt(self, plan: FahrtPlan, ordner, sim: bool) -> Zusammenfassung:
        self.fahrt_laeuft = True
        try:
            schreiber = Fahrtenschreiber(self, plan, ordner, sim, self._fahrt_marken,
                                         self._fahrt_ende)
            return schreiber.ausfuehren()
        finally:
            self.fahrt_laeuft = False

    def scannen(self, adressen_: Sequence[int] | None = None, mit_fehlern: bool = True,
                mit_airbag: bool = False, bauds: Sequence[int] = (10400, 9600)) -> Future:
        """Alle Adressen nacheinander abfragen: Kennung und (auf Wunsch) Fehlerspeicher.
        Der Airbag (15) nur mit mit_airbag und Freigabe. Ergebnis: Liste von ScanEintrag."""
        self._abbruch.clear()
        liste = tuple(adressen_ if adressen_ is not None else adressen.ADRESSEN)
        return self.ausfuehren(self._scannen, liste, mit_fehlern, mit_airbag, tuple(bauds))

    # Expertenmodus (siehe experte.py) – jede Funktion prüft selbst, ob sie darf
    def drosselklappe_pruefen(self, gruppe: int) -> Future:
        return self.ausfuehren(expertenfunktionen.drosselklappe_pruefen, self, gruppe)

    def drosselklappe_anlernen(self, gruppe: int, dauer: float = expertenfunktionen.DAUER,
                               ohne_pruefung_ok: bool = False,
                               kennung: tuple | None = None) -> Future:
        self._abbruch.clear()
        return self.ausfuehren(lambda: expertenfunktionen.drosselklappe_anlernen(
            self, gruppe, dauer, self._melden, ohne_pruefung_ok, kennung))

    def service_lesen(self) -> Future:
        return self.ausfuehren(expertenfunktionen.service_lesen, self)

    def service_zuruecksetzen(self, erwartet: int, ordner=None,
                              kennung: tuple | None = None) -> Future:
        return self.ausfuehren(expertenfunktionen.service_zuruecksetzen, self, erwartet, ordner,
                               kennung)

    def stellglied_pruefen(self) -> Future:
        """Nur lesen: Darf das geöffnete Steuergerät? Beim Motor: steht er?"""
        return self.ausfuehren(expertenfunktionen.stellglied_pruefen, self)

    def stellglieddiagnose(self, ohne_pruefung_ok: bool = False,
                           kennung: tuple | None = None,
                           gefahr_bestaetigt: str | None = None) -> Future:
        """Stellglieddiagnose am geöffneten Steuergerät (mit `kennung` nur an genau diesem).
        Läuft, bis das Steuergerät „Ende“ meldet, stellglied_beenden() oder abbrechen()
        kommt; weiter mit stellglied_weiter(). Ergebnis: experte.StellgliedErgebnis.
        gefahr_bestaetigt: bei Bremsen, Airbag usw. die Art der bestätigten Warnung."""
        self._abbruch.clear()
        while not self._stellglied_befehle.empty():
            self._stellglied_befehle.get_nowait()
        return self.ausfuehren(lambda: expertenfunktionen.stellglieddiagnose(
            self, self._stellglied_befehle, self._melden, ohne_pruefung_ok,
            self.stellglied_schritt_max, kennung, gefahr_bestaetigt))

    def stellglied_weiter(self) -> None:
        self._stellglied_befehle.put("weiter")

    def stellglied_beenden(self) -> None:
        self._stellglied_befehle.put("ende")

    def sim_motor_aus(self, an: bool) -> Future:
        """Nur Simulator: Motor aus (Zündung an) bzw. wieder an."""
        def setzen():
            self._port_oeffnen()
            fahrzeug = getattr(self._port, "fahrzeug", None)
            if fahrzeug is not None:
                fahrzeug.motor_aus = bool(an)
        return self.ausfuehren(setzen)

    def kilometerstand(self) -> Future:
        """Kilometerstand aus dem Kombi: Gruppe 002, sonst Anpassungskanal 09."""
        return self.ausfuehren(lambda: km_lesen.lesen(self._proto_pruefen()))

    def kabeltest(self) -> Future:
        return self.ausfuehren(self._kabeltest)

    def obd2_test(self, fast_init: bool = True) -> Future:
        """OBD-II-Test an Adresse 33 (nur lesen): beendet eine offene Verbindung, prüft
        Protokoll, unterstützte Werte, Readiness und FIN. Ergebnis: obd2.Obd2Ergebnis."""
        self._abbruch.clear()
        return self.ausfuehren(self._obd2_test, fast_init)

    # ------------------------------------------------------------ im Thread
    def _melden(self, art: str, daten: object) -> None:
        """Ereignis weitergeben – ein Fehler im Empfänger darf die
        Diagnose nicht stören."""
        try:
            self._ereignis(art, daten)
        except Exception:
            log.exception(t("Fehler beim Verarbeiten des Ereignisses %s"), art)

    def _proto_pruefen(self) -> KW1281:
        if not self.verbunden:
            raise NotConnected(t("Keine Verbindung zum Steuergerät"))
        return self._proto

    def _wiederholt(self, funktion: Callable, versuche: int = 3):
        """Passt eine Antwort nicht zur Anfrage (Stoerung), neu anfragen.
        Bleibt es dabei, gilt ein unbekannter Antworttyp als „nicht
        auswertbar“, alles andere als Leitungsproblem (→ neu verbinden)."""
        for versuch in range(1, versuche + 1):
            try:
                return funktion()
            except Stoerung as exc:
                if versuch < versuche:
                    log.warning(t("%s – frage erneut"), exc)
                    continue
                if exc.art == "titel":
                    raise NotAvailable(str(exc)) from exc
                if self._proto is not None:
                    self._proto.verloren()
                raise ProtocolError(t("{fehler} (dreimal hintereinander)", fehler=exc)) from exc

    def _port_oeffnen(self) -> None:
        if self._port is None:
            self._port = self._port_fabrik()
            self._kline = KLine(self._port)
            self._proto = KW1281(self._kline, self.timing)
            self._proto.experte = self._experte

    def _bauds_ordnen(self, adresse: int, bauds: tuple[int, ...]) -> tuple[int, ...]:
        gemerkt = self.baudraten.get(adresse)
        if gemerkt in bauds and len(bauds) > 1:
            return (gemerkt,) + tuple(b for b in bauds if b != gemerkt)
        return bauds

    def _warten(self, sekunden: float) -> None:
        if self._abbruch.wait(max(0.0, sekunden)):
            raise Abgebrochen(t("Abgebrochen"))

    def _verbinden(self, adresse: int, bauds: tuple[int, ...]) -> Verbindung:
        if adresse == airbag.ADRESSE and not self.airbag_freigegeben:
            raise airbag.AirbagGesperrt(airbag.gesperrt_text())
        self._port_oeffnen()
        if self._proto.verbunden:
            self._trennen()   # bewusster Wechsel: meldet „Verbindung beendet“
        rest = self._pause_vor_reizung(adresse)
        if rest > 0:
            if rest > 0.6:
                log.info(t("Warte %.1f s, bis das Steuergerät wieder bereit ist"), rest)
            self._warten(rest)
        self._letzte_adresse, self._letzte_bauds = adresse, bauds
        # Airbag-Prüfung bei jeder Verbindung: Hat eine Störung die Reizung verfälscht, kann
        # sich unter einer anderen Adresse der Airbag melden
        def pruefung(v: Verbindung) -> None:
            airbag.pruefen(adresse, v.teilenummer, v.bauteil)
        fast_init = self.fast_init and self._fast_init_klappt.get(adresse, True)
        try:
            verbindung = self._proto.connect(adresse, self._bauds_ordnen(adresse, bauds),
                                             fast_init=fast_init, pruefung=pruefung)
        except airbag.AirbagRisiko as exc:
            # gleich nach der Kennung sauber beendet – kein weiterer Block an dieses Gerät
            self._getrennt_um = time.monotonic()
            log.warning("%s", exc)
            raise
        except DiagError as exc:
            self._verloren_um = time.monotonic()
            self._verloren_adresse = adresse
            log.info(t("Keine Verbindung zu %02X: %s"), adresse, exc)
            raise
        if fast_init and adresse == FAST_INIT_ADRESSE:
            klappt = bool(getattr(verbindung, "fast_init", False))
            self._fast_init_klappt[adresse] = klappt
            if not klappt:
                log.info(t("Fast-Init ohne Antwort, die normale Reizung klappt – in dieser "
                           "Sitzung nur noch die normale Reizung"))
        if self.baudraten.get(adresse) != verbindung.baud:
            self.baudraten[adresse] = verbindung.baud
            self._melden("baud", (adresse, verbindung.baud))
        self._melden("verbunden", verbindung)
        return verbindung

    def _pause_vor_reizung(self, adresse: int) -> float:
        """Sekunden, die vor der Reizung von `adresse` noch zu warten sind.

        - Nach dem Trennen kurz Ruhe auf der Leitung (trenn_pause).
        - Hat ein Steuergerät gerade nicht geantwortet oder die Verbindung verloren, braucht
          es selbst Zeit, bis es wieder reizbar ist (reconnect_pause); ein anderes nur eine
          kurze Ruhe der Leitung (wechsel_pause).
        - Endete eine Sitzung ohne Ende (Abbruch, Störung), hört ihr Steuergerät womöglich
          noch zu. KW1281-Blöcke tragen keine Adresse – es könnte Blöcke für das nächste
          Steuergerät als seine eigenen nehmen. Ein anderes deshalb erst reizen, wenn die
          alte Sitzung sicher vorbei ist (KW1281: reconnect_pause, KWP2000: P3 max + 0,5 s);
          dasselbe ebenso, außer beim eiligen Neuverbinden während einer Messung."""
        frei_ab = self._getrennt_um + self.timing.trenn_pause
        pause = self.timing.reconnect_pause
        if self._verloren_adresse is not None and adresse != self._verloren_adresse:
            pause = min(pause, self.timing.wechsel_pause)
        frei_ab = max(frei_ab, self._verloren_um + pause)
        p = self._proto
        if p is not None and p.verloren_adresse is not None and (
                adresse != p.verloren_adresse or not self._eilig):
            ruhe = (self.timing.kwp_p3_max + 0.5 if p.verloren_kwp2000
                    else self.timing.reconnect_pause)
            frei_ab = max(frei_ab, p.verloren_um + ruhe)
        return frei_ab - time.monotonic()

    def _neu_verbinden(self) -> None:
        """Nach einem Abbruch so lange neu verbinden, bis es klappt oder
        abgebrochen wird."""
        versuch = 0
        self._warten(1.0)   # dem Steuergerät Zeit geben, die alte Sitzung zu beenden
        while True:
            versuch += 1
            self._melden("neu_verbinden", versuch)
            log.info(t("Neuverbindung, Versuch %d"), versuch)
            try:
                # Pause nach dem Abbruch kurz halten: beim Anlassen zählt jede Sekunde
                # (dasselbe Steuergerät – ein anderes wartet trotzdem, bis die alte Sitzung
                # sicher vorbei ist, siehe _pause_vor_reizung)
                self._verloren_um = time.monotonic() - self.timing.reconnect_pause + 0.2
                self._verloren_adresse = self._letzte_adresse
                self._eilig = True
                try:
                    self._verbinden(self._letzte_adresse, self._letzte_bauds)
                finally:
                    self._eilig = False
                return
            except Abgebrochen:
                raise
            except (DiagError, KLineError, PortError) as exc:
                log.info(t("Neuverbindung fehlgeschlagen: %s"), exc)
                self._warten(0.5)

    def _gruppe_lesen(self, gruppe: int, neu_verbinden: bool):
        while True:
            try:
                if not self.verbunden and neu_verbinden and self._letzte_adresse is not None:
                    if self._abbruch.is_set():
                        raise Abgebrochen(t("Abgebrochen"))
                    self._neu_verbinden()
                return self._wiederholt(lambda: self._proto_pruefen().gruppe_lesen(gruppe))
            except (Nak, NotAvailable, Abgebrochen):
                raise
            except (ProtocolError, NotConnected, KLineError) as exc:
                if not neu_verbinden or self._letzte_adresse is None:
                    raise
                if self.verbunden:
                    raise   # anderer Fehler bei bestehender Verbindung
                self._verloren(exc, neu=True)

    def _gruppen_suchen(self, von: int, bis: int) -> dict[int, list]:
        gefunden = {}
        for gruppe in range(von, bis + 1):
            if self._abbruch.is_set():
                log.info(t("Gruppensuche abgebrochen bei %03d"), gruppe)
                break
            try:
                werte = self._wiederholt(lambda: self._proto_pruefen().gruppe_lesen(gruppe))
            except (Nak, NotAvailable):
                self._melden("suche", (gruppe, None))
                continue
            gefunden[gruppe] = werte
            log.info(t("Gruppe %03d: %s"), gruppe, " | ".join(w.text for w in werte))
            self._melden("suche", (gruppe, werte))
        return gefunden

    def _anpassungen_suchen(self, von: int, bis: int) -> dict[int, Anpassung]:
        self._proto_pruefen()
        gefunden = {}
        for kanal in range(max(1, von), min(255, bis) + 1):   # nie Kanal 00
            if self._abbruch.is_set():
                log.info(t("Kanalsuche abgebrochen bei %02d"), kanal)
                break
            try:
                anpassung = self._wiederholt(
                    lambda: self._proto_pruefen().anpassung_lesen(kanal))
            except (Nak, NotAvailable):
                self._melden("anpassung_suche", (kanal, None))
                continue
            gefunden[kanal] = anpassung
            self._melden("anpassung_suche", (kanal, anpassung))
        return gefunden

    def _scannen(self, liste: tuple[int, ...], mit_fehlern: bool, mit_airbag: bool,
                 bauds: tuple[int, ...] = (10400, 9600)) -> list[ScanEintrag]:
        self._trennen()
        ergebnis: list[ScanEintrag] = []
        for i, adresse in enumerate(liste):
            if self._abbruch.is_set():
                log.info(t("Scan abgebrochen vor %02X"), adresse)
                break
            self._melden("scan", {"index": i, "anzahl": len(liste), "adresse": adresse,
                                  "eintrag": None})
            eintrag = ScanEintrag(adresse)
            if adresse in adressen.UEBERSPRINGEN:
                eintrag.status = "uebersprungen"
                eintrag.meldung = t(adressen.UEBERSPRINGEN[adresse])
            elif adresse == airbag.ADRESSE and not (mit_airbag and self.airbag_freigegeben):
                eintrag.status = "gesperrt"
            else:
                try:
                    eintrag.verbindung = self._verbinden(adresse, bauds)
                    eintrag.status = "gefunden"
                    if mit_fehlern:
                        try:
                            eintrag.fehler = self._wiederholt(
                                lambda: self._proto_pruefen().fehler_lesen())
                        except (Nak, NotAvailable) as exc:
                            eintrag.meldung = str(exc)
                except NoResponse:
                    eintrag.status = "keine_antwort"
                except airbag.AirbagRisiko as exc:
                    eintrag.status = "getrennt"
                    eintrag.meldung = str(exc)
                except Abgebrochen:
                    break
                except (DiagError, KLineError, PortError) as exc:
                    if isinstance(exc, PortError):
                        raise          # ohne Kabel hat der Rest keinen Sinn
                    eintrag.status = "fehler" if eintrag.verbindung is None else "gefunden"
                    eintrag.meldung = str(exc)
                finally:
                    try:
                        self._trennen()
                    except (DiagError, KLineError, PortError) as exc:
                        log.debug(t("Trennen: %s"), exc)
            ergebnis.append(eintrag)
            self._melden("scan", {"index": i, "anzahl": len(liste), "adresse": adresse,
                                  "eintrag": eintrag})
        return ergebnis

    def _trennen(self) -> None:
        if self._proto and self._proto.verbunden:
            self._proto.trennen()
            self._getrennt_um = time.monotonic()
            self._melden("getrennt", {"grund": t("Verbindung beendet"), "neu_verbinden": False})

    def _obd2_test(self, fast_init: bool) -> obd2.Obd2Ergebnis:
        self._port_oeffnen()
        self._trennen()
        rest = self._pause_vor_reizung(obd2.ADRESSE)
        if rest > 0:
            if rest > 0.6:
                log.info(t("Warte %.1f s, bis das Steuergerät wieder bereit ist"), rest)
            self._warten(rest)
        pruefer = obd2.Obd2(self._kline, self.timing)
        try:
            return pruefer.test(fast_init, sim=bool(getattr(self._port, "simulator", False)))
        except (KLineError, PortError) as exc:
            raise ProtocolError(t("OBD-II-Test abgebrochen: {fehler}", fehler=exc)) from exc
        finally:
            self._getrennt_um = time.monotonic()
            if pruefer.offen:
                # Das Steuergerät hält seine OBD-Sitzung noch bis zu 5 s – ein anderes erst
                # danach reizen (siehe _pause_vor_reizung)
                self._proto.verloren(obd2.ADRESSE, kwp2000=True)

    def _kabeltest(self) -> dict:
        self._port_oeffnen()
        if self._proto.verbunden:
            return {"geraet": self._port.description, "echo": self._kline.echo,
                    "hinweis": t("Verbindung zum Steuergerät besteht, Kabel funktioniert.")}
        # Ein einzelnes Byte senden. Mit 12 V an OBD-Pin 16 kommt es als Echo
        # zurück; Steuergeräte ignorieren es (sie reagieren nur auf die Reizung).
        self._kline.discard_input()
        self._port.write(b"\x55")
        echo = self._port.read(8, 0.1)
        hat_echo = b"\x55" in echo
        return {
            "geraet": self._port.description,
            "echo": hat_echo,
            "hinweis": (t("Echo empfangen – Kabel hat Strom und hört die K-Leitung.")
                        if hat_echo else
                        t("Kein Echo – normal ohne 12 V an OBD-Pin 16 (Kabel nicht im Auto). Im "
                          "Auto mit Zündung an: Kabelproblem oder ein Kabel ohne Echo.")),
        }

    def _verloren(self, grund: Exception, neu: bool = False) -> None:
        self._verloren_um = time.monotonic()
        self._verloren_adresse = self._letzte_adresse
        log.warning(t("Verbindung verloren: %s"), grund)
        self._melden("getrennt", {"grund": str(grund), "neu_verbinden": neu})

    def _lauf(self) -> None:
        while True:
            try:
                auftrag = self._q.get(timeout=self.keepalive)
            except queue.Empty:
                if self.verbunden:
                    try:
                        self._proto.keep_alive()
                    except (DiagError, KLineError, PortError) as exc:
                        self._verloren(exc)
                continue
            if auftrag is None:
                break
            future, funktion, args = auftrag
            if not future.set_running_or_notify_cancel():
                continue
            war_verbunden = self.verbunden
            beginn = time.monotonic()
            try:
                ergebnis = funktion(*args)
            except BaseException as exc:  # an die Oberfläche weiterreichen
                future.set_exception(exc)
                # „verloren“ nur, wenn die Verbindung nicht absichtlich beendet
                # wurde (z. B. beim Wechsel zu einem anderen Steuergerät, das
                # dann nicht antwortet)
                if war_verbunden and not self.verbunden and self._getrennt_um < beginn:
                    self._verloren(exc)
            else:
                future.set_result(ergebnis)
        # Aufräumen
        try:
            if self._proto and self._proto.verbunden:
                self._proto.trennen()
        finally:
            if self._port is not None:
                self._port.close()

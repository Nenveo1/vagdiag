"""Diagnose-Sitzung in einem eigenen Thread.

Alle Zugriffe auf das Kabel laufen nacheinander in einem Arbeits-Thread. Ist
gerade nichts zu tun, hält er die Verbindung mit ACK-Blöcken am Leben – sonst
legt das Steuergerät nach gut einer Sekunde auf. Die Oberfläche bekommt
Ergebnisse als concurrent.futures.Future.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import Future
from typing import Callable, Sequence

from .kline import KLine, KLineError
from .kw1281 import KW1281, DiagError, NotConnected, Timing, Verbindung
from .port import PortError, RawPort

log = logging.getLogger("vagdiag.proto")

Ereignis = Callable[[str, object], None]


class DiagSession:
    def __init__(self, port_fabrik: Callable[[], RawPort], timing: Timing | None = None,
                 keepalive: float = 0.5, ereignis: Ereignis | None = None):
        self._port_fabrik = port_fabrik
        self.timing = timing or Timing()
        self.keepalive = keepalive
        self._ereignis = ereignis or (lambda art, daten: None)
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._lauf, name="diag", daemon=True)
        self._port: RawPort | None = None
        self._kline: KLine | None = None
        self._proto: KW1281 | None = None
        self._verloren_um = -1e9
        self._getrennt_um = -1e9
        self._laeuft = False

    # ------------------------------------------------------------ Steuerung
    def start(self) -> "DiagSession":
        self._laeuft = True
        self._thread.start()
        return self

    def schliessen(self, warten: float = 3.0) -> None:
        if not self._laeuft:
            return
        self._q.put(None)
        self._thread.join(warten)
        self._laeuft = False

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
    def verbinden(self, adresse: int, bauds: Sequence[int] = (10400, 9600)) -> Future:
        return self.ausfuehren(self._verbinden, adresse, tuple(bauds))

    def trennen(self) -> Future:
        return self.ausfuehren(self._trennen)

    def fehler_lesen(self) -> Future:
        return self.ausfuehren(lambda: self._proto_pruefen().fehler_lesen())

    def fehler_loeschen(self) -> Future:
        return self.ausfuehren(lambda: self._proto_pruefen().fehler_loeschen())

    def gruppe_lesen(self, gruppe: int) -> Future:
        return self.ausfuehren(lambda: self._proto_pruefen().gruppe_lesen(gruppe))

    def kabeltest(self) -> Future:
        return self.ausfuehren(self._kabeltest)

    # ------------------------------------------------------------ im Thread
    def _proto_pruefen(self) -> KW1281:
        if not self.verbunden:
            raise NotConnected("Keine Verbindung zum Steuergerät")
        return self._proto

    def _port_oeffnen(self) -> None:
        if self._port is None:
            self._port = self._port_fabrik()
            self._kline = KLine(self._port)
            self._proto = KW1281(self._kline, self.timing)

    def _verbinden(self, adresse: int, bauds: tuple[int, ...]) -> Verbindung:
        self._port_oeffnen()
        if self._proto.verbunden:
            self._proto.trennen()
            self._getrennt_um = time.monotonic()
        rest = max(self._verloren_um + self.timing.reconnect_pause,
                   self._getrennt_um + 0.5) - time.monotonic()
        if rest > 0:
            if rest > 0.6:
                log.info("Warte %.1f s, bis das Steuergerät wieder bereit ist", rest)
            time.sleep(rest)
        try:
            verbindung = self._proto.connect(adresse, bauds)
        except DiagError:
            self._verloren_um = time.monotonic()
            raise
        self._ereignis("verbunden", verbindung)
        return verbindung

    def _trennen(self) -> None:
        if self._proto and self._proto.verbunden:
            self._proto.trennen()
            self._getrennt_um = time.monotonic()
            self._ereignis("getrennt", "Verbindung beendet")

    def _kabeltest(self) -> dict:
        self._port_oeffnen()
        if self._proto.verbunden:
            return {"geraet": self._port.description, "echo": self._kline.echo,
                    "hinweis": "Verbindung zum Steuergerät besteht, Kabel funktioniert."}
        # Ein einzelnes Byte senden. Mit 12 V an OBD-Pin 16 kommt es als Echo
        # zurück; Steuergeräte ignorieren es (sie reagieren nur auf die Reizung).
        self._kline.discard_input()
        self._port.write(b"\x55")
        echo = self._port.read(8, 0.1)
        hat_echo = b"\x55" in echo
        return {
            "geraet": self._port.description,
            "echo": hat_echo,
            "hinweis": ("Echo empfangen – Kabel hat Strom und hört die K-Leitung."
                        if hat_echo else
                        "Kein Echo. Ohne 12 V an OBD-Pin 16 ist das normal "
                        "(Kabel nicht im Auto). Im Auto mit Zündung an deutet es "
                        "auf ein Kabelproblem hin – oder auf ein Kabel ohne Echo."),
        }

    def _verloren(self, grund: Exception) -> None:
        self._verloren_um = time.monotonic()
        log.warning("Verbindung verloren: %s", grund)
        self._ereignis("getrennt", str(grund))

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
            try:
                ergebnis = funktion(*args)
            except BaseException as exc:  # an die Oberfläche weiterreichen
                future.set_exception(exc)
                if war_verbunden and not self.verbunden:
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

"""Byte-Ebene der K-Leitung: Echo des KKL-Kabels und Protokollierung.

Ein KKL-Kabel hört auf der Eindraht-K-Leitung jedes selbst gesendete Byte
wieder mit (Echo). Ob das eigene Kabel das tut, wird beim ersten gesendeten
Byte automatisch erkannt.
"""

from __future__ import annotations

import logging
import time

from .port import RawPort
from .sprache import t

log = logging.getLogger("vagdiag.proto")
wire = logging.getLogger("vagdiag.bytes")

# Dauert ein Lesen am Kabel mindestens so lange, hat vagdiag auf das Byte gewartet (es kam
# erst währenddessen); schneller zurück heißt: es lag schon im Puffer
WARTEN_AB = 0.0015


class KLineError(Exception):
    """Fehler auf der Leitung – die laufende Verbindung ist damit verloren."""


class Timeout(KLineError):
    pass


class EchoError(KLineError):
    pass


class KLine:
    def __init__(self, port: RawPort, echo: bool | None = None,
                 echo_timeout: float = 0.05):
        self.port = port
        self.echo = echo          # None = noch nicht erkannt
        self.echo_timeout = echo_timeout
        self._rx = bytearray()
        # Zum zuletzt gelesenen Byte (für den Zeitwächter in kw1281.py), gemessen direkt am
        # Kabel – vor dem Protokollieren: frisch = vagdiag musste darauf warten, ankunft =
        # wann das Kabel es geliefert hat. Nicht frisch: Es lag schon da, womöglich lange.
        self.frisch = False
        self.ankunft = 0.0
        self._chunk_frisch = False
        self._chunk_ankunft = 0.0
        # Wann das zuletzt gesendete Byte ans Kabel ging – direkt danach gemessen, vor dem
        # Protokollieren und dem Warten auf das Echo (das Byte ist dann schon unterwegs)
        self.gesendet = 0.0

    # -- Einstellungen ----------------------------------------------------
    def set_baudrate(self, baud: int) -> None:
        self.port.set_baudrate(baud)

    def send_5baud(self, address: int) -> None:
        self._rx.clear()
        wire.debug(t("5-Baud-Reizung Adresse %02X"), address)
        self.port.send_5baud(address)

    def discard_input(self) -> None:
        self._rx.clear()
        self.port.purge_rx()

    def fast_init_puls(self) -> None:
        """Weckmuster für den KWP2000-Fast-Init (siehe RawPort.fast_init_puls)."""
        self._rx.clear()
        wire.debug(t("Fast-Init: 25 ms Low, 25 ms High"))
        self.port.fast_init_puls()

    # -- Lesen ------------------------------------------------------------
    def _next_byte(self, timeout: float) -> int:
        erstes = False
        if not self._rx:
            beginn = time.perf_counter()
            data = self.port.read(64, timeout)
            ende = time.perf_counter()
            if not data:
                raise Timeout(t("Keine Daten innerhalb {ms:.0f} ms", ms=timeout * 1000))
            self._rx.extend(data)
            # Musste der Aufruf warten, kam das erste Byte erst währenddessen an
            self._chunk_frisch = ende - beginn >= WARTEN_AB
            self._chunk_ankunft = ende
            erstes = True
        self.frisch = erstes and self._chunk_frisch
        self.ankunft = self._chunk_ankunft
        return self._rx.pop(0)

    def read_byte(self, timeout: float) -> int:
        byte = self._next_byte(timeout)
        wire.debug("RX %02X", byte)
        return byte

    # -- Schreiben --------------------------------------------------------
    def write_raw(self, data: bytes) -> None:
        """Mehrere Bytes am Stück senden, ohne einzeln auf das Echo zu warten
        (StartCommunication direkt nach dem Fast-Init). Das Echo bleibt im Empfang."""
        self.port.write(bytes(data))
        self.gesendet = time.perf_counter()
        for byte in data:
            wire.debug("TX %02X", byte)

    def write_byte(self, byte: int) -> None:
        self.port.write(bytes([byte]))
        self.gesendet = time.perf_counter()
        wire.debug("TX %02X", byte)
        if self.echo is False:
            return
        try:
            echo = self._next_byte(self.echo_timeout)
        except Timeout:
            if self.echo is None:
                self.echo = False
                log.info(t("Kabel liefert kein Echo"))
                return
            raise EchoError(t("Echo auf {byte:02X} fehlt – Kabel getrennt?", byte=byte)) from None
        if echo == byte:
            if self.echo is None:
                self.echo = True
                log.info(t("Kabel liefert Echo (normal bei KKL-Kabeln)"))
            return
        if self.echo is None:
            # Kein Echo – das Byte ist schon die Antwort des Steuergeräts.
            self.echo = False
            self._rx.insert(0, echo)
            log.info(t("Kabel liefert kein Echo"))
            return
        if echo == byte ^ 0xFF:
            # Das Echo ging verloren, das Komplement des Steuergeräts ist schon da:
            # zurücklegen, damit es als Antwort gelesen werden kann.
            self._rx.insert(0, echo)
            raise EchoError(t("Echo auf {byte:02X} fehlt – Kabel getrennt?", byte=byte))
        raise EchoError(t("Echo {echo:02X} statt {byte:02X} – Störung auf der K-Leitung?",
                          echo=echo, byte=byte))

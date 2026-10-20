"""Byte-Ebene der K-Leitung: Echo des KKL-Kabels und Protokollierung.

Ein KKL-Kabel hört auf der Eindraht-K-Leitung jedes selbst gesendete Byte
wieder mit (Echo). Ob das eigene Kabel das tut, wird beim ersten gesendeten
Byte automatisch erkannt.
"""

from __future__ import annotations

import logging

from .port import RawPort

log = logging.getLogger("vagdiag.proto")
wire = logging.getLogger("vagdiag.bytes")


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

    # -- Einstellungen ----------------------------------------------------
    def set_baudrate(self, baud: int) -> None:
        self.port.set_baudrate(baud)

    def send_5baud(self, address: int) -> None:
        self._rx.clear()
        wire.debug("5-Baud-Reizung Adresse %02X", address)
        self.port.send_5baud(address)

    def discard_input(self) -> None:
        self._rx.clear()
        self.port.purge_rx()

    # -- Lesen ------------------------------------------------------------
    def _next_byte(self, timeout: float) -> int:
        if not self._rx:
            data = self.port.read(64, timeout)
            if not data:
                raise Timeout(f"Keine Daten innerhalb {timeout * 1000:.0f} ms")
            self._rx.extend(data)
        return self._rx.pop(0)

    def read_byte(self, timeout: float) -> int:
        byte = self._next_byte(timeout)
        wire.debug("RX %02X", byte)
        return byte

    # -- Schreiben --------------------------------------------------------
    def write_byte(self, byte: int) -> None:
        self.port.write(bytes([byte]))
        wire.debug("TX %02X", byte)
        if self.echo is False:
            return
        try:
            echo = self._next_byte(self.echo_timeout)
        except Timeout:
            if self.echo is None:
                self.echo = False
                log.info("Kabel liefert kein Echo")
                return
            raise EchoError(f"Echo auf {byte:02X} fehlt – Kabel getrennt?") from None
        if echo == byte:
            if self.echo is None:
                self.echo = True
                log.info("Kabel liefert Echo (normal bei KKL-Kabeln)")
            return
        if self.echo is None:
            # Kein Echo – das Byte ist schon die Antwort des Steuergeräts.
            self.echo = False
            self._rx.insert(0, echo)
            log.info("Kabel liefert kein Echo")
            return
        raise EchoError(f"Echo {echo:02X} statt {byte:02X} – Störung auf der K-Leitung?")

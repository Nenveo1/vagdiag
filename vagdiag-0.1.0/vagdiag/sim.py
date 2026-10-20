"""Simulierte Steuergeräte auf Byte-Ebene.

Der Simulator spielt das KW1281-Protokoll Byte für Byte mit (inklusive
Komplement-Handshake und auf Wunsch Kabel-Echo). So läuft der echte
Protokollcode – nur ohne Auto. Gut zum Ausprobieren der Oberfläche und für
die automatischen Tests.

Simuliert werden:
  01 Motorelektronik (10400 Baud) – Fehler, Gruppen 001, 002, 004
  17 Kombiinstrument (9600 Baud) – Gruppen 001, 002 (Kilometerstand)
  15 ein KWP2000-Gerät, um die Protokollerkennung zu zeigen
"""

from __future__ import annotations

import random
import time
from typing import Callable

from .port import RawPort

Gruppe = Callable[[], list[tuple[int, int, int]]]

ACK, NAK = 0x09, 0x0A


class SimEcu:
    def __init__(self, adresse: int, kennung: list[bytes], baud: int = 10400,
                 fehler: list[tuple[int, int]] | None = None,
                 gruppen: dict[int, Gruppe | None] | None = None,
                 keybytes: tuple[int, int] = (0x01, 0x8A)):
        self.adresse = adresse
        self.kennung = kennung
        self.baud = baud
        self.fehler = list(fehler or [])
        self.gruppen = gruppen or {}
        self.keybytes = keybytes
        self.geloescht = 0
        self.port: SimPort | None = None
        self._zustand = "aus"
        self._tx = b""
        self._pos = 0
        self._rx: list[int] = []
        self._zaehler = 0
        self._wartend: list[tuple[int, bytes]] = []

    # -- Verbindungsaufbau ------------------------------------------------
    def reizen(self, port: "SimPort") -> None:
        self.port = port
        self._zustand = "warte_kb2"
        port.ausgeben(bytes([0x55, *self.keybytes]))

    def byte_vom_tester(self, byte: int) -> None:
        z = self._zustand
        if z == "warte_kb2":
            if byte != self.keybytes[1] ^ 0xFF:
                self._zustand = "aus"
                return
            if (self.keybytes[1] & 0x7F) == 0x0F:  # KWP2000
                self.port.ausgeben(bytes([self.adresse ^ 0xFF]))
                self._zustand = "kwp2000"
                return
            self._zaehler = 0
            bloecke = [(0xF6, k) for k in self.kennung]
            self._wartend = bloecke[1:]
            self._starte_block(*bloecke[0])
        elif z == "senden":
            if byte != self._tx[self._pos] ^ 0xFF:
                self._zustand = "aus"
                return
            self._pos += 1
            self.port.ausgeben(self._tx[self._pos:self._pos + 1])
            if self._pos == len(self._tx) - 1:
                self._zustand = "empfangen"
                self._rx = []
        elif z == "empfangen":
            self._rx.append(byte)
            if len(self._rx) == self._rx[0] + 1:
                self._verarbeite(self._rx)
            else:
                self.port.ausgeben(bytes([byte ^ 0xFF]))

    # -- Blöcke -----------------------------------------------------------
    def _starte_block(self, titel: int, daten: bytes = b"") -> None:
        self._zaehler = (self._zaehler + 1) & 0xFF
        self._tx = bytes([len(daten) + 3, self._zaehler, titel]) + bytes(daten) + b"\x03"
        self._pos = 0
        self._zustand = "senden"
        self.port.ausgeben(self._tx[:1])

    def _verarbeite(self, roh: list[int]) -> None:
        self._zaehler = roh[1]
        titel, daten = roh[2], bytes(roh[3:-1])
        if titel == ACK:
            if self._wartend:
                self._starte_block(*self._wartend.pop(0))
            else:
                self._starte_block(ACK)
        elif titel == 0x07:
            bloecke = self._fehlerbloecke()
            self._wartend = bloecke[1:]
            self._starte_block(*bloecke[0])
        elif titel == 0x05:
            self.fehler.clear()
            self.geloescht += 1
            self._starte_block(ACK)
        elif titel == 0x29:
            gruppe = daten[0] if daten else 0
            if gruppe in self.gruppen and self.gruppen[gruppe] is None:
                self._zustand = "aus"  # simuliert ein verstummtes Steuergerät
                return
            funktion = self.gruppen.get(gruppe)
            if funktion is None:
                self._starte_block(ACK)
            else:
                werte = b"".join(bytes(t) for t in funktion())
                self._starte_block(0xE7, werte)
        elif titel == 0x06:
            self._zustand = "aus"
        else:
            self._starte_block(NAK)

    def _fehlerbloecke(self) -> list[tuple[int, bytes]]:
        if not self.fehler:
            return [(0xFC, b"\xff\xff\x88")]
        bloecke = []
        for i in range(0, len(self.fehler), 4):
            daten = b"".join(bytes([c >> 8, c & 0xFF, s]) for c, s in self.fehler[i:i + 4])
            bloecke.append((0xFC, daten))
        return bloecke


class SimPort(RawPort):
    """Virtuelle K-Leitung mit angeschlossenen simulierten Steuergeräten."""

    def __init__(self, steuergeraete: dict[int, SimEcu], echo: bool = True):
        self.steuergeraete = steuergeraete
        self.echo = echo
        self.baud = 10400
        self._rx = bytearray()
        self._aktiv: SimEcu | None = None
        self.description = "Simulator"

    def ausgeben(self, daten: bytes) -> None:
        self._rx.extend(daten)

    def set_baudrate(self, baud: int) -> int:
        self.baud = baud
        return baud

    def send_5baud(self, address: int) -> None:
        time.sleep(0.05)  # die echte Reizung dauert 2 s; hier nur angedeutet
        self._rx.clear()
        self._aktiv = None
        ecu = self.steuergeraete.get(address)
        if ecu is None:
            return
        if ecu.baud != self.baud:
            self._rx.extend(b"\xe6\x7f\xf5")  # falsche Baudrate: unlesbar
            ecu._zustand = "aus"
            return
        self._aktiv = ecu
        ecu.reizen(self)

    def write(self, data: bytes) -> None:
        for byte in data:
            if self.echo:
                self._rx.append(byte)
            if self._aktiv is not None:
                self._aktiv.byte_vom_tester(byte)

    def read(self, max_bytes: int, timeout: float) -> bytes:
        if not self._rx:
            time.sleep(min(timeout, 0.02))
            if not self._rx:
                return b""
        daten = bytes(self._rx[:max_bytes])
        del self._rx[:max_bytes]
        return daten

    def purge_rx(self) -> None:
        self._rx.clear()


# --------------------------------------------------------------------------
def _rauschen(wert: float, spanne: float) -> float:
    return wert + random.uniform(-spanne, spanne)


def _clamp(x: float) -> int:
    return max(0, min(255, int(round(x))))


def motor_steuergeraet() -> SimEcu:
    def drehzahl():
        return (1, 200, _clamp(_rauschen(820, 25) / 40))

    def gruppe_001():
        return [drehzahl(), (5, 10, _clamp(100 + _rauschen(90, 1))),
                (11, 100, _clamp(_rauschen(128, 3))), (16, 0xFF, 0b01100000)]

    def gruppe_002():
        return [drehzahl(), (2, 50, _clamp(_rauschen(230, 10))),
                (15, 10, _clamp(_rauschen(35, 2))), (25, 0, _clamp(_rauschen(2, 0.4)))]

    def gruppe_004():
        return [drehzahl(), (6, 100, _clamp(_rauschen(138, 1.5))),
                (5, 10, _clamp(100 + _rauschen(90, 1))), (5, 10, _clamp(100 + _rauschen(25, 1)))]

    return SimEcu(
        0x01,
        [b"SIM906032   ", b"1,4l R4 SIMULATION ", b"V01 ", b"\x00\x3e\x0a\x81\x00"],
        baud=10400,
        fehler=[(16486, 0x23 | 0x80), (16684, 0x23)],
        gruppen={1: gruppe_001, 2: gruppe_002, 4: gruppe_004},
    )


def kombi_steuergeraet() -> SimEcu:
    def gruppe_001():
        return [(7, 100, 0), (1, 200, _clamp(_rauschen(820, 25) / 40)),
                (19, 100, 31), (44, 14, 37)]

    def gruppe_002():
        return [(36, 73, 55), (5, 10, 190)]

    return SimEcu(
        0x17,
        [b"SIM920800   ", b"KOMBI SIMULATION   ", b"V02 "],
        baud=9600,
        fehler=[(771, 30 | 0x80)],
        gruppen={1: gruppe_001, 2: gruppe_002},
    )


def kwp2000_steuergeraet() -> SimEcu:
    return SimEcu(0x15, [b"SIM KWP2000 "], baud=10400, keybytes=(0xEF, 0x8F))


def sim_port(echo: bool = True) -> SimPort:
    geraete = [motor_steuergeraet(), kombi_steuergeraet(), kwp2000_steuergeraet()]
    return SimPort({g.adresse: g for g in geraete}, echo=echo)

"""Simulierte Steuergeräte auf Byte-Ebene.

Der Simulator spielt das KW1281-Protokoll Byte für Byte mit (inklusive
Komplement-Handshake und Kabel-Echo). So läuft der echte Protokollcode – nur
ohne Auto. Mit echtzeit=True verhält er sich zeitlich wie dein Polo: Reizung
gut 2 s, etwa 10 ms pro Byte, also rund 3 Messwertabfragen pro Sekunde.

Simuliert werden:
  01 Motorelektronik (10400 Baud) – Fehler, Gruppen 001, 002, 004
  17 Kombiinstrument (9600 Baud) – Gruppen 001, 002 (Kilometerstand wie bei
     deinem TRW-Kombi: FF FF = kein Wert)
  25 Wegfahrsperre (9600 Baud) – mit Zusatzkennung (Fahrgestellnr., Immo-ID)
  15 ein KWP2000-Gerät, um die Protokollerkennung zu zeigen
"""

from __future__ import annotations

import bisect
import itertools
import logging
import random
import time
from typing import Callable

from .port import RawPort

log = logging.getLogger("vagdiag.port")

Gruppe = Callable[[], list[tuple[int, int, int]]]

ACK, NAK = 0x09, 0x0A


class SimEcu:
    def __init__(self, adresse: int, kennung: list[bytes], baud: int = 10400,
                 fehler: list[tuple[int, int]] | None = None,
                 gruppen: dict[int, Gruppe | None] | None = None,
                 keybytes: tuple[int, int] = (0x01, 0x8A),
                 zusatzkennung: list[bytes] | None = None):
        self.adresse = adresse
        self.kennung = kennung
        self.baud = baud
        self.fehler = list(fehler or [])
        self.gruppen = gruppen or {}
        self.keybytes = keybytes
        self.zusatzkennung = zusatzkennung or []
        self.geloescht = 0
        self.port: SimPort | None = None
        self._zustand = "aus"
        self._tx = b""
        self._pos = 0
        self._rx: list[int] = []
        self._zaehler = 0
        self._wartend: list[tuple[int, bytes]] = []
        self._ausfall_in: int | None = None
        self._stoerung_in: int | None = None
        self._bloecke_empfangen = 0

    # -- Testhilfen -------------------------------------------------------
    def ausfall_nach(self, gruppenabfragen: int) -> None:
        """Nach n weiteren Gruppenabfragen einmal verstummen (wie beim Anlassen)."""
        self._ausfall_in = gruppenabfragen

    def stoerung_nach(self, bloecke: int) -> None:
        """Im n-ten folgenden Testerblock ein Komplement als 00 verfälschen."""
        self._stoerung_in = bloecke

    # -- Verbindungsaufbau ------------------------------------------------
    def reizen(self, port: "SimPort") -> None:
        self.port = port
        self._zustand = "warte_kb2"
        port.ausgeben(bytes([0x55, *self.keybytes]), pause=port.sync_pause)

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
            if len(self._rx) == 1:
                self._bloecke_empfangen += 1
            if len(self._rx) == self._rx[0] + 1:
                self._verarbeite(self._rx)
                return
            if (len(self._rx) == 2 and self._stoerung_in is not None):
                self._stoerung_in -= 1
                if self._stoerung_in <= 0:
                    self._stoerung_in = None
                    self.port.ausgeben(b"\x00")   # gestörtes Komplement
                    return
            self.port.ausgeben(bytes([byte ^ 0xFF]))

    # -- Blöcke -----------------------------------------------------------
    def _starte_block(self, titel: int, daten: bytes = b"") -> None:
        self._zaehler = (self._zaehler + 1) & 0xFF
        self._tx = bytes([len(daten) + 3, self._zaehler, titel]) + bytes(daten) + b"\x03"
        self._pos = 0
        self._zustand = "senden"
        self.port.ausgeben(self._tx[:1], pause=self.port.antwort_pause)

    def _verarbeite(self, roh: list[int]) -> None:
        self._zaehler = roh[1]
        titel, daten = roh[2], bytes(roh[3:-1])
        if titel == ACK:
            if self._wartend:
                self._starte_block(*self._wartend.pop(0))
            else:
                self._starte_block(ACK)
        elif titel == 0x00:   # Zusatzkennung
            if self.zusatzkennung:
                bloecke = [(0xF6, k) for k in self.zusatzkennung]
                self._wartend = bloecke[1:]
                self._starte_block(*bloecke[0])
            else:
                self._starte_block(NAK)
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
            if self._ausfall_in is not None:
                self._ausfall_in -= 1
                if self._ausfall_in < 0:
                    self._ausfall_in = None
                    self._zustand = "aus"   # verstummt einmal
                    return
            if gruppe in self.gruppen and self.gruppen[gruppe] is None:
                self._zustand = "aus"  # simuliert ein dauerhaft verstummtes Steuergerät
                return
            funktion = self.gruppen.get(gruppe)
            if funktion is None:
                self._starte_block(NAK, bytes([self._zaehler]))
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

    def __init__(self, steuergeraete: dict[int, SimEcu], echo: bool = True,
                 echtzeit: bool = False):
        self.steuergeraete = steuergeraete
        self.echo = echo
        self.echtzeit = echtzeit
        # Zeitverhalten wie beim echten Motorsteuergerät (aus deinem Log)
        self.byte_zeit = 0.010 if echtzeit else 0.0
        self.antwort_pause = 0.10 if echtzeit else 0.0
        self.sync_pause = 0.25 if echtzeit else 0.0
        self.reizung_dauer = 1.8 if echtzeit else 0.05
        self.baud = 10400
        self._rx: list[tuple[float, int, int]] = []
        self._nummer = itertools.count()
        self._frei_ab = 0.0
        self._aktiv: SimEcu | None = None
        self.description = "Simulator (keine echten Fahrzeugdaten)"

    def ausgeben(self, daten: bytes, pause: float = 0.0) -> None:
        t = max(time.monotonic(), self._frei_ab) + pause
        for byte in daten:
            t += self.byte_zeit
            bisect.insort(self._rx, (t, next(self._nummer), byte))
        self._frei_ab = t

    def set_baudrate(self, baud: int) -> int:
        self.baud = baud
        return baud

    def send_5baud(self, address: int) -> None:
        time.sleep(self.reizung_dauer)
        self._rx.clear()
        self._frei_ab = 0.0
        self._aktiv = None
        ecu = self.steuergeraete.get(address)
        if ecu is None:
            return
        if ecu.baud != self.baud:
            self.ausgeben(b"\xe6\x7f\xf5", pause=self.sync_pause)  # falsche Baudrate
            ecu._zustand = "aus"
            return
        self._aktiv = ecu
        ecu.reizen(self)

    def write(self, data: bytes) -> None:
        for byte in data:
            if self.echo:
                t = time.monotonic() + (0.001 if self.echtzeit else 0.0)
                bisect.insort(self._rx, (t, next(self._nummer), byte))
            if self._aktiv is not None:
                self._aktiv.byte_vom_tester(byte)

    def read(self, max_bytes: int, timeout: float) -> bytes:
        ende = time.monotonic() + timeout
        while True:
            jetzt = time.monotonic()
            daten = bytearray()
            while self._rx and self._rx[0][0] <= jetzt and len(daten) < max_bytes:
                daten.append(self._rx.pop(0)[2])
            if daten:
                return bytes(daten)
            if jetzt >= ende:
                return b""
            naechstes = self._rx[0][0] if self._rx else ende
            time.sleep(max(0.0, min(naechstes, ende) - jetzt))

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
        return [drehzahl(), (33, 133, _clamp(_rauschen(29, 2))),
                (15, 41, _clamp(_rauschen(14, 1))), (18, 250, _clamp(_rauschen(34, 2)))]

    def gruppe_002():
        return [drehzahl(), (5, 10, _clamp(100 + _rauschen(90, 1))),
                (20, 100, _clamp(_rauschen(128, 3))), (16, 0xFF, 0b10110010)]

    def gruppe_004():
        return [drehzahl(), (21, 100, _clamp(_rauschen(138, 1.5))),
                (5, 10, _clamp(100 + _rauschen(90, 1))), (5, 10, _clamp(100 + _rauschen(25, 1)))]

    return SimEcu(
        0x01,
        [b"SIM906032   ", b"ME7.5 SIMULATION    ", b"S001", b"\x00\x00\x3e\x30\x39"],
        baud=10400,
        fehler=[(16486, 0x23 | 0x80), (16684, 0x23)],
        gruppen={1: gruppe_001, 2: gruppe_002, 4: gruppe_004},
    )


def kombi_steuergeraet() -> SimEcu:
    def gruppe_001():
        jetzt = time.localtime()
        return [(7, 100, 0), (1, 200, _clamp(_rauschen(820, 25) / 40)),
                (37, 0, 30), (44, jetzt.tm_hour, jetzt.tm_min)]

    def gruppe_002():
        # wie dein TRW-Kombi: Kilometerstand-Feld meldet FF FF (= kein Wert)
        return [(36, 0xFF, 0xFF), (19, 100, 21), (64, 82, 82), (37, 0, 0)]

    return SimEcu(
        0x17,
        [b"SIM920806   ", b"KOMBI SIMULA", b"TION    V01", b"\x00\x01\x1a\xd4\x31"],
        baud=9600,
        fehler=[(771, 30 | 0x80)],
        gruppen={1: gruppe_001, 2: gruppe_002},
    )


def wegfahrsperre() -> SimEcu:
    def gruppe_001():
        return [(54, 0x28, 0xA0), (17, 0x20, 0x31), (17, 0x20, 0x31), (17, 0x20, 0x31)]

    return SimEcu(
        0x25,
        [bytes([ord("S") | 0x80]) + b"IM953257   ", b"IMMO        ", b"SIMULATION01",
         b"\x00\x00\x02\x30\x39"],
        baud=9600,
        gruppen={1: gruppe_001},
        zusatzkennung=[b"WVWZZZ6KZ1SIM0001", b"VWZ7Z0S0000001"],
    )


def kwp2000_steuergeraet() -> SimEcu:
    return SimEcu(0x15, [b"SIM KWP2000 "], baud=10400, keybytes=(0xEF, 0x8F))


def sim_port(echo: bool = True, echtzeit: bool = True) -> SimPort:
    geraete = [motor_steuergeraet(), kombi_steuergeraet(), wegfahrsperre(),
               kwp2000_steuergeraet()]
    log.info("Interface: Simulator – keine echten Fahrzeugdaten")
    return SimPort({g.adresse: g for g in geraete}, echo=echo, echtzeit=echtzeit)

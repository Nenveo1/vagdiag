"""Simulierte Steuergeräte auf Byte-Ebene.

Der Simulator spielt das KW1281-Protokoll Byte für Byte mit (inklusive
Komplement-Handshake und Kabel-Echo). So läuft der echte Protokollcode – nur
ohne Auto. Mit echtzeit=True verhält er sich zeitlich wie dein Polo: Reizung
gut 2 s, etwa 10 ms pro Byte, also rund 3 Messwertabfragen pro Sekunde.

Belegung und Rohformate wie in den Logs deines Polos (19.10.2026):
  01 Motorelektronik (10400 Baud) – Fehler, Gruppen 001, 002, 004,
     Anpassungskanal 01
  03 ABS (9600 Baud) – Gruppen 001 (Raddrehzahlen) und 002 (FF-Platzhalter)
  15 Airbag (9600 Baud) – nur Kennung und Fehlerspeicher
  17 Kombiinstrument (10400 Baud) – Gruppen 001–003, Kilometerstand-Feld wie
     bei deinem TRW-Kombi FF FF (= kein Wert), Anpassungskanal 09
  25 Wegfahrsperre (9600 Baud) – Gruppen 001–003, mit Zusatzkennung
  56 ein KWP2000-Gerät, um die Protokollerkennung zu zeigen
Die Kennungen beginnen mit „SIM“, damit nichts mit echten Daten verwechselt
wird. Mit Fahrprofil (Standard außer in den Tests) fahren die simulierten
Steuergeräte gemeinsam eine Runde von 4 Minuten in Schleife (SimFahrzeug).
"""

from __future__ import annotations

import bisect
import itertools
import logging
import math
import random
import time
from dataclasses import dataclass
from typing import Callable

from .port import RawPort
from . import sprache

log = logging.getLogger("vagdiag.port")

Gruppe = Callable[[], list[tuple[int, int, int]]]

ACK, NAK = 0x09, 0x0A


class SimEcu:
    def __init__(self, adresse: int, kennung: list[bytes], baud: int = 10400,
                 fehler: list[tuple[int, int]] | None = None,
                 gruppen: dict[int, Gruppe | None] | None = None,
                 keybytes: tuple[int, int] = (0x01, 0x8A),
                 zusatzkennung: list[bytes] | None = None,
                 anpassungen: dict[int, int] | None = None,
                 anpassung_zusatz: dict[int, bytes] | None = None):
        self.adresse = adresse
        self.anpassungen = dict(anpassungen or {})
        self.anpassung_zusatz = dict(anpassung_zusatz or {})
        self.anfragen: list[tuple[int, bytes]] = []   # (Titel, Daten) aller Testerblöcke
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
        self._sonderantwort: str | None = None
        self._letzte_messwerte = b""
        self.titel_gruppen: set[int] = set()     # antworten immer mit Fehlerliste (FC)

    # -- Testhilfen -------------------------------------------------------
    def ausfall_nach(self, gruppenabfragen: int) -> None:
        """Nach n weiteren Gruppenabfragen einmal verstummen (wie beim Anlassen)."""
        self._ausfall_in = gruppenabfragen

    def stoerung_nach(self, bloecke: int) -> None:
        """Im n-ten folgenden Testerblock ein Komplement als 00 verfälschen."""
        self._stoerung_in = bloecke

    def naechste_gruppenantwort(self, art: str) -> None:
        """Die nächste Gruppenabfrage gestört beantworten:
        "muell"   Längenbyte FF und Datenmüll (wie am 19.10. um 19:16:47)
        "zaehler" vorige Antwort mit falschem Blockzähler (wie um 19:37:18)
        "format"  Antwort im Format einer anderen Gruppe
        "titel"   Fehlerliste statt Messwerten"""
        self._sonderantwort = art

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
    def _starte_block(self, titel: int, daten: bytes = b"", versatz: int = 1) -> None:
        self._zaehler = (self._zaehler + versatz) & 0xFF
        self._tx = bytes([len(daten) + 3, self._zaehler, titel]) + bytes(daten) + b"\x03"
        self._pos = 0
        self._zustand = "senden"
        self.port.ausgeben(self._tx[:1], pause=self.port.antwort_pause)

    def _verarbeite(self, roh: list[int]) -> None:
        self._zaehler = roh[1]
        titel, daten = roh[2], bytes(roh[3:-1])
        self.anfragen.append((titel, daten))
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
            sonder, self._sonderantwort = self._sonderantwort, None
            if gruppe in self.titel_gruppen:
                self._starte_block(0xFC, b"\xff\xff\x88")
            elif funktion is None:
                self._starte_block(NAK, bytes([self._zaehler]))
            elif sonder == "muell":
                self.port.ausgeben(b"\xff" + b"\x03" * 12, pause=self.port.antwort_pause)
                self._zustand = "aus"
            elif sonder == "zaehler":
                self._starte_block(0xE7, self._letzte_messwerte or b"".join(
                    bytes(t) for t in funktion()), versatz=0)
            elif sonder == "titel":
                self._starte_block(0xFC, b"\xff\xff\x88")
            else:
                if sonder == "format":
                    andere = next((f for g, f in self.gruppen.items() if g != gruppe and f), None)
                    werte = b"".join(bytes(t) for t in (andere or funktion)())
                    if andere is None:
                        werte = werte[::-1]
                else:
                    werte = b"".join(bytes(t) for t in funktion())
                    self._letzte_messwerte = werte
                self._starte_block(0xE7, werte)
        elif titel == 0x21:   # Anpassung lesen
            kanal = daten[0] if daten else 0
            wert = self.anpassungen.get(kanal) if kanal else None
            if wert is None:
                self._starte_block(NAK, bytes([self._zaehler]))
            else:
                self._starte_block(0xE6, bytes([kanal, wert >> 8, wert & 0xFF])
                                   + self.anpassung_zusatz.get(kanal, b""))
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
        self._echo_aus_in: int | None = None
        self.fahrzeug = None
        self.description = sprache.t("Simulator (keine echten Fahrzeugdaten)")

    def echo_auslassen_nach(self, bytes_: int) -> None:
        """Beim n-ten folgenden gesendeten Byte kein Echo liefern (Kabel kurz weg)."""
        self._echo_aus_in = bytes_

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
            ohne_echo = False
            if self._echo_aus_in is not None:
                self._echo_aus_in -= 1
                if self._echo_aus_in <= 0:
                    self._echo_aus_in = None
                    ohne_echo = True
            if self.echo and not ohne_echo:
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


UEBERSETZUNG = {1: 7.0, 2: 13.1, 3: 18.7, 4: 25.0, 5: 32.2}   # km/h je 1000/min (dein Polo)


@dataclass
class Zustand:
    motor_an: bool = True
    n: float = 820            # /min
    v: float = 0              # km/h
    gang: int = 0
    kmt: float = 90           # °C Kühlmittel
    iat: float = 25           # °C Ansaugluft
    u: float = 13.8           # V Bordspannung
    p: float = 300            # mbar Saugrohrdruck
    dk: float = 4.3           # % Drosselklappe
    zw: float = 8.0           # ° v.OT (negativ = n.OT)
    last: float = 19.0        # %
    ti: float = 4.5           # ms Einspritzzeit
    lam: float = 0.0          # % Lambdaregelung
    lambda_aktiv: bool = True
    schub: bool = False
    bremse: bool = False
    lastzustand: int = 5      # Text: 5 Leerlauf, 6 Teillast, 7 Volllast, 9 Schub
    tank: float = 21.0        # l, wie der Geber ihn meldet
    kurve: float = 0.0        # km/h, linke minus rechte Räder
    gefahren: bool = False    # schon einmal gerollt (ABS-Gruppe 002)


class SimFahrzeug:
    """Gemeinsamer Zustand der simulierten Steuergeräte.

    Ohne Fahrprofil: warmer Motor im Leerlauf (für Tests). Mit Fahrprofil:
    eine Runde von 240 s in Schleife – Leerlauf, Vollgas auf 100 km/h,
    Landstraße, Schub, Ort mit Bremsungen und einer Rechtskurve, Halt.
    Angelehnt an deine Fahrt vom 19.10.: Kühlmittel bleibt bei etwa 78 °C,
    der Tankgeber meldet im Stand weniger als beim Fahren.
    zeitfaktor beschleunigt das Profil, motor_start_nach lässt den Motor
    erst nach so vielen (Profil-)Sekunden anspringen."""

    RUNDE = 240.0
    TANK_STAND = 21.0
    TANK_FAHRT = 28.0

    def __init__(self, fahrprofil: bool = True, zeitfaktor: float = 1.0,
                 motor_start_nach: float = 0.0):
        self.fahrprofil = fahrprofil
        self.zeitfaktor = zeitfaktor
        self.motor_start_nach = motor_start_nach if fahrprofil else 0.0
        self.t0 = time.monotonic()
        self._gefahren = False

    def t(self) -> float:
        return (time.monotonic() - self.t0) * self.zeitfaktor

    @staticmethod
    def _tempo(tz: float) -> tuple[float, str]:
        """Tempo und Fahrzustand innerhalb einer Runde."""
        punkte = [(0, 0, "leerlauf"), (20, 0, "vollgas"), (35, 100, "reise"),
                  (110, 100, "schub"), (140, 50, "ort"), (160, 50, "bremse"),
                  (165, 30, "beschleunigen"), (175, 50, "ort"), (190, 50, "bremse"),
                  (205, 0, "leerlauf"), (240, 0, "leerlauf")]
        for (t1, v1, art), (t2, v2, _) in zip(punkte, punkte[1:]):
            if t1 <= tz < t2:
                return v1 + (v2 - v1) * (tz - t1) / (t2 - t1), art
        return 0.0, "leerlauf"

    def zustand(self) -> Zustand:
        z = Zustand()
        if not self.fahrprofil:
            z.n = _rauschen(820, 25)
            z.kmt = _rauschen(90, 0.6)
            z.iat = _rauschen(25, 0.6)
            z.u = _rauschen(13.8, 0.1)
            z.lam = _rauschen(0, 3)
            return z
        t = self.t()
        if t < self.motor_start_nach:
            z.motor_an, z.n, z.u, z.p, z.dk, z.zw, z.last, z.ti = False, 0, 12.1, 980, 0, 0, 100, 0
            z.kmt, z.iat, z.lam, z.lambda_aktiv = 40, 22, 0, False
            z.tank = self.TANK_STAND
            return z
        if t < self.motor_start_nach + 1.2:            # Anlasser
            z.n, z.u, z.p, z.dk, z.zw, z.last, z.ti = 200, 10.0, 950, 0, 5, 66, 7
            z.kmt, z.iat, z.lam, z.lambda_aktiv = 40, 22, 0, False
            z.tank = self.TANK_STAND
            return z
        lauf = t - self.motor_start_nach - 1.2
        tz = lauf % self.RUNDE
        v, art = self._tempo(tz)
        z.v = v
        if v > 3:
            self._gefahren = True
        z.gefahren = self._gefahren
        z.kmt = 40 + 38 * (1 - math.exp(-lauf / 150))
        if art == "reise":                            # Fahrtwind kühlt
            z.kmt -= 4 * min(1.0, (tz - 35) / 40)
        z.iat = 22 + 25 * (1 - math.exp(-lauf / 600))
        z.u = 13.3 + 0.6 * math.exp(-lauf / 600)
        z.lambda_aktiv = lauf > 15
        if v < 5:
            z.gang, z.n = 0, _rauschen(820, 25)
        else:
            mindest = 1800 if art in ("vollgas", "beschleunigen") else 1300
            gang = 1
            for g in sorted(UEBERSETZUNG):
                if v / UEBERSETZUNG[g] * 1000 >= mindest:
                    gang = g
            z.gang = gang
            z.n = max(820, v / UEBERSETZUNG[gang] * 1000)
        werte = {               # p, dk, zw, last, ti, lastzustand
            "leerlauf": (300, 4.3, 8, 19, 4.5, 5),
            "vollgas": (965, 99.6, 16.5, 77, 20, 7),
            "reise": (480, 18, 32, 37, 9, 6),
            "ort": (380, 12, 33, 25, 6.5, 6),
            "beschleunigen": (700, 30, 25, 55, 13, 6),
            "schub": (220, 5, -7, 16, 3, 9),
            "bremse": (220, 5, -7, 16, 3, 9),
        }[art]
        z.p, z.dk, z.zw, z.last, z.ti, z.lastzustand = werte
        z.schub = art in ("schub", "bremse") and z.n > 1100
        if art in ("schub", "bremse") and not z.schub:      # unter 1100/min: wieder Leerlauf
            z.p, z.dk, z.zw, z.last, z.ti, z.lastzustand = (300, 4.3, 8, 19, 4.5, 5)
        z.bremse = art == "bremse"
        z.lam = 0.0 if (z.schub or not z.lambda_aktiv) else 5 * math.sin(lauf * 2.1)
        z.p = _rauschen(z.p, 8)
        if v < 3:
            z.tank = self.TANK_STAND
        else:
            schwappen = 15 if z.bremse else 8
            z.tank = min(43, max(2, _rauschen(self.TANK_FAHRT, schwappen)))
        z.kurve = 2.0 if 177 <= tz < 183 else 0.0
        return z


def _drehzahl(z: Zustand) -> tuple[int, int, int]:
    return (1, 200, _clamp(z.n / 40))                     # 0,2 · a · b /min


def _temperatur(grad: float) -> tuple[int, int, int]:
    return (5, 10, _clamp(100 + grad))                    # a · (b − 100) · 0,1 °C


def motor_steuergeraet(fz: SimFahrzeug | None = None) -> SimEcu:
    """Wie dein ME7.5.10: 001 Drehzahl/Kühlmittel/Lambda/Bits,
    002 Drehzahl/Last/Einspritzzeit/Saugrohrdruck, 003 Drehzahl/Saugrohrdruck/
    Drosselklappe/Zündwinkel, 004 Drehzahl/Spannung/Temperaturen.
    005 (Drehzahl/Last/Tempo/Lastzustand) ist üblich bei ME7, an deinem Auto
    aber noch nicht geprüft."""
    fz = fz or SimFahrzeug(fahrprofil=False)

    def bits(z: Zustand) -> int:
        b = 0b11100000
        if z.lambda_aktiv and not z.schub:
            b |= 0b1000
        if z.v < 3 and z.dk < 7:
            b |= 0b100
        if z.n < 2000:
            b |= 0b10
        if z.kmt > 80:
            b |= 0b1
        return b

    def gruppe_001():
        z = fz.zustand()
        return [_drehzahl(z), _temperatur(z.kmt), (20, 100, _clamp(128 + z.lam * 1.28)),
                (16, 0xFF, bits(z))]

    def gruppe_002():
        z = fz.zustand()
        return [_drehzahl(z), (33, 133, _clamp(z.last * 1.33)), (15, 41, _clamp(z.ti / 0.41)),
                (18, 250, _clamp(z.p / 10))]

    def gruppe_003():
        z = fz.zustand()
        return [_drehzahl(z), (18, 250, _clamp(z.p / 10)), (33, 255, _clamp(z.dk * 2.55)),
                (27, 75, _clamp(128 + z.zw / 0.75))]

    def gruppe_004():
        z = fz.zustand()
        return [_drehzahl(z), (21, 70, _clamp(z.u / 0.07)),   # 0,07 V je Schritt
                _temperatur(z.kmt), _temperatur(z.iat)]

    def gruppe_005():
        z = fz.zustand()
        return [_drehzahl(z), (33, 133, _clamp(z.last * 1.33)), (7, 100, _clamp(z.v)),
                (37, 0, z.lastzustand)]

    return SimEcu(
        0x01,
        [b"SIM906032   ", b"ME7.5 SIMULATION    ", b"S001", b"\x00\x00\x3e\x30\x39"],
        baud=10400,
        fehler=[(16486, 0x23 | 0x80), (16684, 0x23)],
        gruppen={1: gruppe_001, 2: gruppe_002, 3: gruppe_003, 4: gruppe_004, 5: gruppe_005},
        anpassungen={1: 128},
    )


def abs_steuergeraet(fz: SimFahrzeug | None = None) -> SimEcu:
    fz = fz or SimFahrzeug(fahrprofil=False)

    def gruppe_001():
        z = fz.zustand()
        links, rechts = z.v + z.kurve / 2, z.v - z.kurve / 2
        return [(7, 100, _clamp(links)), (7, 100, _clamp(rechts)),
                (7, 100, _clamp(links)), (7, 100, _clamp(rechts))]

    def gruppe_002():
        z = fz.zustand()
        if not z.gefahren:
            return [(7, 100, 0xFF)] * 4       # wie dein ABS im Stand: FF-Platzhalter
        return [(7, 100, 2), (7, 100, 1), (7, 100, 1), (7, 100, 1)]

    def gruppe_003():
        z = fz.zustand()
        return [(37, 0, 0xC1 if z.bremse else 0xA7)]   # betätigt / unbetätigt

    return SimEcu(
        0x03,
        [b"SIM907379   ", b"ABS SIMULATI", b"ON     V004", b"\x00\x31\x44\x2b\x67"],
        baud=9600,
        gruppen={1: gruppe_001, 2: gruppe_002, 3: gruppe_003},
    )


def airbag_steuergeraet() -> SimEcu:
    return SimEcu(
        0x15,
        [b"SIM959655   ", b"AIRBAG SIMUL", b"ATION  0001", b"\x00\x00\x2a\x30\x39"],
        baud=9600,
    )


def kombi_steuergeraet(fz: SimFahrzeug | None = None) -> SimEcu:
    """Wie dein TRW-Kombi: Kilometerstand-Feld FF FF, Öldruck als Text 31,
    Kanal 09 mit Beschreibung „Kilometerstand in 10 km“ (Wert hier gesetzt)."""
    fz = fz or SimFahrzeug(fahrprofil=False)

    def gruppe_001():
        z = fz.zustand()
        jetzt = time.localtime()
        return [(7, 100, _clamp(z.v)), _drehzahl(z), (37, 0, 0x1F),
                (44, jetzt.tm_hour, jetzt.tm_min)]

    def gruppe_002():
        z = fz.zustand()
        ohm = 70 + (z.tank - 2) * (286 - 70) / (43 - 2)
        return [(36, 0xFF, 0xFF), (19, 100, _clamp(z.tank)),
                (64, _clamp(ohm / 2), _clamp(ohm - _clamp(ohm / 2))), (37, 0, 0)]

    def gruppe_003():
        z = fz.zustand()
        return [_temperatur(z.kmt + 3), (37, 0, 0), (37, 0, 0)]

    return SimEcu(
        0x17,
        [b"SIM920806   ", b"KOMBI SIMULA", b"TION    V01", b"\x00\x01\x1a\xd4\x31"],
        baud=10400,
        fehler=[(771, 30 | 0x80)],
        gruppen={1: gruppe_001, 2: gruppe_002, 3: gruppe_003},
        anpassungen={9: 12345},           # = 123.450 km, falls Kanal 09 der Kilometerstand ist
        anpassung_zusatz={9: bytes([0xE7, 0x25, 0x00, 0x95, 0x25, 0x01, 0x49,
                                    0x25, 0x01, 0x4A, 0x25, 0x00, 0x6B])},
    )


def wegfahrsperre() -> SimEcu:
    def zeichen(*texte: str) -> list[tuple[int, int, int]]:
        return [(17, 0x20, ord(t)) for t in texte]

    return SimEcu(
        0x25,
        [bytes([ord("S") | 0x80]) + b"IM953257   ", b"IMMO        ", b"SIMULATION01",
         b"\x00\x00\x02\x30\x39"],
        baud=9600,
        gruppen={1: lambda: [(54, 0x28, 0xA0)] + zeichen("1", "1", "1"),
                 2: lambda: zeichen("1", "1", "1", "2"),
                 3: lambda: zeichen("1", "0", "1", "6")},
        zusatzkennung=[b"WVWZZZ6KZ1SIM0001", b"VWZ7Z0S0000001"],
    )


def kwp2000_steuergeraet() -> SimEcu:
    return SimEcu(0x56, [b"SIM KWP2000 "], baud=10400, keybytes=(0xEF, 0x8F))


def sim_port(echo: bool = True, echtzeit: bool = True, fahrprofil: bool = True,
             zeitfaktor: float = 1.0, motor_start_nach: float = 0.0) -> SimPort:
    fz = SimFahrzeug(fahrprofil, zeitfaktor, motor_start_nach)
    geraete = [motor_steuergeraet(fz), abs_steuergeraet(fz), airbag_steuergeraet(),
               kombi_steuergeraet(fz), wegfahrsperre(), kwp2000_steuergeraet()]
    log.info(sprache.t("Interface: Simulator – keine echten Fahrzeugdaten"))
    port = SimPort({g.adresse: g for g in geraete}, echo=echo, echtzeit=echtzeit)
    port.fahrzeug = fz
    return port

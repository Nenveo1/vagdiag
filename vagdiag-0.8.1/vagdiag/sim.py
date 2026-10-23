"""Simulierte Steuergeräte auf Byte-Ebene.

Der Simulator spielt das KW1281-Protokoll Byte für Byte mit (inklusive
Komplement-Handshake und Kabel-Echo). So läuft der echte Protokollcode – nur
ohne Auto. Mit echtzeit=True verhält er sich zeitlich wie ein echtes Auto:
Reizung gut 2 s, etwa 10 ms pro Byte, also rund 3 Messwertabfragen pro Sekunde.

Belegung und Rohformate nach Aufzeichnungen an einem Polo 6KV (ME7.5.10):
  01 Motorelektronik (10400 Baud) – Fehler, Gruppen 001–005, Anpassungskanal 01;
     Gruppe 060 (Drosselklappe) lesen und als Grundeinstellung anlernen – klappt nur
     bei stehendem Motor (SimFahrzeug.motor_aus), ebenso die Stellglieddiagnose (vier
     Stellglieder mit Simulator-Nummern ab F0B1)
  03 ABS (9600 Baud) – Gruppen 001 (Raddrehzahlen) und 002 (FF-Platzhalter); mit
     Fahrprofil nimmt es eine Verbindung nur im Stand an (wie im Polo beobachtet)
  15 Airbag (9600 Baud) – nur Kennung und Fehlerspeicher
  17 Kombiinstrument (10400 Baud) – Gruppen 001–003, Kilometerstand-Feld wie
     bei manchen TRW-Kombis FF FF (= kein Wert), Anpassungskanal 09 (nur lesen) und
     Kanal 02 (Service-Intervall: Testen und Speichern nur mit dem Wert 0),
     Stellglieddiagnose wie ein Kombi in kw1281test (Zeiger, Segmenttest, Gong, Ende)
  25 Wegfahrsperre (9600 Baud) – Gruppen 001–003, mit Zusatzkennung
  56 ein Gerät mit KWP2000 (Keyword 2027) – Kennung, Fehlerspeicher, Gruppe 001
Mit kwp2000_motor=True spricht auch der Motor KWP2000 (Keyword 2031,
Kopfadresse 10, auch per Fast-Init erreichbar) – mit denselben Messwerten, mit
kwp2000_kombi=True das Kombi (Keyword 2027) mit Anpassung über die KWP2000-Routinen.
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
from . import sprache, stellglied, texte

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
                 anpassung_zusatz: dict[int, bytes] | None = None,
                 anpassung_erlaubt: dict[int, Callable[[int], bool]] | None = None,
                 grundeinstellungen: dict[int, Gruppe] | None = None,
                 stellglieder: list[int] | None = None,
                 stellglied_bedingung: Callable[[], bool] | None = None):
        self.adresse = adresse
        # Stellglieddiagnose: Nummern in Reihenfolge (None: nicht unterstützt) und wann sie
        # erlaubt ist (z. B. nur bei stehendem Motor)
        self.stellglieder = stellglieder
        self.stellglied_bedingung = stellglied_bedingung
        self.stellglied_aktiv: int | None = None      # gerade angesteuert (für Tests)
        self._stellglied_index = 0
        self.anpassungen = dict(anpassungen or {})
        self.anpassung_zusatz = dict(anpassung_zusatz or {})
        # Kanal → welche Werte Testen/Speichern annimmt (fehlt: jeder Wert)
        self.anpassung_erlaubt = dict(anpassung_erlaubt or {})
        self.grundeinstellungen = dict(grundeinstellungen or {})
        self.geschrieben: list[tuple[int, bytes]] = []   # Blöcke 04, 22, 28, 2A (für Tests)
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
        self._empfangsfehler: tuple[int, int, int | None] | None = None
        self._kennung_verweigern = 0
        # Kommt das nächste Byte eines Testerblocks später, verwirft das Steuergerät den
        # halben Block und nimmt das späte Byte als Anfang eines neuen – so hat es ein ME7.5
        # im Auto gemacht (nach etwa 45 ms). "aus": stattdessen Verbindung beenden.
        self.empfang_timeout = 0.5
        self.nach_timeout = "neuer_block"
        self._rx_zeit = 0.0
        self.verworfen: list[bytes] = []          # verworfene halbe Blöcke (für Tests)
        self._bloecke_empfangen = 0
        self._sonderantwort: str | None = None
        self._letzte_messwerte = b""
        self.titel_gruppen: set[int] = set()     # antworten immer mit Fehlerliste (FC)
        # None: antwortet immer auf die Reizung; sonst nur, wenn reizbar() wahr ist
        # (z. B. ABS nur im Stand)
        self.reizbar: Callable[[], bool] | None = None

    # -- Testhilfen -------------------------------------------------------
    def ausfall_nach(self, gruppenabfragen: int) -> None:
        """Nach n weiteren Gruppenabfragen einmal verstummen (wie beim Anlassen)."""
        self._ausfall_in = gruppenabfragen

    def stoerung_nach(self, bloecke: int) -> None:
        """Im n-ten folgenden Testerblock ein Komplement als 00 verfälschen."""
        self._stoerung_in = bloecke

    def kennung_verweigern(self, mal: int = 1) -> None:
        """Bei den nächsten `mal` Verbindungsaufbauten nach dem invertierten KB2 verstummen,
        statt die Kennung zu senden – so im Auto am 20., 21. und 22.10. je einmal beim Motor."""
        self._kennung_verweigern = mal

    def empfangsfehler(self, position: int, maske: int = 0x01, titel: int | None = None) -> None:
        """Im nächsten Testerblock (mit diesem Titel) kommt das Byte an dieser Stelle
        verfälscht an (0 = Länge, 1 = Zähler, 2 = Titel, 3 = erstes Datenbyte): Das
        Steuergerät übernimmt es mit maske gekippten Bits und quittiert das verfälschte
        Byte – wie bei einem Spannungseinbruch auf der Leitung."""
        self._empfangsfehler = (position, maske, titel)

    def _empfangen(self, byte: int) -> int:
        if self._empfangsfehler is None:
            return byte
        position, maske, titel = self._empfangsfehler
        if position != len(self._rx):
            return byte
        if titel is not None and not ((position == 2 and byte == titel)
                                      or (position > 2 and self._rx[2] == titel)):
            return byte
        self._empfangsfehler = None
        return byte ^ maske

    def naechste_gruppenantwort(self, art: str) -> None:
        """Die nächste Gruppenabfrage gestört beantworten:
        "muell"   Längenbyte FF und Datenmüll (so im Auto beobachtet)
        "zaehler" vorige Antwort mit falschem Blockzähler (wie um 19:37:18)
        "format"  Antwort im Format einer anderen Gruppe
        "titel"   Fehlerliste statt Messwerten"""
        self._sonderantwort = art

    # -- Verbindungsaufbau ------------------------------------------------
    def reizen(self, port: "SimPort") -> None:
        self.port = port
        self._zustand = "warte_kb2"
        self.stellglied_aktiv = None
        self._stellglied_index = 0
        port.ausgeben(bytes([0x55, *self.keybytes]), pause=port.sync_pause)

    def byte_vom_tester(self, byte: int) -> None:
        z = self._zustand
        if z == "warte_kb2":
            if byte != self.keybytes[1] ^ 0xFF:
                self._zustand = "aus"
                return
            if self._kennung_verweigern > 0:
                self._kennung_verweigern -= 1
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
            jetzt = time.monotonic()
            if self._rx and jetzt - self._rx_zeit > self.empfang_timeout:
                self.verworfen.append(bytes(self._rx))
                self._rx = []
                if self.nach_timeout == "aus":
                    self._zustand = "aus"
                    self.stellglied_aktiv = None
                    return
            self._rx_zeit = jetzt
            byte = self._empfangen(byte)
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
        elif titel == 0x28:   # Grundeinstellung
            self.geschrieben.append((titel, daten))
            gruppe = daten[0] if daten else 0
            funktion = self.grundeinstellungen.get(gruppe)
            if funktion is None:
                self._starte_block(NAK, bytes([self._zaehler]))
            else:
                self._starte_block(0xE7, b"".join(bytes(t) for t in funktion()))
        elif titel in (0x22, 0x2A):   # Anpassung testen / speichern
            self.geschrieben.append((titel, daten))
            kanal = daten[0] if daten else 0
            wert = (daten[1] << 8) | daten[2] if len(daten) >= 3 else None
            erlaubt = self.anpassung_erlaubt.get(kanal, lambda w: True)
            if not kanal or kanal not in self.anpassungen or wert is None or not erlaubt(wert):
                self._starte_block(NAK, bytes([self._zaehler]))
            else:
                if titel == 0x2A:
                    self.anpassungen[kanal] = wert
                self._starte_block(0xE6, bytes([kanal, wert >> 8, wert & 0xFF]))
        elif titel == 0x04:   # Stellglieddiagnose
            self.geschrieben.append((titel, daten))
            if self.stellglieder is None or (self.stellglied_bedingung is not None
                                             and not self.stellglied_bedingung()):
                self.stellglied_aktiv = None
                self._starte_block(NAK, bytes([self._zaehler]))
            elif self._stellglied_index < len(self.stellglieder):
                code = self.stellglieder[self._stellglied_index]
                self._stellglied_index += 1
                self.stellglied_aktiv = None if code in stellglied.ENDE else code
                self._starte_block(0xF5, bytes([code >> 8, code & 0xFF]))
            else:
                self.stellglied_aktiv = None
                self._stellglied_index = 0
                self._starte_block(ACK)
        elif titel == 0x06:
            self._zustand = "aus"
            self.stellglied_aktiv = None
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


TESTER = 0xF1


def kwp_laenge(puffer: bytes | bytearray) -> int | None:
    """Gesamtlänge einer KWP2000-Nachricht samt Prüfsumme – None, solange der Kopf
    dafür noch nicht reicht."""
    if not puffer:
        return None
    fmt = puffer[0]
    kopf = 3 if fmt & 0x80 else 1
    laenge = fmt & 0x3F
    if laenge == 0:
        if len(puffer) <= kopf:
            return None
        laenge = puffer[kopf]
        kopf += 1
    return kopf + laenge + 1


class SimKwpEcu:
    """KWP2000-Steuergerät (ISO 14230) auf Byte-Ebene, so wie VAG-Geräte ab etwa 2002.

    Antwortet auf 1A 9B (Kennung im VAG-Aufbau), 10 (Diagnosesitzung), 18
    (Fehlerspeicher), 14 (löschen – zuerst „Antwort folgt“), 21 (Messwertblock,
    auf acht Felder mit 25 00 00 aufgefüllt), 3E und 82, mit anpassungen auf die
    Anpassungsroutinen 31/32 B8–BB 01 03 und mit stellglieder auf die Stellglied-
    diagnose 31/32 B8–BA 01 02 (Ablauf wie im EDC16-Mitschnitt von kw1281test: der
    erste Schritt steuert an, der zweite schaltet weiter; vor jedem Zustand kommt
    einmal ein Messwert-Datensatz). Alles andere lehnt es ab (7F xx 11).
    Nachrichten an eine andere Kopfadresse überhört es – wie ein EDC16, das nach der
    Reizung an 01 nur auf 10 hört. Kommt länger als P3 (5 s) keine Anfrage, beendet
    es die Verbindung."""

    def __init__(self, adresse: int, teilenummer: str, beschreibung: str,
                 software: str = "0001", baud: int = 10400,
                 keybytes: tuple[int, int] = (0x6B, 0x8F), kopf: int | None = None,
                 codierung: int = 0, werkstattcode: tuple[int, int, int] = (12345, 0, 0),
                 fehler: list[tuple[int, int]] | None = None,
                 gruppen: dict[int, Gruppe] | None = None,
                 sitzungen: tuple[int, ...] = (0x89, 0x81, 0x85),
                 stumme_sitzungen: tuple[int, ...] = (), fast_init: bool = False,
                 tester_present: bool = True, fehler_mit_anzahl: bool = True,
                 loeschen_folgt: bool = True, kennung: bytes | None = None,
                 anpassungen: dict[int, int] | None = None,
                 anpassung_erlaubt: dict[int, Callable[[int], bool]] | None = None,
                 anpassung_messwert: dict[int, tuple[int, int, int]] | None = None,
                 zugriffsschutz: set[int] | None = None,
                 stellglieder: list[int] | None = None,
                 stellglied_bedingung: Callable[[], bool] | None = None):
        self.adresse = adresse
        self.anpassungen = dict(anpassungen or {})
        self.anpassung_erlaubt = dict(anpassung_erlaubt or {})
        self.anpassung_messwert = dict(anpassung_messwert or {})
        self.zugriffsschutz = set(zugriffsschutz or ())   # Kanäle nur nach Anmeldung
        self.stellglieder = stellglieder
        self.stellglied_bedingung = stellglied_bedingung
        self.stellglied_aktiv: int | None = None
        self.geschrieben: list[bytes] = []     # Anfragen, die etwas ändern/ansteuern
        self._routinen_zuruecksetzen()
        self.baud = baud
        self.keybytes = keybytes
        self.kopf = adresse if kopf is None else kopf
        wsc, importeur, geraet = werkstattcode
        self.kennung = kennung if kennung is not None else (
            b"\x9b" + teilenummer.ljust(12)[:12].encode("ascii")
            + software.ljust(4)[:4].encode("ascii") + b"\x03" + codierung.to_bytes(3, "big")
            + ((geraet << 27) | (importeur << 17) | wsc).to_bytes(6, "big")
            + beschreibung.encode("ascii"))
        self.fehler = list(fehler or [])
        self.gruppen = gruppen or {}
        self.sitzungen = tuple(sitzungen)
        self.stumme_sitzungen = set(stumme_sitzungen)
        self.fast_init = fast_init
        self.tester_present = tester_present
        self.fehler_mit_anzahl = fehler_mit_anzahl
        self.loeschen_folgt = loeschen_folgt
        self.p3_max = 5.0
        self.anfragen: list[bytes] = []      # Dienst + Daten jeder angenommenen Anfrage
        self.geloescht = 0
        self.sitzung: int | None = None
        self.port: SimPort | None = None
        self._zustand = "aus"
        self._puffer = bytearray()
        self._letzte = 0.0
        self._ausfall_in: int | None = None
        self._sonder: str | None = None
        self._stoerung: str | None = None
        self._sonderfaelle: list[tuple[bytes, str]] = []

    # -- Testhilfen -------------------------------------------------------
    def naechste_antwort(self, art: str) -> None:
        """Die nächste Anfrage gestört beantworten: "stumm" (gar nicht),
        "pruefsumme", "abgeschnitten", "fremd" (von anderer Quelladresse) oder
        "beschaeftigt" (7F xx 21, beim nächsten Mal richtig)."""
        self._sonder = art

    def sonderfall(self, anfrage: str | bytes, art: str) -> None:
        """Die nächste Anfrage, die so beginnt, nicht ausführen, sondern einmal so
        beantworten: "beschaeftigt" (7F xx 21), "ablehnen" (7F xx 22), "stumm" (gar nicht)
        oder "andere_routine" (positive Antwort einer anderen Routine)."""
        muster = bytes.fromhex(anfrage) if isinstance(anfrage, str) else bytes(anfrage)
        self._sonderfaelle.append((muster, art))

    def ausfall_nach(self, gruppenabfragen: int) -> None:
        """Nach n weiteren Messwertblöcken verstummen (wie beim Anlassen)."""
        self._ausfall_in = gruppenabfragen

    def _routinen_zuruecksetzen(self) -> None:
        self._anp = False
        self._anp_kanal: int | None = None
        self._anp_test: int | None = None
        self._stg = False
        self._stg_index = 0
        self._stg_an = False
        self._stg_zwischen = False
        self.stellglied_aktiv = None

    # -- Verbindungsaufbau ------------------------------------------------
    def reizen(self, port: "SimPort") -> None:
        self.port = port
        self.sitzung = None
        self._stoerung = None
        self._routinen_zuruecksetzen()
        self._zustand = "warte_kb2"
        port.ausgeben(bytes([0x55, *self.keybytes]), pause=port.sync_pause)

    def _bereit(self) -> None:
        self._zustand = "bereit"
        self._puffer.clear()
        self._letzte = time.monotonic()

    def fast_init_start(self, port: "SimPort", nachricht: bytes) -> None:
        """StartCommunication nach dem Fast-Init (die Port-Seite hat schon geprüft,
        dass sie an diese Kopfadresse ging)."""
        self.port = port
        self.sitzung = None
        self._stoerung = None
        self._routinen_zuruecksetzen()
        self.anfragen.append(bytes(nachricht[3:-1]))
        self._bereit()
        self._antworten(bytes([0xC1, *self.keybytes]), True)

    def byte_vom_tester(self, byte: int) -> None:
        if self._zustand == "warte_kb2":
            if byte != self.keybytes[1] ^ 0xFF:
                self._zustand = "aus"
                return
            self.port.ausgeben(bytes([self.adresse ^ 0xFF]), pause=self.port.kwp_p2)
            self._bereit()
            return
        if self._zustand != "bereit":
            return
        if not self._puffer and time.monotonic() - self._letzte > self.p3_max:
            self._zustand = "aus"          # P3 überschritten – Verbindung beendet
            return
        self._puffer.append(byte)
        laenge = kwp_laenge(self._puffer)
        if laenge is None or len(self._puffer) < laenge:
            return
        nachricht = bytes(self._puffer)
        self._puffer.clear()
        self._letzte = time.monotonic()
        self._verarbeite(nachricht)

    # -- Nachrichten ------------------------------------------------------
    def _antworten(self, daten: bytes, mit_adressen: bool, pause: float | None = None) -> None:
        n = len(daten)
        quelle = 0x33 if self._stoerung == "fremd" else self.kopf
        if mit_adressen:
            kopf = (bytes([0x80 | n, TESTER, quelle]) if n <= 0x3F
                    else bytes([0x80, TESTER, quelle, n]))
        else:
            kopf = bytes([n]) if n <= 0x3F else bytes([0x00, n])
        roh = kopf + bytes(daten)
        roh += bytes([sum(roh) & 0xFF])
        if self._stoerung == "pruefsumme":
            roh = roh[:-1] + bytes([(roh[-1] + 1) & 0xFF])
        elif self._stoerung == "abgeschnitten":
            roh = roh[:max(1, len(roh) // 2)]
        self.port.ausgeben(roh, pause=self.port.kwp_p2 if pause is None else pause,
                           byte_zeit=self.port.kwp_byte_zeit)

    def _verarbeite(self, nachricht: bytes) -> None:
        if (sum(nachricht[:-1]) & 0xFF) != nachricht[-1]:
            return                                  # Prüfsumme falsch: verwerfen
        fmt = nachricht[0]
        mit_adressen = bool(fmt & 0x80)
        if mit_adressen:
            if nachricht[1] != self.kopf:
                return                              # nicht an mich
            kopf = 3
        else:
            if not self.keybytes[0] & 0x04:
                return                              # kann keinen Kopf ohne Adressen
            kopf = 1
        if fmt & 0x3F == 0:
            kopf += 1
        daten = nachricht[kopf:-1]
        if not daten:
            return
        self.anfragen.append(bytes(daten))
        self._stoerung, self._sonder = self._sonder, None
        if self._stoerung == "stumm":
            return
        if self._stoerung == "beschaeftigt":
            self._sonder = None
            self._antworten(bytes([0x7F, daten[0], 0x21]), mit_adressen)
            return
        for i, (muster, art) in enumerate(self._sonderfaelle):
            if daten.startswith(muster):
                del self._sonderfaelle[i]
                if art in ("beschaeftigt", "ablehnen"):
                    code = 0x21 if art == "beschaeftigt" else 0x22
                    self._antworten(bytes([0x7F, daten[0], code]), mit_adressen)
                elif art == "andere_routine" and len(daten) >= 2:
                    self._antworten(bytes([daten[0] | 0x40, daten[1] ^ 0x01]) + daten[2:4],
                                    mit_adressen)
                return                                  # "stumm": keine Antwort

        def antwort(inhalt: bytes, pause: float | None = None) -> None:
            self._antworten(inhalt, mit_adressen, pause)

        def ablehnen(code: int) -> None:
            antwort(bytes([0x7F, daten[0], code]))

        dienst, arg = daten[0], daten[1:]
        if dienst == 0x10:
            sitzung = arg[0] if arg else None
            if sitzung in self.stumme_sitzungen:
                return
            if sitzung in self.sitzungen:
                self.sitzung = sitzung
                antwort(bytes([0x50, sitzung]))
            else:
                ablehnen(0x12)
        elif dienst == 0x1A:
            if arg[:1] == b"\x9b":
                antwort(b"\x5a" + self.kennung)
            else:
                ablehnen(0x12)
        elif dienst == 0x18:
            eintraege = b"".join(bytes([c >> 8, c & 0xFF, s]) for c, s in self.fehler)
            if self.fehler_mit_anzahl:
                antwort(bytes([0x58, len(self.fehler)]) + eintraege)
            else:
                antwort(b"\x58" + eintraege)
        elif dienst == 0x14:
            self.fehler.clear()
            self.geloescht += 1
            if self.loeschen_folgt:
                ablehnen(0x78)                       # Antwort folgt …
                antwort(b"\x54\xff\x00", pause=0.3 if self.port.echtzeit else 0.0)
            else:
                antwort(b"\x54\xff\x00")
        elif dienst == 0x21:
            gruppe = arg[0] if arg else 0
            if self._ausfall_in is not None:
                self._ausfall_in -= 1
                if self._ausfall_in < 0:
                    self._ausfall_in = None
                    self._zustand = "aus"            # verstummt
                    return
            funktion = self.gruppen.get(gruppe)
            if funktion is None:
                ablehnen(0x31)
                return
            felder = list(funktion())[:8]
            felder += [(0x25, 0x00, 0x00)] * (8 - len(felder))
            antwort(bytes([0x61, gruppe]) + b"".join(bytes(f) for f in felder))
        elif dienst == 0x3E:
            if self.tester_present:
                antwort(b"\x7e")
            else:
                ablehnen(0x11)
        elif dienst == 0x82:
            antwort(b"\xc2")
            self._routinen_zuruecksetzen()
            self._zustand = "aus"
        elif dienst == 0x81:
            antwort(bytes([0xC1, *self.keybytes]))
        elif dienst in (0x31, 0x32):
            self._routine(dienst, bytes(arg), antwort, ablehnen)
        else:
            ablehnen(0x11)

    def _stg_code(self) -> int:
        if self._stg_index < len(self.stellglieder):
            return self.stellglieder[self._stg_index]
        return 0x04AB                                        # Ende

    def _routine(self, dienst: int, arg: bytes, antwort, ablehnen) -> None:
        if len(arg) < 3:
            ablehnen(0x13)
            return
        routine, unter, rest = arg[0], arg[1:3], arg[3:]
        positiv = bytes([dienst | 0x40]) + arg
        if dienst == 0x32:
            if routine == 0xB8 and unter == b"\x01\x03" and not rest:
                self._anp, self._anp_kanal, self._anp_test = False, None, None
                antwort(positiv)
            elif routine == 0xB8 and unter == b"\x01\x02" and not rest:
                self._stg, self._stg_an, self.stellglied_aktiv = False, False, None
                antwort(positiv)
            else:
                ablehnen(0x12)
            return
        if unter == b"\x01\x03":
            if not self.anpassungen:
                ablehnen(0x12)                               # kennt keine Anpassung
            elif routine == 0xB8 and not rest:
                self._anp, self._anp_kanal, self._anp_test = True, None, None
                antwort(positiv)
            elif not self._anp:
                ablehnen(0x22)
            elif routine == 0xB9 and len(rest) == 1:
                kanal = rest[0]
                if kanal in self.zugriffsschutz:
                    ablehnen(0x33)
                elif kanal not in self.anpassungen:
                    ablehnen(0x31)
                else:
                    self._anp_kanal, self._anp_test = kanal, None
                    antwort(positiv)
            elif routine == 0xB9 and len(rest) == 2:
                self.geschrieben.append(bytes([dienst]) + arg)
                wert = (rest[0] << 8) | rest[1]
                erlaubt = self.anpassung_erlaubt.get(self._anp_kanal, lambda w: True)
                if self._anp_kanal is None:
                    ablehnen(0x22)
                elif not erlaubt(wert):
                    ablehnen(0x31)
                else:
                    self._anp_test = wert
                    antwort(positiv)
            elif routine == 0xBA and not rest:
                if self._anp_kanal is None:
                    ablehnen(0x22)
                    return
                wert = (self._anp_test if self._anp_test is not None
                        else self.anpassungen[self._anp_kanal])
                daten = bytes([0x71, 0xBA, 0x01, 0x03, 0x01, 0x03, wert >> 8, wert & 0xFF])
                messwert = self.anpassung_messwert.get(self._anp_kanal)
                if messwert:
                    daten += bytes([0x04, *messwert])
                antwort(daten)
            elif routine == 0xBB and len(rest) == 8:
                self.geschrieben.append(bytes([dienst]) + arg)
                wert = (rest[0] << 8) | rest[1]
                if self._anp_kanal is None or self._anp_test != wert:
                    ablehnen(0x22)
                else:
                    self.anpassungen[self._anp_kanal] = wert
                    antwort(bytes([0x71, 0xBB]) + unter)
            else:
                ablehnen(0x12)
            return
        if unter == b"\x01\x02" and self.stellglieder is not None and not rest:
            if routine == 0xB8:
                if self.stellglied_bedingung is not None and not self.stellglied_bedingung():
                    ablehnen(0x22)
                    return
                self._stg, self._stg_index, self._stg_an = True, 0, False
                self._stg_zwischen = True
                antwort(positiv)
            elif not self._stg:
                ablehnen(0x22)
            elif routine == 0xB9:
                self.geschrieben.append(bytes([dienst]) + arg)
                if not self._stg_an:                         # ansteuern
                    self._stg_an = True
                    code = self._stg_code()
                    self.stellglied_aktiv = None if code in stellglied.ENDE else code
                else:                                        # weiterschalten
                    self._stg_an, self.stellglied_aktiv = False, None
                    self._stg_index += 1
                self._stg_zwischen = True
                antwort(positiv)
            elif routine == 0xBA:
                if self._stg_zwischen:                       # erst ein Messwert-Datensatz
                    self._stg_zwischen = False
                    antwort(bytes([0x71, 0xBA, 0x01, 0x02, 0x02, 0x01, 0x25, 0x00]))
                else:
                    code = self._stg_code()
                    antwort(bytes([0x71, 0xBA, 0x01, 0x02, 0x03, 0x03, code >> 8, code & 0xFF]))
            else:
                ablehnen(0x12)
            return
        ablehnen(0x12)


class SimPort(RawPort):
    """Virtuelle K-Leitung mit angeschlossenen simulierten Steuergeräten."""

    simulator = True

    def __init__(self, steuergeraete: dict[int, SimEcu], echo: bool = True,
                 echtzeit: bool = False):
        self.steuergeraete = steuergeraete
        self.echo = echo
        self.echtzeit = echtzeit
        # Zeitverhalten wie bei einem echten Motorsteuergerät (aus einem Protokoll)
        self.byte_zeit = 0.010 if echtzeit else 0.0
        self.antwort_pause = 0.10 if echtzeit else 0.0
        self.sync_pause = 0.25 if echtzeit else 0.0
        self.reizung_dauer = 1.8 if echtzeit else 0.05
        # KWP2000: Bytes am Stück (10400 Baud ≈ 1 ms je Byte), Antwort nach P2
        self.kwp_byte_zeit = 0.001 if echtzeit else 0.0
        self.kwp_p2 = 0.03 if echtzeit else 0.0
        self.baud = 10400
        self._rx: list[tuple[float, int, int]] = []
        self._nummer = itertools.count()
        self._frei_ab = 0.0
        self._aktiv: SimEcu | SimKwpEcu | None = None
        self._echo_aus_in: int | None = None
        self._fast_puffer: bytearray | None = None
        self.fast_inits = 0
        self.reizungen: list[int] = []        # gereizte Adressen (für Tests)
        self.abgewiesen: list[int] = []       # Reizungen, die ein Steuergerät nicht annahm
        self._zuendung = True
        self.fahrzeug = None
        self.description = sprache.t("Simulator (keine echten Fahrzeugdaten)")

    def fahrzeug_parken(self) -> None:
        """Das Fahrprofil anhalten: das Auto steht (für Start- und Abschlussprüfung)."""
        if self.fahrzeug is not None:
            self.fahrzeug.geparkt = True

    def fahrzeug_losfahren(self) -> None:
        """Das Fahrprofil wieder freigeben – die Runde beginnt von vorn (Leerlauf)."""
        if self.fahrzeug is not None:
            self.fahrzeug.losfahren()

    @property
    def zuendung(self) -> bool:
        """Zündung aus: kein Steuergerät antwortet mehr, eine laufende Verbindung bricht ab.
        Das Kabel selbst hängt an Dauerplus (OBD-Pin 16) und liefert weiter sein Echo."""
        return self._zuendung

    @zuendung.setter
    def zuendung(self, an: bool) -> None:
        self._zuendung = bool(an)
        if not an:
            if self._aktiv is not None:
                self._aktiv._zustand = "aus"
            self._aktiv = None
            self._fast_puffer = None

    def echo_auslassen_nach(self, bytes_: int) -> None:
        """Beim n-ten folgenden gesendeten Byte kein Echo liefern (Kabel kurz weg)."""
        self._echo_aus_in = bytes_

    def ausgeben(self, daten: bytes, pause: float = 0.0, byte_zeit: float | None = None) -> None:
        schritt = self.byte_zeit if byte_zeit is None else byte_zeit
        t = max(time.monotonic(), self._frei_ab) + pause
        for byte in daten:
            t += schritt
            bisect.insort(self._rx, (t, next(self._nummer), byte))
        self._frei_ab = t

    def set_baudrate(self, baud: int) -> int:
        self.baud = baud
        return baud

    def fast_init_puls(self) -> None:
        """Weckmuster des Fast-Init: wer danach mit StartCommunication an seine
        Kopfadresse angesprochen wird, antwortet."""
        if self.echtzeit:
            time.sleep(0.35)
        self.fast_inits += 1
        self._rx.clear()
        self._frei_ab = 0.0
        if self._aktiv is not None:
            self._aktiv._zustand = "aus"
        self._aktiv = None
        self._fast_puffer = bytearray()

    def _fast_init_byte(self, byte: int) -> None:
        puffer = self._fast_puffer
        puffer.append(byte)
        laenge = kwp_laenge(puffer)
        if laenge is None or len(puffer) < laenge:
            return
        self._fast_puffer = None
        nachricht = bytes(puffer)
        if not self._zuendung:
            return
        if (sum(nachricht[:-1]) & 0xFF) != nachricht[-1] or not nachricht[0] & 0x80:
            return
        if nachricht[3:-1] != b"\x81":
            return
        for ecu in self.steuergeraete.values():
            if (getattr(ecu, "fast_init", False) and ecu.kopf == nachricht[1]
                    and ecu.baud == self.baud):
                self._aktiv = ecu
                ecu.fast_init_start(self, nachricht)
                return

    def send_5baud(self, address: int) -> None:
        time.sleep(self.reizung_dauer)
        self._rx.clear()
        self._frei_ab = 0.0
        self._aktiv = None
        self._fast_puffer = None
        self.reizungen.append(address)
        ecu = self.steuergeraete.get(address)
        if ecu is None or not self._zuendung:
            return
        if getattr(ecu, "reizbar", None) is not None and not ecu.reizbar():
            self.abgewiesen.append(address)
            return          # nimmt gerade keine Verbindung an (z. B. ABS während der Fahrt)
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
            elif self._fast_puffer is not None:
                self._fast_init_byte(byte)

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


UEBERSETZUNG = {1: 7.0, 2: 13.1, 3: 18.7, 4: 25.0, 5: 32.2}   # km/h je 1000/min (Polo 6KV)


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
    Landstraße, Schub, Ort mit einem Ampelhalt (Fuß auf der Bremse), einer
    Rechtskurve und Bremsungen, Halt.
    Angelehnt an eine aufgezeichnete Fahrt: Kühlmittel bleibt bei etwa 78 °C,
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
        self.geparkt = False          # steht mit laufendem Motor (Start-/Abschlussprüfung)
        self.motor_aus = False        # Zündung an, Motor aus (z. B. für die Grundeinstellung)
        self._runde_ab = 0.0          # Motorlauf-Sekunden, ab denen die Runde zählt

    def losfahren(self) -> None:
        """Nach dem Parken: die Runde beginnt jetzt von vorn."""
        self.geparkt = False
        self._runde_ab = max(0.0, self.t() - self.motor_start_nach - 1.2)

    def t(self) -> float:
        return (time.monotonic() - self.t0) * self.zeitfaktor

    @staticmethod
    def _tempo(tz: float) -> tuple[float, str]:
        """Tempo und Fahrzustand innerhalb einer Runde."""
        punkte = [(0, 0, "leerlauf"), (20, 0, "vollgas"), (35, 100, "reise"),
                  (110, 100, "schub"), (140, 50, "ort"), (148, 50, "bremse"),
                  (156, 0, "ampel"), (166, 0, "beschleunigen"), (175, 50, "ort"),
                  (190, 50, "bremse"), (205, 0, "leerlauf"), (240, 0, "leerlauf")]
        for (t1, v1, art), (t2, v2, _) in zip(punkte, punkte[1:]):
            if t1 <= tz < t2:
                return v1 + (v2 - v1) * (tz - t1) / (t2 - t1), art
        return 0.0, "leerlauf"

    def zustand(self) -> Zustand:
        z = self._profil_zustand()
        if self.motor_aus:
            # Zündung an, Motor aus – die Temperaturen bleiben, wo sie gerade sind
            z.motor_an, z.n, z.u, z.p, z.dk, z.zw, z.last, z.ti = False, 0, 12.4, 980, 0, 0, 100, 0
            z.v, z.lam, z.lambda_aktiv, z.schub, z.lastzustand = 0.0, 0.0, False, False, 5
            z.kurve = 0.0
        return z

    def _profil_zustand(self) -> Zustand:
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
        tz = max(0.0, lauf - self._runde_ab) % self.RUNDE
        v, art = (0.0, "leerlauf") if self.geparkt else self._tempo(tz)
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
            "ampel": (300, 4.3, 8, 19, 4.5, 5),
        }[art]
        z.p, z.dk, z.zw, z.last, z.ti, z.lastzustand = werte
        z.schub = art in ("schub", "bremse") and z.n > 1100
        if art in ("schub", "bremse") and not z.schub:      # unter 1100/min: wieder Leerlauf
            z.p, z.dk, z.zw, z.last, z.ti, z.lastzustand = (300, 4.3, 8, 19, 4.5, 5)
        z.bremse = art in ("bremse", "ampel")      # an der Ampel steht der Fuß auf der Bremse
        z.lam = 0.0 if (z.schub or not z.lambda_aktiv) else 5 * math.sin(lauf * 2.1)
        z.p = _rauschen(z.p, 8)
        if v < 3:
            z.tank = self.TANK_STAND
        else:
            schwappen = 15 if z.bremse else 8
            z.tank = min(43, max(2, _rauschen(self.TANK_FAHRT, schwappen)))
        # Rechtskurve nur, solange das Auto fährt – geparkt stehen alle Räder (seit 0.8.1;
        # vorher meldete das Sim-ABS dann alle 240 Profil-Sekunden 1 / 0 / 1 / 0 km/h)
        z.kurve = 2.0 if 177 <= tz < 183 and v > 3 else 0.0
        return z


def _drehzahl(z: Zustand) -> tuple[int, int, int]:
    return (1, 200, _clamp(z.n / 40))                     # 0,2 · a · b /min


def _temperatur(grad: float) -> tuple[int, int, int]:
    return (5, 10, _clamp(100 + grad))                    # a · (b − 100) · 0,1 °C


# Statustexte der Drosselklappen-Anpassung im Simulator – die Nummern echter
# Steuergeräte sind noch nicht bekannt (siehe texte.SIMULATOR)
SIM_ADP_LAEUFT, SIM_ADP_OK, SIM_ADP_FEHLER = 0xF0A1, 0xF0A2, 0xF0A3
SIM_ADP_TEXTE = {
    SIM_ADP_LAEUFT: ("ADP läuft (Simulator)", "ADP running (simulator)"),
    SIM_ADP_OK: ("ADP i.O. (Simulator)", "ADP OK (simulator)"),
    SIM_ADP_FEHLER: ("ADP ERROR (Simulator)", "ADP ERROR (simulator)"),
}
# Stellglieder des simulierten Motors – Nummern ab F0B1, die echte Steuergeräte nach
# bisheriger Kenntnis nicht nutzen; die Namen tragen „(Simulator)“
SIM_STELLGLIEDER = {
    0xF0B1: ("Kraftstoffpumpe (Simulator)", "Fuel pump (simulator)"),
    0xF0B2: ("Magnetventil Aktivkohlebehälter (Simulator)", "EVAP purge valve (simulator)"),
    0xF0B3: ("Einspritzventile (Simulator)", "Injectors (simulator)"),
    0xF0B4: ("Kühlerlüfter (Simulator)", "Radiator fan (simulator)"),
}
# Stellglieder des simulierten Kombis – wie ein Kombi in kw1281test, mit „Ende“ (04AB)
KOMBI_STELLGLIEDER = [0x0296, 0x0295, 0x0298, 0x0297, 0x031E, 0x029A, 0x04AB]
# Stellglieder des simulierten ABS (Nummern nur im Simulator) – damit sich die Warnung vor
# möglichen Schäden ausprobieren lässt; nur wenn alle Räder stehen
SIM_ABS_STELLGLIEDER = {
    0xF0C1: ("Rückförderpumpe (Simulator)", "Return pump (simulator)"),
    0xF0C2: ("Einlassventil vorn links (Simulator)", "Inlet valve front left (simulator)"),
    0xF0C3: ("Auslassventil vorn links (Simulator)", "Outlet valve front left (simulator)"),
}


def motor_steuergeraet(fz: SimFahrzeug | None = None) -> SimEcu:
    """Wie ein ME7.5.10: 001 Drehzahl/Kühlmittel/Lambda/Bits,
    002 Drehzahl/Last/Einspritzzeit/Saugrohrdruck, 003 Drehzahl/Saugrohrdruck/
    Drosselklappe/Zündwinkel, 004 Drehzahl/Spannung/Temperaturen.
    005 (Drehzahl/Last/Tempo/Lastzustand) ist üblich bei ME7, am Auto aber noch
    nicht geprüft."""
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

    # Drosselklappe (E-Gas): Gruppe 060 = Poti 1, Poti 2, Lernschritt, Status. Als
    # Grundeinstellung läuft das Anlernen: acht Lernschritte, dann „ADP i.O.“ – bei
    # laufendem Motor „ADP ERROR“.
    texte.SIMULATOR.update(SIM_ADP_TEXTE)
    dk = {"schritt": 8, "status": SIM_ADP_OK, "start": None, "letzte": -1e9}

    def dk_werte(bewegt: bool) -> list[tuple[int, int, int]]:
        poti1 = 2.7 + (35.0 if bewegt and dk["schritt"] % 2 else 0.0)
        return [(33, 255, _clamp(poti1 * 2.55)), (33, 255, _clamp((85.1 - poti1) * 2.55)),
                (8, 10, dk["schritt"]), (37, dk["status"] >> 8, dk["status"] & 0xFF)]

    def gruppe_060():
        return dk_werte(False)

    def grundeinstellung_060():
        jetzt = time.monotonic()
        if jetzt - dk["letzte"] > 2.0:          # neuer Lauf
            dk["start"] = jetzt
        dk["letzte"] = jetzt
        if fz.zustand().n > 0:
            dk["schritt"], dk["status"] = 0, SIM_ADP_FEHLER
            return dk_werte(False)
        schrittzeit = 0.6 / max(1.0, fz.zeitfaktor)
        dk["schritt"] = min(8, int((jetzt - dk["start"]) / schrittzeit))
        dk["status"] = SIM_ADP_OK if dk["schritt"] >= 8 else SIM_ADP_LAEUFT
        return dk_werte(dk["status"] == SIM_ADP_LAEUFT)

    stellglied.SIMULATOR.update(SIM_STELLGLIEDER)
    return SimEcu(
        0x01,
        [b"SIM906032   ", b"ME7.5 SIMULATION    ", b"S001", b"\x00\x00\x3e\x30\x39"],
        baud=10400,
        fehler=[(16486, 0x23 | 0x80), (16684, 0x23)],
        gruppen={1: gruppe_001, 2: gruppe_002, 3: gruppe_003, 4: gruppe_004, 5: gruppe_005,
                 60: gruppe_060},
        anpassungen={1: 128},
        grundeinstellungen={60: grundeinstellung_060},
        stellglieder=list(SIM_STELLGLIEDER),
        stellglied_bedingung=lambda: fz.zustand().n == 0,   # nur bei stehendem Motor
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
            return [(7, 100, 0xFF)] * 4       # wie ein ABS im Stand: FF-Platzhalter
        return [(7, 100, 2), (7, 100, 1), (7, 100, 1), (7, 100, 1)]

    def gruppe_003():
        z = fz.zustand()
        return [(37, 0, 0xC1 if z.bremse else 0xA7)]   # betätigt / unbetätigt

    stellglied.SIMULATOR.update(SIM_ABS_STELLGLIEDER)
    ecu = SimEcu(
        0x03,
        [b"SIM907379   ", b"ABS SIMULATI", b"ON     V004", b"\x00\x31\x44\x2b\x67"],
        baud=9600,
        gruppen={1: gruppe_001, 2: gruppe_002, 3: gruppe_003},
        stellglieder=list(SIM_ABS_STELLGLIEDER) + [0x04AB],
        stellglied_bedingung=lambda: fz.zustand().v < 1,     # nur wenn alle Räder stehen
    )
    if fz.fahrprofil:
        # wie das ABS im Polo (Mark 20 IE): Verbindung nur im Stand, danach auch beim Anfahren
        ecu.reizbar = lambda: fz.zustand().v < 1
    return ecu


def airbag_steuergeraet() -> SimEcu:
    return SimEcu(
        0x15,
        [b"SIM959655   ", b"AIRBAG SIMUL", b"ATION  0001", b"\x00\x00\x2a\x30\x39"],
        baud=9600,
    )


def kombi_steuergeraet(fz: SimFahrzeug | None = None) -> SimEcu:
    """Wie ein TRW-Kombi: Kilometerstand-Feld FF FF, Öldruck als Text 31,
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
        # Kanal 09 = 123.450 km, falls er der Kilometerstand ist; Kanal 02 = Service-
        # Intervall (zurücksetzen mit 0)
        anpassungen={2: 3, 9: 12345},
        anpassung_zusatz={9: bytes([0xE7, 0x25, 0x00, 0x95, 0x25, 0x01, 0x49,
                                    0x25, 0x01, 0x4A, 0x25, 0x00, 0x6B])},
        anpassung_erlaubt={2: lambda wert: wert == 0, 9: lambda wert: False},
        stellglieder=list(KOMBI_STELLGLIEDER),
    )


def kwp2000_kombisteuergeraet(fz: SimFahrzeug | None = None) -> SimKwpEcu:
    """Kombi mit KWP2000 (Keyword 2027): Messwerte wie das KW1281-Kombi, Anpassung über
    die KWP2000-Routinen – Kanal 02 (Service-Intervall, nur 0) und 09 (nie schreiben) –
    und Stellglieddiagnose."""
    kombi = kombi_steuergeraet(fz)
    return SimKwpEcu(0x17, "SIM920806KWP", "KOMBI KWP2000 SIMULATION", software="0101",
                     keybytes=(0x6B, 0x8F), codierung=1, werkstattcode=(12345, 123, 4567),
                     fehler=[(771, 0x23)], gruppen=kombi.gruppen,
                     anpassungen={2: 3, 9: 12345},
                     anpassung_erlaubt={2: lambda wert: wert == 0, 9: lambda wert: False},
                     stellglieder=list(KOMBI_STELLGLIEDER))


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


def kwp2000_steuergeraet(fz: SimFahrzeug | None = None) -> SimKwpEcu:
    """Ein Gerät mit KWP2000 (Keyword 2027, Kopfadresse = Reizadresse)."""
    fz = fz or SimFahrzeug(fahrprofil=False)

    def gruppe_001():
        z = fz.zustand()
        return [(21, 70, _clamp(z.u / 0.07)), (37, 0, 0x01)]

    return SimKwpEcu(0x56, "SIMKWP2000", "KWP2000 SIMULATION", software="0010",
                     keybytes=(0x6B, 0x8F), codierung=401, werkstattcode=(12345, 123, 4567),
                     fehler=[(771, 0x23)], gruppen={1: gruppe_001},
                     # Kanal 03 nur nach Anmeldung, Kanal 05 mit Messwert (Spannung)
                     anpassungen={1: 5, 3: 300, 5: 1380},
                     anpassung_messwert={5: (21, 70, 197)}, zugriffsschutz={3})


def kwp2000_motorsteuergeraet(fz: SimFahrzeug | None = None) -> SimKwpEcu:
    """Motor mit KWP2000 wie spätere VAG-Motorsteuergeräte: Reizung an 01, Keyword
    2031 (EF 8F), Nachrichten an Kopfadresse 10, auch per Fast-Init erreichbar.
    Messwerte und Fehler wie beim KW1281-Motor des Simulators."""
    kw1281 = motor_steuergeraet(fz)
    return SimKwpEcu(0x01, "SIM906032KWP", "ME7.5 KWP2000 SIMULATION", software="0001",
                     keybytes=(0xEF, 0x8F), kopf=0x10, codierung=71,
                     werkstattcode=(12345, 123, 45678), fehler=kw1281.fehler,
                     gruppen=kw1281.gruppen, fast_init=True, anpassungen={1: 128},
                     stellglieder=kw1281.stellglieder,
                     stellglied_bedingung=kw1281.stellglied_bedingung)


def sim_port(echo: bool = True, echtzeit: bool = True, fahrprofil: bool = True,
             zeitfaktor: float = 1.0, motor_start_nach: float = 0.0,
             kwp2000_motor: bool = False, kwp2000_kombi: bool = False) -> SimPort:
    fz = SimFahrzeug(fahrprofil, zeitfaktor, motor_start_nach)
    motor = kwp2000_motorsteuergeraet(fz) if kwp2000_motor else motor_steuergeraet(fz)
    kombi = kwp2000_kombisteuergeraet(fz) if kwp2000_kombi else kombi_steuergeraet(fz)
    geraete = [motor, abs_steuergeraet(fz), airbag_steuergeraet(), kombi,
               wegfahrsperre(), kwp2000_steuergeraet(fz)]
    kwp = [n for n, an in ((sprache.t("Motor"), kwp2000_motor),
                           (sprache.t("Kombi"), kwp2000_kombi)) if an]
    log.info(sprache.t("Interface: Simulator – keine echten Fahrzeugdaten")
             + (" (" + sprache.t("KWP2000: {geraete}", geraete=", ".join(kwp)) + ")"
                if kwp else ""))
    port = SimPort({g.adresse: g for g in geraete}, echo=echo, echtzeit=echtzeit)
    port.fahrzeug = fz
    return port

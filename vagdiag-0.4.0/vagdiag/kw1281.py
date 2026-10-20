"""KW1281-Protokoll (VAG, K-Leitung).

Ablauf:
  1. Adresse mit 5 Baud senden, Steuergerät antwortet mit 0x55 (Sync) und zwei
     Keybytes. Keyword = (KB2 & 0x7F) * 128 + (KB1 & 0x7F); 1281 = KW1281.
  2. Tester schickt das invertierte KB2, danach sendet das Steuergerät seine
     Identifikationsblöcke.
  3. Blöcke: [Länge][Zähler][Titel][Daten …][03]. Jedes Byte außer dem
     Blockende quittiert der Empfänger mit dem invertierten Byte.
  4. Jeder Block des Testers wird mit genau einem Block beantwortet. Hat das
     Steuergerät mehrere Blöcke (Identifikation, Fehlerliste), quittiert der
     Tester jeden mit ACK, bis das Steuergerät selbst ACK schickt.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Sequence

from .fehler import Fehler
from .kline import EchoError, KLine, KLineError, Timeout
from .messwerte import Messwert, gruppe_auswerten
from .port import PortError
from .sprache import N_, t

log = logging.getLogger("vagdiag.proto")

# Blocktitel
KENNUNG_ANFORDERN = 0x00   # Zusatzkennung (z. B. Fahrgestellnummer, Immo-ID)
ACK = 0x09
NAK = 0x0A
ENDE = 0x06
FEHLER_LOESCHEN = 0x05
FEHLER_LESEN = 0x07
ANPASSUNG_LESEN = 0x21     # nur lesen – Testen (0x22) und Speichern (0x2A) gibt es hier nicht
GRUPPE_LESEN = 0x29
ANPASSUNG_ANTWORT = 0xE6
ASCII = 0xF6
FEHLER_ANTWORT = 0xFC
GRUPPE_ANTWORT = 0xE7

TITEL = {
    KENNUNG_ANFORDERN: N_("Zusatzkennung anfordern"),
    ACK: "ACK", NAK: "NAK", ENDE: N_("Ende"), FEHLER_LOESCHEN: N_("Fehler löschen"),
    FEHLER_LESEN: N_("Fehler lesen"), GRUPPE_LESEN: N_("Messwertgruppe lesen"),
    ANPASSUNG_LESEN: N_("Anpassung lesen"), ANPASSUNG_ANTWORT: N_("Anpassungswert"),
    ASCII: N_("Kennung"), FEHLER_ANTWORT: N_("Fehlerliste"), GRUPPE_ANTWORT: N_("Messwerte"),
}


# --------------------------------------------------------------------------
# Fehlerklassen
# --------------------------------------------------------------------------
class DiagError(Exception):
    """Basisklasse aller Diagnosefehler."""


class NoResponse(DiagError):
    """Steuergerät reagiert nicht auf die Reizung."""


class WrongBaud(DiagError):
    """Antwort empfangen, aber nicht lesbar – vermutlich andere Baudrate."""


class UnsupportedProtocol(DiagError):
    def __init__(self, text: str, keyword: int | None = None,
                 protocol: str | None = None, baud: int | None = None):
        super().__init__(text)
        self.keyword = keyword
        self.protocol = protocol
        self.baud = baud


class ProtocolError(DiagError):
    """Handshake gestört – die Verbindung ist damit beendet."""


class Nak(DiagError):
    """Steuergerät lehnt die Anfrage ab (Funktion nicht unterstützt)."""


class NotAvailable(DiagError):
    """Angefragte Daten gibt es in diesem Steuergerät nicht."""


class NotConnected(DiagError):
    pass


class Abgebrochen(DiagError):
    """Vom Benutzer abgebrochen (z. B. Stopp während des Neuverbindens)."""


class Stoerung(DiagError):
    """Antwort passt nicht zur Anfrage (falscher Blockzähler, unerwarteter
    Blocktyp, anderes Format als bisher). Die Verbindung steht noch; die
    Anfrage sollte wiederholt werden."""

    def __init__(self, text: str, art: str):
        super().__init__(text)
        self.art = art          # "zaehler", "titel" oder "format"


# Längere Blöcke kommen bei KW1281 nicht vor – so ein Längenbyte ist eine Störung.
MAX_BLOCKLAENGE = 0x80


# --------------------------------------------------------------------------
@dataclass
class Timing:
    sync_timeout: float = 0.8      # Stoppbit (200 ms) + W1 (bis 300 ms) + Reserve
    keybyte_timeout: float = 0.3
    w4: float = 0.03               # Pause vor dem invertierten KB2 (25–50 ms)
    retry_pause: float = 1.2       # vor erneuter Reizung mit anderer Baudrate
    byte_timeout: float = 0.3      # Warten auf Komplement bzw. nächstes Byte
    block_timeout: float = 1.5     # Warten auf den Anfang eines Antwortblocks
    inter_byte: float = 0.001      # Pause zwischen eigenen Bytes
    ack_delay: float = 0.0         # Pause vor dem eigenen Komplement
    reconnect_pause: float = 2.5   # nach Abbruch, bis das Steuergerät wieder bereit ist


@dataclass
class Block:
    zaehler: int
    titel: int
    daten: bytes = b""

    def __str__(self) -> str:
        name = t(TITEL.get(self.titel, "?"))
        hexdaten = " ".join(f"{b:02X}" for b in self.daten)
        text = f"Block {self.zaehler:02X} {self.titel:02X} ({name})"
        if self.daten:
            text += f" [{hexdaten}]"
            if self.titel == ASCII:
                klartext = als_text(self.daten)
                if klartext is not None:
                    text += f" '{klartext}'"
        return text


def als_text(daten: bytes) -> str | None:
    """Kennungsblock als Text. Bit 7 des ersten Zeichens ist ein Merker
    („Zusatzkennung vorhanden“) und gehört nicht zum Zeichen."""
    if not daten:
        return ""
    roh = bytes([daten[0] & 0x7F]) + daten[1:]
    if all(0x20 <= b < 0x7F for b in roh):
        return roh.decode("ascii")
    return None


def _hex(daten: bytes) -> str:
    return " ".join(f"{b:02X}" for b in daten)


@dataclass
class Anpassung:
    """Gelesener Anpassungswert (16 Bit, wie VCDS ihn unter „Anpassung“ zeigt).

    Manche Steuergeräte hängen an die Antwort Messwerte an (Titel E7 und
    Dreiergruppen) – z. B. beschreibt das TRW-Kombi Kanal 09 so als
    „Kilometerstand in 10 km“."""
    kanal: int
    wert: int
    daten: bytes = b""
    messwerte: list[Messwert] = field(default_factory=list)

    @property
    def hex(self) -> str:
        return f"{self.wert:04X}"

    @property
    def beschreibung(self) -> str:
        """Mitgeschickte Messwerte als Text; Silbentrennung („Kilometer-“ +
        „stand“) wird zusammengezogen."""
        text = ""
        for m in self.messwerte:
            teil = m.text.strip()
            if not teil or teil == "–":
                continue
            if text.endswith("-"):
                text = text[:-1] + teil
            else:
                text = f"{text} {teil}" if text else teil
        return text

    @property
    def text(self) -> str:
        text = t("Kanal {kanal:02d}: {wert} (hex {hex})", kanal=self.kanal, wert=self.wert,
                 hex=self.hex)
        if self.beschreibung:
            text += f" – {self.beschreibung}"
        return text


@dataclass
class Verbindung:
    adresse: int
    protokoll: str
    keyword: int
    baud: int
    echo: bool | None
    bloecke: list[Block] = field(default_factory=list)
    zusatzbloecke: list[Block] = field(default_factory=list)

    def _kennung(self) -> list[Block]:
        return [b for b in self.bloecke if b.titel == ASCII]

    def _codierblock(self) -> bytes | None:
        """Block mit Codierung und Werkstattcode: 5 Bytes, kein Text."""
        for blk in self._kennung()[1:]:
            if len(blk.daten) == 5 and als_text(blk.daten) is None:
                return blk.daten
        return None

    @property
    def hat_zusatzkennung(self) -> bool:
        kennung = self._kennung()
        return bool(kennung and kennung[0].daten and kennung[0].daten[0] & 0x80)

    @property
    def teilenummer(self) -> str:
        kennung = self._kennung()
        text = als_text(kennung[0].daten) if kennung else None
        return (text or "").strip()

    @property
    def bauteil(self) -> str:
        teile = [als_text(b.daten) for b in self._kennung()[1:]]
        return "".join(x for x in teile if x is not None).strip()

    @property
    def codierung(self) -> int | None:
        d = self._codierblock()
        return None if d is None else ((d[1] << 8) | d[2]) >> 1

    @property
    def werkstattcode(self) -> int | None:
        d = self._codierblock()
        return None if d is None else ((d[2] & 0x01) << 16) | (d[3] << 8) | d[4]

    @property
    def zusatzkennung(self) -> str:
        """z. B. Fahrgestellnummer und Immo-ID bei der Wegfahrsperre."""
        teile = [als_text(b.daten) for b in self.zusatzbloecke if b.titel == ASCII]
        return "".join(x for x in teile if x is not None).strip()

    @property
    def zusatzdaten(self) -> list[str]:
        """Übrige Kennungsblöcke, die kein Text sind, als Hex."""
        codier = self._codierblock()
        return [_hex(blk.daten) for blk in self._kennung()[1:]
                if als_text(blk.daten) is None and blk.daten != codier]


# --------------------------------------------------------------------------
class KW1281:
    def __init__(self, kline: KLine, timing: Timing | None = None):
        self.kl = kline
        self.timing = timing or Timing()
        self.zaehler: int | None = None
        self.verbunden = False
        self.verbindung: Verbindung | None = None
        self.toleranz = True   # ein gestörtes Komplement/Echo pro Block hinnehmen
        self._zaehler_abweichung = False
        self._signaturen: dict[int, tuple[int, ...]] = {}   # Gruppe → Formeltypen
        self._kandidaten: dict[int, tuple[int, ...]] = {}

    # ---------------------------------------------------------------- Aufbau
    def connect(self, adresse: int, bauds: Sequence[int] = (10400, 9600)) -> Verbindung:
        self.verbunden = False
        self.verbindung = None
        letzter: DiagError | None = None
        for i, baud in enumerate(bauds):
            if i:
                time.sleep(self.timing.retry_pause)
            try:
                return self._connect_einmal(adresse, baud)
            except WrongBaud as exc:
                log.info("%s", exc)
                letzter = exc
        raise WrongBaud(t(
            "Steuergerät {adresse:02X} antwortet, aber bei keiner der Baudraten {bauds} "
            "lesbar. Letzter Befund: {befund}", adresse=adresse,
            bauds=", ".join(map(str, bauds)), befund=letzter))

    def _connect_einmal(self, adresse: int, baud: int) -> Verbindung:
        self._signaturen.clear()
        self._kandidaten.clear()
        try:
            self.kl.set_baudrate(baud)
            log.info(t("Reize Adresse %02X (Empfang mit %d Baud) …"), adresse, baud)
            self.kl.send_5baud(adresse)
            self._warte_auf_sync(adresse, baud)
            try:
                kb1 = self.kl.read_byte(self.timing.keybyte_timeout)
                kb2 = self.kl.read_byte(self.timing.keybyte_timeout)
            except Timeout:
                raise WrongBaud(t("Sync bei {baud} Baud, aber keine Keybytes",
                                  baud=baud)) from None
            keyword = ((kb2 & 0x7F) << 7) | (kb1 & 0x7F)
            log.info(t("Sync 55, Keybytes %02X %02X → Keyword %d"), kb1, kb2, keyword)
            ist_kwp2000 = (kb2 & 0x7F) == 0x0F
            if keyword != 1281 and not ist_kwp2000:
                raise WrongBaud(t("Unbekannte Keybytes {kb1:02X} {kb2:02X} bei {baud} Baud",
                                  kb1=kb1, kb2=kb2, baud=baud))
            time.sleep(self.timing.w4)
            self.kl.write_byte(kb2 ^ 0xFF)
            if ist_kwp2000:
                try:
                    inv = self.kl.read_byte(self.timing.keybyte_timeout)
                    log.info(t("KWP2000-Bestätigung (invertierte Adresse): %02X"), inv)
                except Timeout:
                    pass
                raise UnsupportedProtocol(
                    t("Steuergerät {adresse:02X} spricht KWP2000 (Keybytes {kb1:02X} "
                      "{kb2:02X}, Keyword {keyword}, {baud} Baud). Dieses Protokoll ist in "
                      "dieser Version noch nicht eingebaut.", adresse=adresse, kb1=kb1,
                      kb2=kb2, keyword=keyword, baud=baud),
                    keyword=keyword, protocol="KWP2000", baud=baud)
            self.zaehler = None
            bloecke = self._empfange_bis_ack()
            verbindung = Verbindung(adresse, "KW1281", keyword, baud, self.kl.echo, bloecke)
            if verbindung.hat_zusatzkennung:
                # Bit 7 im ersten Zeichen: es gibt eine Zusatzkennung
                # (bei der Wegfahrsperre z. B. Fahrgestellnummer und Immo-ID).
                self._sende_block(KENNUNG_ANFORDERN)
                try:
                    verbindung.zusatzbloecke = self._empfange_bis_ack()
                except Nak:
                    log.info(t("Zusatzkennung angekündigt, aber abgelehnt"))
        except (KLineError, PortError) as exc:
            raise ProtocolError(t("Verbindungsaufbau abgebrochen: {fehler}",
                                  fehler=exc)) from exc
        self.verbindung = verbindung
        self.verbunden = True
        log.info(t("Verbunden mit %02X: %s %s%s"), adresse, verbindung.teilenummer,
                 verbindung.bauteil,
                 t(" – Codierung {codierung:05d}, WSC {wsc:05d}", codierung=verbindung.codierung,
                   wsc=verbindung.werkstattcode)
                 if verbindung.codierung is not None else "")
        if verbindung.zusatzkennung:
            log.info(t("Zusatzkennung: %s"), verbindung.zusatzkennung)
        return self.verbindung

    def _warte_auf_sync(self, adresse: int, baud: int) -> None:
        ende = time.perf_counter() + self.timing.sync_timeout
        while True:
            rest = ende - time.perf_counter()
            try:
                if rest <= 0:
                    raise Timeout(t("Sync-Zeit abgelaufen"))
                byte = self.kl.read_byte(rest)
            except Timeout:
                raise NoResponse(t(
                    "Keine Antwort von Adresse {adresse:02X}. Zündung an? Steuergerät "
                    "vorhanden? Kabel an OBD-Pin 7?", adresse=adresse)) from None
            if byte == 0x55:
                return
            if byte == 0x00:
                continue  # Reste der Reizung
            raise WrongBaud(t("Byte {byte:02X} statt Sync 55 bei {baud} Baud", byte=byte,
                              baud=baud))

    # ---------------------------------------------------------------- Blöcke
    def _quittiere(self, byte: int) -> None:
        if self.timing.ack_delay:
            time.sleep(self.timing.ack_delay)
        self.kl.write_byte(byte ^ 0xFF)

    def _rest_verwerfen(self, dauer: float) -> None:
        """Nach einer Störung: kurz warten und nachlaufende Bytes verwerfen."""
        ende = time.perf_counter() + dauer
        while True:
            rest = ende - time.perf_counter()
            if rest <= 0:
                return
            try:
                byte = self.kl.read_byte(rest)
                log.debug(t("Verworfen nach Störung: %02X"), byte)
            except Timeout:
                return

    def _sende_block(self, titel: int, daten: bytes = b"") -> None:
        self.zaehler = 1 if self.zaehler is None else (self.zaehler + 1) & 0xFF
        roh = bytes([len(daten) + 3, self.zaehler, titel]) + bytes(daten) + b"\x03"
        log.debug("→ %s", Block(self.zaehler, titel, bytes(daten)))
        toleriert = False
        for i, byte in enumerate(roh):
            if i and self.timing.inter_byte:
                time.sleep(self.timing.inter_byte)
            try:
                self.kl.write_byte(byte)
            except EchoError as exc:
                if not self.toleranz or toleriert:
                    raise
                # z. B. beim Anlassen: das Kabel hängt an der Bordspannung.
                # Das Komplement des Steuergeräts kann trotzdem kommen.
                toleriert = True
                log.warning(t("Störung: %s – versuche weiterzumachen"), exc)
            if i == len(roh) - 1:
                return  # Blockende wird nicht quittiert
            try:
                antwort = self.kl.read_byte(self.timing.byte_timeout)
            except Timeout:
                raise ProtocolError(t("Kein Komplement auf Byte {nummer}/{anzahl} ({byte:02X})",
                                      nummer=i + 1, anzahl=len(roh), byte=byte)) from None
            if antwort != byte ^ 0xFF:
                if self.toleranz and not toleriert:
                    # Einzelne gestörte Bytes kommen z. B. beim Spannungseinbruch
                    # während des Anlassens vor. Einmal pro Block weitermachen –
                    # war das Steuergerät wirklich weg, scheitert das nächste Byte.
                    toleriert = True
                    log.warning(t("Störung: Komplement %02X auf %02X (erwartet %02X) – "
                                  "versuche weiterzumachen"), antwort, byte, byte ^ 0xFF)
                    self._rest_verwerfen(0.03)
                    continue
                raise ProtocolError(t(
                    "Falsches Komplement {antwort:02X} auf {byte:02X} (erwartet {soll:02X})",
                    antwort=antwort, byte=byte, soll=byte ^ 0xFF))

    def _empfange_block(self) -> Block:
        try:
            laenge = self.kl.read_byte(self.timing.block_timeout)
        except Timeout:
            raise ProtocolError(t("Steuergerät antwortet nicht mehr")) from None
        if laenge < 3 or laenge > MAX_BLOCKLAENGE:
            raise ProtocolError(t("Ungültige Blocklänge {laenge:02X}", laenge=laenge))
        toleriert = False

        def quittieren(byte: int) -> None:
            nonlocal toleriert
            try:
                self._quittiere(byte)
            except EchoError as exc:
                if not self.toleranz or toleriert:
                    raise
                toleriert = True
                log.warning(t("Störung: %s – versuche weiterzumachen"), exc)

        quittieren(laenge)
        inhalt = []
        for i in range(laenge - 1):
            try:
                byte = self.kl.read_byte(self.timing.byte_timeout)
            except Timeout:
                raise ProtocolError(t("Block bricht nach {anzahl} Bytes ab",
                                      anzahl=i + 1)) from None
            quittieren(byte)
            inhalt.append(byte)
        try:
            ende = self.kl.read_byte(self.timing.byte_timeout)
        except Timeout:
            raise ProtocolError(t("Blockende fehlt")) from None
        if ende != 0x03:
            raise ProtocolError(t("Blockende {ende:02X} statt 03", ende=ende))
        zaehler, titel, daten = inhalt[0], inhalt[1], bytes(inhalt[2:])
        if self.zaehler is not None and zaehler != (self.zaehler + 1) & 0xFF:
            log.warning(t("Blockzähler %02X statt %02X – übernehme"),
                        zaehler, (self.zaehler + 1) & 0xFF)
            self._zaehler_abweichung = True
        self.zaehler = zaehler
        block = Block(zaehler, titel, daten)
        log.debug("← %s", block)
        return block

    def _empfange_bis_ack(self) -> list[Block]:
        bloecke = []
        while True:
            block = self._empfange_block()
            if block.titel == ACK:
                return bloecke
            if block.titel == NAK:
                raise Nak(t("Steuergerät lehnt ab ({block})", block=block))
            bloecke.append(block)
            self._sende_block(ACK)

    # ------------------------------------------------------- Grundfunktionen
    def _pruefe(self) -> None:
        if not self.verbunden:
            raise NotConnected(t("Keine Verbindung zum Steuergerät"))

    def _sicher(self, funktion, *args):
        """Leitungsfehler beenden die Verbindung, Ablehnungen nicht."""
        self._pruefe()
        try:
            return funktion(*args)
        except (Nak, NotAvailable):
            raise
        except (KLineError, PortError) as exc:
            self.verbunden = False
            raise ProtocolError(str(exc)) from exc
        except ProtocolError:
            self.verbunden = False
            raise

    def austausch(self, titel: int, daten: bytes = b"") -> Block:
        """Einen Block senden, genau einen Antwortblock empfangen."""
        def ablauf():
            self._zaehler_abweichung = False
            self._sende_block(titel, daten)
            return self._empfange_block()
        return self._sicher(ablauf)

    def transaktion(self, titel: int, daten: bytes = b"") -> list[Block]:
        """Block senden, alle Antwortblöcke bis zum ACK des Steuergeräts holen."""
        def ablauf():
            self._zaehler_abweichung = False
            self._sende_block(titel, daten)
            return self._empfange_bis_ack()
        return self._sicher(ablauf)

    # -------------------------------------------------------------- Funktionen
    def fehler_lesen(self) -> list[Fehler]:
        return _fehler_auswerten(self.transaktion(FEHLER_LESEN))

    def fehler_loeschen(self) -> list[Fehler]:
        """Löscht den Fehlerspeicher; zurück kommen ggf. sofort wieder gesetzte Fehler."""
        log.info(t("Fehlerspeicher wird gelöscht"))
        return _fehler_auswerten(self.transaktion(FEHLER_LOESCHEN))

    def gruppe_lesen(self, gruppe: int) -> list[Messwert]:
        if not 0 <= gruppe <= 255:
            raise ValueError(t("Messwertgruppe muss zwischen 0 und 255 liegen"))
        block = self.austausch(GRUPPE_LESEN, bytes([gruppe]))
        if self._zaehler_abweichung:
            # z. B. wiederholt das Steuergerät nach einer gestörten Anfrage
            # seine vorige Antwort – die gehört zu einer anderen Gruppe
            raise Stoerung(t("Antwort auf Gruppe {gruppe:03d} mit falschem Blockzähler "
                             "verworfen", gruppe=gruppe), "zaehler")
        if block.titel == GRUPPE_ANTWORT:
            werte = gruppe_auswerten(block.daten)
            self._format_pruefen(gruppe, werte)
            return werte
        if block.titel == ACK:
            raise NotAvailable(t("Messwertgruppe {gruppe:03d} ist nicht belegt", gruppe=gruppe))
        if block.titel == NAK:
            raise Nak(t("Messwertgruppe {gruppe:03d} abgelehnt", gruppe=gruppe))
        raise Stoerung(t(
            "Messwertgruppe {gruppe:03d}: unerwartete Antwort {titel:02X} (gestört oder noch "
            "nicht auswertbar)", gruppe=gruppe, titel=block.titel), "titel")

    def _format_pruefen(self, gruppe: int, werte: list[Messwert]) -> None:
        """Jede Gruppe hat feste Formeltypen. Weicht eine Antwort davon ab,
        gehört sie vermutlich zu einer anderen Anfrage. Kommt das neue Format
        zweimal hintereinander, gilt es (manche Steuergeräte wechseln es)."""
        signatur = tuple(w.typ for w in werte)
        bekannt = self._signaturen.get(gruppe)
        if bekannt is None or signatur == bekannt:
            self._signaturen[gruppe] = signatur
            self._kandidaten.pop(gruppe, None)
            return
        if self._kandidaten.get(gruppe) == signatur:
            log.info(t("Gruppe %03d: Format geändert, übernehme"), gruppe)
            self._signaturen[gruppe] = signatur
            self._kandidaten.pop(gruppe, None)
            return
        self._kandidaten[gruppe] = signatur
        raise Stoerung(t("Antwort auf Gruppe {gruppe:03d} hat ein anderes Format als bisher "
                         "– verworfen", gruppe=gruppe), "format")

    def anpassung_lesen(self, kanal: int) -> Anpassung:
        """Wert eines Anpassungskanals lesen. Ändert nichts am Steuergerät.

        Kanal 00 wird bewusst nie angesprochen: bei vielen Steuergeräten
        steht er für „alle Anpassungswerte löschen“."""
        if not 1 <= kanal <= 255:
            raise ValueError(t("Anpassungskanal muss zwischen 1 und 255 liegen (Kanal 00 "
                               "wird bewusst nicht angesprochen)"))
        block = self.austausch(ANPASSUNG_LESEN, bytes([kanal]))
        if self._zaehler_abweichung:
            raise Stoerung(t("Antwort auf Kanal {kanal:02d} mit falschem Blockzähler "
                             "verworfen", kanal=kanal), "zaehler")
        if block.titel == ANPASSUNG_ANTWORT and len(block.daten) >= 3:
            if block.daten[0] != kanal:
                log.warning(t("Antwort für Kanal %02d statt %02d"), block.daten[0], kanal)
            rest = block.daten[3:]
            messwerte = (gruppe_auswerten(rest[1:])
                         if rest[:1] == bytes([GRUPPE_ANTWORT]) and len(rest) >= 4 else [])
            anpassung = Anpassung(kanal, (block.daten[1] << 8) | block.daten[2],
                                  block.daten, messwerte)
            log.info(t("Anpassung gelesen: %s"), anpassung.text)
            return anpassung
        if block.titel == NAK:
            raise Nak(t("Anpassungskanal {kanal:02d} abgelehnt – nicht vorhanden oder nur "
                        "nach Anmeldung (Login) lesbar", kanal=kanal))
        if block.titel == ACK:
            raise NotAvailable(t("Anpassungskanal {kanal:02d} ist nicht belegt", kanal=kanal))
        raise NotAvailable(t(
            "Anpassungskanal {kanal:02d}: Antworttyp {titel:02X} wird nicht ausgewertet "
            "({block})", kanal=kanal, titel=block.titel, block=block))

    def keep_alive(self) -> None:
        block = self.austausch(ACK)
        if block.titel != ACK:
            log.warning(t("Unerwartete Antwort auf Keep-Alive: %s"), block)

    def trennen(self) -> None:
        if self.verbunden:
            try:
                self._sende_block(ENDE)
            except (KLineError, PortError, ProtocolError) as exc:
                log.debug(t("Trennen: %s"), exc)
            log.info(t("Verbindung beendet"))
        self.verbunden = False


def _fehler_auswerten(bloecke: list[Block]) -> list[Fehler]:
    fehler = []
    for block in bloecke:
        if block.titel != FEHLER_ANTWORT:
            log.warning(t("Unerwarteter Block in der Fehlerliste: %s"), block)
            continue
        d = block.daten
        for i in range(0, len(d) - 2, 3):
            code = (d[i] << 8) | d[i + 1]
            status = d[i + 2]
            if code == 0xFFFF and status == 0x88:
                continue  # „Kein Fehler erkannt“
            fehler.append(Fehler(code, status))
    return fehler

"""KW1281-Protokoll (VAG, K-Leitung) – und der Einstieg für KWP2000.

Ablauf:
  1. Adresse mit 5 Baud senden, Steuergerät antwortet mit 0x55 (Sync) und zwei
     Keybytes. Keyword = (KB2 & 0x7F) * 128 + (KB1 & 0x7F); 1281 = KW1281.
  2. Tester schickt das invertierte KB2, danach sendet das Steuergerät seine
     Identifikationsblöcke.
  3. Blöcke: [Länge][Zähler][Titel][Daten …][03]. Jedes Byte außer dem
     Blockende quittiert der Empfänger mit dem invertierten Byte. Stimmt eins
     davon nicht, bricht vagdiag seinen Block sofort ab (siehe _sende_block).
  4. Jeder Block des Testers wird mit genau einem Block beantwortet. Hat das
     Steuergerät mehrere Blöcke (Identifikation, Fehlerliste), quittiert der
     Tester jeden mit ACK, bis das Steuergerät selbst ACK schickt.

Meldet sich das Steuergerät mit einem Keyword 2000–2031 (KB2 = 8F), spricht es
KWP2000. Dann übernimmt kwp2000.py nach dem Handshake; Fehlerspeicher,
Messwertblöcke usw. laufen über dieselben Methoden dieser Klasse.

Schreibsperre: Jeder Block läuft durch _sende_block. Ohne Weiteres gehen nur
lesende Blöcke (und „Fehlerspeicher löschen“, das die Oberfläche vorher
bestätigen lässt). Grundeinstellung (28), Anpassung testen (22) und speichern
(2A) sowie die Stellglieddiagnose (04) gehen nur im Expertenmodus und nur
innerhalb einer Freigabe, die genau diese Gruppe, diesen Kanal und Wert bzw. die
Stellglieddiagnose nennt (siehe experte.py) – für das geöffnete Steuergerät, bis
zum nächsten Verbindungsaufbau. Kanal 00 („alle Anpassungen löschen“, auch nicht
lesend) und Kanal 09 des Kombis (Kilometerstand) bleiben immer gesperrt, alle
übrigen schreibenden Blöcke (Codierung, Login, EEPROM …) ebenfalls. Bremsen, Airbag,
Wegfahrsperre, Lenkung und Niveauregulierung (stellglied.GEFAHR) bekommen nie eine
Grundeinstellung oder Anpassung; ihre Stellglieddiagnose geht nur mit einer Freigabe,
die die Warnung für genau diese Art bestätigt (Freigabe.gefahr). Für KWP2000 gilt
dieselbe Freigabe (siehe kwp2000.py). Testen, Speichern und die Schritte der
Stellglieddiagnose wiederholt vagdiag nie von selbst.
"""

from __future__ import annotations

import gc
import logging
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Sequence

from .fehler import Fehler
from .kline import EchoError, KLine, KLineError, Timeout
from .messwerte import Messwert, gruppe_auswerten, rohwerte_auswerten
from .port import PortError
from .sprache import N_, t
from .stellglied import ARTEN as STELLGLIED_ARTEN
from .stellglied import GEFAHR as STELLGLIED_GEFAHR
from .stellglied import Stellglied, gesperrt_nach_kennung
from .stellglied import gefahr as stellglied_gefahr

log = logging.getLogger("vagdiag.proto")

# Blocktitel
KENNUNG_ANFORDERN = 0x00   # Zusatzkennung (z. B. Fahrgestellnummer, Immo-ID)
STELLGLIED = 0x04          # Stellglieddiagnose – nur Expertenmodus mit Freigabe
ACK = 0x09
NAK = 0x0A
ENDE = 0x06
FEHLER_LOESCHEN = 0x05
FEHLER_LESEN = 0x07
ANPASSUNG_LESEN = 0x21
ANPASSUNG_TESTEN = 0x22    # nur Expertenmodus mit Freigabe
GRUNDEINSTELLUNG = 0x28    # nur Expertenmodus mit Freigabe
GRUPPE_LESEN = 0x29
ROHWERTE_LESEN = 0x12      # Gruppe 000: zehn Rohwerte (VAG 1551/1552 Funktion 08, Gruppe 0)
ANPASSUNG_SPEICHERN = 0x2A  # nur Expertenmodus mit Freigabe
ANPASSUNG_ANTWORT = 0xE6
STELLGLIED_ANTWORT = 0xF5
ASCII = 0xF6
FEHLER_ANTWORT = 0xFC
GRUPPE_ANTWORT = 0xE7
ROHWERTE_ANTWORT = 0xF4

TITEL = {
    KENNUNG_ANFORDERN: N_("Zusatzkennung anfordern"),
    ACK: "ACK", NAK: "NAK", ENDE: N_("Ende"), FEHLER_LOESCHEN: N_("Fehler löschen"),
    FEHLER_LESEN: N_("Fehler lesen"), GRUPPE_LESEN: N_("Messwertgruppe lesen"),
    ANPASSUNG_LESEN: N_("Anpassung lesen"), ANPASSUNG_ANTWORT: N_("Anpassungswert"),
    ANPASSUNG_TESTEN: N_("Anpassung testen"), ANPASSUNG_SPEICHERN: N_("Anpassung speichern"),
    GRUNDEINSTELLUNG: N_("Grundeinstellung"),
    STELLGLIED: N_("Stellglieddiagnose"), STELLGLIED_ANTWORT: N_("Stellglied"),
    ASCII: N_("Kennung"), FEHLER_ANTWORT: N_("Fehlerliste"), GRUPPE_ANTWORT: N_("Messwerte"),
    ROHWERTE_LESEN: N_("Gruppe 000 lesen"), ROHWERTE_ANTWORT: N_("Rohwerte"),
}

# Blöcke, die der Tester ohne Expertenmodus senden darf
LESEND = {KENNUNG_ANFORDERN, ACK, NAK, ENDE, FEHLER_LOESCHEN, FEHLER_LESEN, ANPASSUNG_LESEN,
          GRUPPE_LESEN, ROHWERTE_LESEN}
# … und die einzigen schreibenden, die es überhaupt gibt (nur mit Freigabe)
EXPERTE = {GRUNDEINSTELLUNG, ANPASSUNG_TESTEN, ANPASSUNG_SPEICHERN, STELLGLIED}
KOMBI = 0x17
KILOMETERSTAND_KANAL = 9       # Kombi: nie schreiben (§ 22b StVG)


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


class SchreibenGesperrt(DiagError):
    """Ein Block, der etwas im Steuergerät ändern würde, ist hier nicht erlaubt.
    Es wurde nichts gesendet."""


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
    wechsel_pause: float = 1.0     # … bevor danach ein anderes Steuergerät gereizt wird
    trenn_pause: float = 0.5       # nach dem Trennen, bevor das nächste gereizt wird
    abbruch_ruhe: float = 0.5      # eigener Block abgebrochen: so lange nichts senden, bis
                                   # das Steuergerät den halben Block verworfen hat
    byte_frist: float = 0.015      # eigenes nächstes Byte spätestens so lange nach dem
                                   # Komplement (ein ME7.5 wartete im Auto etwa 45 ms)
    # KWP2000 (siehe kwp2000.py)
    kwp_beruhigen: float = 0.3     # nach der Reizung, vor der ersten Anfrage
    kwp_p2: float = 1.5            # Warten auf den Anfang einer Antwort (Norm: bis 50 ms,
                                   # mit „erweitertem Timing“ bis 1 s)
    kwp_p2_start: float = 1.0      # … beim Ausprobieren von Kopfadresse und Sitzung
    kwp_p2_lang: float = 5.0       # nach „Antwort folgt“ (7F xx 78)
    kwp_p1: float = 0.1            # zwischen zwei Bytes einer Antwort (Norm: bis 20 ms)
    kwp_p3: float = 0.055          # nach einer Antwort, bevor die nächste Anfrage kommt
    kwp_p4: float = 0.005          # zwischen den eigenen Bytes
    kwp_p4_frist: float = 0.018    # … höchstens so lange (Norm P4: bis 20 ms; 2 ms Reserve
                                   # für die Übertragung des Bytes)
    kwp_keepalive: float = 2.0     # Tester present nach so langer Ruhe (P3 max. 5 s)
    kwp_p3_max: float = 5.0        # so lange hält ein Steuergerät die Sitzung ohne Anfrage


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
    Dreiergruppen) – z. B. beschreibt ein TRW-Kombi Kanal 09 so als
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

    codierung_stellen = 5       # KW1281: fünfstellig, KWP2000: siebenstellig

    @property
    def kennung(self) -> tuple[int, str, str]:
        """Woran sich dieses Steuergerät wiedererkennen lässt: Adresse, Teilenummer,
        Bauteil. Eine Rückfrage gilt nur, solange genau dieses Gerät verbunden ist."""
        return (self.adresse, self.teilenummer, self.bauteil)

    @property
    def kennung_text(self) -> str:
        return " ".join(x for x in (self.teilenummer, self.bauteil) if x) or "?"

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


@dataclass
class Freigabe:
    """Was eine Expertenfunktion schreiben darf – genau das, nur bei diesem Steuergerät
    und nur in dieser Verbindung (ein neuer Verbindungsaufbau hebt sie auf)."""
    grundeinstellung: frozenset[int] = frozenset()            # Gruppen
    anpassung: frozenset[tuple[int, int]] = frozenset()       # (Kanal, Wert)
    stellglied: bool = False                                  # Stellglieddiagnose
    adresse: int | None = None                                # nur dieses Steuergerät
    kennung: tuple = ()                                       # … mit dieser Kennung
    gemeldet: set[int] = field(default_factory=set)           # Grundeinstellung im Protokoll
    gefahr: str | None = None                                 # bestätigte Warnung (Art)


# --------------------------------------------------------------------------
class KW1281:
    def __init__(self, kline: KLine, timing: Timing | None = None):
        self.kl = kline
        self.timing = timing or Timing()
        self.zaehler: int | None = None
        self.verbunden = False
        self.verbindung: Verbindung | None = None
        # Ein gestörtes Echo pro Block hinnehmen, wenn das Komplement des Steuergeräts
        # danach stimmt (nie ein falsches Komplement – siehe _sende_block)
        self.toleranz = True
        self._zaehler_abweichung = False
        self._signaturen: dict[int, tuple[int, ...]] = {}   # Gruppe → Formeltypen
        self._kandidaten: dict[int, tuple[int, ...]] = {}
        self._kwp = None          # Kwp2000-Dialog, wenn das Steuergerät KWP2000 spricht
        self.experte = False      # Expertenmodus der Sitzung (siehe session.py)
        self._freigabe: Freigabe | None = None
        # Endete eine Sitzung ohne Endeblock (Abbruch, Störung), hört ihr Steuergerät womöglich
        # noch ein paar Sekunden zu – KW1281-Blöcke tragen keine Adresse. Ein anderes
        # Steuergerät erst danach reizen (siehe DiagSession._pause_vor_reizung).
        self.verloren_um = -1e9
        self.verloren_adresse: int | None = None
        self.verloren_kwp2000 = False
        self._verzug: list[float] = []    # wie schnell dieses Steuergerät quittiert (s)
        self._ohne_gc_tiefe = 0
        self._gc_war_an = True

    def verloren(self, adresse: int | None = None, kwp2000: bool | None = None) -> None:
        """Die Sitzung endet ohne sauberes Ende: festhalten, wann und mit wem."""
        if adresse is None and self.verbindung is not None:
            adresse = self.verbindung.adresse
        if adresse is not None:
            self.verloren_um = time.monotonic()
            self.verloren_adresse = adresse
            self.verloren_kwp2000 = self._kwp is not None if kwp2000 is None else kwp2000
        self.verbunden = False

    @property
    def ist_kwp2000(self) -> bool:
        return self._kwp is not None

    # ---------------------------------------------------------------- Aufbau
    def connect(self, adresse: int, bauds: Sequence[int] = (10400, 9600),
                fast_init: bool = False, pruefung=None) -> Verbindung:
        """Verbinden (KW1281 oder KWP2000, je nach Antwort des Steuergeräts).

        fast_init: beim Motor (Adresse 01) zuerst den KWP2000-Fast-Init probieren,
        ohne Antwort weiter mit der 5-Baud-Reizung.
        pruefung(verbindung): läuft direkt nach der Identifikation; eine Ausnahme
        darin beendet die Verbindung sofort (z. B. beim Airbag)."""
        self.verbunden = False
        self.verbindung = None
        self._kwp = None
        self._freigabe = None     # eine Freigabe gilt nie über einen Verbindungsaufbau hinaus
        self._verzug.clear()
        if fast_init:
            from .kwp2000 import FAST_INIT_ADRESSE
            if adresse == FAST_INIT_ADRESSE:
                try:
                    return self._fast_init(adresse, pruefung)
                except (NoResponse, ProtocolError, UnsupportedProtocol) as exc:
                    log.info(t("Fast-Init: %s – weiter mit der 5-Baud-Reizung"), exc)
                    time.sleep(self.timing.retry_pause)
            else:
                log.info(t("Fast-Init gibt es nur beim Motor (Adresse 01) – nehme die "
                           "5-Baud-Reizung"))
        letzter: DiagError | None = None
        for i, baud in enumerate(bauds):
            if i:
                time.sleep(self.timing.retry_pause)
            try:
                return self._connect_einmal(adresse, baud, pruefung)
            except WrongBaud as exc:
                log.info("%s", exc)
                letzter = exc
        raise WrongBaud(t(
            "Steuergerät {adresse:02X} antwortet, aber bei keiner der Baudraten {bauds} "
            "lesbar. Letzter Befund: {befund}", adresse=adresse,
            bauds=", ".join(map(str, bauds)), befund=letzter))

    def _fast_init(self, adresse: int, pruefung) -> Verbindung:
        """KWP2000-Fast-Init zum Motor (Kopfadresse 10), bis zu drei Versuche – über
        ein USB-Kabel trifft das Weckmuster nicht immer genau."""
        from .kwp2000 import FAST_INIT_KOPF, Kwp2000
        self._signaturen.clear()
        self._kandidaten.clear()
        kwp = Kwp2000(self.kl, self.timing, adresse, 0, 0, 10400, kopf=FAST_INIT_KOPF)
        kwp.schutz = self._schutz
        offen = False             # nach der Antwort auf StartCommunication: Sitzung offen
        try:
            try:
                self.kl.set_baudrate(10400)
                for versuch in range(1, 4):
                    log.info(t("Fast-Init an Kopfadresse %02X (Versuch %d von 3) …"),
                             FAST_INIT_KOPF, versuch)
                    if kwp.fast_init_versuch() is not None:
                        break
                else:
                    raise NoResponse(t("keine Antwort auf den Fast-Init"))
                offen = True
                verbindung = kwp.starten(varianten=[(True, FAST_INIT_KOPF)], pruefung=pruefung)
            except (KLineError, PortError) as exc:
                raise ProtocolError(t("Verbindungsaufbau abgebrochen: {fehler}",
                                      fehler=exc)) from exc
        except BaseException:
            if offen:
                self.verloren(adresse, kwp2000=True)
            raise
        return self._kwp_verbunden(kwp, verbindung)

    def _kwp_verbunden(self, kwp, verbindung: Verbindung) -> Verbindung:
        self._kwp = kwp
        self.verbindung = verbindung
        self.verbunden = True
        return verbindung

    def _connect_einmal(self, adresse: int, baud: int, pruefung=None) -> Verbindung:
        self._signaturen.clear()
        self._kandidaten.clear()
        offen = False             # ab dem invertierten KB2 hat das Steuergerät eine Sitzung
        ist_kwp2000 = False
        try:
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
                offen = True
                if ist_kwp2000:
                    return self._kwp2000_uebernehmen(adresse, keyword, kb1, baud, pruefung)
                self.zaehler = None
                bloecke = self._empfange_bis_ack()
                verbindung = Verbindung(adresse, "KW1281", keyword, baud, self.kl.echo, bloecke)
                if pruefung is not None:
                    try:
                        pruefung(verbindung)
                    except BaseException:
                        offen = not self._ende_senden()
                        raise
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
        except BaseException:
            if offen:             # abgebrochen, ohne dass das Steuergerät ein Ende bekam
                self.verloren(adresse, kwp2000=ist_kwp2000)
            raise
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

    def _kwp2000_uebernehmen(self, adresse: int, keyword: int, kb1: int, baud: int,
                             pruefung) -> Verbindung:
        """Nach dem 5-Baud-Handshake: Bestätigung abwarten, dann KWP2000-Dialog."""
        from .kwp2000 import Kwp2000
        try:
            bestaetigung = self.kl.read_byte(self.timing.keybyte_timeout)
            if bestaetigung == adresse ^ 0xFF:
                log.info(t("KWP2000-Bestätigung (invertierte Adresse): %02X"), bestaetigung)
            else:
                log.warning(t("KWP2000: Bestätigung %02X statt %02X – versuche es trotzdem"),
                            bestaetigung, adresse ^ 0xFF)
        except Timeout:
            log.warning(t("KWP2000: keine Bestätigung (invertierte Adresse) – versuche es "
                          "trotzdem"))
        kwp = Kwp2000(self.kl, self.timing, adresse, keyword, kb1, baud)
        kwp.schutz = self._schutz
        try:
            verbindung = kwp.starten(pruefung=pruefung)
        except (KLineError, PortError) as exc:
            raise ProtocolError(t("Verbindungsaufbau abgebrochen: {fehler}",
                                  fehler=exc)) from exc
        return self._kwp_verbunden(kwp, verbindung)

    def _ende_senden(self) -> bool:
        """Verbindung sofort beenden (Endeblock), Fehler dabei ignorieren. Zurück: ob der
        Endeblock vollständig hinausging."""
        try:
            self._sende_block(ENDE)
            return True
        except (KLineError, PortError, ProtocolError) as exc:
            log.debug(t("Trennen: %s"), exc)
            return False

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

    # ------------------------------------------------------------ Schreibsperre
    @contextmanager
    def schreiben_freigeben(self, grundeinstellung: Sequence[int] = (),
                            anpassung: Sequence[tuple[int, int]] = (),
                            stellglied: bool = False,
                            gefahr: str | None = None) -> Iterator[None]:
        """Für die Dauer des with-Blocks genau diese Schreibzugriffe erlauben –
        nur im Expertenmodus und nur beim gerade geöffneten Steuergerät. Gilt für
        KW1281 und KWP2000. gefahr: die bestätigte Warnung (Art aus stellglied.ARTEN) für
        die Stellglieddiagnose an Bremsen, Airbag, Wegfahrsperre, Lenkung oder
        Niveauregulierung."""
        if not self.experte:
            raise SchreibenGesperrt(t("Schreiben geht nur im Expertenmodus"))
        if not self.verbunden or self.verbindung is None:
            raise SchreibenGesperrt(t("Schreiben geht nur bei einem geöffneten Steuergerät"))
        v = self.verbindung
        if grundeinstellung or anpassung:
            grund = self._nur_stellglied(v.adresse, v.teilenummer, v.bauteil)
            if grund:
                raise SchreibenGesperrt(grund)
        if stellglied:
            grund = self.stellglied_gesperrt(v.adresse, v, gefahr)
            if grund:
                raise SchreibenGesperrt(grund)
        alt = self._freigabe
        self._freigabe = Freigabe(frozenset(grundeinstellung), frozenset(anpassung),
                                  bool(stellglied), v.adresse, v.kennung, gefahr=gefahr)
        try:
            yield
        finally:
            self._freigabe = alt

    def _schutz(self) -> tuple[bool, Freigabe | None]:
        """Stand der Schreibsperre für den KWP2000-Dialog: Expertenmodus und Freigabe."""
        return self.experte, self._freigabe

    @staticmethod
    def stellglied_gesperrt(adresse: int | None, verbindung=None,
                            bestaetigt: str | None = None) -> str | None:
        """Grund, warum die Stellglieddiagnose hier gerade nicht geht (oder None): Die
        Kennung passt nicht zur Adresse – oder es ist ein gefährliches Steuergerät (Bremsen,
        Airbag …) und die Warnung für genau diese Art ist nicht bestätigt (`bestaetigt`).
        verbindung: Verbindung oder Kennung (Adresse, Teilenummer, Bauteil)."""
        if isinstance(verbindung, tuple):
            teilenummer, bauteil = (verbindung[1], verbindung[2]) if len(verbindung) == 3 \
                else ("", "")
        elif verbindung is not None:
            teilenummer, bauteil = verbindung.teilenummer, verbindung.bauteil
        else:
            teilenummer = bauteil = ""
        gefahr, widerspruch = stellglied_gefahr(adresse, teilenummer, bauteil)
        if widerspruch:
            return widerspruch
        if gefahr is not None and bestaetigt != gefahr.art:
            return t("Stellglieddiagnose bei {adresse:02X} ({art}) nur nach bestätigter Warnung "
                     "vor möglichen Schäden", adresse=adresse, art=gefahr.name)
        return None

    @staticmethod
    def _nur_stellglied(adresse: int | None, teilenummer: str, bauteil: str) -> str | None:
        """Grundeinstellung und Anpassung nie bei Bremsen, Airbag, Wegfahrsperre, Lenkung
        und Niveauregulierung – nach Adresse und Kennung."""
        grund = gesperrt_nach_kennung(teilenummer, bauteil)
        if grund is None and adresse in STELLGLIED_GEFAHR:
            grund = t("Grundeinstellung und Anpassung sind bei {adresse:02X} ({art}) in vagdiag "
                      "gesperrt", adresse=adresse, art=t(STELLGLIED_ARTEN[STELLGLIED_GEFAHR[adresse]]))
        return grund

    def _schreibschutz(self, titel: int, daten: bytes) -> None:
        """Wirft SchreibenGesperrt, wenn dieser Block nicht gesendet werden darf."""
        if titel == ANPASSUNG_LESEN and (len(daten) != 1 or daten[0] == 0):
            # Kanal 00 nie, auch nicht lesend (bei manchen Steuergeräten setzt Kanal 00
            # alle Anpassungen zurück)
            raise SchreibenGesperrt(t("Anpassungskanal 00 (alle Anpassungen löschen) ist "
                                      "gesperrt"))
        if titel == ROHWERTE_LESEN and daten:
            # Gruppe 000 kommt ohne Daten aus – alles andere wäre ein unbekannter Block 12
            raise SchreibenGesperrt(t("Block {titel:02X} mit Daten ist in vagdiag gesperrt",
                                      titel=titel))
        if titel in LESEND:
            return
        name = t(TITEL[titel]) if titel in TITEL else f"{titel:02X}"
        if titel not in EXPERTE:
            raise SchreibenGesperrt(t("Block {titel:02X} ({name}) ist in vagdiag gesperrt",
                                      titel=titel, name=name))
        if self.verbindung is None:
            raise SchreibenGesperrt(t("Schreiben geht nur bei einem geöffneten Steuergerät"))
        adresse = self.verbindung.adresse
        if titel == STELLGLIED:
            bestaetigt = self._freigabe.gefahr if self._freigabe is not None else None
            grund = self.stellglied_gesperrt(adresse, self.verbindung, bestaetigt)
        else:
            grund = self._nur_stellglied(adresse, self.verbindung.teilenummer,
                                         self.verbindung.bauteil)
        if grund:
            raise SchreibenGesperrt(grund)
        if titel in (ANPASSUNG_TESTEN, ANPASSUNG_SPEICHERN) and daten:
            if daten[0] == 0:
                raise SchreibenGesperrt(t("Anpassungskanal 00 (alle Anpassungen löschen) ist "
                                          "gesperrt"))
            if adresse == KOMBI and daten[0] == KILOMETERSTAND_KANAL:
                raise SchreibenGesperrt(t("Kanal 09 des Kombis (Kilometerstand) ist gesperrt"))
        if not self.experte or self._freigabe is None:
            raise SchreibenGesperrt(t("{name} geht nur im Expertenmodus über eine "
                                      "Expertenfunktion", name=name))
        if (self._freigabe.adresse != adresse
                or self._freigabe.kennung != self.verbindung.kennung):
            raise SchreibenGesperrt(t("Die Freigabe gilt für ein anderes Steuergerät – "
                                      "{name} gesperrt", name=name))
        if titel == GRUNDEINSTELLUNG:
            erlaubt = bool(daten) and daten[0] in self._freigabe.grundeinstellung
        elif titel == STELLGLIED:
            erlaubt = self._freigabe.stellglied and daten == b"\x00"
        else:
            erlaubt = (len(daten) >= 3
                       and (daten[0], (daten[1] << 8) | daten[2]) in self._freigabe.anpassung)
        if not erlaubt:
            raise SchreibenGesperrt(t("{name} mit {daten} ist nicht freigegeben",
                                      name=name, daten=_hex(daten)))

    def _block_abbrechen(self) -> None:
        """Eigenen Block mittendrin abbrechen: Verbindung gilt als beendet, und bis das
        Steuergerät den unvollständigen Block verworfen hat (es wartet nur kurz auf das
        nächste Byte), geht nichts mehr auf die Leitung – sonst könnten die nächsten Bytes
        den halben Block vervollständigen."""
        self.verloren()
        try:
            self._rest_verwerfen(self.timing.abbruch_ruhe)
        except (KLineError, PortError) as exc:
            log.debug(t("Trennen: %s"), exc)

    @contextmanager
    def _ohne_gc(self) -> Iterator[None]:
        """Während eines Blockwechsels keine automatische Speicherbereinigung: Sie hält den
        Thread für Millisekunden an – womöglich genau dann, wenn das Steuergerät auf das
        nächste Byte wartet. Danach läuft sie wie gewohnt."""
        if self._ohne_gc_tiefe == 0:
            self._gc_war_an = gc.isenabled()
            gc.disable()
        self._ohne_gc_tiefe += 1
        try:
            yield
        finally:
            self._ohne_gc_tiefe -= 1
            if self._ohne_gc_tiefe == 0 and self._gc_war_an:
                gc.enable()

    def _sende_block(self, titel: int, daten: bytes = b"") -> None:
        with self._ohne_gc():
            self._sende_block_(titel, daten)

    def _sende_block_(self, titel: int, daten: bytes = b"") -> None:
        """Block senden; jedes Byte außer dem Blockende quittiert das Steuergerät mit dem
        invertierten Byte, das es empfangen hat.

        Ein falsches oder fehlendes Komplement heißt: Das Steuergerät hat ein anderes Byte
        (oder keins) bekommen. Dann bricht vagdiag den Block sofort ab, statt ihn zu Ende
        zu senden – sonst führte das Steuergerät womöglich einen verfälschten Block aus
        (aus 29 „Messwerte“ würde 28 „Grundeinstellung“, aus 07 „Fehler lesen“ 05 „Fehler
        löschen“). Ein gestörtes Echo des eigenen Bytes wird einmal pro Block hingenommen:
        Ob das Steuergerät das richtige Byte hat, zeigt danach sein Komplement.

        Zeitwächter: Nach seinem Komplement wartet das Steuergerät nur kurz auf das nächste
        Byte (ein ME7.5 im Auto etwa 45 ms). Kommt es später, verwirft es den halben Block und
        hält das späte Byte für den Anfang eines neuen – die Komplemente stimmen dann trotzdem,
        und aus dem Rest kann ein anderer Befehl werden (aus „Gruppe 005 lesen“ mit Zähler 03
        wird „Fehlerspeicher löschen“). Deshalb muss jedes Byte innerhalb von byte_frist nach
        dem Komplement hinaus; sonst bricht vagdiag ab, ohne weiterzusenden. Lag das
        Komplement schon im Puffer, zählt vorsichtshalber der Zeitpunkt des eigenen Bytes."""
        self._schreibschutz(titel, bytes(daten))
        self.zaehler = 1 if self.zaehler is None else (self.zaehler + 1) & 0xFF
        roh = bytes([len(daten) + 3, self.zaehler, titel]) + bytes(daten) + b"\x03"
        if titel in EXPERTE:
            # Die Grundeinstellung wird laufend wiederholt – nur die erste Anfrage je
            # Gruppe als Warnung, die übrigen wie jeder andere Block
            erste = titel != GRUNDEINSTELLUNG or daten[0] not in self._freigabe.gemeldet
            if erste:
                if titel == GRUNDEINSTELLUNG:
                    self._freigabe.gemeldet.add(daten[0])
                log.warning(t("STELLGLIED: %s") if titel == STELLGLIED else t("SCHREIBEN: %s"),
                            Block(self.zaehler, titel, bytes(daten)))
        log.debug("→ %s", Block(self.zaehler, titel, bytes(daten)))
        toleriert = False
        frist: float | None = None      # bis dahin muss das nächste Byte hinaus sein
        for i, byte in enumerate(roh):
            if i and self.timing.inter_byte:
                time.sleep(self.timing.inter_byte)
            vor_dem_senden = time.perf_counter()
            if frist is not None and vor_dem_senden > frist:
                self._zu_spaet(i, roh, vor_dem_senden - frist, gesendet=False)
            try:
                self.kl.write_byte(byte)
            except EchoError as exc:
                if not self.toleranz or toleriert:
                    self._block_abbrechen()
                    raise
                # z. B. beim Anlassen: das Kabel hängt an der Bordspannung. Ob das
                # Steuergerät das richtige Byte bekommen hat, zeigt sein Komplement.
                toleriert = True
                log.warning(t("Störung: %s – versuche weiterzumachen"), exc)
            except (KLineError, PortError):
                self._block_abbrechen()
                raise
            # Hing vagdiag mitten im Senden (nach der Prüfung davor), ging das Byte womöglich
            # zu spät hinaus: nichts mehr hinterherschicken. Gemessen, als das Byte ans Kabel
            # ging – das Warten auf das Echo danach macht es nicht mehr später.
            nach_dem_senden = self.kl.gesendet
            if frist is not None and nach_dem_senden > frist:
                self._zu_spaet(i, roh, nach_dem_senden - frist, gesendet=True)
            if i == len(roh) - 1:
                return  # Blockende wird nicht quittiert
            try:
                antwort = self.kl.read_byte(self.timing.byte_timeout)
            except Timeout:
                self._block_abbrechen()
                raise ProtocolError(t("Kein Komplement auf Byte {nummer}/{anzahl} ({byte:02X})",
                                      nummer=i + 1, anzahl=len(roh), byte=byte)) from None
            if antwort != byte ^ 0xFF:
                # Nie weitersenden: das Steuergerät hat ein anderes Byte empfangen
                self._block_abbrechen()
                raise ProtocolError(t(
                    "Falsches Komplement {antwort:02X} auf {byte:02X} (erwartet {soll:02X}) – "
                    "Block abgebrochen, nicht zu Ende gesendet",
                    antwort=antwort, byte=byte, soll=byte ^ 0xFF))
            frist = self._ankunft_schaetzen(vor_dem_senden) + self.timing.byte_frist

    def _ankunft_schaetzen(self, gesendet: float) -> float:
        """Wann kam das Komplement an – im Zweifel früher als später?

        Musste vagdiag am Kabel darauf warten, kam es kurz vor dem Ende des Wartens –
        höchstens aber so spät, wie dieses Steuergerät sonst antwortet: Hing vagdiag erst
        nach der Ankunft (etwa beim Protokollieren), sähe das sonst wie eine späte Antwort
        aus. Lag das Komplement schon im Puffer, vorsichtshalber gleich nach dem eigenen
        Byte."""
        kl = self.kl
        if not kl.frisch:
            return gesendet
        schaetzung = kl.ankunft - 0.002                 # USB-Latenz
        if len(self._verzug) >= 3:
            typisch = statistics.median(self._verzug)
            schaetzung = min(schaetzung, gesendet + typisch + 0.005)
        self._verzug.append(kl.ankunft - gesendet)
        del self._verzug[:-16]
        return schaetzung

    def _zu_spaet(self, i: int, roh: bytes, um: float, gesendet: bool) -> None:
        """Das nächste eigene Byte käme (oder kam) zu spät – Block abbrechen."""
        self._block_abbrechen()
        if gesendet:
            raise ProtocolError(t(
                "Byte {nummer}/{anzahl} ging womöglich {ms:.0f} ms zu spät hinaus (Rechner hing "
                "beim Senden) – Block abgebrochen, nichts mehr hinterhergeschickt",
                nummer=i + 1, anzahl=len(roh), ms=um * 1000))
        raise ProtocolError(t(
            "Byte {nummer}/{anzahl} wäre {ms:.0f} ms zu spät gekommen (Rechner hing) – Block "
            "abgebrochen, nicht zu Ende gesendet", nummer=i + 1, anzahl=len(roh), ms=um * 1000))

    def _empfange_block(self) -> Block:
        with self._ohne_gc():
            return self._empfange_block_()

    def _empfange_block_(self) -> Block:
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
            self.verloren()
            raise ProtocolError(str(exc)) from exc
        except ProtocolError:
            self.verloren()
            raise

    def _nur_kw1281(self) -> None:
        if self._kwp is not None:
            raise NotAvailable(t("Bei KWP2000 gibt es keine KW1281-Blöcke"))

    def austausch(self, titel: int, daten: bytes = b"") -> Block:
        """Einen Block senden, genau einen Antwortblock empfangen."""
        self._nur_kw1281()

        def ablauf():
            self._zaehler_abweichung = False
            with self._ohne_gc():
                self._sende_block(titel, daten)
                return self._empfange_block()
        return self._sicher(ablauf)

    def transaktion(self, titel: int, daten: bytes = b"") -> list[Block]:
        """Block senden, alle Antwortblöcke bis zum ACK des Steuergeräts holen."""
        self._nur_kw1281()

        def ablauf():
            self._zaehler_abweichung = False
            with self._ohne_gc():
                self._sende_block(titel, daten)
                return self._empfange_bis_ack()
        return self._sicher(ablauf)

    # -------------------------------------------------------------- Funktionen
    def fehler_lesen(self) -> list[Fehler]:
        if self._kwp is not None:
            return self._sicher(self._kwp.fehler_lesen)
        return _fehler_auswerten(self.transaktion(FEHLER_LESEN))

    def fehler_loeschen(self) -> list[Fehler]:
        """Löscht den Fehlerspeicher; zurück kommen ggf. sofort wieder gesetzte Fehler."""
        if self._kwp is not None:
            return self._sicher(self._kwp.fehler_loeschen)
        log.info(t("Fehlerspeicher wird gelöscht"))
        return _fehler_auswerten(self.transaktion(FEHLER_LOESCHEN))

    def gruppe_lesen(self, gruppe: int) -> list[Messwert]:
        if not 0 <= gruppe <= 255:
            raise ValueError(t("Messwertgruppe muss zwischen 0 und 255 liegen"))
        if gruppe == 0:
            return self._rohwerte_lesen()
        if self._kwp is not None:
            return self._sicher(self._kwp.gruppe_lesen, gruppe)
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

    def _rohwerte_lesen(self) -> list[Messwert]:
        """Gruppe 000: Block 12 ohne Daten, Antwort F4 mit den Rohwerten (meist zehn) – so
        beschreiben es die freien Programme kw1281test und KLineKWP1281Lib. Nur KW1281: Bei
        KWP2000 gibt es dafür keinen beschriebenen Dienst, deshalb fragt vagdiag dort nicht."""
        if self._kwp is not None:
            raise NotAvailable(t("Gruppe 000 gibt es nur bei KW1281"))
        block = self.austausch(ROHWERTE_LESEN)
        if self._zaehler_abweichung:
            raise Stoerung(t("Antwort auf Gruppe 000 mit falschem Blockzähler verworfen"),
                           "zaehler")
        if block.titel == ROHWERTE_ANTWORT and block.daten:
            return rohwerte_auswerten(block.daten)
        if block.titel == ACK:
            raise NotAvailable(t("Messwertgruppe {gruppe:03d} ist nicht belegt", gruppe=0))
        if block.titel == NAK:
            raise Nak(t("Messwertgruppe {gruppe:03d} abgelehnt", gruppe=0))
        raise Stoerung(t(
            "Messwertgruppe {gruppe:03d}: unerwartete Antwort {titel:02X} (gestört oder noch "
            "nicht auswertbar)", gruppe=0, titel=block.titel), "titel")

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
        if self._kwp is not None:
            return self._sicher(self._kwp.anpassung_lesen, kanal)
        block = self.austausch(ANPASSUNG_LESEN, bytes([kanal]))
        return self._anpassung_auswerten(block, kanal, t("gelesen"))

    def _anpassung_auswerten(self, block: Block, kanal: int, wie: str) -> Anpassung:
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
            log.info(t("Anpassung %s: %s"), wie, anpassung.text)
            return anpassung
        if block.titel == NAK:
            raise Nak(t("Anpassungskanal {kanal:02d} abgelehnt – nicht vorhanden oder nur "
                        "nach Anmeldung (Login) lesbar", kanal=kanal))
        if block.titel == ACK:
            raise NotAvailable(t("Anpassungskanal {kanal:02d} ist nicht belegt", kanal=kanal))
        raise NotAvailable(t(
            "Anpassungskanal {kanal:02d}: Antworttyp {titel:02X} wird nicht ausgewertet "
            "({block})", kanal=kanal, titel=block.titel, block=block))

    # ------------------------------------------- Expertenfunktionen (mit Freigabe)
    def _nur_kw1281_experte(self) -> None:
        self._pruefe()
        if self._kwp is not None:
            raise NotAvailable(t("Expertenfunktionen gibt es bisher nur bei KW1281 – dieses "
                                 "Steuergerät spricht KWP2000."))

    def grundeinstellung(self, gruppe: int) -> list[Messwert]:
        """Grundeinstellung einer Gruppe (Block 28): das Steuergerät führt den Ablauf aus
        (z. B. Drosselklappe anlernen) und antwortet mit den Messwerten der Gruppe.
        Solange es laufen soll, wiederholt anfragen; eine normale Gruppenabfrage (29)
        beendet die Grundeinstellung."""
        if not 1 <= gruppe <= 255:
            raise ValueError(t("Messwertgruppe muss zwischen 1 und 255 liegen"))
        self._nur_kw1281_experte()
        block = self.austausch(GRUNDEINSTELLUNG, bytes([gruppe]))
        if self._zaehler_abweichung:
            raise Stoerung(t("Antwort auf Grundeinstellung {gruppe:03d} mit falschem "
                             "Blockzähler verworfen", gruppe=gruppe), "zaehler")
        if block.titel == GRUPPE_ANTWORT:
            return gruppe_auswerten(block.daten)
        if block.titel in (ACK, NAK):
            raise Nak(t("Grundeinstellung {gruppe:03d} abgelehnt", gruppe=gruppe))
        raise Stoerung(t("Grundeinstellung {gruppe:03d}: unerwartete Antwort {titel:02X}",
                         gruppe=gruppe, titel=block.titel), "titel")

    def anpassung_testen(self, kanal: int, wert: int) -> Anpassung:
        """Wert vorläufig übernehmen lassen (Block 22) – gespeichert wird er erst mit
        anpassung_speichern."""
        self._nur_kw1281_experte()
        if not 0 <= wert <= 0xFFFF:
            raise ValueError(t("Anpassungswert muss zwischen 0 und 65535 liegen"))
        block = self.austausch(ANPASSUNG_TESTEN, bytes([kanal, wert >> 8, wert & 0xFF]))
        if block.titel == NAK:
            raise Nak(t("Steuergerät lehnt Wert {wert} für Kanal {kanal:02d} ab", wert=wert,
                        kanal=kanal))
        anpassung = self._anpassung_auswerten(block, kanal, t("getestet"))
        self._schreibantwort_pruefen(anpassung, kanal, wert, gespeichert=False)
        return anpassung

    def anpassung_speichern(self, kanal: int, wert: int, werkstattcode: int = 0) -> Anpassung:
        """Wert dauerhaft speichern (Block 2A) – mit dem Werkstattcode wie kw1281test."""
        self._nur_kw1281_experte()
        if not 0 <= wert <= 0xFFFF:
            raise ValueError(t("Anpassungswert muss zwischen 0 und 65535 liegen"))
        if not 0 <= werkstattcode <= 99999:
            raise ValueError(t("Werkstattcode muss zwischen 0 und 99999 liegen"))
        daten = bytes([kanal, wert >> 8, wert & 0xFF, werkstattcode >> 16,
                       (werkstattcode >> 8) & 0xFF, werkstattcode & 0xFF])
        block = self.austausch(ANPASSUNG_SPEICHERN, daten)
        if block.titel == NAK:
            raise Nak(t("Steuergerät speichert Wert {wert} für Kanal {kanal:02d} nicht",
                        wert=wert, kanal=kanal))
        anpassung = self._anpassung_auswerten(block, kanal, t("gespeichert"))
        self._schreibantwort_pruefen(anpassung, kanal, wert, gespeichert=True)
        return anpassung

    def _schreibantwort_pruefen(self, anpassung: Anpassung, kanal: int, wert: int,
                                gespeichert: bool) -> None:
        """Nach Testen und Speichern muss das Steuergerät genau diesen Kanal mit genau
        diesem Wert melden. Zeigt es nach dem Testen einen anderen Wert, hat es ihn nicht
        übernommen – dann wird nicht gespeichert. Jede andere Abweichung beendet die
        Verbindung, ohne noch etwas zu wiederholen."""
        gemeldet = anpassung.daten[0] if anpassung.daten else -1
        if gemeldet == kanal and anpassung.wert == wert:
            return
        if gemeldet == kanal and not gespeichert:
            raise Nak(t("Steuergerät übernimmt Wert {wert} für Kanal {kanal:02d} nicht "
                        "(zeigt {jetzt}) – nichts gespeichert", wert=wert, kanal=kanal,
                        jetzt=anpassung.wert))
        if self._ende_senden():
            self.verbunden = False
        else:
            self.verloren()
        if gespeichert:
            raise ProtocolError(t(
                "Steuergerät meldet nach dem Speichern Kanal {gemeldet:02d} mit Wert {jetzt} "
                "statt Kanal {kanal:02d} mit {wert} – Verbindung beendet. Bitte den Kanal neu "
                "lesen und prüfen.", gemeldet=gemeldet, jetzt=anpassung.wert, kanal=kanal,
                wert=wert))
        raise ProtocolError(t(
            "Steuergerät meldet nach dem Testen Kanal {gemeldet:02d} mit Wert {jetzt} statt "
            "Kanal {kanal:02d} mit {wert} – nichts gespeichert, Verbindung beendet. Ein nur "
            "getesteter Wert gilt bis Zündung aus.", gemeldet=gemeldet, jetzt=anpassung.wert,
            kanal=kanal, wert=wert))

    def anpassung_schreiben(self, kanal: int, wert: int, werkstattcode: int = 0) -> Anpassung:
        """Wert testen und speichern – KW1281 mit den Blöcken 22 und 2A, KWP2000 in einer
        Anpassungssitzung (siehe kwp2000.py). Nur innerhalb einer passenden Freigabe."""
        if self._kwp is not None:
            self._pruefe()
            if not 0 <= wert <= 0xFFFF:
                raise ValueError(t("Anpassungswert muss zwischen 0 und 65535 liegen"))
            return self._sicher(self._kwp.anpassung_schreiben, kanal, wert,
                                kwp_werkstattcode(self.verbindung))
        self.anpassung_testen(kanal, wert)
        return self.anpassung_speichern(kanal, wert, werkstattcode)

    # Stellglieddiagnose: Jeder Schritt schaltet zum nächsten Stellglied und steuert es an,
    # bis zur nächsten Anfrage. Zurück kommt seine Nummer, am Ende None. Beendet wird sie
    # mit dem Ende der Verbindung (session.py/experte.py) – dann hört jedes Steuergerät
    # sicher auf, ein Stellglied anzusteuern.
    def stellglied_starten(self) -> Stellglied | None:
        self._pruefe()
        if self._kwp is not None:
            return self._sicher(self._kwp.stellglied_starten)
        return self._stellglied_block()

    def stellglied_weiter(self) -> Stellglied | None:
        self._pruefe()
        if self._kwp is not None:
            return self._sicher(self._kwp.stellglied_weiter)
        return self._stellglied_block()

    def stellglied_beenden(self) -> None:
        """KWP2000: die Routine beenden (KW1281 kennt dafür keinen eigenen Block)."""
        if self._kwp is not None and self.verbunden:
            self._sicher(self._kwp.stellglied_beenden)

    def _stellglied_block(self) -> Stellglied | None:
        block = self.austausch(STELLGLIED, b"\x00")
        if self._zaehler_abweichung:
            raise Stoerung(t("Antwort der Stellglieddiagnose mit falschem Blockzähler"),
                           "zaehler")
        if block.titel == STELLGLIED_ANTWORT and len(block.daten) >= 2:
            stellglied = Stellglied((block.daten[0] << 8) | block.daten[1], block.daten)
            log.info(t("Stellglied: %s"), stellglied.text)
            return None if stellglied.ende else stellglied
        if block.titel == ACK:
            log.info(t("Stellglieddiagnose: Ende"))
            return None
        if block.titel == NAK:
            raise Nak(t("Stellglieddiagnose abgelehnt – nicht unterstützt oder Bedingungen "
                        "nicht erfüllt (z. B. Motor läuft)"))
        raise Stoerung(t("Stellglieddiagnose: unerwartete Antwort {titel:02X}",
                         titel=block.titel), "titel")

    def keep_alive(self) -> None:
        if self._kwp is not None:
            self._sicher(self._kwp.keep_alive)
            return
        block = self.austausch(ACK)
        if block.titel != ACK:
            log.warning(t("Unerwartete Antwort auf Keep-Alive: %s"), block)

    def trennen(self) -> None:
        if self.verbunden:
            beendet = self._kwp.beenden() if self._kwp is not None else self._ende_senden()
            if not beendet:       # das Steuergerät bekam kein Ende – es hört womöglich noch zu
                self.verloren()
            log.info(t("Verbindung beendet"))
        self.verbunden = False
        self._kwp = None


def kwp_werkstattcode(verbindung) -> bytes:
    """Die sechs Bytes des Werkstattcodes aus der KWP2000-Kennung (1A 9B), wie das
    Steuergerät sie gemeldet hat – leer, wenn die Kennung anders aufgebaut ist."""
    roh = bytes(getattr(verbindung, "kennung_roh", b"") or b"")
    if len(roh) >= 27 and roh[0] == 0x9B and roh[17] == 0x03:
        return roh[21:27]
    return b""


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

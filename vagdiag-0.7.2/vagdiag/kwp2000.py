"""KWP2000 (ISO 14230) über die K-Leitung – so, wie VAG es etwa 2000–2006 nutzt.

Ein Steuergerät mit KWP2000 antwortet auf die 5-Baud-Reizung mit Keybytes,
deren zweites 8F ist (Keyword 2000–2031), quittiert das invertierte zweite
Keybyte mit der invertierten Adresse – und ab dann geht es mit Nachrichten
weiter:

    [Format] [Ziel] [Quelle] ([Länge])  [Dienst] [Daten …]  [Prüfsumme]

Format: Bit 7 = mit Adressen, Bits 0–5 = Länge (0 = eigenes Längenbyte).
Ziel ist die „Kopfadresse“ des Steuergeräts, Quelle der Tester (F1). Die
Prüfsumme ist die Summe aller Bytes (untere 8 Bit). Anders als bei KW1281 gibt
es keine Quittung je Byte; dafür feste Pausen: nach einer Antwort wartet der
Tester mindestens P3 (55 ms), zwischen seinen eigenen Bytes P4 (5 ms).

Benutzte Dienste – alle lesend außer „Fehlerspeicher löschen“:
    1A 9B Identifikation (geht ohne Diagnosesitzung – deshalb die erste Anfrage)
    10 Diagnosesitzung (VAG: 89, sonst 81 – nie 85, das ist die Programmiersitzung
       zum Flashen; antwortet keine, geht es ohne Sitzung weiter)
    18 Fehlerspeicher lesen    14 Fehlerspeicher löschen
    21 Messwertblock (Gruppe)  3E Tester present     82 Verbindung beenden
    81 StartCommunication (nur nach dem Fast-Init)
    31/32 Routinen der VAG-Anpassung, Unterfunktion 01 03 (so in kw1281test und im
       freien Programm bri3d/kwp2000 für einen Service-Reset am Kombi beschrieben):
          31 B8 01 03 Anpassung beginnen      31 B9 01 03 kk  Kanal kk wählen
          31 BA 01 03 Wert lesen              32 B8 01 03     Anpassung beenden
       Nur im Expertenmodus mit Freigabe für genau diesen Kanal und Wert:
          31 B9 01 03 hh ll  Wert testen      31 BB 01 03 hh ll + Werkstattcode  speichern
    31/32 Stellglieddiagnose, Unterfunktion 01 02 – experimentell, nach einem
       EDC16-Mitschnitt in kw1281test, nur im Expertenmodus mit Freigabe:
          31 B8 01 02 beginnen   31 B9 01 02 Schritt   31 BA 01 02 Status   32 B8 01 02 Ende
Alles andere (Anmeldung 27, Schreiben 2E/3B, Ein-/Ausgänge 30, andere Routinen,
Speicher 23/34 …) sperrt senden(), ebenso Kanal 00 und Kanal 09 des Kombis.
Die Antwort 7F <Dienst> 78 heißt „Antwort folgt“ – dann wird weiter gewartet,
7F <Dienst> 21 „beschäftigt“ – dann wird eine lesende Anfrage wiederholt, eine
schreibende oder ansteuernde nie. Die Antwort auf eine Routine muss deren Nummer
nennen. Lässt sich die Anpassung nach einem Schreibversuch nicht beenden, beendet
vagdiag die Verbindung (82).

Die VAG-Besonderheiten (Kopfadresse, Sitzungen, Aufbau der Identifikation,
Messwertblöcke mit Formel/a/b wie bei KW1281, Fast-Init nur zum Motor) stammen
aus dem freien Programm kw1281test (MIT-Lizenz, Greg Menounos), das sie an
EDC15/EDC16 geprüft hat. An weiteren Steuergeräten ist das noch nicht geprüft –
deshalb landet hier jede Nachricht im Protokoll.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .fehler import Fehler
from .kline import EchoError, KLine, KLineError, Timeout
from .kw1281 import (KILOMETERSTAND_KANAL, KOMBI, KW1281, Anpassung, DiagError, Nak,
                     NotAvailable, ProtocolError, SchreibenGesperrt, Stoerung, Timing,
                     UnsupportedProtocol, Verbindung)
from .messwerte import Messwert, gruppe_auswerten
from .port import PortError
from .sprache import N_, t
from .stellglied import Stellglied, gesperrt_nach_kennung

log = logging.getLogger("vagdiag.proto")

TESTER = 0xF1
# In dieser Reihenfolge probieren. Nie 85: das ist die Programmiersitzung (Download zum
# Flashen) – nichts für ein Programm, das nur liest, und gefährlich, wenn der Motor läuft.
SITZUNGEN = (0x89, 0x81)
# Die einzigen Dienste, die vagdiag bei KWP2000 ohne Weiteres sendet – dazu kommen die
# Routinen der Anpassung und der Stellglieddiagnose (siehe _schreibschutz)
ERLAUBTE_DIENSTE = {0x10, 0x14, 0x18, 0x1A, 0x21, 0x3E, 0x81, 0x82}
ANPASSUNG = bytes([0x01, 0x03])       # Unterfunktion der Anpassungsroutinen
STELLGLIED = bytes([0x01, 0x02])      # Unterfunktion der Stellglieddiagnose
FAST_INIT_ADRESSE = 0x01                # Fast-Init nur zum Motor …
FAST_INIT_KOPF = 0x10                   # … mit dieser Kopfadresse

# (Reizadresse, Keyword) → Kopfadresse. Sonst gilt die Reizadresse (ISO-Regel).
KOPF_ADRESSEN = {
    (0x01, 2031): 0x10,     # EDC16: Reizung an 01, Nachrichten an 10
    (0x01, 2027): 0x01,     # EDC15: bleibt bei 01
}

DIENSTE = {
    0x10: "StartDiagnosticSession", 0x14: "ClearDiagnosticInformation",
    0x18: "ReadDTCByStatus", 0x1A: "ReadEcuIdentification",
    0x21: "ReadDataByLocalIdentifier", 0x3E: "TesterPresent",
    0x31: "StartRoutineByLocalIdentifier", 0x32: "StopRoutineByLocalIdentifier",
    0x81: "StartCommunication", 0x82: "StopCommunication", 0x7F: "NegativeResponse",
}

ABLEHNUNGEN = {
    0x10: N_("allgemein abgelehnt"),
    0x11: N_("Dienst nicht unterstützt"),
    0x12: N_("Unterfunktion nicht unterstützt"),
    0x13: N_("falsche Länge oder falsches Format"),
    0x21: N_("beschäftigt – später wiederholen"),
    0x22: N_("Bedingungen nicht erfüllt"),
    0x31: N_("außerhalb des gültigen Bereichs"),
    0x33: N_("Zugriff verweigert (Anmeldung nötig)"),
    0x78: N_("Antwort folgt"),
    0x80: N_("in dieser Diagnosesitzung nicht unterstützt"),
}

ANTWORT_FOLGT = 0x78
BESCHAEFTIGT = 0x21
PADDING = (0x25, 0x00, 0x00)    # leere Felder am Ende eines Messwertblocks
MAX_FOLGT = 20                  # so oft „Antwort folgt“ hinnehmen


class KeineAntwort(ProtocolError):
    """Auf eine KWP2000-Anfrage kam nichts zurück."""


class KwpAblehnung(Nak):
    """Negative Antwort (7F) des Steuergeräts."""

    def __init__(self, dienst: int, code: int):
        grund = t(ABLEHNUNGEN.get(code, N_("Code {code:02X}")), code=code)
        super().__init__(t("Steuergerät lehnt {dienst:02X} ab: {grund}", dienst=dienst,
                           grund=grund))
        self.dienst = dienst
        self.code = code


def _hex(daten: bytes) -> str:
    return " ".join(f"{b:02X}" for b in daten)


def _text(daten: bytes) -> str:
    """Lesbare Zeichen, mehrfache Leerzeichen zusammengezogen."""
    zeichen = "".join(chr(b) if 0x20 <= b < 0x7F else " " for b in daten)
    return " ".join(zeichen.split())


def _textteile(daten: bytes) -> list[str]:
    """Lesbare Abschnitte (getrennt durch nicht druckbare Bytes oder lange Lücken)."""
    teile, aktuell = [], ""
    for b in daten:
        if 0x20 <= b < 0x7F:
            aktuell += chr(b)
        else:
            teile.append(aktuell)
            aktuell = ""
    teile.append(aktuell)
    ergebnis = []
    for teil in teile:
        ergebnis += [" ".join(x.split()) for x in teil.split("   ")]
    return [x for x in ergebnis if x]


def _druckbar(daten: bytes) -> bool:
    return bool(daten) and all(0x20 <= b < 0x7F for b in daten)


def _genau_warten(sekunden: float) -> None:
    """Kurze Pausen genau einhalten (time.sleep ist unter Windows oft zu grob)."""
    ende = time.perf_counter() + sekunden
    while time.perf_counter() < ende:
        pass


def keyword(kb1: int, kb2: int) -> int:
    return ((kb2 & 0x7F) << 7) | (kb1 & 0x7F)


def ist_kwp2000(kb2: int) -> bool:
    return (kb2 & 0x7F) == 0x0F


def werkstattcode_auswerten(daten: bytes) -> tuple[int, int, int]:
    """6 Bytes → (Werkstattcode, Importeur, Gerätenummer)."""
    wert = int.from_bytes(daten, "big")
    return wert & 0x1FFFF, (wert >> 17) & 0x3FF, (wert >> 27) & 0xFFFFF


def kennung_auswerten(daten: bytes) -> dict:
    """Antwort auf 1A 9B (ohne das Dienst-Byte 5A). Aufbau bei VAG:
    9B | Teilenummer (12) | Softwarestand (4) | 03 | Codierung (3) | Werkstattcode (6) | Text."""
    info: dict = {"kennung_roh": bytes(daten)}
    if len(daten) >= 17 and daten[0] == 0x9B and _druckbar(daten[1:13]):
        info["teil"] = _text(daten[1:13])
        info["software"] = _text(daten[13:17])
        if len(daten) >= 27 and daten[17] == 0x03:
            info["codier"] = int.from_bytes(daten[18:21], "big")
            info["wsc"], info["importeur"], info["geraet"] = werkstattcode_auswerten(daten[21:27])
            info["beschreibung"] = _text(daten[27:])
        else:
            info["beschreibung"] = " ".join(_textteile(daten[17:]))
        return info
    # anderer Aufbau: nur die lesbaren Teile
    teile = _textteile(daten[1:] if daten[:1] == b"\x9b" else daten)
    info["teil"] = teile[0] if teile else ""
    info["beschreibung"] = " ".join(teile[1:])
    return info


@dataclass
class KwpVerbindung(Verbindung):
    """Verbindung zu einem KWP2000-Steuergerät (Kennung aus 1A 9B statt aus Blöcken)."""
    teil: str = ""
    beschreibung: str = ""
    software: str = ""
    codier: int | None = None
    wsc: int | None = None
    importeur: int | None = None
    geraet: int | None = None
    kopf: int | None = None
    sitzung: int | None = None
    fast_init: bool = False
    kennung_roh: bytes = b""

    codierung_stellen = 7

    @property
    def teilenummer(self) -> str:
        return self.teil

    @property
    def bauteil(self) -> str:
        return f"{self.beschreibung} {self.software}".strip()

    @property
    def codierung(self) -> int | None:
        return self.codier

    @property
    def werkstattcode(self) -> int | None:
        return self.wsc

    @property
    def hat_zusatzkennung(self) -> bool:
        return False

    @property
    def zusatzkennung(self) -> str:
        return ""

    @property
    def zusatzdaten(self) -> list[str]:
        daten = []
        if self.importeur is not None:
            daten.append(t("Importeur {importeur}, Gerätenummer {geraet}",
                           importeur=self.importeur, geraet=self.geraet))
        sitzung = f"{self.sitzung:02X}" if self.sitzung is not None else "–"
        kopf = f"{self.kopf:02X}" if self.kopf is not None else t("ohne Adressen")
        text = t("KWP2000: Kopfadresse {kopf}, Diagnosesitzung {sitzung}", kopf=kopf,
                 sitzung=sitzung)
        if self.fast_init:
            text += ", " + t("Fast-Init")
        daten.append(text)
        if not self.teil and self.kennung_roh:
            daten.append(_hex(self.kennung_roh))
        return daten


class Kwp2000:
    """Ein KWP2000-Dialog auf einer schon gereizten K-Leitung."""

    def __init__(self, kline: KLine, timing: Timing, adresse: int, keyword_: int, kb1: int,
                 baud: int, kopf: int | None = None):
        self.kl = kline
        self.timing = timing
        self.adresse = adresse
        self.keyword = keyword_
        self.kb1 = kb1
        self.baud = baud
        self.kopf = kopf if kopf is not None else KOPF_ADRESSEN.get((adresse, keyword_), adresse)
        # KB1 Bit 3: Kopf mit Adressen, Bit 2: Kopf nur aus dem Formatbyte. Ohne
        # Angabe (oder mit beidem) werden Adressen benutzt.
        self.mit_adressen = bool(kb1 & 0x08) or not kb1 & 0x04
        self.sitzung: int | None = None
        self.fast_init = False
        self._frei_ab = 0.0              # früheste nächste Anfrage (P3)
        self._letzte_antwort = time.monotonic()
        self._keepalive_dienst = bytes([0x3E])
        self._keepalive_vorher: bytes | None = None
        self._fremde_quelle_gemeldet = False
        # Schreibsperre: liefert (Expertenmodus, Freigabe) – gesetzt von KW1281
        self.schutz = None
        self._anp_kanal: int | None = None    # gewählter Anpassungskanal

    # ------------------------------------------------------------ Nachrichten
    def _nachricht(self, daten: bytes) -> bytes:
        n = len(daten)
        if self.mit_adressen:
            kopf = (bytes([0x80 | n, self.kopf, TESTER]) if n <= 0x3F
                    else bytes([0x80, self.kopf, TESTER, n]))
        else:
            kopf = bytes([n]) if n <= 0x3F else bytes([0x00, n])
        roh = kopf + bytes(daten)
        return roh + bytes([sum(roh) & 0xFF])

    @staticmethod
    def _beschreiben(daten: bytes) -> str:
        dienst = daten[0] if daten else 0
        if dienst == 0x7F:
            return DIENSTE[0x7F]
        name = DIENSTE.get(dienst) or DIENSTE.get(dienst & ~0x40 & 0xFF, "?")
        return name + (" +" if dienst & 0x40 else "")

    # ------------------------------------------------------------ Schreibsperre
    def _freigabe(self):
        """Die Freigabe der laufenden Expertenfunktion – nur im Expertenmodus und nur,
        wenn sie für dieses Steuergerät gilt."""
        experte, freigabe = self.schutz() if self.schutz is not None else (False, None)
        if not experte or freigabe is None or freigabe.adresse != self.adresse:
            return None
        return freigabe

    def _schreibschutz(self, daten: bytes) -> str | None:
        """Wirft SchreibenGesperrt, wenn diese Anfrage nicht gesendet werden darf. Zurück
        kommt "schreiben" bzw. "stellglied" für Anfragen, die etwas am Steuergerät ändern
        oder ansteuern (fürs Protokoll), sonst None."""
        dienst = daten[0] if daten else None
        gesperrt = SchreibenGesperrt(t("KWP2000: Anfrage {daten} ist in vagdiag gesperrt",
                                       daten=_hex(daten)))
        if dienst in ERLAUBTE_DIENSTE:
            if dienst == 0x10 and (len(daten) != 2 or daten[1] not in SITZUNGEN):
                raise gesperrt                           # nur die Diagnosesitzungen 89/81
            return None
        if dienst == 0x32 and daten[1:] in (b"\xb8" + ANPASSUNG, b"\xb8" + STELLGLIED):
            return None                                  # Routine beenden ändert nichts
        if dienst != 0x31 or len(daten) < 4:
            raise gesperrt
        routine, unter, rest = daten[1], daten[2:4], daten[4:]
        if unter == ANPASSUNG:
            if routine in (0xB8, 0xBA) and not rest:
                return None                              # beginnen, Wert lesen
            if routine == 0xB9 and len(rest) == 1:       # Kanal wählen
                if rest[0] == 0:
                    raise SchreibenGesperrt(t("Anpassungskanal 00 (alle Anpassungen löschen) "
                                              "ist gesperrt"))
                return None
            if (routine == 0xB9 and len(rest) == 2) or (routine == 0xBB and len(rest) == 8):
                self._anpassung_pruefen((rest[0] << 8) | rest[1])
                return "schreiben"                       # testen bzw. speichern
        elif unter == STELLGLIED and routine in (0xB8, 0xB9, 0xBA) and not rest:
            grund = KW1281.stellglied_gesperrt(self.adresse)
            if grund:
                raise SchreibenGesperrt(grund)
            freigabe = self._freigabe()
            if freigabe is not None and len(freigabe.kennung) == 3:
                grund = gesperrt_nach_kennung(*freigabe.kennung[1:])
                if grund:
                    raise SchreibenGesperrt(grund)
            if freigabe is None or not freigabe.stellglied:
                raise SchreibenGesperrt(t("{name} geht nur im Expertenmodus über eine "
                                          "Expertenfunktion", name=t("Stellglieddiagnose")))
            return "stellglied"
        raise gesperrt

    def _anpassung_pruefen(self, wert: int) -> None:
        kanal = self._anp_kanal
        if kanal is None:
            raise SchreibenGesperrt(t("KWP2000: Anpassungswert ohne gewählten Kanal – gesperrt"))
        if self.adresse == KOMBI and kanal == KILOMETERSTAND_KANAL:
            raise SchreibenGesperrt(t("Kanal 09 des Kombis (Kilometerstand) ist gesperrt"))
        freigabe = self._freigabe()
        name = t("Anpassung speichern")
        if freigabe is None:
            raise SchreibenGesperrt(t("{name} geht nur im Expertenmodus über eine "
                                      "Expertenfunktion", name=name))
        if (kanal, wert) not in freigabe.anpassung:
            raise SchreibenGesperrt(t("{name} mit {daten} ist nicht freigegeben", name=name,
                                      daten=f"{kanal:02X} {wert >> 8:02X} {wert & 0xFF:02X}"))

    def senden(self, daten: bytes, p4: float | None = None) -> str | None:
        """Anfrage senden (nach der Schreibsperre). Zurück: "schreiben"/"stellglied" für
        Anfragen, die etwas ändern oder ansteuern, sonst None."""
        daten = bytes(daten)
        art = self._schreibschutz(daten)
        if art == "schreiben":
            log.warning(t("SCHREIBEN: KWP %s"), _hex(daten))
        elif art == "stellglied" and daten[1] != 0xBA:
            log.warning(t("STELLGLIED: KWP %s"), _hex(daten))
        if daten[0] == 0x31 and daten[2:4] == ANPASSUNG:
            if daten[1] == 0xB8:
                self._anp_kanal = None
            elif daten[1] == 0xB9 and len(daten) == 5:
                self._anp_kanal = daten[4]
        elif daten[0] == 0x32:
            self._anp_kanal = None
        roh = self._nachricht(daten)
        rest = self._frei_ab - time.monotonic()
        if rest > 0:
            time.sleep(rest)
        log.debug("→ KWP %s (%s)", _hex(roh), self._beschreiben(daten))
        pause = self.timing.kwp_p4 if p4 is None else p4
        # Zeitwächter wie bei KW1281: Zwischen zwei eigenen Bytes darf höchstens P4 (Norm:
        # 20 ms) vergehen. Hängt vagdiag länger, verwirft das Steuergerät womöglich den
        # Anfang und hält den Rest für eine neue Nachricht (davor schützt sonst nur die
        # Prüfsumme) – dann nichts mehr hinterherschicken. Gemessen wird, wann jedes Byte
        # ans Kabel ging (vor dem Warten auf sein Echo).
        frist: float | None = None
        for i, byte in enumerate(roh):
            if i and pause:
                _genau_warten(pause)
            vorher = time.perf_counter()
            if frist is not None and vorher > frist:
                self._zu_spaet(i, roh, vorher - frist, gesendet=False)
            self.kl.write_byte(byte)
            if frist is not None and self.kl.gesendet > frist:
                self._zu_spaet(i, roh, self.kl.gesendet - frist, gesendet=True)
            frist = self.kl.gesendet + max(pause, self.timing.kwp_p4_frist)
        return art

    @staticmethod
    def _zu_spaet(i: int, roh: bytes, um: float, gesendet: bool) -> None:
        """Das nächste eigene Byte käme (oder kam) zu spät: Nachricht abbrechen. Die
        Verbindung gilt als verloren (KW1281._sicher bzw. der Verbindungsaufbau)."""
        if gesendet:
            raise ProtocolError(t(
                "KWP2000: Byte {nummer}/{anzahl} ging womöglich {ms:.0f} ms zu spät hinaus "
                "(Rechner hing) – Anfrage abgebrochen, nichts mehr hinterhergeschickt",
                nummer=i + 1, anzahl=len(roh), ms=um * 1000))
        raise ProtocolError(t(
            "KWP2000: Byte {nummer}/{anzahl} wäre {ms:.0f} ms zu spät gekommen (Rechner hing) – "
            "Anfrage abgebrochen, nicht zu Ende gesendet", nummer=i + 1, anzahl=len(roh),
            ms=um * 1000))

    def _rest_verwerfen(self, stille: float = 0.06, hoechstens: float = 0.5) -> None:
        """Nach einer Störung nachlaufende Bytes verwerfen, bis die Leitung ruhig ist
        (stille etwas länger als P2, damit auch eine verspätete Antwort verschwindet)."""
        ende = time.monotonic() + hoechstens
        verworfen = []
        while time.monotonic() < ende:
            try:
                verworfen.append(self.kl.read_byte(stille))
            except Timeout:
                break
        if verworfen:
            log.debug(t("Verworfen nach Störung: %s"), _hex(bytes(verworfen)))
        self._frei_ab = time.monotonic() + self.timing.kwp_p3

    def empfangen(self, timeout: float) -> tuple[int | None, int | None, bytes]:
        """Eine Nachricht lesen: (Ziel, Quelle, Daten ab dem Dienst-Byte)."""
        try:
            fmt = self.kl.read_byte(timeout)
        except Timeout:
            raise KeineAntwort(t("KWP2000: keine Antwort vom Steuergerät")) from None
        roh = [fmt]
        p1 = self.timing.kwp_p1
        try:
            ziel = quelle = None
            if fmt & 0x80:
                ziel = self.kl.read_byte(p1)
                quelle = self.kl.read_byte(p1)
                roh += [ziel, quelle]
            laenge = fmt & 0x3F
            if laenge == 0:
                laenge = self.kl.read_byte(p1)
                roh.append(laenge)
            daten = bytes(self.kl.read_byte(p1) for _ in range(laenge))
            summe = self.kl.read_byte(p1)
        except Timeout:
            self._frei_ab = time.monotonic() + self.timing.kwp_p3
            raise Stoerung(t("KWP2000: Nachricht unvollständig ({roh})", roh=_hex(bytes(roh))),
                           "unvollstaendig") from None
        roh_bytes = bytes(roh) + daten
        self._frei_ab = time.monotonic() + self.timing.kwp_p3
        self._letzte_antwort = time.monotonic()
        log.debug("← KWP %s %02X (%s)", _hex(roh_bytes), summe, self._beschreiben(daten))
        if (sum(roh_bytes) & 0xFF) != summe or not daten:
            self._rest_verwerfen()
            raise Stoerung(t("KWP2000: Prüfsumme falsch – Antwort verworfen"), "pruefsumme")
        return ziel, quelle, daten

    def anfrage(self, daten: bytes, timeout: float | None = None,
                p4: float | None = None) -> bytes:
        """Anfrage senden, positive Antwort zurückgeben (ab dem Dienst-Byte). Meldet das
        Steuergerät „beschäftigt“, wird eine lesende Anfrage bis zu zweimal wiederholt –
        eine schreibende oder ansteuernde nie."""
        daten = bytes(daten)
        dienst = daten[0]
        warten = self.timing.kwp_p2 if timeout is None else timeout
        versuch = 0
        while True:
            versuch += 1
            try:
                art = self.senden(daten, p4)
            except EchoError as exc:
                # Die Anfrage kam gestört auf die Leitung – das Steuergerät verwirft sie.
                self._rest_verwerfen()
                raise Stoerung(t("KWP2000: Anfrage gestört ({fehler})", fehler=exc),
                               "echo") from exc
            try:
                antwort = self._antwort(dienst, warten)
            except KwpAblehnung as exc:
                if exc.code != BESCHAEFTIGT or versuch >= 3:
                    raise
                if art is not None:
                    log.warning(t("KWP2000: Steuergerät beschäftigt – %s wird nicht "
                                  "wiederholt"), _hex(daten))
                    raise
                log.info(t("KWP2000: Steuergerät beschäftigt – frage erneut"))
                time.sleep(0.2)
                continue
            if dienst in (0x31, 0x32) and (len(antwort) < 2 or antwort[1] != daten[1]):
                # Antwort einer anderen Routine – z. B. verspätet auf eine frühere Anfrage
                self._rest_verwerfen()
                raise Stoerung(t("KWP2000: Antwort {antwort} passt nicht zur Routine "
                                 "{routine:02X} – verworfen", antwort=_hex(antwort),
                                 routine=daten[1]), "titel")
            return antwort

    def _antwort(self, dienst: int, warten: float) -> bytes:
        folgt = 0
        while True:
            ziel, quelle, antwort = self.empfangen(warten)
            if ziel is not None and ziel != TESTER:
                self._rest_verwerfen()
                raise Stoerung(t("KWP2000: Nachricht an {ziel:02X} statt an den Tester – "
                                 "verworfen", ziel=ziel), "titel")
            if quelle is not None and quelle != self.kopf and not self._fremde_quelle_gemeldet:
                self._fremde_quelle_gemeldet = True
                log.warning(t("KWP2000: Antwort kommt von %02X statt von %02X – angenommen"),
                            quelle, self.kopf)
            if antwort[0] == 0x7F and len(antwort) >= 3 and antwort[1] == dienst:
                if antwort[2] == ANTWORT_FOLGT and folgt < MAX_FOLGT:
                    folgt += 1
                    warten = self.timing.kwp_p2_lang
                    continue
                raise KwpAblehnung(dienst, antwort[2])
            if antwort[0] != (dienst | 0x40):
                self._rest_verwerfen()       # z. B. verspätete Antwort auf eine frühere Anfrage
                raise Stoerung(t("KWP2000: unerwartete Antwort {antwort:02X} auf {dienst:02X}",
                                 antwort=antwort[0], dienst=dienst), "titel")
            return antwort

    # ------------------------------------------------------------ Aufbau
    def _burst_lesen(self, hoechstens: int, erstes: float, luecke: float) -> bytes:
        """Alles lesen, was kommt, bis die Leitung luecke Sekunden ruhig ist."""
        daten = bytearray()
        warten = erstes
        while len(daten) < hoechstens:
            try:
                daten.append(self.kl.read_byte(warten))
            except Timeout:
                break
            warten = luecke
        return bytes(daten)

    @staticmethod
    def _nachrichten_suchen(daten: bytes) -> list[tuple[int | None, int | None, bytes]]:
        """Alle gültigen Nachrichten (Prüfsumme stimmt) in einem Byte-Strom."""
        gefunden = []
        for start in range(len(daten)):
            fmt = daten[start]
            kopf = 3 if fmt & 0x80 else 1
            laenge = fmt & 0x3F
            if laenge == 0:
                if start + kopf >= len(daten):
                    continue
                laenge = daten[start + kopf]
                kopf += 1
            ende = start + kopf + laenge
            if laenge == 0 or ende >= len(daten):
                continue
            if (sum(daten[start:ende]) & 0xFF) != daten[ende]:
                continue
            ziel, quelle = (daten[start + 1], daten[start + 2]) if fmt & 0x80 else (None, None)
            gefunden.append((ziel, quelle, bytes(daten[start + kopf:ende])))
        return gefunden

    def fast_init_versuch(self) -> tuple[int, int] | None:
        """ISO 14230 Fast-Init: Leitung 300 ms frei, 25 ms Low, 25 ms High, dann sofort
        StartCommunication an die Kopfadresse. Antwort: C1 mit den Keybytes.
        Zurück kommen die Keybytes oder None (keine Antwort)."""
        self.mit_adressen = True
        anfrage = self._nachricht(bytes([0x81]))
        self.kl.fast_init_puls()
        self.kl.write_raw(anfrage)
        log.debug("→ KWP %s (%s)", _hex(anfrage), self._beschreiben(b"\x81"))
        daten = self._burst_lesen(48, erstes=0.4, luecke=0.03)
        self._frei_ab = time.monotonic() + self.timing.kwp_p3
        # Vor dem Echo kann noch ein Rest des Low-Pulses stehen (00 mit Rahmenfehler)
        stelle = daten.find(anfrage)
        echo = stelle >= 0
        rest = daten[stelle + len(anfrage):] if echo else daten
        if rest:
            log.debug("← KWP %s", _hex(rest))
        for ziel, _quelle, antwort in self._nachrichten_suchen(rest):
            if ziel not in (None, TESTER):
                continue
            if antwort[0] == 0x7F and antwort[1:2] == b"\x81":
                log.info(t("Fast-Init: StartCommunication abgelehnt (%s)"), _hex(antwort))
                return None
            if antwort[0] == 0xC1 and len(antwort) >= 3:
                kb1, kb2 = antwort[1], antwort[2]
                break
        else:
            # zur Not: C1 und zwei Keybytes irgendwo im Strom (wie kw1281test)
            stelle = rest.find(b"\xc1")
            if stelle < 0 or stelle + 2 >= len(rest) or not ist_kwp2000(rest[stelle + 2]):
                if daten:
                    log.info(t("Fast-Init: keine gültige Antwort (%s)"), _hex(daten))
                return None
            kb1, kb2 = rest[stelle + 1], rest[stelle + 2]
            log.warning(t("Fast-Init: Antwort mit falscher Prüfsumme – Keybytes übernommen"))
        if self.kl.echo is None:
            self.kl.echo = echo
            log.info(t("Kabel liefert Echo (normal bei KKL-Kabeln)") if echo
                     else t("Kabel liefert kein Echo"))
        self.kb1 = kb1
        self.keyword = keyword(kb1, kb2)
        self.fast_init = True
        self._letzte_antwort = time.monotonic()
        log.info(t("Fast-Init: Keybytes %02X %02X → Keyword %d"), kb1, kb2, self.keyword)
        return kb1, kb2

    def _kopf_varianten(self) -> list[tuple[bool, int]]:
        varianten: list[tuple[bool, int]] = []

        def dazu(variante: tuple[bool, int]) -> None:
            if variante not in varianten:
                varianten.append(variante)

        dazu((self.mit_adressen, self.kopf))
        dazu((True, self.kopf))
        dazu((True, self.adresse))
        if self.adresse == FAST_INIT_ADRESSE:
            dazu((True, FAST_INIT_KOPF))
        if self.kb1 & 0x04:                  # KB1 Bit 2: Kopf ohne Adressen möglich
            dazu((False, self.kopf))
        return varianten

    def starten(self, beruhigen: bool = True, varianten: list[tuple[bool, int]] | None = None,
                pruefung=None) -> KwpVerbindung:
        """Kopfadresse finden (über die Identifikation, die keine Sitzung braucht),
        dann die Diagnosesitzung eröffnen. pruefung(verbindung) läuft vor der
        Sitzung und darf die Verbindung mit einer Ausnahme verhindern."""
        if beruhigen:
            time.sleep(self.timing.kwp_beruhigen)   # am Auto nötig (kw1281test)
        kennung: bytes | None = None
        for mit_adressen, kopf in (varianten or self._kopf_varianten()):
            self.mit_adressen, self.kopf = mit_adressen, kopf
            log.info(t("KWP2000: versuche Kopfadresse %s"),
                     f"{kopf:02X}" if mit_adressen else t("ohne Adressen"))
            try:
                kennung = self.anfrage(bytes([0x1A, 0x9B]), timeout=self.timing.kwp_p2_start)
            except KeineAntwort:
                continue
            except KwpAblehnung as exc:           # antwortet – nur ohne Kennung
                log.info(t("KWP2000: Identifikation abgelehnt: %s"), exc)
            except Stoerung as exc:               # antwortet – nur gestört
                log.warning("%s", exc)
            break
        else:
            raise UnsupportedProtocol(
                t("Steuergerät {adresse:02X} spricht KWP2000 (Keyword {keyword}), antwortet aber "
                  "auf keine Anfrage. Für eine Fehlermeldung bitte das Protokoll mitschicken.",
                  adresse=self.adresse, keyword=self.keyword),
                keyword=self.keyword, protocol="KWP2000", baud=self.baud)
        log.info(t("KWP2000: Steuergerät antwortet unter Kopfadresse %s"),
                 f"{self.kopf:02X}" if self.mit_adressen else t("ohne Adressen"))
        verbindung = self._verbindung(kennung)
        if pruefung is not None:
            try:
                pruefung(verbindung)
            except BaseException:
                self.beenden()
                raise
        self._sitzung_eroeffnen()
        verbindung.sitzung = self.sitzung
        if kennung is None:      # manche Geräte nennen ihre Kennung erst in der Sitzung
            try:
                verbindung = self._verbindung(self.anfrage(bytes([0x1A, 0x9B])))
            except (KwpAblehnung, Stoerung, KeineAntwort) as exc:
                log.info(t("KWP2000: Identifikation nicht lesbar: %s"), exc)
        log.info(t("Verbunden mit %02X (KWP2000): %s %s"), self.adresse,
                 verbindung.teilenummer, verbindung.bauteil)
        return verbindung

    def _sitzung_eroeffnen(self) -> None:
        for sitzung in SITZUNGEN:
            try:
                self.anfrage(bytes([0x10, sitzung]), timeout=self.timing.kwp_p2_start)
            except KeineAntwort:
                log.info(t("KWP2000: keine Antwort auf Diagnosesitzung %02X"), sitzung)
                continue
            except (KwpAblehnung, Stoerung) as exc:
                log.info(t("KWP2000: Diagnosesitzung %02X: %s"), sitzung, exc)
                continue
            self.sitzung = sitzung
            log.info(t("KWP2000: Diagnosesitzung %02X eröffnet"), sitzung)
            return
        log.warning(t("KWP2000: keine Diagnosesitzung eröffnet – versuche es ohne"))

    def _verbindung(self, kennung: bytes | None) -> KwpVerbindung:
        info = kennung_auswerten(kennung[1:]) if kennung is not None else {}
        return KwpVerbindung(self.adresse, "KWP2000", self.keyword, self.baud, self.kl.echo,
                             kopf=self.kopf if self.mit_adressen else None,
                             sitzung=self.sitzung, fast_init=self.fast_init, **info)

    # ------------------------------------------------------------ Funktionen
    def fehler_lesen(self) -> list[Fehler]:
        """18 02 FF 00: alle gespeicherten Fehler. Antwort: Anzahl, dann je drei Bytes
        (Code hoch, Code tief, Status) – manche Geräte lassen die Anzahl weg."""
        antwort = self.anfrage(bytes([0x18, 0x02, 0xFF, 0x00]))
        daten = antwort[1:]
        if not daten:
            return []
        start = 1 if len(daten) == 1 + daten[0] * 3 else 0
        if start == 0 and len(daten) % 3:
            log.warning(t("KWP2000: Fehlerliste mit unerwarteter Länge %d: %s"), len(daten),
                        _hex(daten))
        fehler = []
        for i in range(start, len(daten) - 2, 3):
            code, status = (daten[i] << 8) | daten[i + 1], daten[i + 2]
            if code == 0xFFFF and status == 0x88:
                continue   # „Kein Fehler erkannt“
            # Das Statusbyte wird wie bei KW1281 gelesen (Fehlerart + Bit 7 sporadisch) –
            # bei KWP2000 ist das noch nicht an echten Geräten bestätigt, deshalb roh ins Protokoll
            log.info(t("KWP2000: Fehler %05d, Status %02X"), code, status)
            fehler.append(Fehler(code, status))
        return fehler

    def fehler_loeschen(self) -> list[Fehler]:
        log.info(t("Fehlerspeicher wird gelöscht"))
        self.anfrage(bytes([0x14, 0xFF, 0x00]))
        return []

    def gruppe_lesen(self, gruppe: int) -> list[Messwert]:
        if not 1 <= gruppe <= 255:
            raise NotAvailable(t("Messwertgruppe {gruppe:03d} ist nicht belegt", gruppe=gruppe))
        try:
            antwort = self.anfrage(bytes([0x21, gruppe]))
        except KwpAblehnung as exc:
            if exc.code in (0x12, 0x31):
                raise NotAvailable(t("Messwertgruppe {gruppe:03d} ist nicht belegt",
                                     gruppe=gruppe)) from exc
            raise
        daten = antwort[1:]
        if len(daten) % 3 == 1:
            if daten[0] != gruppe:
                self._rest_verwerfen()
                raise Stoerung(t("Antwort auf Gruppe {gruppe:03d} gehört zu Gruppe {andere:03d} "
                                 "– verworfen", gruppe=gruppe, andere=daten[0]), "zaehler")
            daten = daten[1:]
        felder = [tuple(daten[i:i + 3]) for i in range(0, len(daten) - 2, 3)]
        while felder and felder[-1] == PADDING:
            felder.pop()
        if not felder:
            raise NotAvailable(t("Messwertgruppe {gruppe:03d} ist nicht belegt", gruppe=gruppe))
        werte = gruppe_auswerten(b"".join(bytes(f) for f in felder))
        if len(werte) > 4:
            log.info(t("Gruppe %03d hat %d Felder (angezeigt werden die ersten vier): %s"),
                     gruppe, len(werte), " | ".join(w.text for w in werte))
        return werte

    # ------------------------------------------------------------ Anpassung
    def _routine(self, routine: int, unter: bytes, daten: bytes = b"") -> bytes:
        return self.anfrage(bytes([0x31, routine]) + unter + bytes(daten))

    def _anpassung_beginnen(self) -> None:
        try:
            self._routine(0xB8, ANPASSUNG)
        except KwpAblehnung as exc:
            if exc.code in (0x11, 0x12, 0x31):
                raise NotAvailable(t("Dieses Steuergerät bietet keine Anpassung über KWP2000 an "
                                     "({grund})", grund=exc)) from exc
            if exc.code == 0x33:
                raise Nak(t("Anpassung nur nach Anmeldung (Zugriffsschutz) – vagdiag meldet "
                            "sich nicht an")) from exc
            raise

    def _anpassung_beenden(self, nach_schreiben: bool = False) -> None:
        """32 B8 01 03 – verwirft einen nur getesteten Wert. Klappt das nach einem
        Schreibversuch nicht, wird die Verbindung beendet (82, ohne Wiederholung): Mit
        dem Ende der Diagnosesitzung soll das Steuergerät auch die Anpassung verlassen.
        Wirft dann ProtocolError."""
        try:
            self.anfrage(bytes([0x32, 0xB8]) + ANPASSUNG)
        except (DiagError, KLineError, PortError) as exc:
            if not nach_schreiben:
                log.info(t("KWP2000: Anpassung beenden: %s"), exc)
                return
            log.warning(t("KWP2000: Anpassung lässt sich nach dem Schreiben nicht beenden "
                          "(%s) – beende die Verbindung"), exc)
            self.beenden()
            raise ProtocolError(t("Anpassung ließ sich nicht beenden ({fehler}) – Verbindung "
                                  "beendet, damit das Steuergerät keinen Testwert behält",
                                  fehler=exc)) from exc
        finally:
            self._anp_kanal = None

    @staticmethod
    def _kanal_fehler(exc: KwpAblehnung, kanal: int) -> DiagError:
        if exc.code in (0x12, 0x31):
            return NotAvailable(t("Anpassungskanal {kanal:02d} ist nicht belegt", kanal=kanal))
        if exc.code == 0x33:
            return Nak(t("Anpassungskanal {kanal:02d} abgelehnt – nicht vorhanden oder nur "
                         "nach Anmeldung (Login) lesbar", kanal=kanal))
        return Nak(t("Anpassungskanal {kanal:02d}: {fehler}", kanal=kanal, fehler=exc))

    def _kanal_waehlen(self, kanal: int) -> None:
        try:
            self._routine(0xB9, ANPASSUNG, bytes([kanal]))
        except KwpAblehnung as exc:
            raise self._kanal_fehler(exc, kanal) from exc

    def _anpassung_holen(self, kanal: int, wie: str) -> Anpassung:
        """31 BA 01 03 → 71 BA 01 03 <Status> 03 <Wert hoch> <Wert tief>, manchmal danach
        04 und ein Messwert (Formel, a, b) – Aufbau wie in kw1281test."""
        try:
            antwort = self._routine(0xBA, ANPASSUNG)
        except KwpAblehnung as exc:
            raise self._kanal_fehler(exc, kanal) from exc
        log.info(t("KWP2000: Anpassung Kanal %02d, Antwort %s"), kanal, _hex(antwort))
        if len(antwort) >= 8 and antwort[1] == 0xBA and antwort[2:4] == ANPASSUNG:
            messwerte = (gruppe_auswerten(bytes(antwort[9:12]))
                         if len(antwort) >= 12 and antwort[8] == 0x04 else [])
            anpassung = Anpassung(kanal, (antwort[6] << 8) | antwort[7], bytes(antwort[1:]),
                                  messwerte)
            log.info(t("Anpassung %s: %s"), wie, anpassung.text)
            return anpassung
        raise NotAvailable(t("Anpassungskanal {kanal:02d}: Antwort {roh} wird nicht ausgewertet",
                             kanal=kanal, roh=_hex(antwort)))

    def anpassung_lesen(self, kanal: int) -> Anpassung:
        """Ändert nichts: Anpassung beginnen, Kanal wählen, Wert lesen, Anpassung beenden."""
        if not 1 <= kanal <= 255:
            raise ValueError(t("Anpassungskanal muss zwischen 1 und 255 liegen (Kanal 00 "
                               "wird bewusst nicht angesprochen)"))
        self._anpassung_beginnen()
        try:
            self._kanal_waehlen(kanal)
            return self._anpassung_holen(kanal, t("gelesen"))
        finally:
            self._anpassung_beenden()

    def anpassung_schreiben(self, kanal: int, wert: int, werkstattcode: bytes) -> Anpassung:
        """Expertenmodus: in einer Anpassungssitzung Kanal wählen, Wert testen und nachlesen,
        speichern – mit den sechs Bytes des Werkstattcodes aus der Kennung des Steuergeräts
        – und nachlesen. Übernimmt das Steuergerät den Testwert nicht, wird nichts
        gespeichert (Ende der Anpassung verwirft den Testwert)."""
        if len(werkstattcode) != 6:
            raise NotAvailable(t("Werkstattcode des Steuergeräts nicht lesbar – nichts "
                                 "geschrieben"))
        wert_bytes = bytes([wert >> 8, wert & 0xFF])
        self._anpassung_beginnen()
        geschrieben = False
        try:
            self._kanal_waehlen(kanal)
            geschrieben = True              # ab hier: Ende der Anpassung muss klappen
            try:
                self._routine(0xB9, ANPASSUNG, wert_bytes)
            except KwpAblehnung as exc:
                raise Nak(t("Steuergerät lehnt Wert {wert} für Kanal {kanal:02d} ab", wert=wert,
                            kanal=kanal)) from exc
            getestet = self._anpassung_holen(kanal, t("getestet"))
            if getestet.wert != wert:
                raise Nak(t("Steuergerät übernimmt Wert {wert} für Kanal {kanal:02d} nicht "
                            "(zeigt {jetzt}) – nichts gespeichert", wert=wert, kanal=kanal,
                            jetzt=getestet.wert))
            try:
                self._routine(0xBB, ANPASSUNG, wert_bytes + bytes(werkstattcode))
            except KwpAblehnung as exc:
                raise Nak(t("Steuergerät speichert Wert {wert} für Kanal {kanal:02d} nicht",
                            wert=wert, kanal=kanal)) from exc
            ergebnis = self._anpassung_holen(kanal, t("gespeichert"))
        except BaseException as exc:
            try:
                self._anpassung_beenden(geschrieben)
            except ProtocolError as ende:
                # beide Gründe nennen – der erste erklärt, warum es nicht weiterging
                raise ProtocolError(f"{exc} – {ende}") from exc
            raise
        self._anpassung_beenden(geschrieben)
        return ergebnis

    # ------------------------------------------------------------ Stellglieddiagnose
    @staticmethod
    def _stellglied_fehler(exc: KwpAblehnung) -> DiagError:
        if exc.code in (0x11, 0x12, 0x31):
            return NotAvailable(t("Dieses Steuergerät bietet keine Stellglieddiagnose über "
                                  "KWP2000 an ({grund})", grund=exc))
        if exc.code == 0x22:
            return Nak(t("Stellglieddiagnose abgelehnt: Bedingungen nicht erfüllt (z. B. Motor "
                         "läuft)"))
        if exc.code == 0x33:
            return Nak(t("Stellglieddiagnose nur nach Anmeldung (Zugriffsschutz) – vagdiag "
                         "meldet sich nicht an"))
        return exc

    def stellglied_starten(self) -> Stellglied | None:
        """Experimentell: 31 B8 01 02, danach den Status lesen. Solange die Diagnose läuft,
        hält die Statusabfrage die Verbindung wach (wie in kw1281test)."""
        try:
            self._routine(0xB8, STELLGLIED)
        except KwpAblehnung as exc:
            raise self._stellglied_fehler(exc) from exc
        if self._keepalive_vorher is None:
            self._keepalive_vorher = self._keepalive_dienst
        self._keepalive_dienst = bytes([0x31, 0xBA]) + STELLGLIED
        return self._stellglied_status()

    def stellglied_weiter(self) -> Stellglied | None:
        """Ein Schritt (31 B9 01 02). Beim EDC16 steuert der erste Schritt das angezeigte
        Stellglied an, der zweite schaltet zum nächsten (laut kw1281test)."""
        try:
            self._routine(0xB9, STELLGLIED)
        except KwpAblehnung as exc:
            raise self._stellglied_fehler(exc) from exc
        return self._stellglied_status()

    def _stellglied_status(self) -> Stellglied | None:
        """Bis zu acht Statusabfragen, bis ein Zustandsdatensatz kommt:
        71 BA 01 02 03 03 <Nummer hoch> <Nummer tief>. Dazwischen schickt das EDC16
        Messwert-Datensätze. Kommt keiner, ist die Liste zu Ende (None)."""
        for _ in range(8):
            try:
                antwort = self._routine(0xBA, STELLGLIED)
            except KwpAblehnung as exc:
                raise self._stellglied_fehler(exc) from exc
            if (len(antwort) >= 8 and antwort[1] == 0xBA and antwort[2:4] == STELLGLIED
                    and antwort[4] == 0x03 and antwort[5] == 0x03):
                stellglied = Stellglied((antwort[6] << 8) | antwort[7], bytes(antwort[1:]))
                log.info(t("Stellglied: %s (KWP %s)"), stellglied.text, _hex(antwort))
                return stellglied
            log.info(t("KWP2000: Stellglied-Status ohne Nummer: %s"), _hex(antwort))
        return None

    def stellglied_beenden(self) -> None:
        if self._keepalive_vorher is not None:
            self._keepalive_dienst, self._keepalive_vorher = self._keepalive_vorher, None
        try:
            self.anfrage(bytes([0x32, 0xB8]) + STELLGLIED)
        except (DiagError, KLineError, PortError) as exc:
            log.info(t("KWP2000: Stellglieddiagnose beenden: %s"), exc)

    def keep_alive(self) -> None:
        """Tester present – aber nur, wenn länger nichts los war (P3 höchstens 5 s)."""
        if time.monotonic() - self._letzte_antwort < self.timing.kwp_keepalive:
            return
        try:
            self.anfrage(self._keepalive_dienst)
        except KwpAblehnung:
            if self._keepalive_dienst[0] != 0x3E:
                raise
            # ohne Tester present: die Sitzung erneut anfordern hält ebenfalls wach
            self._keepalive_dienst = bytes([0x10, self.sitzung or 0x81])
            log.info(t("KWP2000: Tester present nicht unterstützt – halte die Verbindung "
                       "über die Diagnosesitzung"))

    def beenden(self) -> bool:
        """StopCommunication (82). Zurück: ob das Steuergerät es bestätigt hat."""
        try:
            self.anfrage(bytes([0x82]), timeout=0.5)
            return True
        except (DiagError, KLineError, PortError, OSError) as exc:
            log.debug(t("Trennen: %s"), exc)
            return False

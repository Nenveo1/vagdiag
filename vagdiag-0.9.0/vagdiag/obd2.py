"""Allgemeine Abgasdiagnose OBD-II/EOBD über die K-Leitung (Adresse 33) – nur lesen.

VCDS-Lite prüft hier nur, ob ein Auto OBD-II spricht. vagdiag zeigt dazu die Readiness
und die Motorkontrollleuchte (Mode 01 PID 01), die OBD-Norm (PID 1C), welche Werte das
Auto über OBD-II liefert und die Fahrgestellnummer (Mode 09 PID 02).

Ablauf (ISO 9141-2 bzw. ISO 14230-4, beide mit 10400 Baud):
  1. Reizung: Adresse 33 mit 5 Baud. Das Steuergerät antwortet mit Sync 55 und zwei
     Keybytes: 08 08 oder 94 94 = ISO 9141-2, xx 8F = ISO 14230-4 (KWP2000). Nach 25–50 ms
     (W4) geht das invertierte zweite Keybyte zurück, das Steuergerät bestätigt mit der
     invertierten Adresse (CC). Antwortet niemand, folgt der Fast-Init (25 ms Low, 25 ms
     High) mit StartCommunication C1 33 F1 81 66 (ISO 14230-4).
  2. Jede Anfrage geht an alle Abgas-Steuergeräte zugleich (funktionale Adresse 33):
       ISO 9141-2:   68 6A F1 <Mode> <PID> <Prüfsumme>  →  48 6B <SG> <Mode+40> <PID> …
       ISO 14230-4:  C2 33 F1 <Mode> <PID> <Prüfsumme>  →  8x F1 <SG> <Mode+40> <PID> …
     Prüfsumme = Summe aller Bytes (untere 8 Bit). Zwischen den eigenen Bytes 5–20 ms
     (P4), nach den Antworten mindestens 55 ms Ruhe (P3). Antworten mehrere Steuergeräte
     (Motor, Getriebe), kommen ihre Nachrichten nacheinander. Wer einen Wert nicht kennt,
     schweigt (ISO 9141-2) oder lehnt ab (7F).
  3. Gesendet werden nur die lesenden Anfragen aus ERLAUBT: Mode 01 PID 00/20/40/… (welche
     Werte es gibt), 01 (Readiness, Motorkontrollleuchte) und 1C (OBD-Norm), Mode 09 PID 00
     und 02 (Fahrgestellnummer). Nie Mode 04 – das löscht die Abgasfehler und setzt die
     Readiness zurück – und keine anderen Modes.
Danach hält das Steuergerät seine OBD-Sitzung noch bis zu 5 s (P3 max). Das nächste
Steuergerät reizt vagdiag erst danach (siehe DiagSession._obd2_test).

Die Bedeutung der Werte folgt SAE J1979 (ISO 15031-5); die Bits der Readiness bei VAG
stehen in derselben Reihenfolge (Katalysator in Bit 0 bis Abgasrückführung in Bit 7).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .berichte import kopf
from .kline import KLine, Timeout
from .kw1281 import ProtocolError, SchreibenGesperrt, Timing
from .kwp2000 import _genau_warten
from .sprache import N_, t

log = logging.getLogger("vagdiag.proto")

ADRESSE = 0x33
TESTER = 0xF1
BAUD = 10400
ISO9141 = "ISO 9141-2"
KWP_5BAUD = N_("ISO 14230-4 (KWP2000, 5-Baud-Reizung)")
KWP_FAST = N_("ISO 14230-4 (KWP2000, Fast-Init)")
ISO9141_KEYBYTES = {(0x08, 0x08), (0x94, 0x94)}
KWP_KB2 = 0x8F
START_COMMUNICATION = 0x81

# Die einzigen Anfragen, die vagdiag über OBD-II sendet: Mode → PIDs. Alle nur lesend.
ERLAUBT: dict[int, frozenset[int]] = {
    0x01: frozenset({0x00, 0x01, 0x1C, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0}),
    0x09: frozenset({0x00, 0x02}),
}

# Readiness (Mode 01 PID 01): Prüfungen, die laufend stattfinden (Byte B, Bits 0–2) …
LAUFEND = (N_("Verbrennungsaussetzer"), N_("Kraftstoffsystem"),
           N_("Bauteile (umfassende Überwachung)"))
# … und die einmal je Fahrt abgeschlossen werden (Bytes C/D, Bits 0–7) – je nach Zündart
OTTO = (N_("Katalysator"), N_("Katalysatorheizung"), N_("Tankentlüftung"),
        N_("Sekundärluftsystem"), N_("Klimaanlage (Kältemittel)"), N_("Lambdasonden"),
        N_("Lambdasondenheizung"), N_("Abgasrückführung"))
DIESEL = (N_("NMHC-Katalysator"), N_("NOx-Nachbehandlung"), None, N_("Ladedruck"), None,
          N_("Abgassensor"), N_("Partikelfilter"),
          N_("Abgasrückführung / variable Ventilsteuerung"))

# OBD-Norm (Mode 01 PID 1C)
NORMEN = {
    1: N_("OBD-II (Kalifornien, CARB)"), 2: N_("OBD (US-Umweltbehörde EPA)"),
    3: N_("OBD und OBD-II"), 4: N_("OBD-I"), 5: N_("keine OBD-Norm"), 6: N_("EOBD (Europa)"),
    7: N_("EOBD und OBD-II"), 8: N_("EOBD und OBD"), 9: N_("EOBD, OBD und OBD-II"),
    10: N_("JOBD (Japan)"), 11: N_("JOBD und OBD-II"), 12: N_("JOBD und EOBD"),
    13: N_("JOBD, EOBD und OBD-II"),
}

# Namen der Werte (Mode 01) – die übrigen zeigt vagdiag nur mit Nummer
PIDS_01 = {
    0x01: N_("Readiness und Motorkontrollleuchte"), 0x02: N_("Fehler des Freeze Frame"),
    0x03: N_("Status Kraftstoffsystem"), 0x04: N_("Motorlast (berechnet)"),
    0x05: N_("Kühlmitteltemperatur"), 0x06: N_("Gemischanpassung kurzfristig, Bank 1"),
    0x07: N_("Gemischanpassung langfristig, Bank 1"),
    0x08: N_("Gemischanpassung kurzfristig, Bank 2"),
    0x09: N_("Gemischanpassung langfristig, Bank 2"), 0x0A: N_("Kraftstoffdruck"),
    0x0B: N_("Saugrohrdruck"), 0x0C: N_("Motordrehzahl"), 0x0D: N_("Geschwindigkeit"),
    0x0E: N_("Zündzeitpunkt"), 0x0F: N_("Ansauglufttemperatur"), 0x10: N_("Luftmasse"),
    0x11: N_("Drosselklappenstellung"), 0x12: N_("Status Sekundärluft"),
    0x13: N_("Vorhandene Lambdasonden"), 0x1C: N_("OBD-Norm"),
    0x1D: N_("Vorhandene Lambdasonden (vier Bänke)"), 0x1E: N_("Nebenabtrieb"),
    0x1F: N_("Laufzeit seit Motorstart"), 0x21: N_("Fahrstrecke mit Motorkontrollleuchte an"),
}
PIDS_09 = {0x02: N_("Fahrgestellnummer (FIN)"), 0x04: N_("Kalibrierungs-ID"),
           0x06: N_("Kalibrierungs-Prüfnummer (CVN)"), 0x08: N_("Zähler der Überwachungen"),
           0x0A: N_("Name des Steuergeräts")}


def _hex(daten: bytes) -> str:
    return " ".join(f"{b:02X}" for b in daten)


def pid_name(mode: int, pid: int) -> str:
    if mode == 0x01 and 0x14 <= pid <= 0x1B:
        return t("Lambdasonde Bank {bank}, Sonde {sonde}", bank=(pid - 0x14) // 4 + 1,
                 sonde=(pid - 0x14) % 4 + 1)
    name = (PIDS_01 if mode == 0x01 else PIDS_09).get(pid)
    return t(name) if name else ""


# --------------------------------------------------------------------------- Auswertung
@dataclass
class Monitor:
    name: str               # intern deutsch, angezeigt mit t()
    vorhanden: bool
    fertig: bool

    @property
    def status(self) -> str:
        if not self.vorhanden:
            return t("nicht vorhanden")
        return t("abgeschlossen") if self.fertig else t("nicht abgeschlossen")


@dataclass
class Readiness:
    mil: bool               # Motorkontrollleuchte an
    fehler: int             # gespeicherte Abgasfehler
    diesel: bool
    monitore: list[Monitor]

    @property
    def alle_fertig(self) -> bool:
        return all(m.fertig for m in self.monitore if m.vorhanden)


def readiness_auswerten(daten: bytes) -> Readiness:
    """Mode 01 PID 01 (vier Bytes A–D): A Bit 7 = Motorkontrollleuchte an, Bits 0–6 = Zahl
    der gespeicherten Abgasfehler; B Bit 3 = Diesel (Kompressionszündung), Bits 0–2 = laufende
    Prüfungen vorhanden, Bits 4–6 = davon noch nicht abgeschlossen; C = vorhandene, D = noch
    nicht abgeschlossene Prüfungen (Bit 0–7, Bedeutung je nach Zündart)."""
    a, b, c, d = daten[:4]
    diesel = bool(b & 0x08)
    monitore = [Monitor(name, bool(b >> i & 1), not b >> (i + 4) & 1)
                for i, name in enumerate(LAUFEND)]
    for i, name in enumerate(DIESEL if diesel else OTTO):
        if name is not None:          # reservierte Bits bei Diesel
            monitore.append(Monitor(name, bool(c >> i & 1), not d >> i & 1))
    return Readiness(bool(a & 0x80), a & 0x7F, diesel, monitore)


def unterstuetzte(basis: int, daten: bytes) -> set[int]:
    """Antwort auf PID 00/20/40 …: 32 Bit, das höchste steht für PID basis+1."""
    if len(daten) < 4:
        return set()
    wert = int.from_bytes(daten[:4], "big")
    return {basis + i + 1 for i in range(32) if wert >> (31 - i) & 1}


def fin_zusammensetzen(teile: list[bytes]) -> str | None:
    """Mode 09 PID 02 über die K-Leitung: Nachrichten <Nummer> d1 d2 d3 d4 – die erste mit
    drei Füllbytes 00 –, zusammen 17 Zeichen (manche Steuergeräte schicken alles in einer)."""
    geordnet = sorted((t_[0], t_[1:]) for t_ in teile if len(t_) >= 2)
    roh = b"".join(d for _, d in geordnet).lstrip(b"\x00")
    text = "".join(chr(b) for b in roh if 0x20 < b < 0x7F)
    return text or None


def iso9141_nachrichten(daten: bytes) -> list[tuple[int, bytes]]:
    """(Steuergerät, Daten) aller Antworten 48 6B <SG> <Daten …> <Prüfsumme>. ISO 9141-2
    kennt kein Längenbyte: Eine Nachricht (höchstens 7 Datenbytes) endet dort, wo die
    Prüfsumme stimmt und die nächste beginnt – oder der Strom endet."""
    gefunden = []
    i = 0
    while i + 4 < len(daten):
        if daten[i:i + 2] != b"\x48\x6b":
            i += 1
            continue
        for ende in range(i + 4, min(len(daten), i + 11)):
            if (sum(daten[i:ende]) & 0xFF) == daten[ende] and (
                    ende + 1 == len(daten) or daten[ende + 1:ende + 3] == b"\x48\x6b"):
                gefunden.append((daten[i + 2], bytes(daten[i + 3:ende])))
                i = ende + 1
                break
        else:
            i += 1
    return gefunden


def kwp_nachrichten(daten: bytes) -> list[tuple[int | None, int | None, bytes]]:
    """(Ziel, Quelle, Daten) aller Nachrichten nach ISO 14230 – eine nach der anderen; was
    nicht passt (Prüfsumme falsch), wird byteweise übersprungen."""
    gefunden = []
    i = 0
    while i < len(daten):
        fmt = daten[i]
        kopf_ = 3 if fmt & 0x80 else 1
        laenge = fmt & 0x3F
        if laenge == 0:
            if i + kopf_ >= len(daten):
                break
            laenge = daten[i + kopf_]
            kopf_ += 1
        ende = i + kopf_ + laenge
        if laenge and ende < len(daten) and (sum(daten[i:ende]) & 0xFF) == daten[ende]:
            ziel, quelle = (daten[i + 1], daten[i + 2]) if fmt & 0x80 else (None, None)
            gefunden.append((ziel, quelle, bytes(daten[i + kopf_:ende])))
            i = ende + 1
        else:
            i += 1
    return gefunden


# --------------------------------------------------------------------------- Ergebnis
@dataclass
class ObdSteuergeraet:
    adresse: int
    pids: set[int] = field(default_factory=set)        # Mode 01, unterstützt
    pids_09: set[int] = field(default_factory=set)
    readiness: Readiness | None = None
    norm: int | None = None


@dataclass
class Obd2Ergebnis:
    protokoll: str | None = None            # None: kein OBD-II gefunden
    keybytes: tuple[int, int] | None = None
    steuergeraete: dict[int, ObdSteuergeraet] = field(default_factory=dict)
    fin: str | None = None
    fin_hinweis: str = ""
    meldungen: list[str] = field(default_factory=list)
    sim: bool = False
    zeit: float = field(default_factory=time.time)

    def steuergeraet(self, adresse: int) -> ObdSteuergeraet:
        return self.steuergeraete.setdefault(adresse, ObdSteuergeraet(adresse))

    @property
    def ok(self) -> bool:
        return self.protokoll is not None and bool(self.steuergeraete)

    @property
    def readiness(self) -> tuple[int, Readiness] | None:
        """Die Readiness des ersten Steuergeräts, das sie nennt (meist der Motor, 10)."""
        for adresse in sorted(self.steuergeraete):
            r = self.steuergeraete[adresse].readiness
            if r is not None:
                return adresse, r
        return None

    def kurz(self) -> str:
        """Eine Zeile fürs Ergebnis: OBD-II ja/nein, Protokoll."""
        if not self.ok:
            return t("Kein OBD-II gefunden")
        sg = ", ".join(f"{a:02X}" for a in sorted(self.steuergeraete))
        return t("OBD-II wird unterstützt: {protokoll}, Steuergerät(e) {sg}",
                 protokoll=t(self.protokoll), sg=sg)

    def zeilen(self) -> list[str]:
        z = kopf(t("OBD-II-Test"), self.sim) + [""]
        z.append(t("Ergebnis: {kurz}", kurz=self.kurz()))
        if self.protokoll is not None and self.keybytes is not None:
            z.append(t("Protokoll: {protokoll}, Keybytes {kb1:02X} {kb2:02X}",
                       protokoll=t(self.protokoll), kb1=self.keybytes[0], kb2=self.keybytes[1]))
        z += self.meldungen
        if self.fin:
            z.append(t("Fahrgestellnummer (Mode 09): {fin}", fin=self.fin))
        elif self.fin_hinweis:
            z.append(t("Fahrgestellnummer: {hinweis}", hinweis=self.fin_hinweis))
        for adresse in sorted(self.steuergeraete):
            sg = self.steuergeraete[adresse]
            z += ["", t("Steuergerät {adresse:02X}:", adresse=adresse)]
            if sg.norm is not None:
                norm = NORMEN.get(sg.norm)
                z.append("  " + t("OBD-Norm: {norm}", norm=t(norm) if norm else
                                  t("Code {code}", code=sg.norm)))
            r = sg.readiness
            if r is not None:
                z.append("  " + t("Motorkontrollleuchte: {an}",
                                  an=t("an") if r.mil else t("aus")))
                z.append("  " + t("Gespeicherte Abgasfehler: {anzahl}", anzahl=r.fehler))
                z.append("  " + t("Zündart: {art}", art=t("Diesel (Kompressionszündung)")
                                  if r.diesel else t("Otto (Fremdzündung)")))
                z.append("  " + t("Readiness:"))
                breite = max(len(t(m.name)) for m in r.monitore)
                for m in r.monitore:
                    z.append(f"    {t(m.name):<{breite}}  {m.status}")
            if sg.pids:
                z.append("  " + t("Werte über OBD-II (Mode 01):"))
                z += [f"    {pid:02X}  {pid_name(1, pid)}".rstrip()
                      for pid in sorted(sg.pids) if pid % 0x20]
            if sg.pids_09:
                z.append("  " + t("Fahrzeuginformationen (Mode 09):"))
                z += [f"    {pid:02X}  {pid_name(9, pid)}".rstrip()
                      for pid in sorted(sg.pids_09) if pid % 0x20]
        z += ["", t("Nur gelesen. Abgasfehler löschen (Mode 04) sendet vagdiag nie – das "
                    "würde auch die Readiness zurücksetzen.")]
        return z


# --------------------------------------------------------------------------- Ablauf
@dataclass
class ObdZeiten:
    p2: float = 0.5          # Warten auf die erste Antwort (Norm: bis 50 ms)
    luecke: float = 0.1      # so lange Ruhe: alle Antworten sind da (Norm P2: bis 50 ms)
    p3: float = 0.06         # Ruhe vor der nächsten Anfrage (Norm: mindestens 55 ms)
    p4: float = 0.006        # zwischen den eigenen Bytes (Norm: 5–20 ms)
    fast_init_antwort: float = 0.4


class Obd2:
    """Ein OBD-II-Dialog über die K-Leitung – nur die lesenden Anfragen aus ERLAUBT."""

    def __init__(self, kline: KLine, timing: Timing, zeiten: ObdZeiten | None = None):
        self.kl = kline
        self.timing = timing
        self.z = zeiten or ObdZeiten()
        self.protokoll: str | None = None
        self.keybytes: tuple[int, int] | None = None
        self.offen = False          # ein Steuergerät hat eine OBD-Sitzung (danach Pause)
        self._frei_ab = 0.0

    # ------------------------------------------------------------ Aufbau
    def verbinden(self, fast_init: bool = True) -> bool:
        self.kl.set_baudrate(BAUD)
        log.info(t("OBD-II: reize Adresse 33 (5 Baud, Empfang mit 10400 Baud) …"))
        if self._reizen():
            return True
        if not fast_init:
            return False
        log.info(t("OBD-II: keine Antwort auf die 5-Baud-Reizung – versuche den Fast-Init"))
        return self._fast_init()

    def _reizen(self) -> bool:
        self.kl.send_5baud(ADRESSE)
        ende = time.perf_counter() + self.timing.sync_timeout
        while True:
            rest = ende - time.perf_counter()
            try:
                if rest <= 0:
                    raise Timeout(t("Sync-Zeit abgelaufen"))
                byte = self.kl.read_byte(rest)
            except Timeout:
                return False
            if byte == 0x55:
                break
            if byte != 0x00:                    # 00: Reste der Reizung
                log.info(t("OBD-II: Byte %02X statt Sync 55"), byte)
                return False
        try:
            kb1 = self.kl.read_byte(self.timing.keybyte_timeout)
            kb2 = self.kl.read_byte(self.timing.keybyte_timeout)
        except Timeout:
            log.info(t("OBD-II: Sync, aber keine Keybytes"))
            return False
        if (kb1, kb2) in ISO9141_KEYBYTES:
            protokoll = ISO9141
        elif kb2 == KWP_KB2:
            protokoll = KWP_5BAUD
        else:
            log.info(t("OBD-II: unbekannte Keybytes %02X %02X"), kb1, kb2)
            return False
        log.info(t("OBD-II: Sync 55, Keybytes %02X %02X → %s"), kb1, kb2, t(protokoll))
        time.sleep(self.timing.w4)
        self.offen = True                       # ab dem invertierten KB2 gibt es eine Sitzung
        self.kl.write_byte(kb2 ^ 0xFF)
        try:
            bestaetigung = self.kl.read_byte(self.timing.keybyte_timeout)
            if bestaetigung != ADRESSE ^ 0xFF:
                log.warning(t("OBD-II: Bestätigung %02X statt CC – versuche es trotzdem"),
                            bestaetigung)
        except Timeout:
            log.warning(t("OBD-II: keine Bestätigung (invertierte Adresse) – versuche es "
                          "trotzdem"))
        self.protokoll, self.keybytes = protokoll, (kb1, kb2)
        self._frei_ab = time.monotonic() + self.z.p3
        return True

    def _fast_init(self) -> bool:
        """ISO 14230-4: Leitung frei, 25 ms Low, 25 ms High, dann sofort StartCommunication
        an die funktionale Adresse 33. Antwort: C1 mit den Keybytes."""
        anfrage = self._kwp_nachricht(bytes([START_COMMUNICATION]))
        self.kl.fast_init_puls()
        self.kl.write_raw(anfrage)
        self.offen = True                       # womöglich hat eins zugehört
        log.debug("→ OBD %s (StartCommunication)", _hex(anfrage))
        daten = self._burst(self.z.fast_init_antwort)
        stelle = daten.find(anfrage)
        rest = daten[stelle + len(anfrage):] if stelle >= 0 else daten
        if self.kl.echo is None and daten:
            self.kl.echo = stelle >= 0
        for ziel, quelle, antwort in kwp_nachrichten(rest):
            if ziel == TESTER and antwort[:1] == b"\xc1" and len(antwort) >= 3:
                self.protokoll, self.keybytes = KWP_FAST, (antwort[1], antwort[2])
                log.info(t("OBD-II: Fast-Init beantwortet von %02X, Keybytes %02X %02X"),
                         quelle, antwort[1], antwort[2])
                return True
        if rest:
            log.info(t("OBD-II: keine gültige Antwort auf den Fast-Init (%s)"), _hex(rest))
        self.offen = False
        return False

    # ------------------------------------------------------------ Nachrichten
    @staticmethod
    def _kwp_nachricht(daten: bytes) -> bytes:
        roh = bytes([0xC0 | len(daten), ADRESSE, TESTER]) + bytes(daten)
        return roh + bytes([sum(roh) & 0xFF])

    def _nachricht(self, daten: bytes) -> bytes:
        if self.protokoll == ISO9141:
            roh = bytes([0x68, 0x6A, TESTER]) + bytes(daten)
            return roh + bytes([sum(roh) & 0xFF])
        return self._kwp_nachricht(daten)

    @staticmethod
    def pruefen(daten: bytes) -> None:
        """Schreibsperre: nur Mode 01 und 09 mit den PIDs aus ERLAUBT, sonst nichts."""
        if len(daten) != 2 or daten[1] not in ERLAUBT.get(daten[0], ()):
            raise SchreibenGesperrt(t("OBD-II: Anfrage {daten} ist in vagdiag gesperrt (nur "
                                      "lesende Anfragen)", daten=_hex(daten)))

    def _senden(self, daten: bytes) -> None:
        daten = bytes(daten)
        self.pruefen(daten)
        roh = self._nachricht(daten)
        rest = self._frei_ab - time.monotonic()
        if rest > 0:
            time.sleep(rest)
        log.debug("→ OBD %s", _hex(roh))
        # Zeitwächter wie bei KWP2000: zwischen zwei eigenen Bytes höchstens P4 max
        frist: float | None = None
        for i, byte in enumerate(roh):
            if i and self.z.p4:
                _genau_warten(self.z.p4)
            if frist is not None and time.perf_counter() > frist:
                raise ProtocolError(t("OBD-II: Byte {nummer}/{anzahl} wäre zu spät gekommen "
                                      "(Rechner hing) – Anfrage abgebrochen",
                                      nummer=i + 1, anzahl=len(roh)))
            self.kl.write_byte(byte)
            if frist is not None and self.kl.gesendet > frist:
                raise ProtocolError(t("OBD-II: Byte {nummer}/{anzahl} ging zu spät hinaus "
                                      "(Rechner hing) – Anfrage abgebrochen",
                                      nummer=i + 1, anzahl=len(roh)))
            frist = self.kl.gesendet + max(self.z.p4, self.timing.kwp_p4_frist)

    def _burst(self, erstes: float) -> bytes:
        """Alles lesen, bis die Leitung z.luecke ruhig ist."""
        daten = bytearray()
        warten = erstes
        while len(daten) < 255:
            try:
                daten.append(self.kl.read_byte(warten))
            except Timeout:
                break
            warten = self.z.luecke
        self._frei_ab = time.monotonic() + self.z.p3
        return bytes(daten)

    def anfrage(self, mode: int, pid: int) -> list[tuple[int, bytes]]:
        """Anfrage an alle; zurück (Steuergerät, Daten nach Mode+40 und PID) je Antwort –
        bei der FIN auch mehrere je Steuergerät. Ablehnungen (7F) stehen im Protokoll."""
        self._senden(bytes([mode, pid]))
        daten = self._burst(self.z.p2)
        if not daten:
            log.info(t("OBD-II: keine Antwort auf %02X %02X"), mode, pid)
            return []
        log.debug("← OBD %s", _hex(daten))
        if self.protokoll == ISO9141:
            nachrichten = iso9141_nachrichten(daten)
        else:
            nachrichten = [(quelle, inhalt) for ziel, quelle, inhalt in kwp_nachrichten(daten)
                           if ziel in (TESTER, None)]
        if not nachrichten:
            log.info(t("OBD-II: Antwort nicht lesbar: %s"), _hex(daten))
        antworten = []
        for quelle, inhalt in nachrichten:
            if inhalt[:2] == bytes([mode | 0x40, pid]):
                antworten.append((quelle, inhalt[2:]))
            elif inhalt[:1] == b"\x7f":
                log.info(t("OBD-II: %02X lehnt %02X %02X ab (%s)"), quelle, mode, pid,
                         _hex(inhalt))
        return antworten

    # ------------------------------------------------------------ Test
    def test(self, fast_init: bool = True, sim: bool = False) -> Obd2Ergebnis:
        e = Obd2Ergebnis(sim=sim)
        if not self.verbinden(fast_init):
            e.meldungen.append(t("Keine Antwort an Adresse 33 – das Auto spricht über die "
                                 "K-Leitung kein OBD-II (oder die Zündung ist aus)."))
            return e
        e.protokoll, e.keybytes = self.protokoll, self.keybytes
        basis = 0x00
        while True:                             # welche Werte gibt es (Mode 01)?
            antworten = self.anfrage(0x01, basis)
            weiter = False
            for sg, daten in antworten:
                eintrag = e.steuergeraet(sg)
                eintrag.pids |= unterstuetzte(basis, daten)
                weiter = weiter or basis + 0x20 in eintrag.pids
            basis += 0x20
            if not weiter or basis not in ERLAUBT[0x01]:
                break
        if not e.steuergeraete:
            e.meldungen.append(t("Die Reizung klappte, aber kein Steuergerät nannte seine "
                                 "Werte (Mode 01 PID 00)."))
            return e
        if any(0x01 in sg.pids for sg in e.steuergeraete.values()):
            for sg, daten in self.anfrage(0x01, 0x01):
                if len(daten) >= 4:
                    e.steuergeraet(sg).readiness = readiness_auswerten(daten)
        if any(0x1C in sg.pids for sg in e.steuergeraete.values()):
            for sg, daten in self.anfrage(0x01, 0x1C):
                if daten:
                    e.steuergeraet(sg).norm = daten[0]
        antworten = self.anfrage(0x09, 0x00)
        for sg, daten in antworten:
            e.steuergeraet(sg).pids_09 |= unterstuetzte(0x00, daten)
        if any(0x02 in sg.pids_09 for sg in e.steuergeraete.values()):
            teile: dict[int, list[bytes]] = {}
            for sg, daten in self.anfrage(0x09, 0x02):
                teile.setdefault(sg, []).append(daten)
            for sg in sorted(teile):
                e.fin = fin_zusammensetzen(teile[sg])
                if e.fin:
                    break
            if not e.fin:
                e.fin_hinweis = t("angefordert, aber keine lesbare Antwort")
        elif antworten:
            e.fin_hinweis = t("nicht über OBD-II verfügbar (Mode 09 PID 02 fehlt)")
        else:
            e.fin_hinweis = t("nicht über OBD-II verfügbar (keine Antwort auf Mode 09)")
        return e

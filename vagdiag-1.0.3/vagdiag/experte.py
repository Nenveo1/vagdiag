# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Expertenmodus: die ersten Funktionen, die etwas im Steuergerät ändern.

Grundsätze
  - Nur im Expertenmodus (DiagSession.experte – bei jedem Programmstart aus, die
    Oberfläche zeigt beim Einschalten einen Hinweis).
  - Jede Funktion gibt im Protokoll genau ihre Blöcke frei (KW1281.schreiben_freigeben)
    – alles andere bleibt gesperrt, auch im Expertenmodus.
  - Vorher werden die Bedingungen über Live-Messwerte geprüft, alte Werte werden
    gesichert, jeder Schreibblock steht im Protokoll.
  - Alle drei Funktionen auch bei KWP2000; dort sind Drosselklappe und
    Stellglieddiagnose experimentell – ihr Ablauf stammt aus einem EDC16-Mitschnitt in
    kw1281test und ist an keinem Benziner mit KWP2000 geprüft.

Drosselklappe anlernen (Motor 01, Grundeinstellung)
  Gruppe 060 bei E-Gas (z. B. ME7), Gruppe 098 bei Seilzug-Drosselklappe. Bedingungen
  laut Ross-Tech: Zündung an, Motor aus, Gaspedal nicht berühren, Bordspannung
  mindestens 11,5 V, Kühlmittel 5–95 °C, kein Fehler im Motor-Fehlerspeicher. Die
  Grundeinstellung läuft etwa 30 Sekunden, dann zurück zu den Messwerten (das beendet
  sie; bei KWP2000 vorher 32 B8 00 gg) und Fehlerspeicher lesen. Feld 4 der Gruppe 060
  zeigt das Ergebnis
  („ADP i.O.“ / „ADP ERROR“) – als Textnummer; kennt vagdiag sie noch nicht, steht
  dort „Text Nr. …“.
  Gestartet wird nur, wenn die Gruppe wie die Drosselklappen-Anpassung aufgebaut ist
  (drosselklappe_aufbau) – sonst könnte das Steuergerät mit derselben Gruppe etwas anderes
  anlernen. Weicht eine Antwort während der Grundeinstellung davon ab, hört vagdiag sofort
  auf. Das ist die einzige Prüfung nach dem Steuergerät: Ungeprüfte Steuergeräte bekommen
  sonst nur den Hinweis aus geprueft.py.

Service-Intervall zurücksetzen (Kombi 17, Anpassungskanal 02 → 0)
  Wie Ross-Tech es für Modelle ab etwa 1998 beschreibt: lesen, testen, speichern. Der
  alte Wert landet vorher als JSON-Datei in ~/vagdiag-daten/sicherungen. Bei KWP2000
  laufen Testen und Speichern in einer Anpassungssitzung (siehe kwp2000.py).

Stellglieddiagnose (das geöffnete Steuergerät)
  Das Steuergerät steuert seine Stellglieder nacheinander an; jeder Schritt schaltet
  weiter, bis es „Ende“ meldet oder der Benutzer aufhört – kommt 60 Sekunden lang kein
  „Weiter“, hört vagdiag von selbst auf. Beim Motor vorher: steht er (Drehzahl 0)? Beim
  ABS: stehen alle Räder? Bei Bremsen, Airbag, Wegfahrsperre, Lenkung und
  Niveauregulierung startet sie erst, wenn der Benutzer die Warnung mit den möglichen
  Schäden bestätigt hat (gefahr_bestaetigt, siehe stellglied.py). Danach wird die
  Verbindung beendet – dann hört jedes Steuergerät sicher auf, ein Stellglied
  anzusteuern – und neu aufgebaut; die Reihenfolge der Stellglieder merkt sich vagdiag.

Verfügbarkeit (verfuegbarkeit): Für die Oberfläche steht bei jeder Expertenfunktion, ob sie
gerade geht und wenn nicht, warum – ohne etwas zu senden.

Alle Abläufe laufen im Diagnose-Thread der Sitzung (siehe session.py).
"""

from __future__ import annotations

import json
import logging
import queue
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from . import __version__, adressen, geprueft
from . import stellglied as stellglieder
from .fehler import Fehler
from .kline import KLineError
from .kw1281 import DiagError, Nak, NotAvailable, SchreibenGesperrt, Verbindung
from .messwerte import ZAHL_TYPEN, Messwert
from .pfade import DATEN_ORDNER
from .port import PortError
from .sprache import N_, t, zahl
from .stellglied import Gefahr, Stellglied, gesperrt_nach_kennung

if TYPE_CHECKING:
    from .session import DiagSession

log = logging.getLogger("vagdiag.proto")

# Hinweis beim Einschalten (Oberfläche: Rückfrage, Kommandozeile: „ja“ eintippen)
HINWEIS = N_(
    "Im Expertenmodus kann vagdiag Werte in Steuergeräten ändern und Stellglieder ansteuern: "
    "Drosselklappe anlernen, Service-Intervall zurücksetzen, Stellglieddiagnose.\n\n"
    "Nur am stehenden Auto mit eingeschalteter Zündung. Eine falsche Einstellung kann "
    "Fehlfunktionen verursachen – Benutzung auf eigene Gefahr. vagdiag prüft vorher die "
    "Bedingungen, sichert alte Werte und protokolliert jeden Schritt.\n\n"
    "Immer gesperrt: Kanal 00, Kilometerstand, Codierung, Login sowie Grundeinstellung und "
    "Anpassung bei Airbag, Bremsen, Wegfahrsperre, Lenkung und Niveauregulierung; deren "
    "Stellglieddiagnose erst nach einer Warnung.\n\n"
    "Gilt bis zum Beenden von vagdiag. Expertenmodus einschalten?")

MOTOR = 0x01
ABS = 0x03
KOMBI = 0x17
DROSSELKLAPPE_GRUPPEN = {60: N_("060 – E-Gas (z. B. ME7)"),
                         98: N_("098 – Drosselklappe mit Seilzug")}
DAUER = 30.0                 # s Grundeinstellung (Ross-Tech: „etwa 30 Sekunden“)
MIN_SPANNUNG = 11.5          # V
KUEHLMITTEL = (5.0, 95.0)    # °C
SERVICE_KANAL = 2
SICHERUNGEN = DATEN_ORDNER / "sicherungen"
# Feldnamen der Gruppe 060 bei E-Gas (Ross-Tech) – nur angezeigt, wenn die Einheiten
# passen (zwei Prozentwerte, eine Zahl, ein Text)
FELDER_060 = (N_("Drosselklappe Poti 1"), N_("Drosselklappe Poti 2"), N_("Lernschritt"),
              N_("Anpassungsstatus"))
MAX_SCHRITTE = 100           # Stellglieddiagnose: höchstens so viele Stellglieder …
SCHRITT_MAX = 60.0           # … und jedes höchstens so viele Sekunden ohne „Weiter“


class Nichts(DiagError):
    """Ablauf vor dem ersten Schreibblock beendet – am Steuergerät hat sich nichts
    geändert."""


# ---------------------------------------------------------------- Ergebnisse
@dataclass
class Bedingung:
    name: str               # interner (deutscher) Text, angezeigt mit t()
    wert: str               # gemessen, als Text
    ok: bool | None         # None = nicht prüfbar


@dataclass
class Pruefung:
    gruppe: int
    bedingungen: list[Bedingung]
    vorher: list[Messwert]
    fehler: list[Fehler]
    kennung: tuple = ()      # geprüftes Steuergerät – die Ausführung gilt nur dafür

    @property
    def verletzt(self) -> list[Bedingung]:
        return [b for b in self.bedingungen if b.ok is False]

    @property
    def ungeprueft(self) -> list[Bedingung]:
        return [b for b in self.bedingungen if b.ok is None]


@dataclass
class GrundeinstellungErgebnis:
    gruppe: int
    vorher: list[Messwert]
    nachher: list[Messwert]
    fehler_nachher: list[Fehler] | None
    dauer: float
    abgebrochen: bool
    status: str | None      # "ok", "fehler", "laeuft" oder None (Text unbekannt)
    abweichung: str | None = None   # Antwort passte nicht mehr zur Anpassung – deshalb beendet


@dataclass
class ServiceErgebnis:
    alt: int
    neu: int
    sicherung: Path
    werkstattcode: int


@dataclass
class StellgliedPruefung:
    adresse: int
    kwp2000: bool
    bedingungen: list[Bedingung]
    kennung: tuple = ()
    gefahr: Gefahr | None = None        # Bremsen, Airbag …: erst nach bestätigter Warnung

    @property
    def verletzt(self) -> list[Bedingung]:
        return [b for b in self.bedingungen if b.ok is False]

    @property
    def ungeprueft(self) -> list[Bedingung]:
        return [b for b in self.bedingungen if b.ok is None]


@dataclass
class StellgliedErgebnis:
    adresse: int
    schritte: list[Stellglied]
    grund: str              # "ende", "durch", "kein_status", "max", "zeit", "beendet",
                            # "abgebrochen"
    dauer: float
    wieder_verbunden: bool
    kwp2000: bool


@dataclass
class _Live:
    drehzahl: float | None = None
    spannung: float | None = None
    kuehlmittel: float | None = None
    quellen: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- Hilfen
def feldnamen_060(werte: list[Messwert]) -> list[str]:
    """Namen für Gruppe 060, wenn die Einheiten zur E-Gas-Belegung passen."""
    if (len(werte) >= 4 and werte[0].einheit == "%" and werte[1].einheit == "%"
            and werte[2].einheit == "" and werte[3].typ == 37):
        return [t(n) for n in FELDER_060]
    return [t("Feld {nummer}", nummer=i + 1) for i in range(len(werte))]


ADP_TEXTNUMMERN = {0x0001: "laeuft", 0x0002: "ok"}   # „ADP. läuft“, „ADP. i.O.“ (Texttabelle)


def drosselklappe_aufbau(gruppe: int, werte: list[Messwert]) -> str | None:
    """Ist die Gruppe wie die Drosselklappen-Anpassung aufgebaut (Ross-Tech, Werkstatt-
    handbuch)? None: ja. Sonst, was abweicht.
      060: Feld 1 und 2 in %, Feld 3 Lernschritt (Zahl ohne Einheit, E-Gas) oder
           Betriebszustand (Text), Feld 4 Anpassungsstatus (Text)
      098: Feld 1 und 2 in V, Feld 3 Betriebszustand (Text), Feld 4 Anpassungsstatus (Text)"""
    def zahl_ohne_einheit(m: Messwert) -> bool:
        return m.typ in ZAHL_TYPEN and m.einheit == "" and m.gueltig

    if gruppe == 60:
        einheit, feld3 = "%", (lambda m: m.typ == 37 or zahl_ohne_einheit(m))
        erwartet = t("Feld 1 und 2 in %, Feld 3 Zahl oder Text, Feld 4 Text")
    elif gruppe == 98:
        einheit, feld3 = "V", (lambda m: m.typ == 37)
        erwartet = t("Feld 1 und 2 in V, Feld 3 und 4 Text")
    else:
        return t("Gruppe {gruppe:03d} ist keine Gruppe zum Anlernen der Drosselklappe",
                 gruppe=gruppe)
    passt = (len(werte) == 4 and werte[0].einheit == einheit and werte[1].einheit == einheit
             and werte[0].zahl is not None and werte[1].zahl is not None
             and feld3(werte[2]) and werte[3].typ == 37)
    if passt:
        return None
    gelesen = " | ".join(f"{w.text} ({w.roh})" for w in werte) or "–"
    return t("erwartet: {erwartet}; gelesen: {gelesen}", erwartet=erwartet, gelesen=gelesen)


def adp_status(werte: list[Messwert]) -> str | None:
    """Status aus Feld 4 („ADP läuft / i.O. / ERROR“): zuerst nach der Textnummer (1 und 2
    in der Tabelle aus KLineKWP1281Lib), sonst nach dem Text – None, solange er unbekannt
    ist („Text Nr. …“)."""
    if len(werte) < 4:
        return None
    if werte[3].textnummer in ADP_TEXTNUMMERN:
        return ADP_TEXTNUMMERN[werte[3].textnummer]
    text = werte[3].text.lower()
    if "error" in text or "fehler" in text:
        return "fehler"
    if "läuft" in text or "running" in text or " run" in text:
        return "laeuft"
    if "i.o" in text or "ok" in text or "o.k" in text:
        return "ok"
    return None


def kennung_text(kennung: tuple) -> str:
    """„17 – Schalttafeleinsatz (Kombi): 6K9920806 KOMBIINSTRUMENT TRW V04“"""
    if len(kennung) != 3:
        return "?"
    adresse, teilenummer, bauteil = kennung
    return f"{adressen.text(adresse)}: " + (" ".join(x for x in (teilenummer, bauteil) if x)
                                             or "?")


def _verbindung_pruefen(s: "DiagSession", adresse: int | None,
                        kwp2000_ok: bool = False, kennung: tuple | None = None,
                        stellglied: bool = False) -> Verbindung:
    """Verbunden mit diesem Steuergerät (adresse None: mit irgendeinem)? Mit `kennung`:
    genau mit dem Gerät, das der Benutzer bestätigt hat – nicht mit einem anderen, das
    inzwischen verbunden ist. Geräte, die sich als Airbag, Bremse, Wegfahrsperre oder
    Lenkung melden, bekommen keine Grundeinstellung und keine Anpassung; für die
    Stellglieddiagnose (stellglied=True) prüft stellglied_pruefen selbst."""
    proto = s._proto_pruefen()
    v = proto.verbindung
    if v is None or (adresse is not None and v.adresse != adresse):
        if adresse is None:
            raise Nichts(t("Erst ein Steuergerät öffnen"))
        raise Nichts(t("Erst mit {steuergeraet} verbinden",
                       steuergeraet=adressen.text(adresse)))
    if kennung is not None and v.kennung != tuple(kennung):
        raise Nichts(t("Inzwischen ist ein anderes Steuergerät verbunden ({jetzt} statt "
                       "{vorher}) – nichts gesendet.", jetzt=kennung_text(v.kennung),
                       vorher=kennung_text(tuple(kennung))))
    grund = None if stellglied else gesperrt_nach_kennung(v.teilenummer, v.bauteil)
    if grund:
        raise Nichts(grund)
    if proto.ist_kwp2000 and not kwp2000_ok:
        raise NotAvailable(t("Diese Expertenfunktion gibt es bisher nur bei KW1281 – dieses "
                             "Steuergerät spricht KWP2000."))
    return v


def _live_lesen(s: "DiagSession") -> _Live:
    """Drehzahl, Bordspannung und Kühlmittel aus den Gruppen 001 und 004 (bei ME7
    und vielen anderen Motorsteuergeräten so belegt). Fehlt etwas, bleibt es None."""
    live = _Live()
    proto = s._proto_pruefen()
    for gruppe in (1, 4):
        try:
            werte = s._wiederholt(lambda: proto.gruppe_lesen(gruppe))
        except (Nak, NotAvailable):
            continue
        live.quellen.append(f"{gruppe:03d}")
        for m in werte:
            if not m.gueltig or m.zahl is None:
                continue
            if m.einheit == "/min":
                # die höchste Drehzahl aus allen Gruppen – eine einzige über 0 genügt
                live.drehzahl = m.zahl if live.drehzahl is None else max(live.drehzahl, m.zahl)
            elif m.einheit == "V" and live.spannung is None:
                live.spannung = m.zahl
            elif m.einheit == "°C" and live.kuehlmittel is None:
                live.kuehlmittel = m.zahl      # 001 Feld 2 bzw. 004 Feld 3
    return live


def _bedingungen(live: _Live, fehler: list[Fehler]) -> list[Bedingung]:
    def text(wert: float | None, stellen: int, einheit: str) -> str:
        return "–" if wert is None else f"{zahl(wert, stellen)} {einheit}"

    return [
        Bedingung(N_("Motor aus (Drehzahl 0)"), text(live.drehzahl, 0, "/min"),
                  None if live.drehzahl is None else live.drehzahl < 1),
        Bedingung(N_("Bordspannung mindestens 11,5 V"), text(live.spannung, 2, "V"),
                  None if live.spannung is None else live.spannung >= MIN_SPANNUNG),
        Bedingung(N_("Kühlmittel zwischen 5 und 95 °C"), text(live.kuehlmittel, 0, "°C"),
                  None if live.kuehlmittel is None
                  else KUEHLMITTEL[0] <= live.kuehlmittel <= KUEHLMITTEL[1]),
        Bedingung(N_("Kein Fehler im Motor-Fehlerspeicher"),
                  t("{anzahl} Fehler", anzahl=len(fehler)), not fehler),
    ]


# ---------------------------------------------------------------- Drosselklappe
def drosselklappe_pruefen(s: "DiagSession", gruppe: int,
                          kennung: tuple | None = None) -> Pruefung:
    """Nur lesen: Gruppe vorhanden? Bedingungen erfüllt?"""
    if gruppe not in DROSSELKLAPPE_GRUPPEN:
        raise ValueError(t("Drosselklappe anlernen nur mit Gruppe 060 oder 098"))
    v = _verbindung_pruefen(s, MOTOR, kwp2000_ok=True, kennung=kennung)
    proto = s._proto_pruefen()
    try:
        vorher = s._wiederholt(lambda: proto.gruppe_lesen(gruppe))
    except (Nak, NotAvailable) as exc:
        raise Nichts(t("Gruppe {gruppe:03d} gibt es in diesem Motorsteuergerät nicht ({fehler}) "
                       "– die Drosselklappe wird hier anders angelernt.", gruppe=gruppe,
                       fehler=exc)) from exc
    abweichung = drosselklappe_aufbau(gruppe, vorher)
    if abweichung:
        log.warning(t("EXPERTE: Gruppe %03d passt nicht zur Drosselklappen-Anpassung – %s"),
                    gruppe, abweichung)
        raise Nichts(t("Gruppe {gruppe:03d} ist in diesem Motorsteuergerät anders aufgebaut als "
                       "die Drosselklappen-Anpassung ({abweichung}). vagdiag startet die "
                       "Grundeinstellung hier nicht – das Steuergerät könnte damit etwas anderes "
                       "anlernen.", gruppe=gruppe, abweichung=abweichung))
    fehler = proto.fehler_lesen()
    pruefung = Pruefung(gruppe, _bedingungen(_live_lesen(s), fehler), vorher, fehler,
                        v.kennung)
    log.info(t("EXPERTE: Prüfung Grundeinstellung %03d – %s"), gruppe, "; ".join(
        f"{t(b.name)}: {b.wert} ({'?' if b.ok is None else 'ok' if b.ok else 'NEIN'})"
        for b in pruefung.bedingungen))
    return pruefung


def drosselklappe_anlernen(s: "DiagSession", gruppe: int, dauer: float = DAUER,
                           melden: Callable[[str, object], None] | None = None,
                           ohne_pruefung_ok: bool = False,
                           kennung: tuple | None = None) -> GrundeinstellungErgebnis:
    """Grundeinstellung der Gruppe etwa `dauer` Sekunden lang, dann zurück zu den
    Messwerten. Die Bedingungen werden unmittelbar davor noch einmal gelesen; eine
    verletzte bricht ab, bevor etwas gesendet wird. Nicht prüfbare nur mit
    ohne_pruefung_ok (der Benutzer hat sie selbst bestätigt). Mit `kennung` nur an genau
    dem Steuergerät, das der Benutzer bestätigt hat."""
    melden = melden or (lambda art, daten: None)
    pruefung = drosselklappe_pruefen(s, gruppe, kennung)
    if pruefung.verletzt:
        raise Nichts(t("Nicht gestartet – Bedingung nicht erfüllt: {liste}", liste=", ".join(
            f"{t(b.name)} ({b.wert})" for b in pruefung.verletzt)))
    if pruefung.ungeprueft and not ohne_pruefung_ok:
        raise Nichts(t("Nicht gestartet – nicht prüfbar: {liste}", liste=", ".join(
            t(b.name) for b in pruefung.ungeprueft)))
    proto = s._proto_pruefen()
    log.warning(t("EXPERTE: Grundeinstellung %03d startet (%s, %s)%s"), gruppe,
                proto.verbindung.teilenummer, proto.verbindung.bauteil,
                " – " + t("KWP2000, experimentell") if proto.ist_kwp2000 else "")
    start = time.monotonic()
    letzte = pruefung.vorher
    abgebrochen = False
    abweichung = None
    nachher: list[Messwert] = []
    try:
        with proto.schreiben_freigeben(grundeinstellung=[gruppe]):
            while time.monotonic() - start < dauer:
                if s._abbruch.is_set():
                    abgebrochen = True
                    log.warning(t("EXPERTE: Grundeinstellung abgebrochen"))
                    break
                letzte = s._wiederholt(lambda: proto.grundeinstellung(gruppe))
                abweichung = drosselklappe_aufbau(gruppe, letzte)
                if abweichung:
                    # antwortet nicht mehr wie die Anpassung – sofort zurück zu den Messwerten
                    abgebrochen = True
                    log.warning(t("EXPERTE: Grundeinstellung %03d antwortet anders als die "
                                  "Drosselklappen-Anpassung (%s) – beende sie"),
                                gruppe, abweichung)
                    break
                melden("grundeinstellung", {"gruppe": gruppe, "werte": letzte,
                                            "sekunden": time.monotonic() - start,
                                            "dauer": dauer, "status": adp_status(letzte)})
    except (DiagError, KLineError, PortError) as exc:
        log.warning(t("EXPERTE: Grundeinstellung %03d nach %.0f s mit Fehler beendet: %s"),
                    gruppe, time.monotonic() - start, exc)
        raise
    finally:
        # KWP2000: die Routine beenden (klappt das nicht, endet die Verbindung). Danach – und
        # bei KW1281 allein – beendet eine normale Gruppenabfrage die Grundeinstellung, auch
        # nach Fehlern
        try:
            proto.grundeinstellung_beenden()
        except DiagError as exc:
            log.warning(t("EXPERTE: Grundeinstellung beenden: %s"), exc)
        if proto.verbunden:
            try:
                nachher = s._wiederholt(lambda: proto.gruppe_lesen(gruppe))
            except DiagError as exc:
                log.warning(t("EXPERTE: Rückkehr zu den Messwerten: %s"), exc)
    fehler_nachher = None
    try:
        if proto.verbunden:
            fehler_nachher = proto.fehler_lesen()
    except DiagError as exc:
        log.warning(t("EXPERTE: Fehlerspeicher danach nicht lesbar: %s"), exc)
    ergebnis = GrundeinstellungErgebnis(gruppe, pruefung.vorher, nachher or letzte,
                                        fehler_nachher, time.monotonic() - start,
                                        abgebrochen, adp_status(nachher or letzte), abweichung)
    log.warning(t("EXPERTE: Grundeinstellung %03d beendet nach %.0f s – Feld 4: %s"),
                gruppe, ergebnis.dauer,
                ergebnis.nachher[3].text if len(ergebnis.nachher) >= 4 else "–")
    return ergebnis


# ---------------------------------------------------------------- Service-Intervall
def service_lesen(s: "DiagSession", kennung: tuple | None = None):
    """Kanal 02 des Kombis lesen (nur lesen)."""
    _verbindung_pruefen(s, KOMBI, kwp2000_ok=True, kennung=kennung)
    proto = s._proto_pruefen()
    try:
        return s._wiederholt(lambda: proto.anpassung_lesen(SERVICE_KANAL))
    except (Nak, NotAvailable) as exc:
        raise Nichts(t("Kanal 02 gibt es bei diesem Kombi nicht ({fehler}). Dann hat es keine "
                       "Service-Anzeige, oder sie wird nur am Kombi selbst zurückgesetzt "
                       "(Knopf).", fehler=exc)) from exc


def sichern(v: Verbindung, kanal: int, alt: int, neu: int, ordner: Path | None = None) -> Path:
    """Alten Anpassungswert als JSON ablegen – bevor etwas geschrieben wird."""
    ziel = Path(ordner) if ordner is not None else SICHERUNGEN
    ziel.mkdir(parents=True, exist_ok=True)
    pfad = ziel / time.strftime(f"anpassung-{v.adresse:02X}-kanal{kanal:02d}-%Y%m%d-%H%M%S.json")
    pfad.write_text(json.dumps({
        "zeit": time.strftime("%Y-%m-%d %H:%M:%S"), "vagdiag": __version__,
        "adresse": f"{v.adresse:02X}", "teilenummer": v.teilenummer, "bauteil": v.bauteil,
        "codierung": v.codierung, "werkstattcode": v.werkstattcode,
        "kanal": kanal, "alter_wert": alt, "neuer_wert": neu,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.warning(t("EXPERTE: alter Wert gesichert in %s"), pfad)
    return pfad


def service_zuruecksetzen(s: "DiagSession", erwartet: int, ordner: Path | None = None,
                          kennung: tuple | None = None) -> ServiceErgebnis:
    """Kanal 02 auf 0: noch einmal lesen (muss dem angezeigten Wert entsprechen),
    sichern, testen, speichern, zurücklesen – mit `kennung` nur an genau dem Kombi, das
    der Benutzer bestätigt hat."""
    v = _verbindung_pruefen(s, KOMBI, kwp2000_ok=True, kennung=kennung)
    proto = s._proto_pruefen()
    alt = service_lesen(s, kennung)
    if alt.wert != erwartet:
        raise Nichts(t("Kanal 02 steht jetzt auf {jetzt} statt {vorher} – nichts geschrieben, "
                       "bitte neu lesen.", jetzt=alt.wert, vorher=erwartet))
    pfad = sichern(v, SERVICE_KANAL, alt.wert, 0, ordner)
    werkstattcode = v.werkstattcode or 0
    try:
        with proto.schreiben_freigeben(anpassung=[(SERVICE_KANAL, 0)]):
            proto.anpassung_schreiben(SERVICE_KANAL, 0, werkstattcode)
    except (DiagError, KLineError, PortError) as exc:
        log.warning(t("EXPERTE: Service-Intervall nicht zurückgesetzt: %s"), exc)
        raise
    neu = s._wiederholt(lambda: proto.anpassung_lesen(SERVICE_KANAL))
    log.warning(t("EXPERTE: Service-Intervall zurückgesetzt – Kanal 02 vorher %d, jetzt %d"),
                alt.wert, neu.wert)
    return ServiceErgebnis(alt.wert, neu.wert, pfad, werkstattcode)


# ---------------------------------------------------------------- Stellglieddiagnose
def _raeder_lesen(s: "DiagSession") -> Bedingung:
    """ABS: Stehen alle Räder? Gruppe 001 (Raddrehzahlen in km/h, z. B. Mark 20 IE)."""
    proto = s._proto_pruefen()
    try:
        werte = s._wiederholt(lambda: proto.gruppe_lesen(1))
    except (Nak, NotAvailable):
        werte = []
    raeder = [m.zahl for m in werte if m.gueltig and m.zahl is not None and m.einheit == "km/h"]
    if not raeder:
        return Bedingung(N_("Alle Räder stehen (0 km/h)"), "–", None)
    return Bedingung(N_("Alle Räder stehen (0 km/h)"),
                     " / ".join(f"{zahl(r, 0)}" for r in raeder) + " km/h", max(raeder) < 1)


def stellglied_pruefen(s: "DiagSession", kennung: tuple | None = None) -> StellgliedPruefung:
    """Nur lesen: Darf dieses Steuergerät? Beim Motor: steht er (Drehzahl 0)? Beim ABS:
    stehen alle Räder? Bei Bremsen, Airbag, Wegfahrsperre, Lenkung und Niveauregulierung
    kommt die Gefahr mit – gestartet wird dort erst nach bestätigter Warnung."""
    v = _verbindung_pruefen(s, None, kwp2000_ok=True, kennung=kennung, stellglied=True)
    gefahr, widerspruch = stellglieder.gefahr(v.adresse, v.teilenummer, v.bauteil)
    if widerspruch:
        raise Nichts(widerspruch)
    bedingungen: list[Bedingung] = []
    if v.adresse == MOTOR:
        live = _live_lesen(s)
        bedingungen.append(Bedingung(
            N_("Motor aus (Drehzahl 0)"),
            "–" if live.drehzahl is None else f"{zahl(live.drehzahl, 0)} /min",
            None if live.drehzahl is None else live.drehzahl < 1))
    if v.adresse == ABS:
        bedingungen.append(_raeder_lesen(s))
    pruefung = StellgliedPruefung(v.adresse, s._proto_pruefen().ist_kwp2000, bedingungen,
                                  v.kennung, gefahr)
    log.info(t("EXPERTE: Prüfung Stellglieddiagnose %02X – %s"), v.adresse, "; ".join(
        f"{t(b.name)}: {b.wert} ({'?' if b.ok is None else 'ok' if b.ok else 'NEIN'})"
        for b in bedingungen) or "–")
    return pruefung


def _bestaetigung_pruefen(gefahr: Gefahr | None, bestaetigt: str | None) -> None:
    """Bremsen, Airbag …: nur, wenn der Benutzer genau diese Warnung bestätigt hat. Die
    Schreibsperre im Protokoll prüft dieselbe Bestätigung noch einmal selbst."""
    if gefahr is not None and bestaetigt != gefahr.art:
        raise Nichts(t("Nicht gestartet – die Warnung vor möglichen Schäden ({art}) ist nicht "
                       "bestätigt.", art=gefahr.name))


def _befehl_abwarten(s: "DiagSession", befehle: queue.Queue, proto,
                     hoechstens: float) -> str | None:
    """Auf „weiter“ oder „ende“ warten und die Verbindung derweil wach halten.
    None: abgebrochen (DiagSession.abbrechen); "zeit": nach `hoechstens` Sekunden kein
    Befehl – dann soll das Stellglied nicht länger angesteuert bleiben."""
    ende = time.monotonic() + hoechstens
    while True:
        if s._abbruch.is_set():
            return None
        rest = ende - time.monotonic()
        if rest <= 0:
            return "zeit"
        try:
            return befehle.get(timeout=min(s.keepalive, rest))
        except queue.Empty:
            if time.monotonic() < ende:
                proto.keep_alive()


def stellglieddiagnose(s: "DiagSession", befehle: queue.Queue,
                       melden: Callable[[str, object], None] | None = None,
                       ohne_pruefung_ok: bool = False,
                       schritt_max: float = SCHRITT_MAX,
                       kennung: tuple | None = None,
                       gefahr_bestaetigt: str | None = None) -> StellgliedErgebnis:
    """Stellglieder nacheinander ansteuern. Jedes gemeldete Stellglied geht als Ereignis
    „stellglied“ hinaus; dann wartet der Ablauf auf „weiter“ (nächstes) oder „ende“ –
    höchstens schritt_max Sekunden. Zum Schluss: Routine beenden (KWP2000), Verbindung
    beenden, Reihenfolge merken (stellglied.liste_merken), neu verbinden.
    gefahr_bestaetigt: Art der Warnung, die der Benutzer bestätigt hat – Pflicht bei Bremsen,
    Airbag, Wegfahrsperre, Lenkung und Niveauregulierung."""
    melden = melden or (lambda art, daten: None)
    pruefung = stellglied_pruefen(s, kennung)
    _bestaetigung_pruefen(pruefung.gefahr, gefahr_bestaetigt)
    if pruefung.verletzt:
        raise Nichts(t("Nicht gestartet – Bedingung nicht erfüllt: {liste}", liste=", ".join(
            f"{t(b.name)} ({b.wert})" for b in pruefung.verletzt)))
    if pruefung.ungeprueft and not ohne_pruefung_ok:
        raise Nichts(t("Nicht gestartet – nicht prüfbar: {liste}", liste=", ".join(
            t(b.name) for b in pruefung.ungeprueft)))
    proto = s._proto_pruefen()
    if not proto.experte:
        raise SchreibenGesperrt(t("Schreiben geht nur im Expertenmodus"))
    v = proto.verbindung
    adresse, bauds = v.adresse, s._letzte_bauds
    zusatz = ""
    if pruefung.kwp2000:
        zusatz += " – " + t("KWP2000, experimentell")
    if pruefung.gefahr is not None:
        zusatz += " – " + t("Warnung ({art}) bestätigt", art=pruefung.gefahr.name)
    log.warning(t("EXPERTE: Stellglieddiagnose %02X startet (%s, %s)%s"), adresse,
                v.teilenummer, v.bauteil, zusatz)
    schritte: list[Stellglied] = []
    grund = "beendet"
    start = time.monotonic()
    wieder = False
    try:
        # die Bestätigung des Benutzers selbst weitergeben – die Schreibsperre prüft sie
        # noch einmal gegen das gerade verbundene Gerät
        with proto.schreiben_freigeben(stellglied=True, gefahr=gefahr_bestaetigt):
            aktuell = proto.stellglied_starten()
            vorher: Stellglied | None = None
            while True:
                if aktuell is None:
                    grund = "kein_status" if pruefung.kwp2000 else "ende"
                    break
                if aktuell.ende:
                    grund = "ende"
                    break
                if (pruefung.kwp2000 and schritte and aktuell.code == schritte[0].code
                        and any(x.code != schritte[0].code for x in schritte)):
                    grund = "durch"           # einmal durch die Liste, wieder am Anfang
                    break
                if len(schritte) >= MAX_SCHRITTE:
                    grund = "max"
                    break
                gleich = vorher is not None and aktuell.code == vorher.code
                schritte.append(aktuell)
                melden("stellglied", {"schritt": len(schritte), "stellglied": aktuell,
                                      "gleich": gleich, "kwp2000": pruefung.kwp2000,
                                      "adresse": adresse, "hoechstens": schritt_max})
                befehl = _befehl_abwarten(s, befehle, proto, schritt_max)
                if befehl is None:
                    grund = "abgebrochen"
                    break
                if befehl == "zeit":
                    grund = "zeit"
                    log.warning(t("EXPERTE: %.0f s ohne „Weiter“ – Stellglieddiagnose wird "
                                  "beendet"), schritt_max)
                    break
                if befehl != "weiter":
                    grund = "beendet"
                    break
                vorher = aktuell
                aktuell = proto.stellglied_weiter()
    except (DiagError, KLineError, PortError) as exc:
        # abgelehnt (Nak) oder Störung – das Steuergerät hat dann nichts (mehr) angesteuert
        log.warning(t("EXPERTE: Stellglieddiagnose %02X nach %d Schritten nicht fortgesetzt: %s"),
                    adresse, len(schritte), exc)
        raise
    finally:
        try:
            proto.stellglied_beenden()
        except (DiagError, KLineError, PortError) as exc:
            log.info(t("EXPERTE: Stellglieddiagnose beenden: %s"), exc)
        # Ende der Verbindung: damit hört jedes Steuergerät sicher auf, ein Stellglied
        # anzusteuern. Danach wieder verbinden, damit es weitergehen kann.
        try:
            s._trennen()
        except (DiagError, KLineError, PortError) as exc:
            log.info(t("Trennen: %s"), exc)
        dauer = time.monotonic() - start
        if schritte:
            # Reihenfolge merken – beim nächsten Mal steht die Liste vorher da
            stellglieder.liste_merken(adresse, v.teilenummer, v.bauteil,
                                      [x.code for x in schritte], grund in ("ende", "durch"),
                                      sim=bool(getattr(s._port, "simulator", False)))
        if not s._abbruch.is_set():           # beim Abbrechen/Schließen nicht neu verbinden
            try:
                s._verbinden(adresse, bauds)
                wieder = True
            except (DiagError, KLineError, PortError) as exc:
                log.warning(t("EXPERTE: nach der Stellglieddiagnose nicht wieder verbunden: "
                              "%s"), exc)
    log.warning(t("EXPERTE: Stellglieddiagnose %02X beendet nach %.0f s – %d Schritte (%s)"),
                adresse, dauer, len(schritte), grund)
    return StellgliedErgebnis(adresse, schritte, grund, dauer, wieder, pruefung.kwp2000)


# ---------------------------------------------------------------- Verfügbarkeit (Oberfläche)
@dataclass
class Verfuegbar:
    ok: bool
    text: str               # warum es gerade nicht geht – oder ein Hinweis, wenn es geht
    warnung: bool = False   # geht, aber erst nach der Warnung vor möglichen Schäden


def verfuegbarkeit(experte_an: bool, verbindung: Verbindung | None, beschaeftigt: bool,
                   laeuft: str | None) -> dict[str, Verfuegbar]:
    """Für jede Expertenfunktion: Geht sie gerade – und wenn nicht, warum? Nur lesen,
    ohne Verbindung zum Steuergerät; die Oberfläche zeigt den Text unter dem Knopf.
    laeuft: Name dessen, was gerade läuft (Messwertblöcke, Scan …), sonst None."""
    def allgemein() -> str | None:
        if not experte_an:
            return t("Expertenmodus ist aus.")
        if laeuft:
            return t("Gerade läuft: {was} – erst beenden.", was=laeuft)
        if beschaeftigt:
            return t("vagdiag arbeitet gerade – bitte kurz warten.")
        return None

    def fuer(soll: int, kwp2000_ok: bool, experimentell: bool = False) -> Verfuegbar:
        grund = allgemein()
        if grund:
            return Verfuegbar(False, grund)
        if verbindung is None:
            return Verfuegbar(False, t("Erst links {steuergeraet} öffnen.",
                                       steuergeraet=adressen.text(soll)))
        if verbindung.adresse != soll:
            return Verfuegbar(False, t("Offen ist {jetzt} – dafür links {soll} "
                                       "öffnen.", jetzt=adressen.text(verbindung.adresse),
                                       soll=adressen.text(soll)))
        if not kwp2000_ok and verbindung.protokoll == "KWP2000":
            return Verfuegbar(False, t("Gibt es bisher nur bei KW1281 – dieses Steuergerät "
                                       "spricht KWP2000."))
        grund = gesperrt_nach_kennung(verbindung.teilenummer, verbindung.bauteil)
        if grund:
            return Verfuegbar(False, grund)
        if experimentell and verbindung.protokoll == "KWP2000":
            return Verfuegbar(True, t("Bereit – {steuergeraet} (KWP2000: "
                                      "experimentell).", steuergeraet=adressen.text(soll)))
        return Verfuegbar(True, t("Bereit – {steuergeraet}.", steuergeraet=adressen.text(soll)))

    def stellglied() -> Verfuegbar:
        grund = allgemein()
        if grund:
            return Verfuegbar(False, grund)
        if verbindung is None:
            return Verfuegbar(False, t("Erst links ein Steuergerät öffnen."))
        gefahr, widerspruch = stellglieder.gefahr(verbindung.adresse, verbindung.teilenummer,
                                                  verbindung.bauteil)
        if widerspruch:
            return Verfuegbar(False, widerspruch)
        if gefahr is not None:
            return Verfuegbar(True, t("Achtung, {art}: vorher kommt eine "
                                      "Warnung.", art=gefahr.name), warnung=True)
        return Verfuegbar(True, t("Bereit – {steuergeraet}.",
                                  steuergeraet=adressen.text(verbindung.adresse)))

    return {"drosselklappe": fuer(MOTOR, kwp2000_ok=True, experimentell=True),
            "service": fuer(KOMBI, kwp2000_ok=True),
            "stellglied": stellglied()}


# ---------------------------------------------------------------- Texte (Oberfläche und Kommandozeile)
ZEICHEN = {True: "✓", False: "✗", None: "?"}


def bedingungen_text(bedingungen: list[Bedingung]) -> str:
    """Eine Zeile je Bedingung: ✓ erfüllt, ✗ nicht erfüllt, ? nicht prüfbar."""
    return "\n".join(f"{ZEICHEN[b.ok]}  {t(b.name)}: {b.wert}" for b in bedingungen)


def ziel_text(kennung: tuple, sim: bool) -> str:
    """Für jede Rückfrage, die etwas am Steuergerät ändert: welches Gerät genau, und ob
    Simulator oder Auto – damit niemand „im Simulator übt“, während das Kabel steckt."""
    ziel = (t("Ziel: Simulator – kein Auto") if sim else
            t("Ziel: ECHTES FAHRZEUG über das Kabel"))
    text = t("Steuergerät: {kennung}", kennung=kennung_text(kennung)) + "\n" + ziel
    hinweis = geprueft.hinweis_kennung(kennung)
    return text + "\n\n" + hinweis if hinweis else text


def grundeinstellung_urteil(ergebnis: GrundeinstellungErgebnis) -> str:
    """Was die Grundeinstellung ergeben hat – nach Feld 4 der Gruppe."""
    feld4 = ergebnis.nachher[3].text if len(ergebnis.nachher) >= 4 else "–"
    if ergebnis.status == "ok":
        urteil = t("Laut Steuergerät erfolgreich ({text}).", text=feld4)
    elif ergebnis.status == "fehler":
        urteil = t("Das Steuergerät meldet einen Fehler ({text}). Bedingungen prüfen und "
                   "noch einmal versuchen.", text=feld4)
    elif ergebnis.status == "laeuft":
        urteil = t("Die Anpassung lief am Ende noch ({text}).", text=feld4)
    else:
        urteil = t("Ergebnis unklar – vagdiag kennt den Statustext in Feld 4 noch nicht "
                   "({text}). Bitte das Protokoll schicken.", text=feld4)
    if ergebnis.abweichung:
        urteil = t("Beendet nach {sekunden:.0f} s: Die Antwort passte nicht mehr zur "
                   "Drosselklappen-Anpassung ({abweichung}).", sekunden=ergebnis.dauer,
                   abweichung=ergebnis.abweichung)
    elif ergebnis.abgebrochen:
        urteil = t("Abgebrochen nach {sekunden:.0f} s.", sekunden=ergebnis.dauer) + " " + urteil
    return urteil


def fehler_text(fehler: list[Fehler] | None) -> str:
    if fehler is None:
        return t("Fehlerspeicher danach nicht lesbar.")
    if fehler:
        return (t("{anzahl} Fehler gespeichert:", anzahl=len(fehler))
                + "\n" + "\n".join("  " + f.zeile() for f in fehler))
    return t("Kein Fehler gespeichert")


def gefahr_text(pruefung: StellgliedPruefung, steuergeraet: str, ziel: str) -> str:
    """Warnung vor der Stellglieddiagnose an Bremsen, Airbag & Co. – mit den möglichen
    Schäden für genau dieses Steuergerät."""
    gefahr = pruefung.gefahr
    return (t("Achtung: {steuergeraet} gehört zu „{art}“. Eine Stellglieddiagnose kann "
              "hier Schaden anrichten.", steuergeraet=steuergeraet, art=gefahr.name)
            + "\n\n" + ziel
            + "\n\n" + t("Mögliche Schäden:") + "\n" + gefahr.schaeden
            + "\n\n" + t("Nur weitermachen, wenn du weißt, was angesteuert wird, und die "
                         "Vorbereitung erledigt ist."))


def stellglied_hinweise(pruefung: StellgliedPruefung, schritt_max: float) -> list[str]:
    """Die Absätze der Rückfrage vor der Stellglieddiagnose (nach Ziel und Bedingungen)."""
    teile = [t("Zündung an, Motor aus, Auto steht. Zeiger bewegen sich, Relais und Ventile "
               "schalten, Lüfter können anlaufen – nicht in Lüfter oder Gestänge greifen.")]
    hinweis = stellglieder.hinweis(pruefung.adresse)
    if hinweis:
        teile.append(t("Bei diesem Steuergerät: {hinweis}", hinweis=hinweis))
    if pruefung.gefahr is not None:
        teile.append(t("Denk an die Vorbereitung aus der Warnung ({art}).",
                       art=pruefung.gefahr.name))
    teile.append(t("Ohne „Weiter“ endet sie nach {sekunden:.0f} s von "
                   "selbst.", sekunden=schritt_max))
    if pruefung.kwp2000:
        teile.append(t("KWP2000: experimentell (nach einem Mitschnitt am EDC16)."))
    if pruefung.ungeprueft:
        teile.append(t("Nicht prüfbar – bitte selbst sicherstellen: {liste}",
                       liste=", ".join(t(b.name) for b in pruefung.ungeprueft)))
    return teile


def stellglied_bericht(ergebnis: StellgliedErgebnis, schritt_max: float) -> tuple[str, str]:
    """(Kopfzeile, ganzer Text) nach der Stellglieddiagnose."""
    verschiedene = list(dict.fromkeys(s.code for s in ergebnis.schritte))
    texte = {s.code: s.text for s in ergebnis.schritte}
    grund = {
        "ende": t("Das Steuergerät meldet das Ende der Liste."),
        "durch": t("Alle Stellglieder einmal durch – wieder beim ersten."),
        "kein_status": t("Das Steuergerät meldet kein weiteres Stellglied."),
        "max": t("Nach {anzahl} Schritten beendet.", anzahl=len(ergebnis.schritte)),
        "zeit": t("Nach {sekunden:.0f} Sekunden ohne „Weiter“ von selbst beendet.",
                  sekunden=schritt_max),
        "beendet": t("Von dir beendet."),
        "abgebrochen": t("Abgebrochen."),
    }.get(ergebnis.grund, ergebnis.grund)
    kopf = t("Stellglieddiagnose beendet: {anzahl} Stellglieder in {sekunden:.0f} s.",
             anzahl=len(verschiedene), sekunden=ergebnis.dauer) + " " + grund
    text = kopf
    if verschiedene:
        text += "\n\n" + "\n".join(f"  {texte[c]}" for c in verschiedene)
    text += "\n\n" + (t("Die Verbindung wurde beendet und neu aufgebaut.")
                       if ergebnis.wieder_verbunden else
                       t("Die Verbindung wurde beendet – bitte das Steuergerät neu öffnen."))
    return kopf, text

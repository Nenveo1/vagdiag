# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Kommandozeile – für schnelle Tests im Auto und für Protokolle zur Fehlersuche.

Beispiele (jeder Befehl und jede Option hat auch einen englischen Namen,
z. B. „fehler“ = „faults“, „--adresse“ = „--address“):
    python -m vagdiag.cli geraete
    python -m vagdiag.cli kabeltest
    python -m vagdiag.cli --adresse 01 ident
    python -m vagdiag.cli --adresse 01 fehler
    python -m vagdiag.cli --adresse 01 gruppe 4 --dauer --csv    (bis Strg+C, mit CSV)
    python -m vagdiag.cli obd2                                   (OBD-II-Test, nur lesen)
    python -m vagdiag.cli --adresse 17 gruppensuche
    python -m vagdiag.cli kilometerstand                         (Kombi, Adresse 17)
    python -m vagdiag.cli --adresse 17 anpassung 9               (nur lesen)
    python -m vagdiag.cli --adresse 17 anpassungssuche --bis 99  (nur lesen)
    python -m vagdiag.cli fahrt                                  (Fahrtenschreiber)
    python -m vagdiag.cli fahrt --passiv 1h                      (passiv, wie eine Dashcam)
    python -m vagdiag.cli fahrt-export --zeitspanne 1h           (Zeitspanne sichern)
    python -m vagdiag.cli --experte drosselklappe                (Expertenfunktion, mit
                                                                  Rückfrage; ebenso
                                                                  service-reset, stellglieder)
    python -m vagdiag.cli scan --alle                            (alle Adressen 01–7F)
    python -m vagdiag.cli --log --adresse 01 ident               (mit Protokolldatei)
    python -m vagdiag.cli --sprache en --adresse 01 fehler       (auf Englisch)
    python -m vagdiag.cli einstellungen --sprache-setzen en --csv-automatisch nein
    python -m vagdiag.cli --sim --adresse 01 gruppe 4 --wiederholen 10
    python -m vagdiag.cli --fast-init --adresse 01 ident         (KWP2000-Motor, Fast-Init)
    python -m vagdiag.cli --sim-kwp2000 --adresse 01 fehler      (Simulator, KWP2000 bei Motor
                                                                  und Kombi)

KW1281 oder KWP2000 erkennt vagdiag selbst an der Antwort des Steuergeräts.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import textwrap
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

from . import (adressen, airbag, beschriftung, einstellungen, experte, geprueft, ident,
               lizenz, protokolldatei, ringspeicher, sprache)
from .aufzeichnung import CsvAufzeichnung
from .fahrtenschreiber import Besuch, FahrtPlan, _gruppenliste, passiv_exportieren
from .kw1281 import (Abgebrochen, DiagError, Nak, NoResponse, NotAvailable,
                     UnsupportedProtocol, Verbindung)
from .messwerte import ROHWERT, MinMax
from .port import (PortError, einrichtungs_hinweis, kabel_oeffnen, list_ftdi_devices,
                   standard_url)
from .session import DiagSession
from .sim import sim_port
from .sprache import t

log = logging.getLogger("vagdiag")

BAUDS = {"auto": (10400, 9600), "10400": (10400,), "9600": (9600,),
         "4800": (4800,), "1200": (1200,)}

# Befehle: deutscher Name → englischer Name
BEFEHLE = {
    "geraete": "devices", "kabeltest": "cable-test", "ident": "ident", "fehler": "faults",
    "loeschen": "clear", "gruppe": "group", "gruppensuche": "group-scan",
    "anpassung": "adaptation", "anpassungssuche": "adaptation-scan",
    "kilometerstand": "odometer", "fahrt": "drive", "fahrt-export": "drive-export",
    "scan": "scan", "obd2": "obd2", "einstellungen": "settings", "lizenz": "license",
    "drosselklappe": "throttle-adaptation", "service-reset": "service-reset",
    "stellglieder": "output-tests",
}
# Expertenfunktionen: nur mit --experte, nur interaktiv
EXPERTE_BEFEHLE = ("drosselklappe", "service-reset", "stellglieder")
KANONISCH = {**{de: de for de in BEFEHLE}, **{en: de for de, en in BEFEHLE.items()}}

JA = ("ja", "j", "yes", "y", "an", "on", "1", "true")
NEIN = ("nein", "n", "no", "aus", "off", "0", "false")


def _hex(text: str) -> int:
    return int(text, 16)


def _ja_nein(text: str) -> bool:
    if text.lower() in JA:
        return True
    if text.lower() in NEIN:
        return False
    raise argparse.ArgumentTypeError(t("ja oder nein"))


def _zeitspanne(text: str) -> int:
    try:
        return ringspeicher.fenster_aus_name(text)
    except ValueError:
        raise argparse.ArgumentTypeError("5min | 20min | 1h | 5h") from None


def _sprache_code(text: str) -> str:
    code = text.strip().lower()[:2]
    if code not in sprache.SPRACHEN:
        raise argparse.ArgumentTypeError("de | en")
    return code


def _namen(deutsch: str, englisch: str) -> tuple[str, ...]:
    """Option mit deutschem und englischem Namen – der Sprache entsprechend zuerst."""
    if deutsch == englisch:
        return (deutsch,)
    return (englisch, deutsch) if sprache.englisch() else (deutsch, englisch)


def _befehl(sub, name: str, **kwargs):
    englisch = BEFEHLE[name]
    if englisch == name:
        return sub.add_parser(name, **kwargs)
    erster, zweiter = (englisch, name) if sprache.englisch() else (name, englisch)
    return sub.add_parser(erster, aliases=[zweiter], **kwargs)


def _sprache_vorab(argv: list[str]) -> str | None:
    """--sprache/--language schon vor dem Aufbau der Hilfe auswerten."""
    for i, arg in enumerate(argv):
        for name in ("--sprache", "--language", "--lang"):
            if arg == name and i + 1 < len(argv):
                return argv[i + 1]
            if arg.startswith(name + "="):
                return arg.split("=", 1)[1]
    return None


def _frage(text: str) -> bool:
    try:
        antwort = input(text)
    except EOFError:
        return False
    return antwort.strip().lower() in JA


def _fehler_ausgeben(liste) -> None:
    if not liste:
        print(t("Kein Fehler gespeichert."))
        return
    print(t("{anzahl} Fehler gespeichert:", anzahl=len(liste)))
    for f in liste:
        print("  " + f.zeile())


class _Ereignisse:
    """Meldungen aus dem Diagnose-Thread auf der Konsole (und in der CSV)."""

    def __init__(self, sim: bool = False):
        self.sim = sim
        self.csv: CsvAufzeichnung | None = None
        self.verbindungen = 0
        self.verbindung: Verbindung | None = None
        self.fahrt = False
        self._werte: dict[str, str] = {}
        self._werte_gedruckt = 0.0
        self._letzter_status = ""

    def __call__(self, art: str, daten) -> None:
        if art == "baud":
            if not self.sim:   # der Simulator soll keine Baudraten fürs Auto hinterlassen
                einstellungen.baud_merken(*daten)
        elif art == "fahrt":
            status = f"[{daten['phase']}] {daten['text']}"
            if status != self._letzter_status:
                self._letzter_status = status
                print(f"{time.strftime('%H:%M:%S')}  {status}", flush=True)
        elif art == "fahrt_notiz":
            print(f"  {daten}", flush=True)
        elif art == "fahrt_werte":
            for name, m in zip(daten["namen"], daten["werte"]):
                if name in ("Motordrehzahl", "Fahrgeschwindigkeit", "Geschwindigkeit",
                            "Kühlmitteltemperatur", "Bordspannung", "Tankinhalt"):
                    self._werte[name] = m.text
            if time.monotonic() - self._werte_gedruckt >= 5:
                self._werte_gedruckt = time.monotonic()
                print(f"{time.strftime('%H:%M:%S')}  " + " · ".join(
                    f"{beschriftung.anzeige(name)}: {text}"
                    for name, text in self._werte.items()), flush=True)
        elif art == "verbunden" and self.fahrt:
            self.verbindung = daten
        elif art == "verbunden":
            self.verbindung = daten
            self.verbindungen += 1
            if self.verbindungen > 1:
                print("  … " + t("wieder verbunden ({uhrzeit})",
                                 uhrzeit=time.strftime("%H:%M:%S")), flush=True)
                if self.csv:
                    self.csv.ereignis(t("wieder verbunden"))
        elif art == "getrennt" and daten.get("neu_verbinden"):
            print("  … " + t("Verbindung verloren ({grund}) – verbinde neu",
                             grund=daten["grund"]), flush=True)
            if self.csv:
                self.csv.ereignis(t("Verbindung verloren: {grund}", grund=daten["grund"]))
        elif art == "neu_verbinden" and daten > 1:
            print("  … " + t("Neuverbindung, Versuch {nummer}", nummer=daten), flush=True)
        elif art == "suche":
            gruppe, werte = daten
            if werte is not None:
                namen = beschriftung.namen(self.verbindung, gruppe, werte)
                print("  " + t("Gruppe {gruppe:03d}:", gruppe=gruppe) + " "
                      + " | ".join(beschriftung.mit_namen(namen, werte, self.verbindung)),
                      flush=True)
            elif gruppe % 25 == 0:
                print(f"  … {gruppe:03d}", flush=True)
        elif art == "anpassung_suche":
            kanal, anpassung = daten
            if anpassung is not None:
                print(f"  {anpassung.text}", flush=True)
            elif kanal % 25 == 0:
                print("  … " + t("Kanal {kanal:02d}", kanal=kanal), flush=True)
        elif art == "grundeinstellung":
            if time.monotonic() - self._werte_gedruckt >= 2:
                self._werte_gedruckt = time.monotonic()
                print(f"  {daten['sekunden']:4.0f} s / {daten['dauer']:.0f} s  "
                      + " | ".join(m.text for m in daten["werte"]), flush=True)
        elif art == "stellglied":
            print("  " + t("Stellglied {nummer}: {text}", nummer=daten["schritt"],
                           text=daten["stellglied"].text)
                  + "  – " + t("Enter = weiter, q = beenden"), flush=True)


def _einstellungen(args) -> int:
    aenderung = {}
    if args.sprache_setzen:
        aenderung["sprache"] = args.sprache_setzen
    if args.log_ordner_setzen:
        aenderung["log_ordner"] = args.log_ordner_setzen
    if args.csv_ordner_setzen:
        aenderung["csv_ordner"] = args.csv_ordner_setzen
    if args.log_datei is not None:
        aenderung["log_datei"] = args.log_datei
    if args.csv_automatisch is not None:
        aenderung["csv_automatisch"] = args.csv_automatisch
    if args.neu_verbinden is not None:
        aenderung["neu_verbinden"] = args.neu_verbinden
    if args.fast_init_setzen is not None:
        aenderung["fast_init"] = args.fast_init_setzen
    werte = einstellungen.speichern(**aenderung) if aenderung else einstellungen.laden()
    if "sprache" in aenderung:
        sprache.setzen(werte["sprache"])
    zeilen = [
        (t("Einstellungsdatei:"), einstellungen.DATEI),
        (t("Sprache:"), sprache.SPRACHEN.get(werte["sprache"], werte["sprache"])),
        (t("Protokolldatei:"), sprache.ja_nein(werte["log_datei"])),
        (t("Log-Ordner:"), werte["log_ordner"]),
        (t("CSV automatisch:"), sprache.ja_nein(werte["csv_automatisch"])),
        (t("CSV-Ordner:"), werte["csv_ordner"]),
        (t("Neu verbinden:"), sprache.ja_nein(werte["neu_verbinden"])),
        (t("Fast-Init beim Motor:"), sprache.ja_nein(werte["fast_init"])),
    ]
    if werte["baudraten"]:
        zeilen.append((t("Gemerkte Baudraten:"), ", ".join(
            f"{k}: {v}" for k, v in sorted(werte["baudraten"].items()))))
    breite = max(len(name) for name, _ in zeilen) + 2
    for name, wert in zeilen:
        print(f"{name:<{breite}}{wert}")
    return 0


class _Version(argparse.Action):
    """--version: Version, Urheber, Lizenz, keine Gewährleistung (Zeilen bleiben, wie sie sind)."""

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        print("\n".join(textwrap.fill(absatz, 78) for absatz in lizenz.kurz()))
        parser.exit()


def _lizenz(args) -> int:
    if args.volltext:
        print(lizenz.lizenztext())
        return 0
    print("\n\n".join(textwrap.fill(absatz, 78, break_on_hyphens=False)
                       for absatz in lizenz.kurz() + lizenz.hinweise()))
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m vagdiag.cli",
                                description=t("VAG-Diagnose über KKL-Kabel (KW1281/KWP2000)"),
                                epilog=t("{copyright} – freie Software (GPL-3.0-or-later), ohne "
                                         "Gewährleistung. Mehr dazu: --version, {befehl}",
                                         copyright=lizenz.COPYRIGHT,
                                         befehl=_namen("lizenz", BEFEHLE["lizenz"])[0]))
    p.add_argument("--version", action=_Version,
                   help=t("Version, Urheber und Lizenz anzeigen"))
    p.add_argument(*_namen("--sprache", "--language"), dest="sprache", type=_sprache_code,
                   metavar="de|en", help=t("Sprache für diesen Lauf (Standard: Einstellung)"))
    p.add_argument("--sim", action="store_true", help=t("Simulator statt Kabel"))
    p.add_argument("--sim-kwp2000", dest="sim_kwp2000", action="store_true",
                   help=t("Simulator, dessen Motor und Kombi KWP2000 sprechen"))
    p.add_argument("--fast-init", dest="fast_init", action="store_true", default=None,
                   help=t("Motor (01): zuerst den KWP2000-Fast-Init probieren (Standard: "
                          "Einstellung)"))
    p.add_argument("--url", default=standard_url(),
                   help=t("Kabel-Adresse, z. B. ftdi:///1 (Linux) oder d2xx:0 (Windows)"))
    p.add_argument("--baud", choices=BAUDS, default="auto")
    p.add_argument(*_namen("--reizung", "--init"), dest="reizung",
                   choices=["break", "bitbang"], default="break",
                   help=t("Art der 5-Baud-Reizung; bitbang als Ausweichweg für Klon-Chips"))
    p.add_argument(*_namen("--adresse", "--address"), dest="adresse", type=_hex, default=None,
                   metavar=t("ADRESSE"), help=t("Steuergeräte-Adresse hexadezimal (01 Motor, 17 Kombi); Standard 01, "
                          "bei „kilometerstand“ 17"))
    p.add_argument(*_namen("--mit-airbag", "--with-airbag"), dest="mit_airbag",
                   action="store_true",
                   help=t("Airbag-Steuergerät (15) ohne Rückfrage einbeziehen (siehe README)"))
    p.add_argument("--log", nargs="?", const="", default=None, metavar=t("DATEI"),
                   help=t("Protokolldatei schreiben – ohne DATEI eine neue im Log-Ordner"))
    p.add_argument(*_namen("--log-ordner", "--log-folder"), dest="log_ordner",
                   metavar=t("ORDNER"), help=t("Protokolldatei in diesen Ordner schreiben (nur dieser Lauf)"))
    p.add_argument(*_namen("--csv-ordner", "--csv-folder"), dest="csv_ordner",
                   metavar=t("ORDNER"), help=t("CSV-Ordner nur für diesen Lauf"))
    p.add_argument(*_namen("--experte", "--expert"), dest="experte", action="store_true",
                   help=t("Expertenmodus für diesen Lauf – nur für die Expertenfunktionen, mit "
                          "Warnung und Rückfrage, nur an einer Konsole"))
    p.add_argument("-v", action="store_true", help=t("Protokollablauf anzeigen"))
    p.add_argument("--bytes", action="store_true", help=t("auch jedes Byte anzeigen"))
    sub = p.add_subparsers(dest="befehl", required=True, metavar=t("BEFEHL"))
    _befehl(sub, "geraete", help=t("angeschlossene FTDI-Kabel auflisten"))
    _befehl(sub, "kabeltest", help=t("Kabel öffnen und Echo prüfen"))
    _befehl(sub, "ident", help=t("Steuergerät identifizieren"))
    _befehl(sub, "fehler", help=t("Fehlerspeicher lesen"))
    lo = _befehl(sub, "loeschen", help=t("Fehlerspeicher löschen"))
    lo.add_argument(*_namen("--ja", "--yes"), dest="ja", action="store_true",
                    help=t("ohne Rückfrage"))
    gr = _befehl(sub, "gruppe", help=t("Messwertgruppen lesen (mit Min/Max, auf Wunsch CSV)"))
    gr.add_argument("gruppen", type=int, nargs="+", metavar=t("GRUPPE"))
    wie = gr.add_mutually_exclusive_group()
    wie.add_argument(*_namen("--wiederholen", "--repeat"), dest="wiederholen", type=int,
                     default=1, metavar="N")
    wie.add_argument(*_namen("--dauer", "--continuous"), dest="dauer", action="store_true",
                     help=t("bis Strg+C"))
    csv_wahl = gr.add_mutually_exclusive_group()
    csv_wahl.add_argument("--csv", dest="csv", action="store_true", default=None,
                          help=t("als CSV aufzeichnen"))
    csv_wahl.add_argument(*_namen("--ohne-csv", "--no-csv"), dest="csv", action="store_false",
                          help=t("nicht aufzeichnen"))
    gr.add_argument(*_namen("--ohne-neuverbinden", "--no-reconnect"), dest="ohne_neuverbinden",
                    action="store_true",
                    help=t("bei Verbindungsabbruch aufhören statt neu zu verbinden"))
    gs = _befehl(sub, "gruppensuche", help=t("alle belegten Messwertgruppen finden"))
    gs.add_argument(*_namen("--von", "--from"), dest="von", type=int, default=0, metavar="N",
                    help=t("ab dieser Gruppe (Standard 000 – zehn Rohwerte, nur KW1281)"))
    gs.add_argument(*_namen("--bis", "--to"), dest="bis", type=int, default=255, metavar="N")
    an = _befehl(sub, "anpassung", help=t("Anpassungskanäle lesen (nur lesen, nie Kanal 00)"))
    an.add_argument("kanaele", type=int, nargs="+", metavar=t("KANAL"))
    ans = _befehl(sub, "anpassungssuche",
                  help=t("alle lesbaren Anpassungskanäle finden (nur lesen)"))
    ans.add_argument(*_namen("--von", "--from"), dest="von", type=int, default=1, metavar="N")
    ans.add_argument(*_namen("--bis", "--to"), dest="bis", type=int, default=99, metavar="N")
    _befehl(sub, "kilometerstand",
            help=t("Kilometerstand aus dem Kombi (Gruppe 002, sonst Anpassungskanal 09)"))
    fa = _befehl(sub, "fahrt", help=t("Fahrtenschreiber: ganze Fahrt aufzeichnen (Enter = "
                                      "Ereignis markieren, Strg+C = beenden)"))
    fa.add_argument(*_namen("--motor-gruppen", "--engine-groups"), dest="motor_gruppen",
                    metavar=t("LISTE"), help=t("z. B. 1,2,3,4,5"))
    fa.add_argument(*_namen("--kombi-alle", "--cluster-every"), dest="kombi_alle",
                    type=float, metavar="S",
                    help=t("Sekunden zwischen zwei Besuchen beim Kombi (0 = nie)"))
    fa.add_argument(*_namen("--abs-alle", "--abs-every"), dest="abs_alle", type=float,
                    metavar="S", help=t("Sekunden zwischen zwei Besuchen beim ABS, nur im Stand "
                                        "(0 = nie)"))
    fa.add_argument(*_namen("--besuch", "--visit"), dest="besuch", type=float, metavar="S",
                    help=t("Sekunden je Besuch"))
    fa.add_argument(*_namen("--ohne-pruefung", "--no-check"), dest="ohne_pruefung",
                    action="store_true", help=t("ohne Start- und Abschlussprüfung"))
    fa.add_argument(*_namen("--passiv", "--passive"), dest="passiv", type=_zeitspanne,
                    metavar="5min|20min|1h|5h",
                    help=t("passiv wie eine Dashcam: Ringspeicher mit dieser Zeitspanne "
                           "Fahrzeit, über Fahrten und Neustarts hinweg; Enter sichert sie "
                           "zusätzlich in eine eigene Datei"))
    fe = _befehl(sub, "fahrt-export", help=t("Zeitspanne aus dem Ringspeicher des passiven "
                                             "Fahrtenschreibers in eine eigene Datei sichern"))
    fe.add_argument(*_namen("--zeitspanne", "--span"), dest="zeitspanne", type=_zeitspanne,
                    metavar="5min|20min|1h|5h",
                    help=t("Standard: die zuletzt gewählte (Einstellungen)"))
    sc = _befehl(sub, "scan", help=t("übliche Steuergeräte abfragen (mit --alle: alle Adressen "
                                     "01–7F)"))
    sc.add_argument(*_namen("--alle", "--all"), dest="alle", action="store_true",
                    help=t("alle Adressen 01–7F abfragen (etwa 8 Minuten)"))
    _befehl(sub, "obd2", help=t("OBD-II-Test an Adresse 33: Protokoll, Readiness, "
                                "Motorkontrollleuchte, FIN (nur lesen)"))
    es = _befehl(sub, "einstellungen", help=t("Ordner und Optionen anzeigen/ändern"))
    ordner = t("ORDNER")
    ja_nein = t("ja|nein")
    es.add_argument(*_namen("--sprache-setzen", "--set-language"), dest="sprache_setzen",
                    type=_sprache_code, metavar="de|en")
    es.add_argument(*_namen("--log-ordner-setzen", "--set-log-folder"),
                    dest="log_ordner_setzen", metavar=ordner)
    es.add_argument(*_namen("--csv-ordner-setzen", "--set-csv-folder"),
                    dest="csv_ordner_setzen", metavar=ordner)
    es.add_argument(*_namen("--log-datei", "--log-file"), dest="log_datei", type=_ja_nein,
                    metavar=ja_nein, help=t("Protokolldatei immer schreiben"))
    es.add_argument(*_namen("--csv-automatisch", "--csv-auto"), dest="csv_automatisch",
                    type=_ja_nein, metavar=ja_nein,
                    help=t("Messwertgruppen immer als CSV aufzeichnen"))
    es.add_argument(*_namen("--neu-verbinden", "--reconnect"), dest="neu_verbinden",
                    type=_ja_nein, metavar=ja_nein)
    es.add_argument(*_namen("--fast-init-setzen", "--set-fast-init"), dest="fast_init_setzen",
                    type=_ja_nein, metavar=ja_nein,
                    help=t("beim Motor immer zuerst den Fast-Init probieren"))
    dk = _befehl(sub, "drosselklappe", help=t("Expertenfunktion: Drosselklappe anlernen "
                                              "(Grundeinstellung, Motor 01)"))
    dk.add_argument(*_namen("--gruppe", "--group"), dest="gruppe", type=int,
                    choices=sorted(experte.DROSSELKLAPPE_GRUPPEN), default=60,
                    help=t("060 bei E-Gas (z. B. ME7), 098 bei Seilzug"))
    _befehl(sub, "service-reset", help=t("Expertenfunktion: Service-Intervall zurücksetzen "
                                         "(Kombi 17, Kanal 02 → 0)"))
    _befehl(sub, "stellglieder", help=t("Expertenfunktion: Stellglieddiagnose am Steuergerät "
                                        "(--adresse); Enter = weiter, q = beenden"))
    li = _befehl(sub, "lizenz", help=t("Lizenz, Gewährleistung und fremde Bestandteile anzeigen"))
    li.add_argument(*_namen("--volltext", "--full-text"), dest="volltext", action="store_true",
                    help=t("den ganzen Lizenztext (GPL) ausgeben"))
    return p


def _airbag_erlaubt(args, sitzung: DiagSession) -> bool:
    """Rückfrage vor Adresse 15 – oder Freigabe per --mit-airbag."""
    if args.mit_airbag:
        sitzung.airbag_freigeben()
        return True
    print(airbag.hinweis() + "\n")
    if not sys.stdin.isatty():
        print(t("Ohne Rückfragemöglichkeit nur mit --mit-airbag."))
        return False
    if _frage(t("Trotzdem mit dem Airbag-Steuergerät verbinden? [j/N] ")):
        sitzung.airbag_freigeben()
        return True
    return False


def _ausgabe_absichern() -> None:
    """Kann die Konsole ein Zeichen nicht darstellen (z. B. „→“ in einer umgeleiteten
    Ausgabe unter Windows), lieber ein Ersatzzeichen als ein Absturz."""
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _ausgabe_absichern()
    argv = list(sys.argv[1:] if argv is None else argv)
    # „--log fehler“: fehler ist der Befehl, kein Dateiname
    for i, arg in enumerate(argv[:-1]):
        if arg == "--log" and argv[i + 1] in KANONISCH:
            argv[i] = "--log="
    sprache.setzen(_sprache_vorab(argv) or einstellungen.laden()["sprache"])
    args = _parser().parse_args(argv)
    args.befehl = KANONISCH.get(args.befehl, args.befehl)
    if args.sprache:
        sprache.setzen(args.sprache)

    if args.befehl == "einstellungen":
        return _einstellungen(args)
    if args.befehl == "lizenz":
        return _lizenz(args)
    if args.befehl == "fahrt-export":
        return _fahrt_export(args)

    feste_datei = Path(args.log).expanduser() if args.log else None
    schreiben = True if (args.log is not None or args.log_ordner) else None
    datei = protokolldatei.einrichten(feste_datei, konsole=args.v or args.bytes,
                                      bytes_in_konsole=args.bytes, ordner=args.log_ordner,
                                      schreiben=schreiben)
    if datei:
        print(t("Protokoll: {pfad}", pfad=datei))

    def protokoll_hinweis() -> str:
        if datei:
            return t("Protokolldatei für die Fehlersuche: {pfad}", pfad=datei)
        return t("Für die Fehlersuche mit --log wiederholen – dann entsteht eine "
                 "Protokolldatei.")

    if args.befehl == "geraete":
        try:
            geraete = list_ftdi_devices()
        except PortError as exc:
            print(t("Fehler: {fehler}", fehler=exc))
            return 2
        if not geraete:
            print(t("Kein FTDI-Kabel gefunden.") + " " + einrichtungs_hinweis())
        for url, beschreibung in geraete:
            print(f"  {url}  {beschreibung}")
        return 0

    args.sim = args.sim or args.sim_kwp2000

    def fabrik():
        if args.sim_kwp2000:
            return sim_port(kwp2000_motor=True, kwp2000_kombi=True)
        if args.sim:
            return sim_port()
        return kabel_oeffnen(args.url, args.reizung)

    if args.befehl in EXPERTE_BEFEHLE:
        if not args.experte:
            print(t("„{befehl}“ ändert Werte im Steuergerät oder steuert Stellglieder an – das geht "
                    "nur mit --experte.", befehl=_namen(args.befehl, BEFEHLE[args.befehl])[0]))
            return 4
        if not sys.stdin.isatty():
            print(t("Expertenfunktionen nur mit Rückfrage an einer Konsole – ohne Eingabe "
                    "(z. B. in einem Skript) startet vagdiag sie nicht."))
            return 4
        soll = {"drosselklappe": 0x01, "service-reset": 0x17}.get(args.befehl)
        if soll is not None and args.adresse not in (None, soll):
            print(t("„{befehl}“ gilt {steuergeraet} – ohne --adresse oder mit --adresse "
                    "{adresse:02X}.", befehl=_namen(args.befehl, BEFEHLE[args.befehl])[0],
                    steuergeraet=adressen.text(soll), adresse=soll))
            return 4
        if not _experte_bestaetigt():
            print(t("Abgebrochen."))
            return 4
    if args.adresse is None:
        args.adresse = 0x17 if args.befehl in ("kilometerstand", "service-reset") else 0x01
    melder = _Ereignisse(sim=args.sim)
    gemerkt = ({} if args.sim else
               {int(k, 16): v for k, v in einstellungen.laden()["baudraten"].items()})
    sitzung = DiagSession(fabrik, ereignis=melder, baudraten=gemerkt).start()
    sitzung.fast_init = (bool(einstellungen.laden()["fast_init"]) if args.fast_init is None
                         else args.fast_init)
    if args.mit_airbag:
        sitzung.airbag_freigeben()
    if args.befehl in EXPERTE_BEFEHLE:
        sitzung.experte = True              # nur für diesen Lauf
    bauds = BAUDS[args.baud]
    minmax = MinMax()
    try:
        if args.befehl == "kabeltest":
            erg = sitzung.kabeltest().result()
            print(t("Kabel: {geraet}\nEcho: {echo}", geraet=erg["geraet"],
                    echo=sprache.ja_nein(erg["echo"])) + "\n" + erg["hinweis"])
            return 0

        if args.befehl == "fahrt":
            return _fahrt(args, sitzung, melder)

        if args.befehl == "scan":
            return _scan(args, sitzung, bauds)

        if args.befehl == "obd2":
            print(t("OBD-II-Test an Adresse 33 (nur lesen) …"), flush=True)
            ergebnis = sitzung.obd2_test().result()
            print("\n".join(ergebnis.zeilen()))
            return 0 if ergebnis.ok else 5

        if args.adresse == airbag.ADRESSE and not _airbag_erlaubt(args, sitzung):
            print(t("Abgebrochen."))
            return 4
        v = sitzung.verbinden(args.adresse, bauds).result()
        melder.verbindung = v
        print("\n".join(ident.zeilen(v, args.sim)))
        print()

        if args.befehl == "fehler":
            _fehler_ausgeben(sitzung.fehler_lesen().result())
        elif args.befehl == "loeschen":
            _fehler_ausgeben(sitzung.fehler_lesen().result())
            if not args.ja:
                frage = t("Fehlerspeicher löschen? Readiness wird dabei zurückgesetzt. [j/N] ")
                hinweis = geprueft.hinweis(v)
                if hinweis:
                    frage = hinweis + "\n" + frage
                if not _frage(frage):
                    print(t("Abgebrochen."))
                    return 0
            rest = sitzung.fehler_loeschen(v.kennung).result()   # nur genau dieses Gerät
            print(t("Gelöscht."))
            if rest:
                print(t("Sofort wieder gesetzt:"))
                _fehler_ausgeben(rest)
            print("\n" + t("Fehlerspeicher jetzt:"))
            _fehler_ausgeben(sitzung.fehler_lesen().result())
        elif args.befehl == "gruppensuche":
            print(t("Suche Messwertgruppen {von:03d}–{bis:03d} (Strg+C bricht ab) …",
                    von=args.von, bis=args.bis))
            gefunden = sitzung.gruppen_suchen(args.von, args.bis).result()
            print("\n" + t("{anzahl} belegte Gruppen:", anzahl=len(gefunden)) + " "
                  + ", ".join(f"{g:03d}" for g in gefunden))
        elif args.befehl == "gruppe":
            return _gruppen_messen(args, sitzung, melder, minmax)
        elif args.befehl == "anpassung":
            for kanal in args.kanaele:
                try:
                    print(sitzung.anpassung_lesen(kanal).result().text)
                except (NotAvailable, Nak, ValueError) as exc:
                    print(t("Kanal {kanal:02d}:", kanal=kanal) + f" {exc}")
        elif args.befehl == "anpassungssuche":
            print(t("Lese Anpassungskanäle {von:02d}–{bis:02d} (nur lesen, Strg+C bricht ab) …",
                    von=max(1, args.von), bis=args.bis))
            gefunden = sitzung.anpassungen_suchen(args.von, args.bis).result()
            print("\n" + t("{anzahl} lesbare Kanäle:", anzahl=len(gefunden)) + " "
                  + ", ".join(f"{k:02d}" for k in gefunden))
        elif args.befehl == "kilometerstand":
            if args.adresse != 0x17:
                print(t("Hinweis: Der Kilometerstand steht normalerweise im Kombi (Adresse 17)."))
            print("\n".join(sitzung.kilometerstand().result().zeilen))
        elif args.befehl == "drosselklappe":
            return _drosselklappe(args, sitzung)
        elif args.befehl == "service-reset":
            return _service_reset(sitzung, v)
        elif args.befehl == "stellglieder":
            return _stellglieder(sitzung)
        return 0
    except UnsupportedProtocol as exc:
        print(f"\n{exc}")
        if datei:
            print(t("Für eine Fehlermeldung bitte diese Protokolldatei mitschicken: {pfad}",
                    pfad=datei))
        else:
            print(t("Für eine Fehlermeldung bitte mit --log wiederholen und die "
                    "Protokolldatei mitschicken."))
        return 3
    except Abgebrochen:
        print("\n" + t("Abgebrochen."))
        return 130
    except experte.Nichts as exc:
        print("\n" + str(exc))
        return 1
    except DiagError as exc:
        print("\n" + t("Fehler: {fehler}", fehler=exc))
        print(protokoll_hinweis())
        return 1
    except PortError as exc:
        print("\n" + t("Fehler: {fehler}", fehler=exc))
        return 2
    except KeyboardInterrupt:
        sitzung.abbrechen()
        print("\n" + t("Abgebrochen."))
        return 130
    finally:
        sitzung.schliessen()


# ---------------------------------------------------------------- Expertenfunktionen
def _experte_bestaetigt() -> bool:
    """Hinweis zum Expertenmodus, dann „ja“ eintippen (ein einzelnes j reicht hier nicht)."""
    print("\n\n".join("\n".join(textwrap.fill(zeile, 78) for zeile in absatz.splitlines())
                      for absatz in t(experte.HINWEIS).split("\n\n")))
    try:
        antwort = input("\n" + t("Zum Einschalten „ja“ eintippen: "))
    except EOFError:
        return False
    if antwort.strip().lower() not in ("ja", "yes", t("ja")):
        return False
    log.warning(t("Expertenmodus an (Kommandozeile)"))
    return True


def _ziel(sitzung: DiagSession, kennung: tuple) -> str:
    port = getattr(sitzung, "_port", None)
    return experte.ziel_text(kennung, bool(getattr(port, "simulator", False)))


def _ergebnis_abwarten(sitzung: DiagSession, future):
    """Auf eine laufende Expertenfunktion warten – Strg+C bricht sie ab (sie räumt dann
    selbst auf: zurück zu den Messwerten bzw. Verbindung beenden)."""
    while True:
        try:
            return future.result(timeout=0.5)
        except FutureTimeout:
            continue
        except KeyboardInterrupt:
            sitzung.abbrechen()
            print("\n" + t("Abbruch …"), flush=True)


def _drosselklappe(args, sitzung: DiagSession) -> int:
    gruppe = args.gruppe
    print(t("Prüfe die Bedingungen …"), flush=True)
    pruefung = sitzung.drosselklappe_pruefen(gruppe).result()
    liste = experte.bedingungen_text(pruefung.bedingungen)
    print(t("Prüfung Gruppe {gruppe:03d}:", gruppe=gruppe) + "\n" + liste + "\n")
    if pruefung.verletzt:
        print(t("Nicht erfüllt – vagdiag startet die Grundeinstellung nicht."))
        if pruefung.fehler:
            print(t("Fehler erst beheben oder löschen, danach die Zündung aus- und wieder "
                    "einschalten."))
        return 1
    print(_ziel(sitzung, pruefung.kennung) + "\n")
    print(t("Während der nächsten 30 Sekunden: Gaspedal nicht berühren, Motor nicht starten."))
    if pruefung.ungeprueft:
        print(t("Nicht prüfbar – bitte selbst sicherstellen: {liste}", liste=", ".join(
            t(b.name) for b in pruefung.ungeprueft)))
    if not _frage(t("Grundeinstellung Gruppe {gruppe:03d} jetzt starten?", gruppe=gruppe)
                  + " " + t("[j/N] ")):
        print(t("Nicht gestartet."))
        return 0
    print(t("Grundeinstellung läuft – Strg+C bricht ab.") + "\n", flush=True)
    ergebnis = _ergebnis_abwarten(sitzung, sitzung.drosselklappe_anlernen(
        gruppe, experte.DAUER, ohne_pruefung_ok=bool(pruefung.ungeprueft),
        kennung=pruefung.kennung))
    print("\n" + experte.grundeinstellung_urteil(ergebnis) + "\n\n"
          + experte.fehler_text(ergebnis.fehler_nachher))
    return 0 if ergebnis.status == "ok" else 1


def _service_reset(sitzung: DiagSession, v: Verbindung) -> int:
    anpassung = sitzung.service_lesen().result()
    print(anpassung.text + "\n")
    print(_ziel(sitzung, v.kennung) + "\n")
    if not _frage(t("Auf 0 zurücksetzen? Der alte Wert wird vorher gesichert.") + " "
                  + t("[j/N] ")):
        print(t("Nicht gestartet."))
        return 0
    ergebnis = sitzung.service_zuruecksetzen(anpassung.wert, kennung=v.kennung).result()
    print(t("Kanal 02: vorher {alt}, jetzt {neu}. Sicherung: {pfad}", alt=ergebnis.alt,
            neu=ergebnis.neu, pfad=ergebnis.sicherung))
    return 0


def _stellglieder(sitzung: DiagSession) -> int:
    pruefung = sitzung.stellglied_pruefen().result()
    steuergeraet = adressen.text(pruefung.adresse)
    liste = experte.bedingungen_text(pruefung.bedingungen)
    if liste:
        print(t("Prüfung Stellglieddiagnose {steuergeraet}:", steuergeraet=steuergeraet)
              + "\n" + liste + "\n")
    if pruefung.verletzt:
        print(t("Nicht erfüllt – vagdiag startet die Stellglieddiagnose nicht."))
        return 1
    ziel = _ziel(sitzung, pruefung.kennung)
    gefahr = pruefung.gefahr
    if gefahr is not None:
        print(t("WARNUNG: {art}", art=gefahr.name).upper() + "\n")
        print(experte.gefahr_text(pruefung, steuergeraet, ziel) + "\n")
        if not _frage(t("Warnung gelesen – weiter zur Rückfrage?") + " " + t("[j/N] ")):
            log.info(t("EXPERTE: Warnung (%s) für %s nicht bestätigt – nicht gestartet"),
                     gefahr.name, experte.kennung_text(pruefung.kennung))
            print(t("Nicht gestartet."))
            return 0
        log.warning(t("EXPERTE: Warnung (%s) für %s bestätigt"), gefahr.name,
                    experte.kennung_text(pruefung.kennung))
    schritt_max = getattr(sitzung, "stellglied_schritt_max", experte.SCHRITT_MAX)
    print(ziel + "\n")
    print("\n\n".join(experte.stellglied_hinweise(pruefung, schritt_max)) + "\n")
    if not _frage(t("Stellglieddiagnose an {steuergeraet} starten?", steuergeraet=steuergeraet)
                  + " " + t("[j/N] ")):
        log.info(t("EXPERTE: Stellglieddiagnose %02X – Rückfrage mit Nein beantwortet, "
                   "nicht gestartet"), pruefung.adresse)
        print(t("Nicht gestartet."))
        return 0
    print(t("Enter = nächstes Stellglied, q und Enter = beenden, Strg+C = abbrechen.") + "\n",
          flush=True)
    future = sitzung.stellglieddiagnose(ohne_pruefung_ok=bool(pruefung.ungeprueft),
                                        kennung=pruefung.kennung,
                                        gefahr_bestaetigt=gefahr.art if gefahr else None)

    def eingabe():
        for zeile in sys.stdin:
            if future.done():
                return
            if zeile.strip().lower() in ("q", "s", "x", "ende", "end", "stopp", "stop"):
                sitzung.stellglied_beenden()
                return
            sitzung.stellglied_weiter()

    threading.Thread(target=eingabe, name="stellglied-eingabe", daemon=True).start()
    ergebnis = _ergebnis_abwarten(sitzung, future)
    _kopf, text = experte.stellglied_bericht(ergebnis, schritt_max)
    print("\n" + text)
    return 0


def _scan(args, sitzung: DiagSession, bauds) -> int:
    """Übliche Adressen: jede mit Ergebnis. Alle Adressen: nur die, die antworten, und
    am Ende eine Zeile mit den übrigen."""
    alle = args.alle
    liste = adressen.alle() if alle else list(adressen.ADRESSEN)
    if alle:
        print(t("Frage alle Adressen 01–7F ab – etwa 8 Minuten, Strg+C bricht ab. Gezeigt "
                "werden nur die Adressen, die antworten."), flush=True)
    stumm: list[int] = []
    for adresse in liste:
        if alle and adresse % 0x10 == 0:
            print(t("… Adressen {von:02X}–{bis:02X}", von=adresse, bis=min(adresse + 0x0F, 0x7F)),
                  flush=True)
        if adresse in adressen.UEBERSPRINGEN:
            print(f"\n{adressen.text(adresse)}: " + t("übersprungen – {grund}",
                                                      grund=t(adressen.UEBERSPRINGEN[adresse])))
            continue
        if not alle:
            print(f"\n{adressen.text(adresse)} …", flush=True)
        if adresse == airbag.ADRESSE and not args.mit_airbag:
            if alle:
                print(f"\n{adressen.text(adresse)} …")
            print("  " + t("übersprungen – mit --mit-airbag einschließen (Hinweis in "
                           "der README)"))
            continue
        try:
            v = sitzung.verbinden(adresse, bauds).result()
            if alle:
                print(f"\n{adressen.text(adresse)} …")
            print("\n".join("  " + z for z in ident.zeilen(v)), flush=True)
            sitzung.trennen().result()
        except NoResponse:
            if alle:
                stumm.append(adresse)
            else:
                print("  " + t("keine Antwort"))
        except DiagError as exc:
            if alle:
                print(f"\n{adressen.text(adresse)} …")
            print(f"  {exc}", flush=True)
    if alle and stumm:
        print("\n" + "\n".join(textwrap.wrap(t(
            "Keine Antwort ({anzahl}): {liste}", anzahl=len(stumm),
            liste=", ".join(f"{a:02X}" for a in stumm)), 78)))
    return 0


def _fahrtplan(args) -> FahrtPlan:
    werte = einstellungen.laden()
    plan = FahrtPlan.aus_einstellungen()
    if args.motor_gruppen:
        plan.motor_gruppen = _gruppenliste(args.motor_gruppen) or plan.motor_gruppen
    besuch = args.besuch if args.besuch is not None else float(werte["fahrt_besuch"])
    kombi = args.kombi_alle if args.kombi_alle is not None else float(werte["fahrt_kombi_alle"])
    abs_ = args.abs_alle if args.abs_alle is not None else float(werte["fahrt_abs_alle"])
    plan.besuche = [b for b in (Besuch(0x17, (1, 2, 3), kombi, besuch),
                                Besuch(0x03, (1, 3), abs_, besuch)) if b.alle_sekunden > 0]
    if args.ohne_pruefung:
        plan.pruefung = False
    plan.mit_airbag = bool(args.mit_airbag)
    plan.passiv = float(args.passiv) if args.passiv else None
    return plan


def _fahrt_export(args) -> int:
    """Zeitspanne aus dem Ringspeicher sichern – ohne Kabel, auch während ein anderer
    Fahrtenschreiber (z. B. automatisch gestartet) weiter aufzeichnet."""
    sim = args.sim or args.sim_kwp2000
    fenster = args.zeitspanne or int(einstellungen.laden()["fahrt_passiv_fenster"])
    ordner = ringspeicher.ordner(args.csv_ordner, sim)
    if not ringspeicher.vorhanden(ordner):
        print(t("Im Ringspeicher {ordner} liegt noch nichts – erst mit „fahrt --passiv“ "
                "aufzeichnen.", ordner=ordner))
        return 1
    try:
        ergebnis = passiv_exportieren(args.csv_ordner, fenster, sim, gesichert=True)
    except OSError as exc:
        print(t("Zeitspanne nicht gesichert: {fehler}", fehler=exc))
        return 2
    print("\n".join(ergebnis.zeilen))
    if ergebnis.txt_datei:
        print("\n" + t("Zusammenfassung gespeichert: {pfad}", pfad=ergebnis.txt_datei))
    return 0


def _fahrt(args, sitzung: DiagSession, melder: _Ereignisse) -> int:
    plan = _fahrtplan(args)
    melder.fahrt = True
    print(t("Fahrtenschreiber. Enter markiert ein Ereignis (z. B. Warnlampe an) und liest\n"
            "sofort den Fehlerspeicher des Motors, den des ABS beim nächsten Halt. Strg+C\n"
            "beendet die Fahrt – danach läuft noch die Abschlussprüfung, Zündung so lange\n"
            "an lassen. Das ABS wird nur im Stand besucht.") + "\n",
          flush=True)
    if plan.passiv:
        print(t("Passiv: Der Ringspeicher {ordner} hält die letzten {zeitspanne} Fahrzeit – "
                "auch über Neustarts hinweg. Enter sichert die Zeitspanne zusätzlich in eine "
                "eigene Datei. Beim Herunterfahren (SIGTERM) endet die Aufzeichnung sofort, "
                "ohne Abschlussprüfung.", ordner=ringspeicher.ordner(args.csv_ordner, args.sim),
                zeitspanne=ringspeicher.fenster_text(plan.passiv)) + "\n", flush=True)
    if plan.pruefung and not plan.mit_airbag:
        print(t("Der Airbag-Fehlerspeicher wird nicht gelesen (mit --mit-airbag einschließen).")
              + "\n", flush=True)
    future = sitzung.fahrt_starten(plan, args.csv_ordner, sim=args.sim)
    # Herunterfahren (systemd schickt SIGTERM): sofort beenden – die Zeitspanne wird noch
    # zusammengesetzt, der Ringspeicher bleibt ohnehin auf der Platte
    try:
        vorher = signal.signal(signal.SIGTERM, lambda _nr, _rahmen: sitzung.abbrechen())
    except (ValueError, OSError):        # nicht im Haupt-Thread
        vorher = None
    try:
        return _fahrt_warten(future, sitzung)
    except ringspeicher.RingBelegt as exc:
        print("\n" + str(exc))
        return 6
    finally:
        if vorher is not None:
            signal.signal(signal.SIGTERM, vorher)


def _fahrt_warten(future, sitzung: DiagSession) -> int:
    """Enter = Ereignis, Strg+C = beenden (zweimal: sofort) – bis der Fahrtenschreiber fertig
    ist; dann die Zusammenfassung."""

    def enter_lesen():
        for _zeile in sys.stdin:
            if future.done():
                return
            sitzung.fahrt_ereignis(t("Enter"))
            print("  → " + t("Ereignis markiert, lese Fehlerspeicher …"), flush=True)

    threading.Thread(target=enter_lesen, name="enter", daemon=True).start()
    beendet = False
    while True:
        try:
            ergebnis = future.result(timeout=0.5)
            break
        except FutureTimeout:
            continue
        except KeyboardInterrupt:
            if not beendet:
                beendet = True
                sitzung.fahrt_beenden()
                print("\n" + t("Fahrt wird beendet – Abschlussprüfung läuft, Zündung noch an "
                               "lassen. Nochmal Strg+C bricht sofort ab."), flush=True)
            else:
                sitzung.abbrechen()
                print("\n" + t("Abbruch …"), flush=True)
    print("\n" + "\n".join(ergebnis.zeilen))
    if ergebnis.txt_datei:
        print("\n" + t("Zusammenfassung gespeichert: {pfad}", pfad=ergebnis.txt_datei))
    return 0


def _feldtext(verbindung, w) -> str:
    """Wert eines Felds – bei benannten Rohwerten der Gruppe 000 mit Umrechnung."""
    if w.typ == ROHWERT:
        umgerechnet = beschriftung.rohwert_text(verbindung, w.feld, w.b)
        if umgerechnet:
            return f"{w.text} ({umgerechnet})"
    return w.text


def _gruppen_messen(args, sitzung: DiagSession, melder: _Ereignisse, minmax: MinMax) -> int:
    werte_einst = einstellungen.laden()
    neu = not args.ohne_neuverbinden and werte_einst["neu_verbinden"]
    csv_an = werte_einst["csv_automatisch"] if args.csv is None else args.csv
    if csv_an:
        melder.csv = CsvAufzeichnung.neu(args.adresse, args.csv_ordner, sim=args.sim)
        print(t("Aufzeichnung: {pfad}", pfad=melder.csv.pfad))
    if args.dauer:
        print(t("Messung läuft – Enter setzt einen Marker, Strg+C beendet sie."))
        marker = {"nummer": 0}

        def enter_lesen():
            for _zeile in sys.stdin:
                marker["nummer"] += 1
                text = t("Marker {nummer}", nummer=marker["nummer"])
                if melder.csv:
                    melder.csv.ereignis(text)
                log.info(t("Messwertblöcke: %s"), text)
                print("  → " + text, flush=True)

        threading.Thread(target=enter_lesen, name="enter", daemon=True).start()
    sitzung.messung_starten()
    runde = 0
    namen_gezeigt: dict[int, list[str]] = {}
    breiten: dict[int, list[int]] = {}
    try:
        while args.dauer or runde < args.wiederholen:
            runde += 1
            for g in args.gruppen:
                try:
                    werte = sitzung.gruppe_lesen(g, neu_verbinden=neu).result()
                except (NotAvailable, Nak) as exc:
                    print(t("Gruppe {gruppe:03d}:", gruppe=g) + f" {exc}")
                    continue
                for w in werte:
                    minmax.erfassen((g, w.feld), w)
                namen = beschriftung.namen(melder.verbindung, g, werte)
                if g not in namen_gezeigt and any(namen):
                    namen_gezeigt[g] = namen
                    breiten[g] = [max(14, len(beschriftung.anzeige(n))) for n in namen]
                    print("          " + t("Gruppe {gruppe:03d}:", gruppe=g) + " " + " | ".join(
                        f"{beschriftung.anzeige(n) or '–':>{b}s}"
                        for n, b in zip(namen, breiten[g])), flush=True)
                if melder.csv:
                    melder.csv.messwerte(g, werte, namen)
                b = breiten.get(g, [])
                felder = " | ".join(f"{_feldtext(melder.verbindung, w):>{b[i] if i < len(b) else 14}s}"
                                    for i, w in enumerate(werte))
                print(f"{time.strftime('%H:%M:%S')}  "
                      + t("Gruppe {gruppe:03d}:", gruppe=g) + f" {felder}", flush=True)
    except KeyboardInterrupt:
        sitzung.abbrechen()
        print("\n" + t("Messung beendet."))
    finally:
        if melder.csv:
            melder.csv.schliessen()
    print("\n" + t("Min/Max:"))
    for g in args.gruppen:
        for feld in range(1, 11):           # Gruppe 000: zehn Rohwerte
            text = minmax.text((g, feld))
            if text:
                namen = namen_gezeigt.get(g, [])
                name = (beschriftung.anzeige(namen[feld - 1])
                        if feld <= len(namen) and namen[feld - 1] else "")
                print("  " + t("Gruppe {gruppe:03d} Feld {feld}", gruppe=g, feld=feld)
                      + (f" ({name})" if name else "") + f": {text}")
    if melder.csv:
        print("\n" + t("CSV-Datei: {pfad}", pfad=melder.csv.pfad))
    return 0


if __name__ == "__main__":
    sys.exit(main())

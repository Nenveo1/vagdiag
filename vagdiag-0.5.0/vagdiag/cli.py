"""Kommandozeile – für schnelle Tests im Auto und für Protokolle zur Fehlersuche.

Beispiele (jeder Befehl und jede Option hat auch einen englischen Namen,
z. B. „fehler“ = „faults“, „--adresse“ = „--address“):
    python -m vagdiag.cli geraete
    python -m vagdiag.cli kabeltest
    python -m vagdiag.cli --adresse 01 ident
    python -m vagdiag.cli --adresse 01 fehler
    python -m vagdiag.cli --adresse 01 gruppe 4 --dauer --csv    (bis Strg+C, mit CSV)
    python -m vagdiag.cli --adresse 17 gruppensuche
    python -m vagdiag.cli kilometerstand                         (Kombi, Adresse 17)
    python -m vagdiag.cli --adresse 17 anpassung 9               (nur lesen)
    python -m vagdiag.cli --adresse 17 anpassungssuche --bis 99  (nur lesen)
    python -m vagdiag.cli fahrt                                  (Fahrtenschreiber)
    python -m vagdiag.cli --log --adresse 01 ident               (mit Protokolldatei)
    python -m vagdiag.cli --sprache en --adresse 01 fehler       (auf Englisch)
    python -m vagdiag.cli einstellungen --sprache-setzen en --csv-automatisch nein
    python -m vagdiag.cli --sim --adresse 01 gruppe 4 --wiederholen 10
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

from . import (adressen, airbag, beschriftung, einstellungen, ident, protokolldatei,
               sprache)
from .aufzeichnung import CsvAufzeichnung
from .fahrtenschreiber import Besuch, FahrtPlan, _gruppenliste
from .kw1281 import (Abgebrochen, DiagError, Nak, NoResponse, NotAvailable,
                     UnsupportedProtocol, Verbindung)
from .messwerte import MinMax
from .port import (PortError, einrichtungs_hinweis, kabel_oeffnen, list_ftdi_devices,
                   standard_url)
from .session import DiagSession
from .sim import sim_port
from .sprache import t

BAUDS = {"auto": (10400, 9600), "10400": (10400,), "9600": (9600,),
         "4800": (4800,), "1200": (1200,)}

# Befehle: deutscher Name → englischer Name
BEFEHLE = {
    "geraete": "devices", "kabeltest": "cable-test", "ident": "ident", "fehler": "faults",
    "loeschen": "clear", "gruppe": "group", "gruppensuche": "group-scan",
    "anpassung": "adaptation", "anpassungssuche": "adaptation-scan",
    "kilometerstand": "odometer", "fahrt": "drive", "scan": "scan",
    "einstellungen": "settings",
}
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
                      + " | ".join(beschriftung.mit_namen(namen, werte)), flush=True)
            elif gruppe % 25 == 0:
                print(f"  … {gruppe:03d}", flush=True)
        elif art == "anpassung_suche":
            kanal, anpassung = daten
            if anpassung is not None:
                print(f"  {anpassung.text}", flush=True)
            elif kanal % 25 == 0:
                print("  … " + t("Kanal {kanal:02d}", kanal=kanal), flush=True)


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
    ]
    if werte["baudraten"]:
        zeilen.append((t("Gemerkte Baudraten:"), ", ".join(
            f"{k}: {v}" for k, v in sorted(werte["baudraten"].items()))))
    breite = max(len(name) for name, _ in zeilen) + 2
    for name, wert in zeilen:
        print(f"{name:<{breite}}{wert}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m vagdiag.cli",
                                description=t("VAG-Diagnose über KKL-Kabel (KW1281)"))
    p.add_argument(*_namen("--sprache", "--language"), dest="sprache", type=_sprache_code,
                   metavar="de|en", help=t("Sprache für diesen Lauf (Standard: Einstellung)"))
    p.add_argument("--sim", action="store_true", help=t("Simulator statt Kabel"))
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
    gs.add_argument(*_namen("--von", "--from"), dest="von", type=int, default=1, metavar="N")
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
                    metavar="S", help=t("Sekunden zwischen zwei Besuchen beim ABS (0 = nie)"))
    fa.add_argument(*_namen("--besuch", "--visit"), dest="besuch", type=float, metavar="S",
                    help=t("Sekunden je Besuch"))
    fa.add_argument(*_namen("--ohne-pruefung", "--no-check"), dest="ohne_pruefung",
                    action="store_true", help=t("ohne Start- und Abschlussprüfung"))
    _befehl(sub, "scan", help=t("übliche Steuergeräte abfragen"))
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

    def fabrik():
        return sim_port() if args.sim else kabel_oeffnen(args.url, args.reizung)

    if args.adresse is None:
        args.adresse = 0x17 if args.befehl == "kilometerstand" else 0x01
    melder = _Ereignisse(sim=args.sim)
    gemerkt = ({} if args.sim else
               {int(k, 16): v for k, v in einstellungen.laden()["baudraten"].items()})
    sitzung = DiagSession(fabrik, ereignis=melder, baudraten=gemerkt).start()
    if args.mit_airbag:
        sitzung.airbag_freigeben()
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
            for adresse in adressen.ADRESSEN:
                print(f"\n{adressen.text(adresse)} …", flush=True)
                if adresse == airbag.ADRESSE and not args.mit_airbag:
                    print("  " + t("übersprungen – mit --mit-airbag einschließen (Hinweis in "
                                   "der README)"))
                    continue
                try:
                    v = sitzung.verbinden(adresse, bauds).result()
                    print("\n".join("  " + z for z in ident.zeilen(v)))
                    sitzung.trennen().result()
                except NoResponse:
                    print("  " + t("keine Antwort"))
                except DiagError as exc:
                    print(f"  {exc}")
            return 0

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
                if not _frage(frage):
                    print(t("Abgebrochen."))
                    return 0
            rest = sitzung.fehler_loeschen().result()
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
    return plan


def _fahrt(args, sitzung: DiagSession, melder: _Ereignisse) -> int:
    plan = _fahrtplan(args)
    melder.fahrt = True
    print(t("Fahrtenschreiber. Enter markiert ein Ereignis (z. B. Warnlampe an) und liest\n"
            "sofort die Fehlerspeicher von Motor und ABS. Strg+C beendet die Fahrt –\n"
            "danach läuft noch die Abschlussprüfung, Zündung so lange an lassen.") + "\n",
          flush=True)
    if plan.pruefung and not plan.mit_airbag:
        print(t("Der Airbag-Fehlerspeicher wird nicht gelesen (mit --mit-airbag einschließen).")
              + "\n", flush=True)
    future = sitzung.fahrt_starten(plan, args.csv_ordner, sim=args.sim)

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


def _gruppen_messen(args, sitzung: DiagSession, melder: _Ereignisse, minmax: MinMax) -> int:
    werte_einst = einstellungen.laden()
    neu = not args.ohne_neuverbinden and werte_einst["neu_verbinden"]
    csv_an = werte_einst["csv_automatisch"] if args.csv is None else args.csv
    if csv_an:
        melder.csv = CsvAufzeichnung.neu(args.adresse, args.csv_ordner, sim=args.sim)
        print(t("Aufzeichnung: {pfad}", pfad=melder.csv.pfad))
    if args.dauer:
        print(t("Messung läuft – Strg+C beendet sie."))
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
                felder = " | ".join(f"{w.text:>{b[i] if i < len(b) else 14}s}"
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
        for feld in range(1, 5):
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

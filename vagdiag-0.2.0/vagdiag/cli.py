"""Kommandozeile – für schnelle Tests im Auto und für Protokolle zur Fehlersuche.

Beispiele:
    python -m vagdiag.cli geraete
    python -m vagdiag.cli kabeltest
    python -m vagdiag.cli --adresse 01 ident
    python -m vagdiag.cli --adresse 01 fehler
    python -m vagdiag.cli --adresse 01 gruppe 4 --dauer          (bis Strg+C, mit CSV)
    python -m vagdiag.cli --adresse 17 gruppensuche
    python -m vagdiag.cli einstellungen --csv-ordner-setzen ~/Messungen
    python -m vagdiag.cli --sim --adresse 01 gruppe 4 --wiederholen 10
"""

from __future__ import annotations

import argparse
import sys
import time

from . import adressen, einstellungen, protokolldatei
from .aufzeichnung import CsvAufzeichnung
from .kw1281 import (Abgebrochen, DiagError, Nak, NoResponse, NotAvailable,
                     UnsupportedProtocol, Verbindung)
from .messwerte import MinMax
from .port import FtdiPort, PortError, list_ftdi_devices
from .session import DiagSession
from .sim import sim_port

BAUDS = {"auto": (10400, 9600), "10400": (10400,), "9600": (9600,),
         "4800": (4800,), "1200": (1200,)}


def _hex(text: str) -> int:
    return int(text, 16)


def _ja_nein(text: str) -> bool:
    if text.lower() in ("ja", "j", "an", "1", "true"):
        return True
    if text.lower() in ("nein", "n", "aus", "0", "false"):
        return False
    raise argparse.ArgumentTypeError("ja oder nein")


def ident_zeilen(v: Verbindung) -> list[str]:
    zeilen = [
        f"Adresse:       {adressen.text(v.adresse)}",
        f"Protokoll:     {v.protokoll} (Keyword {v.keyword}), {v.baud} Baud, "
        f"Kabel-Echo: {'ja' if v.echo else 'nein'}",
        f"Teilenummer:   {v.teilenummer}",
        f"Bauteil:       {v.bauteil}",
    ]
    if v.codierung is not None:
        zeilen.append(f"Codierung:     {v.codierung:05d}")
        zeilen.append(f"Werkstattcode: {v.werkstattcode:05d}")
    if v.zusatzkennung:
        zeilen.append(f"Zusatzkennung: {v.zusatzkennung}")
    for z in v.zusatzdaten:
        zeilen.append(f"Zusatzdaten:   {z}")
    return zeilen


def _fehler_ausgeben(liste) -> None:
    if not liste:
        print("Kein Fehler gespeichert.")
        return
    print(f"{len(liste)} Fehler gespeichert:")
    for f in liste:
        print("  " + f.zeile())


class _Ereignisse:
    """Meldungen aus dem Diagnose-Thread auf der Konsole (und in der CSV)."""

    def __init__(self):
        self.csv: CsvAufzeichnung | None = None
        self.verbindungen = 0

    def __call__(self, art: str, daten) -> None:
        if art == "baud":
            einstellungen.baud_merken(*daten)
        elif art == "verbunden":
            self.verbindungen += 1
            if self.verbindungen > 1:
                print(f"  … wieder verbunden ({time.strftime('%H:%M:%S')})", flush=True)
                if self.csv:
                    self.csv.ereignis("wieder verbunden")
        elif art == "getrennt" and daten.get("neu_verbinden"):
            print(f"  … Verbindung verloren ({daten['grund']}) – verbinde neu", flush=True)
            if self.csv:
                self.csv.ereignis(f"Verbindung verloren: {daten['grund']}")
        elif art == "neu_verbinden" and daten > 1:
            print(f"  … Neuverbindung, Versuch {daten}", flush=True)
        elif art == "suche":
            gruppe, werte = daten
            if werte is not None:
                print(f"  Gruppe {gruppe:03d}: " + " | ".join(w.text for w in werte), flush=True)
            elif gruppe % 25 == 0:
                print(f"  … {gruppe:03d}", flush=True)


def _einstellungen(args) -> int:
    aenderung = {}
    if args.log_ordner_setzen:
        aenderung["log_ordner"] = args.log_ordner_setzen
    if args.csv_ordner_setzen:
        aenderung["csv_ordner"] = args.csv_ordner_setzen
    if args.csv_automatisch is not None:
        aenderung["csv_automatisch"] = args.csv_automatisch
    if args.neu_verbinden is not None:
        aenderung["neu_verbinden"] = args.neu_verbinden
    werte = einstellungen.speichern(**aenderung) if aenderung else einstellungen.laden()
    print(f"Einstellungsdatei:  {einstellungen.DATEI}")
    print(f"Log-Ordner:         {werte['log_ordner']}")
    print(f"CSV-Ordner:         {werte['csv_ordner']}")
    print(f"CSV automatisch:    {'ja' if werte['csv_automatisch'] else 'nein'}")
    print(f"Neu verbinden:      {'ja' if werte['neu_verbinden'] else 'nein'}")
    if werte["baudraten"]:
        print("Gemerkte Baudraten: " + ", ".join(
            f"{k}: {v}" for k, v in sorted(werte["baudraten"].items())))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m vagdiag.cli",
                                description="VAG-Diagnose über KKL-Kabel (KW1281)")
    p.add_argument("--sim", action="store_true", help="Simulator statt Kabel")
    p.add_argument("--url", default="ftdi:///1", help="pyftdi-URL des Kabels")
    p.add_argument("--baud", choices=BAUDS, default="auto")
    p.add_argument("--reizung", choices=["break", "bitbang"], default="break",
                   help="Art der 5-Baud-Reizung; bitbang als Ausweichweg für Klon-Chips")
    p.add_argument("--adresse", type=_hex, default=0x01,
                   help="Steuergeräte-Adresse hexadezimal (01 Motor, 17 Kombi)")
    p.add_argument("--log", help="feste Protokolldatei für diesen Lauf")
    p.add_argument("--log-ordner", help="Log-Ordner nur für diesen Lauf")
    p.add_argument("--csv-ordner", help="CSV-Ordner nur für diesen Lauf")
    p.add_argument("-v", action="store_true", help="Protokollablauf anzeigen")
    p.add_argument("--bytes", action="store_true", help="auch jedes Byte anzeigen")
    sub = p.add_subparsers(dest="befehl", required=True)
    sub.add_parser("geraete", help="angeschlossene FTDI-Kabel auflisten")
    sub.add_parser("kabeltest", help="Kabel öffnen und Echo prüfen")
    sub.add_parser("ident", help="Steuergerät identifizieren")
    sub.add_parser("fehler", help="Fehlerspeicher lesen")
    lo = sub.add_parser("loeschen", help="Fehlerspeicher löschen")
    lo.add_argument("--ja", action="store_true", help="ohne Rückfrage")
    gr = sub.add_parser("gruppe", help="Messwertgruppen lesen (mit CSV und Min/Max)")
    gr.add_argument("gruppen", type=int, nargs="+")
    wie = gr.add_mutually_exclusive_group()
    wie.add_argument("--wiederholen", type=int, default=1, metavar="N")
    wie.add_argument("--dauer", action="store_true", help="bis Strg+C")
    gr.add_argument("--ohne-csv", action="store_true", help="nicht aufzeichnen")
    gr.add_argument("--ohne-neuverbinden", action="store_true",
                    help="bei Verbindungsabbruch aufhören statt neu zu verbinden")
    gs = sub.add_parser("gruppensuche", help="alle belegten Messwertgruppen finden")
    gs.add_argument("--von", type=int, default=1)
    gs.add_argument("--bis", type=int, default=255)
    sub.add_parser("scan", help="übliche Steuergeräte abfragen")
    es = sub.add_parser("einstellungen", help="Ordner und Optionen anzeigen/ändern")
    es.add_argument("--log-ordner-setzen", metavar="ORDNER")
    es.add_argument("--csv-ordner-setzen", metavar="ORDNER")
    es.add_argument("--csv-automatisch", type=_ja_nein, metavar="ja|nein")
    es.add_argument("--neu-verbinden", type=_ja_nein, metavar="ja|nein")
    args = p.parse_args(argv)

    if args.befehl == "einstellungen":
        return _einstellungen(args)

    datei = protokolldatei.einrichten(args.log, konsole=args.v or args.bytes,
                                      bytes_in_konsole=args.bytes, ordner=args.log_ordner)
    print(f"Protokoll: {datei}")

    if args.befehl == "geraete":
        try:
            geraete = list_ftdi_devices()
        except PortError as exc:
            print(f"Fehler: {exc}")
            return 2
        if not geraete:
            print("Kein FTDI-Kabel gefunden.")
        for url, beschreibung in geraete:
            print(f"  {url}  {beschreibung}")
        return 0

    def fabrik():
        return sim_port() if args.sim else FtdiPort(args.url, args.reizung)

    melder = _Ereignisse()
    gemerkt = {int(k, 16): v for k, v in einstellungen.laden()["baudraten"].items()}
    sitzung = DiagSession(fabrik, ereignis=melder, baudraten=gemerkt).start()
    bauds = BAUDS[args.baud]
    minmax = MinMax()
    try:
        if args.befehl == "kabeltest":
            erg = sitzung.kabeltest().result()
            print(f"Kabel: {erg['geraet']}\nEcho: {'ja' if erg['echo'] else 'nein'}\n{erg['hinweis']}")
            return 0

        if args.befehl == "scan":
            for adresse in adressen.ADRESSEN:
                print(f"\n{adressen.text(adresse)} …", flush=True)
                try:
                    v = sitzung.verbinden(adresse, bauds).result()
                    print("\n".join("  " + z for z in ident_zeilen(v)))
                    sitzung.trennen().result()
                except NoResponse:
                    print("  keine Antwort")
                except DiagError as exc:
                    print(f"  {exc}")
            return 0

        v = sitzung.verbinden(args.adresse, bauds).result()
        print("\n".join(ident_zeilen(v)))
        print()

        if args.befehl == "fehler":
            _fehler_ausgeben(sitzung.fehler_lesen().result())
        elif args.befehl == "loeschen":
            _fehler_ausgeben(sitzung.fehler_lesen().result())
            if not args.ja:
                antwort = input("Fehlerspeicher löschen? Readiness wird dabei "
                                "zurückgesetzt. [j/N] ")
                if antwort.strip().lower() not in ("j", "ja"):
                    print("Abgebrochen.")
                    return 0
            rest = sitzung.fehler_loeschen().result()
            print("Gelöscht.")
            if rest:
                print("Sofort wieder gesetzt:")
                _fehler_ausgeben(rest)
            print("\nFehlerspeicher jetzt:")
            _fehler_ausgeben(sitzung.fehler_lesen().result())
        elif args.befehl == "gruppensuche":
            print(f"Suche Messwertgruppen {args.von:03d}–{args.bis:03d} "
                  "(Strg+C bricht ab) …")
            gefunden = sitzung.gruppen_suchen(args.von, args.bis).result()
            print(f"\n{len(gefunden)} belegte Gruppen: "
                  + ", ".join(f"{g:03d}" for g in gefunden))
        elif args.befehl == "gruppe":
            return _gruppen_messen(args, sitzung, melder, minmax)
        return 0
    except UnsupportedProtocol as exc:
        print(f"\n{exc}")
        print(f"Bitte schick mir die Protokolldatei: {datei}")
        return 3
    except Abgebrochen:
        print("\nAbgebrochen.")
        return 130
    except DiagError as exc:
        print(f"\nFehler: {exc}")
        print(f"Protokolldatei für die Fehlersuche: {datei}")
        return 1
    except PortError as exc:
        print(f"\nFehler: {exc}")
        return 2
    except KeyboardInterrupt:
        sitzung.abbrechen()
        print("\nAbgebrochen.")
        return 130
    finally:
        sitzung.schliessen()


def _gruppen_messen(args, sitzung: DiagSession, melder: _Ereignisse, minmax: MinMax) -> int:
    neu = not args.ohne_neuverbinden and einstellungen.laden()["neu_verbinden"]
    if not args.ohne_csv and einstellungen.laden()["csv_automatisch"]:
        melder.csv = CsvAufzeichnung.neu(args.adresse, args.csv_ordner)
        print(f"Aufzeichnung: {melder.csv.pfad}")
    if args.dauer:
        print("Messung läuft – Strg+C beendet sie.")
    sitzung.messung_starten()
    runde = 0
    try:
        while args.dauer or runde < args.wiederholen:
            runde += 1
            for g in args.gruppen:
                try:
                    werte = sitzung.gruppe_lesen(g, neu_verbinden=neu).result()
                except (NotAvailable, Nak) as exc:
                    print(f"Gruppe {g:03d}: {exc}")
                    continue
                for w in werte:
                    minmax.erfassen((g, w.feld), w)
                if melder.csv:
                    melder.csv.messwerte(g, werte)
                felder = " | ".join(f"{w.text:>14s}" for w in werte)
                print(f"{time.strftime('%H:%M:%S')}  Gruppe {g:03d}: {felder}", flush=True)
    except KeyboardInterrupt:
        sitzung.abbrechen()
        print("\nMessung beendet.")
    finally:
        if melder.csv:
            melder.csv.schliessen()
    print("\nMin/Max:")
    for g in args.gruppen:
        for feld in range(1, 5):
            text = minmax.text((g, feld))
            if text:
                print(f"  Gruppe {g:03d} Feld {feld}: {text}")
    if melder.csv:
        print(f"\nCSV-Datei: {melder.csv.pfad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

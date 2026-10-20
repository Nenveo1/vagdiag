"""Kommandozeile – für schnelle Tests im Auto und für Protokolle zur Fehlersuche.

Beispiele:
    python -m vagdiag.cli geraete
    python -m vagdiag.cli kabeltest
    python -m vagdiag.cli --adresse 01 ident
    python -m vagdiag.cli --adresse 01 fehler
    python -m vagdiag.cli --adresse 01 gruppe 4 --wiederholen 20
    python -m vagdiag.cli --adresse 17 gruppe 1 2
    python -m vagdiag.cli scan
    python -m vagdiag.cli --sim --adresse 01 fehler      (ohne Auto)
"""

from __future__ import annotations

import argparse
import sys
import time

from . import adressen, protokolldatei
from .kline import KLine
from .kw1281 import (KW1281, DiagError, Nak, NoResponse, NotAvailable, Timing,
                     UnsupportedProtocol, Verbindung)
from .port import FtdiPort, PortError, list_ftdi_devices
from .sim import sim_port

BAUDS = {"auto": (10400, 9600), "10400": (10400,), "9600": (9600,),
         "4800": (4800,), "1200": (1200,)}


def _port(args):
    return sim_port() if args.sim else FtdiPort(args.url, args.reizung)


def _hex(text: str) -> int:
    return int(text, 16)


def _ident_ausgeben(v: Verbindung) -> None:
    print(f"Adresse:      {adressen.text(v.adresse)}")
    print(f"Protokoll:    {v.protokoll} (Keyword {v.keyword}), {v.baud} Baud, "
          f"Kabel-Echo: {'ja' if v.echo else 'nein'}")
    print(f"Teilenummer:  {v.teilenummer}")
    print(f"Bauteil:      {v.bauteil}")
    for z in v.zusatzdaten:
        print(f"Zusatzdaten:  {z}   (Codierung/Werkstattcode, noch roh)")


def _fehler_ausgeben(liste) -> None:
    if not liste:
        print("Kein Fehler gespeichert.")
        return
    print(f"{len(liste)} Fehler gespeichert:")
    for f in liste:
        print("  " + f.zeile())


def _gruppe_ausgeben(gruppe: int, werte) -> None:
    felder = "   ".join(f"{w.text:>16s}" for w in werte)
    print(f"Gruppe {gruppe:03d}: {felder}")


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
    p.add_argument("--log", help="Protokolldatei (Standard: ~/.local/share/vagdiag/logs/)")
    p.add_argument("-v", action="store_true", help="Protokollablauf anzeigen")
    p.add_argument("--bytes", action="store_true", help="auch jedes Byte anzeigen")
    sub = p.add_subparsers(dest="befehl", required=True)
    sub.add_parser("geraete", help="angeschlossene FTDI-Kabel auflisten")
    sub.add_parser("kabeltest", help="Kabel öffnen und Echo prüfen")
    sub.add_parser("ident", help="Steuergerät identifizieren")
    sub.add_parser("fehler", help="Fehlerspeicher lesen")
    lo = sub.add_parser("loeschen", help="Fehlerspeicher löschen")
    lo.add_argument("--ja", action="store_true", help="ohne Rückfrage")
    gr = sub.add_parser("gruppe", help="Messwertgruppen lesen")
    gr.add_argument("gruppen", type=int, nargs="+")
    gr.add_argument("--wiederholen", type=int, default=1, metavar="N")
    sub.add_parser("scan", help="übliche Steuergeräte abfragen")
    args = p.parse_args(argv)

    datei = protokolldatei.einrichten(args.log, konsole=args.v or args.bytes,
                                      bytes_in_konsole=args.bytes)
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

    try:
        port = _port(args)
    except PortError as exc:
        print(f"Fehler: {exc}")
        return 2

    kline = KLine(port)
    proto = KW1281(kline, Timing())
    try:
        if args.befehl == "kabeltest":
            print(f"Kabel geöffnet: {port.description}")
            port.purge_rx()
            port.write(b"\x55")
            echo = port.read(8, 0.1)
            if b"\x55" in echo:
                print("Echo empfangen – Kabel hat Strom (OBD-Pin 16) und hört die K-Leitung.")
            else:
                print("Kein Echo. Ohne 12 V an OBD-Pin 16 normal; im Auto mit Zündung an "
                      "deutet das auf ein Kabelproblem (oder ein Kabel ohne Echo).")
            return 0

        if args.befehl == "scan":
            for adresse in adressen.ADRESSEN:
                print(f"\n{adressen.text(adresse)} …", flush=True)
                try:
                    v = proto.connect(adresse, BAUDS[args.baud])
                    _ident_ausgeben(v)
                    proto.trennen()
                except NoResponse:
                    print("  keine Antwort")
                except UnsupportedProtocol as exc:
                    print(f"  {exc}")
                except DiagError as exc:
                    print(f"  Fehler: {exc}")
                time.sleep(0.6)
            return 0

        v = proto.connect(args.adresse, BAUDS[args.baud])
        _ident_ausgeben(v)
        print()
        if args.befehl == "fehler":
            _fehler_ausgeben(proto.fehler_lesen())
        elif args.befehl == "loeschen":
            vorher = proto.fehler_lesen()
            _fehler_ausgeben(vorher)
            if not args.ja:
                antwort = input("Fehlerspeicher löschen? Readiness wird dabei "
                                "zurückgesetzt. [j/N] ")
                if antwort.strip().lower() not in ("j", "ja"):
                    print("Abgebrochen.")
                    return 0
            rest = proto.fehler_loeschen()
            print("Gelöscht.")
            if rest:
                print("Sofort wieder gesetzt:")
                _fehler_ausgeben(rest)
            print("\nFehlerspeicher jetzt:")
            _fehler_ausgeben(proto.fehler_lesen())
        elif args.befehl == "gruppe":
            for _ in range(args.wiederholen):
                for g in args.gruppen:
                    try:
                        _gruppe_ausgeben(g, proto.gruppe_lesen(g))
                    except (NotAvailable, Nak) as exc:
                        print(f"Gruppe {g:03d}: {exc}")
            print("\nRohwerte der letzten Abfrage:")
            for g in args.gruppen:
                try:
                    for w in proto.gruppe_lesen(g):
                        print(f"  Gruppe {g:03d} Feld {w.feld}: {w.roh:24s} → {w.text}")
                except (NotAvailable, Nak):
                    pass
        return 0
    except UnsupportedProtocol as exc:
        print(f"\n{exc}")
        print(f"Bitte schick mir die Protokolldatei: {datei}")
        return 3
    except DiagError as exc:
        print(f"\nFehler: {exc}")
        print(f"Protokolldatei für die Fehlersuche: {datei}")
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130
    finally:
        proto.trennen()
        port.close()


if __name__ == "__main__":
    sys.exit(main())

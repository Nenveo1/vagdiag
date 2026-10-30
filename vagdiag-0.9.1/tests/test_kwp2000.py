# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""KWP2000 (ISO 14230) gegen den Byte-Simulator.  Start: python -m unittest -v

Geprüft wird der ganze Weg: 5-Baud-Reizung oder Fast-Init, Kopfadresse und
Diagnosesitzung finden, Kennung, Fehlerspeicher, Messwertblöcke, Störungen,
Tester present – und dass vagdiag dabei nur lesende Dienste schickt.
"""

import contextlib
import csv
import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from vagdiag import cli, einstellungen, ident, sprache
from vagdiag.airbag import AirbagFremd, AirbagRisiko
from vagdiag.fahrtenschreiber import FahrtPlan
from vagdiag.kline import KLine
from vagdiag.kw1281 import (KW1281, NotAvailable, ProtocolError, Stoerung, Timing,
                            UnsupportedProtocol)
from vagdiag.kwp2000 import (Kwp2000, gruppe_ohne_echo, ist_auffuellung, kennung_auswerten,
                             keyword, werkstattcode_auswerten)
from vagdiag.port import PortError
from vagdiag.session import DiagSession
from vagdiag.sim import SimKwpEcu, sim_port

# Zeitwächter großzügig: Der Simulator läuft hier nicht in Echtzeit, und Testrechner hängen
# manchmal selbst (virtuelle Maschinen bis 50 ms). Den Wächter mit den echten Fristen prüft
# test_sicherheit.Zeitwaechter.
SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0,
                 kwp_beruhigen=0.0, kwp_p2=0.2, kwp_p2_start=0.1, kwp_p2_lang=0.5,
                 kwp_p3=0.0, kwp_p4=0.0, kwp_keepalive=0.05,
                 byte_frist=0.5, kwp_p4_frist=0.5)

# Dienste, die vagdiag bei KWP2000 überhaupt senden darf – alle lesend außer 14
# (Fehlerspeicher löschen, nur nach Rückfrage) und 82 (Verbindung beenden)
ERLAUBT = {0x1A, 0x10, 0x18, 0x14, 0x21, 0x3E, 0x82, 0x81}


def kwp_port(**geraete):
    """Simulator mit KWP2000-Motor; geraete ersetzt/ergänzt Steuergeräte."""
    port = sim_port(echtzeit=False, fahrprofil=False, kwp2000_motor=True)
    for adresse, ecu in geraete.items():
        port.steuergeraete[int(adresse[1:], 16)] = ecu
    return port


def verbinden(adresse=0x01, port=None, fast_init=False):
    port = port or kwp_port()
    proto = KW1281(KLine(port), SCHNELL)
    return port, proto, proto.connect(adresse, (10400,), fast_init=fast_init)


def geraet(**art) -> SimKwpEcu:
    return SimKwpEcu(0x01, "SIM906032TST", "TEST KWP2000", gruppen={1: lambda: [(1, 200, 21)]},
                     **art)


class Bausteine(unittest.TestCase):
    def test_werkstattcode_wie_kw1281test(self):
        # Beispiel aus kw1281test: WSC 45678, Importeur 345, Gerät 987654
        self.assertEqual(werkstattcode_auswerten(bytes.fromhex("78 90 32 B2 B2 6E")),
                         (45678, 345, 987654))

    def test_keyword(self):
        self.assertEqual(keyword(0xEF, 0x8F), 2031)
        self.assertEqual(keyword(0x6B, 0x8F), 2027)

    def test_kennung_im_vag_aufbau(self):
        roh = (b"\x9b" + b"038906019FT " + b"3311" + b"\x03" + (71).to_bytes(3, "big")
               + bytes.fromhex("78 90 32 B2 B2 6E") + b"1,9l R4 EDC  G000SG  ")
        info = kennung_auswerten(roh)
        self.assertEqual(info["teil"], "038906019FT")
        self.assertEqual(info["software"], "3311")
        self.assertEqual((info["codier"], info["wsc"], info["importeur"], info["geraet"]),
                         (71, 45678, 345, 987654))
        self.assertEqual(info["beschreibung"], "1,9l R4 EDC G000SG")

    def test_kennung_in_anderem_aufbau(self):
        info = kennung_auswerten(b"\x9b" + b"1K0907379  " + b"\x00\x01" + b"ESP  MK60")
        self.assertEqual(info["teil"], "1K0907379")
        self.assertIn("ESP", info["beschreibung"])

    def test_nachricht_mit_pruefsumme(self):
        kwp = Kwp2000(KLine(kwp_port()), SCHNELL, 0x01, 2031, 0xEF, 10400)
        self.assertEqual(kwp.kopf, 0x10)                      # EDC16-Regel
        self.assertEqual(kwp._nachricht(b"\x1a\x9b").hex(" ").upper(), "82 10 F1 1A 9B 38")
        kwp.mit_adressen = False
        self.assertEqual(kwp._nachricht(b"\x3e").hex(" ").upper(), "01 3E 3F")

    def test_nachrichten_im_strom_finden(self):
        strom = bytes.fromhex("81 10 F1 81 03 00 83 F1 10 C1 EF 8F C3 FF")
        gefunden = Kwp2000._nachrichten_suchen(strom)
        self.assertIn((0xF1, 0x10, bytes.fromhex("C1 EF 8F")), gefunden)

    def test_gruppennummer_vor_den_feldern(self):
        h = bytes.fromhex
        # Regelfall: Echo der Gruppe, danach vollständige Felder
        self.assertEqual(gruppe_ohne_echo(h("05 01 C8 15"), 5), h("01 C8 15"))
        # ohne Echo, Felder zu drei Bytes (so behandelt es kw1281test)
        self.assertEqual(gruppe_ohne_echo(h("01 C8 15 05 0A 83"), 5), h("01 C8 15 05 0A 83"))
        # Echo und ein Text mit Länge 0: sechs Bytes – nach der alten Längenregel „ohne Echo“
        self.assertEqual(gruppe_ohne_echo(h("07 5F 00 01 C8 15"), 7), h("5F 00 01 C8 15"))
        self.assertEqual(gruppe_ohne_echo(h("07 A0 01 00 7B 11 01 01 C8 15"), 7),
                         h("A0 01 00 7B 11 01 01 C8 15"))
        # Echo, dann ein Typ ohne bekanntes Format: Echo weg, der Rest wird roh gezeigt
        self.assertEqual(gruppe_ohne_echo(h("05 01 C8 15 00 00 00"), 5), h("01 C8 15 00 00 00"))
        # Antwort einer anderen Gruppe
        self.assertIsNone(gruppe_ohne_echo(h("04 01 C8 15"), 5))
        # „ohne Echo“ nur mit gewöhnlichen Feldern – sonst gilt die Längenregel (hier: Echo
        # einer anderen Gruppe, 5F = 95)
        self.assertIsNone(gruppe_ohne_echo(h("5F 02 41 42 01 C8 15"), 5))
        self.assertEqual(gruppe_ohne_echo(h("05"), 5), b"")

    def test_auffuellung(self):
        from vagdiag.messwerte import gruppe_auswerten
        werte = gruppe_auswerten(bytes.fromhex("25 00 00 25 00 01 5F 01 00"))
        self.assertEqual([ist_auffuellung(w) for w in werte], [True, False, False])


class Verbindungsaufbau(unittest.TestCase):
    def test_motor_mit_5_baud_reizung(self):
        port, proto, v = verbinden()
        self.assertTrue(proto.ist_kwp2000)
        self.assertEqual((v.protokoll, v.keyword, v.baud), ("KWP2000", 2031, 10400))
        self.assertEqual((v.kopf, v.sitzung, v.fast_init), (0x10, 0x89, False))
        self.assertEqual(v.teilenummer, "SIM906032KWP")
        self.assertEqual(v.bauteil, "ME7.5 KWP2000 SIMULATION 0001")
        self.assertEqual((v.codierung, v.werkstattcode), (71, 12345))
        self.assertIs(v.echo, True)
        zeilen = "\n".join(ident.zeilen(v))
        self.assertIn("Protokoll:     KWP2000 (Keyword 2031)", zeilen)
        self.assertIn("Codierung:     0000071", zeilen)
        self.assertIn("Importeur 123, Gerätenummer 45678", zeilen)
        self.assertIn("Kopfadresse 10, Diagnosesitzung 89", zeilen)
        # Kennung zuerst (geht ohne Sitzung), dann die Sitzung
        self.assertEqual(port.steuergeraete[0x01].anfragen[:2], [b"\x1a\x9b", b"\x10\x89"])

    def test_ohne_echo(self):
        port = sim_port(echo=False, echtzeit=False, fahrprofil=False, kwp2000_motor=True)
        _, proto, v = verbinden(port=port)
        self.assertIs(v.echo, False)
        self.assertEqual(len(proto.fehler_lesen()), 2)

    def test_geraet_mit_eigener_adresse(self):
        _, proto, v = verbinden(0x56)
        self.assertEqual((v.keyword, v.kopf), (2027, 0x56))
        self.assertEqual(v.teilenummer, "SIMKWP2000")
        self.assertEqual(proto.fehler_lesen()[0].code, 771)

    def test_kopfadresse_wird_gesucht(self):
        # Keyword 2027 an 01 hieße eigentlich Kopfadresse 01 – dieses Gerät hört aber nur auf 10
        port = kwp_port(a01=geraet(keybytes=(0x6B, 0x8F), kopf=0x10))
        _, proto, v = verbinden(port=port)
        self.assertEqual(v.kopf, 0x10)
        self.assertEqual(len(proto.gruppe_lesen(1)), 1)

    def test_kopf_ohne_adressen(self):
        # KB1 57: Bit 2 (Kopf ohne Adressen) gesetzt, Bit 3 (mit Adressen) nicht
        port = kwp_port(a01=geraet(keybytes=(0x57, 0x8F)))
        _, proto, v = verbinden(port=port)
        self.assertIsNone(v.kopf)
        self.assertIn("ohne Adressen", "\n".join(v.zusatzdaten))
        self.assertEqual(len(proto.gruppe_lesen(1)), 1)

    def test_sitzung_89_ohne_antwort(self):
        port = kwp_port(a01=geraet(stumme_sitzungen=(0x89,)))
        _, _, v = verbinden(port=port)
        self.assertEqual(v.sitzung, 0x81)

    def test_nie_die_programmiersitzung(self):
        """Nimmt ein Gerät nur Sitzung 85 an (Programmiersitzung zum Flashen), wird sie
        trotzdem nie angefragt – es geht ohne Sitzung weiter."""
        port = kwp_port(a01=geraet(sitzungen=(0x85,)))
        _, proto, v = verbinden(port=port)
        self.assertIsNone(v.sitzung)
        self.assertEqual(len(proto.gruppe_lesen(1)), 1)
        gesendet = [bytes(d) for d in port.steuergeraete[0x01].anfragen]
        self.assertIn(bytes([0x10, 0x89]), gesendet)
        self.assertNotIn(bytes([0x10, 0x85]), gesendet)

    def test_keine_sitzung_geht_trotzdem(self):
        port = kwp_port(a01=geraet(sitzungen=()))
        _, proto, v = verbinden(port=port)
        self.assertIsNone(v.sitzung)
        self.assertEqual(len(proto.gruppe_lesen(1)), 1)

    def test_kwp2000_ohne_antwort(self):
        # Handshake klappt, aber keine Kopfadresse passt
        port = kwp_port(a01=geraet(keybytes=(0x6B, 0x8F), kopf=0x77))
        with self.assertRaises(UnsupportedProtocol) as fall:
            verbinden(port=port)
        self.assertEqual(fall.exception.protocol, "KWP2000")
        self.assertIn("KWP2000 (Keyword 2027)", str(fall.exception))

    def test_lange_antwort_mit_laengenbyte(self):
        # mehr als 63 Bytes: Formatbyte 80 und eigenes Längenbyte
        lang = "LANGE BESCHREIBUNG " * 4
        port = kwp_port(a01=SimKwpEcu(0x01, "SIM906032LNG", lang, keybytes=(0xEF, 0x8F),
                                      kopf=0x10))
        _, _, v = verbinden(port=port)
        self.assertEqual(v.beschreibung, lang.strip())
        self.assertGreater(len(v.kennung_roh), 63)

    def test_trennen(self):
        port, proto, _ = verbinden()
        proto.trennen()
        self.assertFalse(proto.verbunden)
        self.assertFalse(proto.ist_kwp2000)
        self.assertEqual(port.steuergeraete[0x01].anfragen[-1], b"\x82")
        self.assertEqual(port.steuergeraete[0x01]._zustand, "aus")


class FastInit(unittest.TestCase):
    def test_motor_per_fast_init(self):
        port, proto, v = verbinden(fast_init=True)
        self.assertTrue(v.fast_init)
        self.assertEqual(port.fast_inits, 1)
        self.assertEqual(port.steuergeraete[0x01].anfragen[:3],
                         [b"\x81", b"\x1a\x9b", b"\x10\x89"])
        self.assertIn("Fast-Init", "\n".join(v.zusatzdaten))
        self.assertEqual(len(proto.gruppe_lesen(4)), 4)

    def test_rest_des_pulses_vor_dem_echo(self):
        # Beim KKL-Kabel kann der Low-Puls noch als 00 im Empfang landen
        port = kwp_port()
        original = port.fast_init_puls

        def mit_rest():
            original()
            port.ausgeben(b"\x00")
        port.fast_init_puls = mit_rest
        _, proto, v = verbinden(port=port, fast_init=True)
        self.assertTrue(v.fast_init)
        self.assertIs(v.echo, True)
        self.assertEqual(len(proto.fehler_lesen()), 2)

    def test_ohne_antwort_weiter_mit_5_baud(self):
        # KW1281-Motor kennt keinen Fast-Init: drei Versuche, dann normale Reizung
        port = sim_port(echtzeit=False, fahrprofil=False)
        _, proto, v = verbinden(port=port, fast_init=True)
        self.assertEqual(port.fast_inits, 3)
        self.assertEqual(v.protokoll, "KW1281")
        self.assertFalse(proto.ist_kwp2000)

    def test_sitzung_merkt_sich_fehlenden_fast_init(self):
        port = sim_port(echtzeit=False, fahrprofil=False)        # KW1281-Motor
        s = DiagSession(lambda: port, SCHNELL, keepalive=0.05).start()
        try:
            s.fast_init = True
            s.verbinden(0x01, (10400,)).result(10)
            self.assertEqual(port.fast_inits, 3)
            s.verbinden(0x01, (10400,)).result(10)
            self.assertEqual(port.fast_inits, 3, "zweites Mal ohne Fast-Init")
            s.fast_init = False
            s.fast_init = True                    # Einstellung geändert: wieder probieren
            s.verbinden(0x01, (10400,)).result(10)
            self.assertEqual(port.fast_inits, 6)
        finally:
            s.schliessen()

    def test_nur_beim_motor(self):
        port, _, v = verbinden(0x56, fast_init=True)
        self.assertEqual(port.fast_inits, 0)
        self.assertFalse(v.fast_init)

    def test_interface_ohne_fast_init(self):
        port = kwp_port()

        def kein_fast_init():
            raise PortError("kein Fast-Init")
        port.fast_init_puls = kein_fast_init
        _, _, v = verbinden(port=port, fast_init=True)
        self.assertFalse(v.fast_init)          # 5-Baud-Reizung hat übernommen
        self.assertEqual(v.protokoll, "KWP2000")


class Funktionen(unittest.TestCase):
    def setUp(self):
        self.port, self.proto, self.v = verbinden()
        self.ecu = self.port.steuergeraete[0x01]

    def test_fehlerspeicher(self):
        fehler = self.proto.fehler_lesen()
        self.assertEqual([f.code for f in fehler], [16486, 16684])
        self.assertTrue(fehler[0].sporadisch)
        self.assertEqual(fehler[0].fehlerart, 0x23)

    def test_fehlerspeicher_ohne_anzahl(self):
        self.ecu.fehler_mit_anzahl = False
        self.assertEqual(len(self.proto.fehler_lesen()), 2)
        self.ecu.fehler = []
        self.assertEqual(self.proto.fehler_lesen(), [])

    def test_loeschen_mit_antwort_folgt(self):
        self.assertEqual(self.proto.fehler_loeschen(), [])
        self.assertEqual(self.ecu.geloescht, 1)
        self.assertEqual(self.proto.fehler_lesen(), [])

    def test_messwertblock_ohne_auffuellung(self):
        werte = self.proto.gruppe_lesen(4)
        self.assertEqual([w.einheit for w in werte], ["/min", "V", "°C", "°C"])
        self.assertEqual(len(self.proto.gruppe_lesen(5)), 4)

    def test_messwertblock_mit_langen_feldern(self):
        # A0 (sechs Bytes), Text mit Länge, ein gewöhnliches Feld – aufgefüllt auf acht Felder
        self.ecu.gruppen[9] = lambda: [(0xA0, 1, 0, 123, 0x11, 1), (0x5F, 2, 0x4F, 0x4B),
                                       (1, 200, 21)]
        werte = self.proto.gruppe_lesen(9)
        self.assertEqual([w.text for w in werte], ["12,3 V", "OK", "840 /min"])
        # Typ ohne bekanntes Format: ab dort roh, die Auffüllung bleibt im Rest sichtbar
        self.ecu.gruppen[9] = lambda: [(1, 200, 21), (0xC8, 1, 2)]
        werte = self.proto.gruppe_lesen(9)
        self.assertEqual(werte[0].text, "840 /min")
        self.assertTrue(werte[1].text.startswith("roh: C8 01 02 25 00 00"))

    def test_fehlende_gruppe(self):
        with self.assertRaises(NotAvailable):
            self.proto.gruppe_lesen(77)
        with self.assertRaises(NotAvailable):
            self.proto.gruppe_lesen(0)
        self.assertTrue(self.proto.verbunden)

    def test_anpassung_lesen(self):
        # VAG-Anpassungsroutine: beginnen, Kanal wählen, lesen, beenden – nichts schreibt
        vorher = len(self.ecu.anfragen)
        anpassung = self.proto.anpassung_lesen(1)
        self.assertEqual((anpassung.kanal, anpassung.wert), (1, 128))
        self.assertEqual(self.ecu.anfragen[vorher:], [
            bytes.fromhex("31 B8 01 03"), bytes.fromhex("31 B9 01 03 01"),
            bytes.fromhex("31 BA 01 03"), bytes.fromhex("32 B8 01 03")])
        with self.assertRaises(NotAvailable):
            self.proto.anpassung_lesen(7)                # nicht belegt
        self.assertEqual(self.ecu.anfragen[-1], bytes.fromhex("32 B8 01 03"))
        with self.assertRaises(ValueError):
            self.proto.anpassung_lesen(0)                # Kanal 00 nie
        self.assertEqual(self.ecu.geschrieben, [])
        self.ecu.anpassungen.clear()                     # Steuergerät ohne Anpassung
        with self.assertRaises(NotAvailable) as fall:
            self.proto.anpassung_lesen(1)
        self.assertIn("KWP2000", str(fall.exception))
        self.assertTrue(self.proto.verbunden)

    def test_tester_present_nur_nach_ruhe(self):
        self.proto._kwp._letzte_antwort = time.monotonic()
        anzahl = len(self.ecu.anfragen)
        self.proto.keep_alive()
        self.assertEqual(len(self.ecu.anfragen), anzahl, "kurz nach einer Antwort: nichts")
        time.sleep(0.1)
        self.proto.keep_alive()
        self.assertEqual(self.ecu.anfragen[-1], b"\x3e")

    def test_ohne_tester_present_haelt_die_sitzung(self):
        self.ecu.tester_present = False
        time.sleep(0.1)
        self.proto.keep_alive()                 # 7F 3E 11 → auf Sitzung umstellen
        time.sleep(0.1)
        self.proto.keep_alive()
        self.assertEqual(self.ecu.anfragen[-2:], [b"\x3e", b"\x10\x89"])
        self.assertTrue(self.proto.verbunden)

    def test_steuergeraet_beschaeftigt(self):
        self.ecu.naechste_antwort("beschaeftigt")
        self.assertEqual(len(self.proto.gruppe_lesen(1)), 4)
        self.assertEqual(self.ecu.anfragen[-2:], [b"\x21\x01", b"\x21\x01"])

    def test_keine_antwort_beendet_die_verbindung(self):
        self.ecu.naechste_antwort("stumm")
        with self.assertRaises(ProtocolError):
            self.proto.fehler_lesen()
        self.assertFalse(self.proto.verbunden, "keine Antwort = Verbindung weg")

    def test_kein_kw1281_block(self):
        with self.assertRaises(NotAvailable):
            self.proto.austausch(0x09)


class Stoerungen(unittest.TestCase):
    """Gestörte Antworten werden verworfen; die Sitzung fragt erneut."""

    def sitzung(self, port=None):
        port = port or kwp_port()
        s = DiagSession(lambda: port, SCHNELL, keepalive=0.05).start()
        s.verbinden(0x01, (10400,)).result(10)
        return s, port.steuergeraete[0x01]

    def test_pruefsumme_falsch(self):
        s, ecu = self.sitzung()
        try:
            ecu.naechste_antwort("pruefsumme")
            self.assertEqual(len(s.gruppe_lesen(1).result(5)), 4)
            self.assertTrue(s.verbunden)
        finally:
            s.schliessen()

    def test_abgeschnitten(self):
        s, ecu = self.sitzung()
        try:
            ecu.naechste_antwort("abgeschnitten")
            self.assertEqual(len(s.gruppe_lesen(2).result(5)), 4)
            self.assertTrue(s.verbunden)
        finally:
            s.schliessen()

    def test_fremde_quelladresse_wird_angenommen(self):
        s, ecu = self.sitzung()
        try:
            ecu.naechste_antwort("fremd")
            self.assertEqual(len(s.gruppe_lesen(3).result(5)), 4)
        finally:
            s.schliessen()

    def test_direkt_ohne_sitzung(self):
        _, proto, _ = verbinden()
        proto._kwp.kl.port.steuergeraete[0x01].naechste_antwort("pruefsumme")
        with self.assertRaises(Stoerung):
            proto.gruppe_lesen(1)
        self.assertTrue(proto.verbunden)
        self.assertEqual(len(proto.gruppe_lesen(1)), 4)

    def test_neu_verbinden_waehrend_der_messung(self):
        s, ecu = self.sitzung()
        try:
            ecu.ausfall_nach(2)
            s.messung_starten()
            for _ in range(5):
                self.assertEqual(len(s.gruppe_lesen(1, neu_verbinden=True).result(15)), 4)
            self.assertGreaterEqual(ecu.anfragen.count(b"\x1a\x9b"), 2, "neu verbunden")
        finally:
            s.schliessen()

    def test_tester_present_haelt_die_verbindung(self):
        port = kwp_port()
        port.steuergeraete[0x01].p3_max = 0.3
        s, ecu = self.sitzung(port)
        try:
            time.sleep(1.0)                     # länger als P3 – ohne 3E wäre es weg
            self.assertEqual(len(s.gruppe_lesen(1).result(5)), 4)
            self.assertIn(b"\x3e", ecu.anfragen)
        finally:
            s.schliessen()

    def test_ohne_tester_present_legt_das_steuergeraet_auf(self):
        port = kwp_port()
        ecu = port.steuergeraete[0x01]
        ecu.p3_max = 0.2
        _, proto, _ = verbinden(port=port)
        time.sleep(0.4)
        with self.assertRaises(ProtocolError):
            proto.gruppe_lesen(1)


class Sitzung(unittest.TestCase):
    def test_ablauf_und_nur_lesende_dienste(self):
        port = kwp_port()
        s = DiagSession(lambda: port, SCHNELL, keepalive=0.05).start()
        try:
            v = s.verbinden(0x01, (10400,)).result(10)
            self.assertEqual(v.protokoll, "KWP2000")
            self.assertEqual(len(s.fehler_lesen().result(5)), 2)
            self.assertEqual(sorted(s.gruppen_suchen(1, 8).result(20)), [1, 2, 3, 4, 5])
            self.assertEqual(s.anpassung_lesen(1).result(5).wert, 128)
            self.assertEqual(sorted(s.anpassungen_suchen(1, 10).result(10)), [1])
            time.sleep(0.3)                     # Tester present
            s.fehler_loeschen().result(5)
            v = s.verbinden(0x01, (10400,), fast_init=True).result(10)
            self.assertTrue(v.fast_init)
            s.trennen().result(5)
        finally:
            s.schliessen()
        anfragen = port.steuergeraete[0x01].anfragen
        dienste = {a[0] for a in anfragen}
        lesend = ERLAUBT | {0x31, 0x32}             # 31/32: nur die lesende Anpassungsroutine
        self.assertTrue(dienste <= lesend, f"unerwartete Dienste: {dienste - lesend}")
        routinen = [a for a in anfragen if a[0] in (0x31, 0x32)]
        self.assertTrue(routinen and all(a[2:4] == b"\x01\x03" and a[1] in (0xB8, 0xB9, 0xBA)
                                         and (a[1] != 0xB9 or len(a) == 5) for a in routinen))
        self.assertEqual(port.steuergeraete[0x01].geschrieben, [])
        self.assertIn(0x3E, dienste)

    def test_airbag_mit_firmwarefehler_nur_kennung(self):
        port = kwp_port(a15=SimKwpEcu(0x15, "6Q0909605A", "AIRBAG VW61", baud=10400,
                                      fehler=[(65535, 0x23)]))
        s = DiagSession(lambda: port, SCHNELL, keepalive=0.05).start()
        s.airbag_freigeben()
        try:
            with self.assertRaises(AirbagRisiko):
                s.verbinden(0x15, (10400,)).result(10)
            self.assertFalse(s.verbunden)
        finally:
            s.schliessen()
        # nur die Kennung, dann sofort Ende – keine Sitzung, kein Fehlerspeicher
        self.assertEqual(port.steuergeraete[0x15].anfragen, [b"\x1a\x9b", b"\x82"])

    def test_airbag_unter_fremder_adresse(self):
        # ohne Freigabe: unter 17 meldet sich (z. B. nach verfälschter Reizung) ein Airbag
        port = kwp_port(a17=SimKwpEcu(0x17, "1J0909609", "AIRBAG VW3", baud=10400))
        s = DiagSession(lambda: port, SCHNELL, keepalive=0.05).start()
        try:
            with self.assertRaises(AirbagFremd):
                s.verbinden(0x17, (10400,)).result(10)
            self.assertFalse(s.verbunden)
        finally:
            s.schliessen()
        self.assertEqual(port.steuergeraete[0x17].anfragen, [b"\x1a\x9b", b"\x82"])

    def test_fahrtenschreiber_mit_kwp2000_motor(self):
        with tempfile.TemporaryDirectory() as ordner:
            s = DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=True, zeitfaktor=20.0,
                                             kwp2000_motor=True),
                            SCHNELL, keepalive=0.05).start()
            try:
                plan = FahrtPlan(besuche=[], stand_dauer=0.1, volle_runde_nach=0.1)
                future = s.fahrt_starten(plan, ordner, sim=True)
                time.sleep(3.5)                 # Startprüfung (4 Steuergeräte), dann Fahrt
                s.fahrt_beenden()
                z = future.result(30)
            finally:
                s.schliessen()
            text = "\n".join(z.zeilen)
            self.assertIn("01 2 Fehler", text)
            with open(z.csv_datei, encoding="utf-8-sig") as datei:
                zeilen = list(csv.reader(datei, delimiter=";"))
            motor = [r for r in zeilen[1:] if r[2] == "01" and r[3]]
            self.assertGreater(len(motor), 5)


class Kommandozeile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._alt = einstellungen.DATEI
        einstellungen._zuruecksetzen_fuer_tests(Path(self._tmp.name) / "e.json")
        self._sim = cli.sim_port
        cli.sim_port = lambda **art: sim_port(echtzeit=False, fahrprofil=False, **art)

    def tearDown(self):
        cli.sim_port = self._sim
        einstellungen._zuruecksetzen_fuer_tests(self._alt)
        sprache.setzen("de")
        self._tmp.cleanup()

    def lauf(self, *argv) -> tuple[int, str]:
        ausgabe = io.StringIO()
        with contextlib.redirect_stdout(ausgabe), contextlib.redirect_stderr(ausgabe):
            try:
                code = cli.main(list(argv))
            except SystemExit as exc:
                code = exc.code
        return code, ausgabe.getvalue()

    def test_fehler_vom_kwp2000_motor(self):
        code, text = self.lauf("--sim-kwp2000", "--adresse", "01", "fehler")
        self.assertEqual(code, 0, text)
        self.assertIn("KWP2000 (Keyword 2031)", text)
        self.assertIn("2 Fehler gespeichert:", text)

    def test_fast_init_und_gruppe(self):
        code, text = self.lauf("--sim-kwp2000", "--fast-init", "gruppe", "1", "2")
        self.assertEqual(code, 0, text)
        self.assertIn("Fast-Init", text)
        self.assertIn("Gruppe 002:", text)

    def test_fast_init_als_einstellung(self):
        code, text = self.lauf("einstellungen", "--fast-init-setzen", "ja")
        self.assertEqual(code, 0, text)
        self.assertIn("Fast-Init beim Motor:", text)
        self.assertTrue(einstellungen.laden()["fast_init"])
        code, text = self.lauf("--sim-kwp2000", "ident")
        self.assertIn("Fast-Init", text)

    def test_englisch(self):
        code, text = self.lauf("--language", "en", "--sim-kwp2000", "--fast-init", "ident")
        self.assertEqual(code, 0, text)
        self.assertIn("header address 10, diagnostic session 89, fast init", text)
        self.assertIn("Importer 123, equipment number 45678", text)

    def test_scan_alle_adressen(self):
        with mock.patch("vagdiag.adressen.alle", return_value=[0x16, 0x17, 0x33]):
            code, text = self.lauf("--sim", "scan", "--alle")
        self.assertEqual(code, 0, text)
        self.assertIn("17 – Schalttafeleinsatz (Kombi) …", text)
        self.assertIn("33 – OBD-II (allgemein): übersprungen – OBD-II-Adresse", text)
        self.assertIn("Keine Antwort (1): 16", text)
        self.assertNotIn("16 – Lenkradelektronik …", text)

    def test_anpassung_bei_kwp2000(self):
        code, text = self.lauf("--sim-kwp2000", "anpassung", "1", "2")
        self.assertEqual(code, 0, text)
        self.assertIn("Kanal 01: 128 (hex 0080)", text)
        self.assertIn("Kanal 02: Anpassungskanal 02 ist nicht belegt", text)


if __name__ == "__main__":
    unittest.main()

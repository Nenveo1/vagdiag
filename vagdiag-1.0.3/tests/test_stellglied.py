# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Stellglieddiagnose (KW1281 und KWP2000), KWP2000-Anpassung und Service-Reset bei
KWP2000. Start: python -m unittest -v"""

import json
import tempfile
import time
import unittest
from pathlib import Path

from vagdiag import stellglied
from vagdiag.experte import Nichts
from vagdiag.kline import KLine
from vagdiag.kw1281 import (KW1281, Freigabe, Nak, NotAvailable, SchreibenGesperrt, Timing,
                            kwp_werkstattcode)
from vagdiag.kwp2000 import Kwp2000
from vagdiag.session import DiagSession
from vagdiag.sim import KOMBI_STELLGLIEDER, SIM_STELLGLIEDER, SimKwpEcu, sim_port

# Zeitwächter großzügig: Der Simulator läuft hier nicht in Echtzeit, und Testrechner hängen
# manchmal selbst (virtuelle Maschinen bis 50 ms). Den Wächter mit den echten Fristen prüft
# test_sicherheit.Zeitwaechter.
SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0,
                 trenn_pause=0.05, wechsel_pause=0.05, kwp_beruhigen=0.0, kwp_p3=0.0,
                 kwp_p4=0.0, kwp_keepalive=0.1,
                 byte_frist=0.5, kwp_p4_frist=0.5)


def sitzung(motor_aus=False, **sim):
    def fabrik():
        port = sim_port(echtzeit=False, fahrprofil=False, **sim)
        port.fahrzeug.motor_aus = motor_aus
        return port
    s = DiagSession(fabrik, SCHNELL, keepalive=0.05).start()
    s._port_oeffnen()
    return s


def durchlaufen(s, ereignisse, weiter=20, pause=0.05, ende_nach=None, **start):
    """Stellglieddiagnose starten und „weiter“ geben, bis sie endet (oder nach ende_nach
    Stellgliedern beenden). Zurück: Ergebnis und gemeldete Stellglieder."""
    future = s.stellglieddiagnose(**start)
    gemeldet = 0
    for _ in range(weiter * 40):
        if future.done():
            break
        schritte = [d for a, d in ereignisse if a == "stellglied"]
        if len(schritte) > gemeldet:
            gemeldet = len(schritte)
            if ende_nach is not None and gemeldet >= ende_nach:
                s.stellglied_beenden()
            else:
                s.stellglied_weiter()
        time.sleep(pause)
    return future.result(10), [d for a, d in ereignisse if a == "stellglied"]


class Sperre(unittest.TestCase):
    """Die Stellglieddiagnose geht nur mit Freigabe – bei Bremsen, Airbag, Wegfahrsperre,
    Lenkung und Niveauregulierung nur mit bestätigter Warnung für genau diese Art."""

    def setUp(self):
        self.port = sim_port(echtzeit=False, fahrprofil=False)
        self.proto = KW1281(KLine(self.port), SCHNELL)

    def test_kw1281_nur_mit_freigabe(self):
        self.proto.connect(0x17, (10400,))
        kombi = self.port.steuergeraete[0x17]
        with self.assertRaises(SchreibenGesperrt):
            self.proto.stellglied_starten()                 # kein Expertenmodus
        self.proto.experte = True
        with self.assertRaises(SchreibenGesperrt):
            self.proto.stellglied_starten()                 # ohne Freigabe
        with self.proto.schreiben_freigeben(grundeinstellung=[60], anpassung=[(2, 0)]):
            with self.assertRaises(SchreibenGesperrt):
                self.proto.stellglied_starten()             # andere Freigabe
        self.assertEqual(kombi.geschrieben, [])
        with self.proto.schreiben_freigeben(stellglied=True):
            with self.assertRaises(SchreibenGesperrt):
                self.proto.austausch(0x04, b"\x01")          # nur mit dem Datenbyte 00
            erstes = self.proto.stellglied_starten()
        self.assertEqual(erstes.code, 0x0296)
        self.assertEqual(erstes.name, "Drehzahlmesser")
        self.assertEqual(kombi.geschrieben, [(0x04, b"\x00")])
        with self.assertRaises(SchreibenGesperrt):
            self.proto.stellglied_weiter()                  # Freigabe vorbei

    def test_gefaehrliche_nur_nach_bestaetigter_warnung(self):
        self.proto.experte = True
        for adresse, art in ((0x03, "bremsen"), (0x25, "wegfahrsperre")):
            with self.subTest(adresse=hex(adresse)):
                self.proto.connect(adresse, (9600,))
                geraet = self.port.steuergeraete[adresse]
                # ohne Bestätigung und mit der Bestätigung für eine andere Art: keine Freigabe
                for falsch in (None, "airbag", "lenkung", ""):
                    with self.assertRaises(SchreibenGesperrt) as fall:
                        with self.proto.schreiben_freigeben(stellglied=True, gefahr=falsch):
                            self.proto.stellglied_starten()
                    self.assertIn("bestätigter Warnung", str(fall.exception))
                self.assertIn("bestätigter Warnung", KW1281.stellglied_gesperrt(adresse))
                self.assertIsNone(KW1281.stellglied_gesperrt(adresse, None, art))
                # Grundeinstellung und Anpassung bleiben dort gesperrt – auch mit Bestätigung
                for frei in ({"grundeinstellung": [1]}, {"anpassung": [(1, 0)]}):
                    with self.assertRaises(SchreibenGesperrt) as fall:
                        with self.proto.schreiben_freigeben(gefahr=art, **frei):
                            pass
                    self.assertIn("gesperrt", str(fall.exception))
                self.assertEqual(geraet.geschrieben, [])
                # mit Bestätigung geht genau der Stellglied-Block hinaus
                with self.proto.schreiben_freigeben(stellglied=True, gefahr=art):
                    try:
                        self.proto.stellglied_starten()
                    except Nak:
                        pass            # die Wegfahrsperre des Simulators kennt keine
                self.assertEqual(geraet.geschrieben, [(0x04, b"\x00")])
                self.proto.trennen()
        self.assertEqual(set(stellglied.GEFAHR), {0x03, 0x15, 0x23, 0x25, 0x34, 0x44, 0x53})
        self.assertEqual(set(stellglied.SCHAEDEN), set(stellglied.GEFAHR))

    def test_freigabe_mit_bestaetigung_gilt_nicht_fuer_ein_anderes_geraet(self):
        # Freigabe am ABS bestätigt, dann meldet sich unter 03 plötzlich ein Airbag: gesperrt
        self.proto.experte = True
        self.proto.connect(0x03, (9600,))
        geraet = self.port.steuergeraete[0x03]
        with self.proto.schreiben_freigeben(stellglied=True, gefahr="bremsen"):
            self.proto.verbindung.bloecke[0].daten = b"1J0909609 Q "      # jetzt ein Airbag
            with self.assertRaises(SchreibenGesperrt) as fall:
                self.proto.stellglied_starten()
        self.assertIn("passt nicht zu dieser Adresse", str(fall.exception))
        self.assertEqual(geraet.geschrieben, [])

    def test_kwp2000_nur_genau_diese_anfragen(self):
        stand = {"experte": False, "freigabe": None}
        kwp = Kwp2000(KLine(self.port), SCHNELL, 0x17, 2027, 0x6B, 10400)
        kwp.schutz = lambda: (stand["experte"], stand["freigabe"])
        lesend = ["31 B8 01 03", "31 B9 01 03 05", "31 BA 01 03", "32 B8 01 03", "32 B8 01 02"]
        for anfrage in lesend:
            with self.subTest(anfrage=anfrage):
                self.assertIsNone(kwp._schreibschutz(bytes.fromhex(anfrage)))
        gesperrt = ["31 B9 01 03 00",               # Kanal 00
                    "31 B9 01 03 00 00",            # Wert testen ohne Freigabe
                    "31 BB 01 03 00 00 00 00 00 00 00 00",
                    "31 BB 01 03 00 00",            # falsche Länge
                    "31 B9 01 03 01 02 03", "31 B8 00 00", "31 B8 00 3C", "31 01 02",
                    "31 B8 01 02", "31 B9 01 02", "31 BA 01 02",   # Stellglieder ohne Freigabe
                    "32 01", "33 B8 01 03", "27 01", "3B 9A 00", "2E 01 00", "30 01 01",
                    "23 00 00 00 10", "34 00", "11 01", "10 85"]
        for anfrage in gesperrt:
            with self.subTest(anfrage=anfrage):
                with self.assertRaises(SchreibenGesperrt):
                    kwp._schreibschutz(bytes.fromhex(anfrage))
        freigabe = Freigabe(anpassung=frozenset({(2, 0)}), stellglied=True, adresse=0x17)
        kwp._anp_kanal = 2
        for experte, gilt_fuer in ((False, 0x17), (True, 0x01), (True, None)):
            # ohne Expertenmodus oder für ein anderes Steuergerät gilt die Freigabe nicht
            with self.subTest(experte=experte, adresse=gilt_fuer):
                stand.update(experte=experte, freigabe=Freigabe(
                    anpassung=freigabe.anpassung, stellglied=True, adresse=gilt_fuer))
                for anfrage in ("31 B9 01 03 00 00", "31 B9 01 02"):
                    with self.assertRaises(SchreibenGesperrt):
                        kwp._schreibschutz(bytes.fromhex(anfrage))
        stand.update(experte=True, freigabe=freigabe)
        kwp._anp_kanal = None
        with self.assertRaises(SchreibenGesperrt):
            kwp._schreibschutz(bytes.fromhex("31 B9 01 03 00 00"))     # kein Kanal gewählt
        kwp._anp_kanal = 2
        self.assertEqual(kwp._schreibschutz(bytes.fromhex("31 B9 01 03 00 00")), "schreiben")
        self.assertEqual(kwp._schreibschutz(bytes.fromhex("31 BB 01 03 00 00 01 02 03 04 05 06")),
                         "schreiben")
        with self.assertRaises(SchreibenGesperrt):
            kwp._schreibschutz(bytes.fromhex("31 B9 01 03 00 01"))     # anderer Wert
        kwp._anp_kanal = 9
        with self.assertRaises(SchreibenGesperrt):                     # Kilometerstand
            kwp._schreibschutz(bytes.fromhex("31 B9 01 03 00 00"))
        self.assertEqual(kwp._schreibschutz(bytes.fromhex("31 B9 01 02")), "stellglied")
        # Bremsen: nur mit bestätigter Warnung für Bremsen und nur, wenn die Kennung passt
        kwp.adresse = 0x03
        abs_kennung = (0x03, "6X0907379 B", "ABS 30 IE CAN V004")
        for gefahr, kennung in ((None, abs_kennung), ("airbag", abs_kennung),
                                ("bremsen", (0x03, "1J0909609 Q", "AIRBAG VW3 SG"))):
            with self.subTest(gefahr=gefahr, kennung=kennung):
                stand.update(freigabe=Freigabe(stellglied=True, adresse=0x03, gefahr=gefahr,
                                               kennung=kennung))
                for anfrage in ("31 B8 01 02", "31 B9 01 02", "31 BA 01 02"):
                    with self.assertRaises(SchreibenGesperrt):
                        kwp._schreibschutz(bytes.fromhex(anfrage))
        stand.update(freigabe=Freigabe(stellglied=True, adresse=0x03, gefahr="bremsen",
                                       kennung=abs_kennung))
        self.assertEqual(kwp._schreibschutz(bytes.fromhex("31 B8 01 02")), "stellglied")
        stand.update(freigabe=Freigabe(stellglied=False, adresse=0x03, gefahr="bremsen",
                                       kennung=abs_kennung))
        with self.assertRaises(SchreibenGesperrt):                     # ohne Freigabe
            kwp._schreibschutz(bytes.fromhex("31 B8 01 02"))
        # Anpassung dort nie – auch nicht mit Bestätigung und passender Freigabe
        stand.update(freigabe=Freigabe(anpassung=frozenset({(2, 0)}), stellglied=True,
                                       adresse=0x03, gefahr="bremsen", kennung=abs_kennung))
        kwp._anp_kanal = 2
        with self.assertRaises(SchreibenGesperrt):
            kwp._schreibschutz(bytes.fromhex("31 B9 01 03 00 00"))

    def test_kwp2000_merkt_den_gewaehlten_kanal(self):
        kwp = Kwp2000(KLine(self.port), SCHNELL, 0x17, 2027, 0x6B, 10400)
        kwp.senden(bytes.fromhex("31 B9 01 03 02"))
        self.assertEqual(kwp._anp_kanal, 2)
        kwp.senden(bytes.fromhex("32 B8 01 03"))
        self.assertIsNone(kwp._anp_kanal)


class Kw1281Ablauf(unittest.TestCase):
    def test_kombi_bis_zum_ende(self):
        ereignisse = []
        s = sitzung()
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            s.experte = True
            s.verbinden(0x17).result(5)
            ergebnis, schritte = durchlaufen(s, ereignisse)
            kombi = s._port.steuergeraete[0x17]
            verbunden = s.verbunden
        finally:
            s.schliessen()
        self.assertEqual(ergebnis.grund, "ende")
        self.assertEqual([x.code for x in ergebnis.schritte], KOMBI_STELLGLIEDER[:-1])
        self.assertEqual([d["schritt"] for d in schritte], [1, 2, 3, 4, 5, 6])
        self.assertTrue(ergebnis.wieder_verbunden and verbunden)
        self.assertIsNone(kombi.stellglied_aktiv)
        self.assertEqual(kombi.geschrieben, [(0x04, b"\x00")] * 7)
        # danach: Ende der Verbindung (06) und neu verbunden
        titel = [t for t, _ in kombi.anfragen]
        self.assertIn(0x06, titel[titel.index(0x04):])

    def test_beenden_mitten_drin(self):
        ereignisse = []
        s = sitzung()
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            s.experte = True
            s.verbinden(0x17).result(5)
            ergebnis, _ = durchlaufen(s, ereignisse, ende_nach=2)
            kombi = s._port.steuergeraete[0x17]
        finally:
            s.schliessen()
        self.assertEqual(ergebnis.grund, "beendet")
        self.assertEqual(len(ergebnis.schritte), 2)
        self.assertIsNone(kombi.stellglied_aktiv, "Verbindungsende beendet das Ansteuern")
        # Das Ende kommt vom Endeblock 06 – nicht erst vom Neuverbinden: nach dem letzten
        # Stellgliedblock nur Keep-Alive (09), dann 06
        titel = [t for t, _ in kombi.anfragen]
        letzte = len(titel) - 1 - titel[::-1].index(0x04)
        rest = titel[letzte + 1:]
        self.assertIn(0x06, rest)
        self.assertEqual(set(rest[:rest.index(0x06)]) - {0x09}, set())
        self.assertEqual(titel.count(0x04), 2)

    def test_abbrechen_beendet_ohne_neu_zu_verbinden(self):
        ereignisse = []
        s = sitzung()
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            s.experte = True
            s.verbinden(0x17).result(5)
            future = s.stellglieddiagnose()
            time.sleep(0.3)
            s.abbrechen()
            ergebnis = future.result(10)
            kombi = s._port.steuergeraete[0x17]
            self.assertFalse(s.verbunden)
        finally:
            s.schliessen()
        self.assertEqual((ergebnis.grund, ergebnis.wieder_verbunden), ("abgebrochen", False))
        self.assertIsNone(kombi.stellglied_aktiv)

    def test_motor_nur_wenn_er_steht(self):
        s = sitzung()                                # Motor läuft
        try:
            s.experte = True
            s.verbinden(0x01).result(5)
            pruefung = s.stellglied_pruefen().result(5)
            with self.assertRaises(Nichts):
                s.stellglieddiagnose().result(10)
            motor = s._port.steuergeraete[0x01]
        finally:
            s.schliessen()
        self.assertEqual([b.ok for b in pruefung.bedingungen], [False])
        self.assertEqual(motor.geschrieben, [])
        ereignisse = []
        s = sitzung(motor_aus=True)
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            s.experte = True
            s.verbinden(0x01).result(5)
            ergebnis, _ = durchlaufen(s, ereignisse)
        finally:
            s.schliessen()
        self.assertEqual([x.code for x in ergebnis.schritte], list(SIM_STELLGLIEDER))
        self.assertEqual(ergebnis.schritte[0].name, "Kraftstoffpumpe (Simulator)")
        self.assertEqual(ergebnis.grund, "ende")          # ACK nach dem letzten

    def test_ohne_drehzahl_nur_mit_bestaetigung(self):
        s = sitzung(motor_aus=True)
        try:
            motor = s._port.steuergeraete[0x01]
            del motor.gruppen[1], motor.gruppen[4]
            s.experte = True
            s.verbinden(0x01).result(5)
            with self.assertRaises(Nichts):
                s.stellglieddiagnose().result(10)
            self.assertEqual(motor.geschrieben, [])
            future = s.stellglieddiagnose(ohne_pruefung_ok=True)
            time.sleep(0.3)
            s.stellglied_beenden()
            ergebnis = future.result(10)
        finally:
            s.schliessen()
        self.assertEqual(ergebnis.grund, "beendet")

    def test_ohne_expertenmodus_und_ohne_bestaetigung(self):
        s = sitzung()
        try:
            s.verbinden(0x17).result(5)
            with self.assertRaises(SchreibenGesperrt):
                s.stellglieddiagnose().result(10)
            s.experte = True
            s.verbinden(0x03).result(5)
            pruefung = s.stellglied_pruefen().result(5)
            self.assertEqual(pruefung.gefahr.art, "bremsen")
            self.assertIn("Rückförderpumpe", pruefung.gefahr.schaeden)
            self.assertEqual([b.ok for b in pruefung.bedingungen], [True])   # Räder stehen
            for falsch in (None, "airbag", "fahrwerk"):
                with self.assertRaises(Nichts) as fall:
                    s.stellglieddiagnose(gefahr_bestaetigt=falsch).result(10)
                self.assertIn("nicht bestätigt", str(fall.exception))
            geschrieben = [g.geschrieben for g in s._port.steuergeraete.values()
                           if hasattr(g, "geschrieben")]
        finally:
            s.schliessen()
        self.assertFalse(any(geschrieben))

    def test_abs_nach_bestaetigung(self):
        ereignisse = []
        s = sitzung()
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            s.experte = True
            s.verbinden(0x03).result(5)
            with self.assertLogs("vagdiag.proto", "WARNING") as protokoll:
                ergebnis, schritte = durchlaufen(s, ereignisse, gefahr_bestaetigt="bremsen")
            abs_geraet = s._port.steuergeraete[0x03]
            gemerkt = stellglied.liste_laden("SIM907379", "ABS SIMULATION V004", sim=True)
        finally:
            s.schliessen()
        self.assertEqual(ergebnis.grund, "ende")
        self.assertEqual([x.code for x in ergebnis.schritte], [0xF0C1, 0xF0C2, 0xF0C3])
        self.assertEqual(len(schritte), 3)
        self.assertEqual(abs_geraet.geschrieben, [(0x04, b"\x00")] * 4)
        self.assertEqual(gemerkt.codes, [0xF0C1, 0xF0C2, 0xF0C3])
        self.assertTrue(gemerkt.vollstaendig)
        start = [z for z in protokoll.output if "Stellglieddiagnose 03 startet" in z]
        self.assertEqual(len(start), 1)
        self.assertTrue(start[0].endswith("– Warnung (Bremsen) bestätigt"), start[0])

    def test_airbag_und_wegfahrsperre(self):
        s = sitzung()
        try:
            s.experte = True
            from vagdiag import airbag
            with self.assertRaises(airbag.AirbagGesperrt):
                s.verbinden(0x15).result(5)                 # ohne Freigabe keine Verbindung
            s.airbag_freigeben()
            for adresse, art in ((0x15, "airbag"), (0x25, "wegfahrsperre")):
                with self.subTest(adresse=hex(adresse)):
                    s.verbinden(adresse).result(5)
                    geraet = s._port.steuergeraete[adresse]
                    pruefung = s.stellglied_pruefen().result(5)
                    self.assertEqual(pruefung.gefahr.art, art)
                    with self.assertRaises(Nichts):
                        s.stellglieddiagnose().result(10)
                    self.assertEqual(geraet.geschrieben, [])
                    # bestätigt: der Simulator kennt dort keine Stellglieder und lehnt ab
                    with self.assertLogs("vagdiag.proto", "WARNING") as protokoll:
                        with self.assertRaises(Nak):
                            s.stellglieddiagnose(gefahr_bestaetigt=art).result(10)
                    self.assertEqual(geraet.geschrieben, [(0x04, b"\x00")])
                    zeilen = "\n".join(protokoll.output)
                    self.assertIn(f"Stellglieddiagnose {adresse:02X} nach 0 Schritten nicht "
                                  "fortgesetzt", zeilen)
                    self.assertIn("bestätigt", zeilen)
                    self.assertTrue(s.verbunden, "danach wieder verbunden")
        finally:
            s.schliessen()

    def test_schreibsperre_prueft_die_bestaetigung_selbst(self):
        """Fiele die Prüfung in experte.py weg, hielte die Schreibsperre im Protokoll trotzdem
        an: Sie bekommt die Bestätigung des Benutzers, nicht die Art aus der Prüfung."""
        from unittest import mock
        from vagdiag import experte
        s = sitzung()
        try:
            s.experte = True
            s.verbinden(0x03).result(5)
            with mock.patch.object(experte, "_bestaetigung_pruefen", lambda *a: None):
                for falsch in (None, "airbag"):
                    with self.assertRaises(SchreibenGesperrt) as fall:
                        s.stellglieddiagnose(gefahr_bestaetigt=falsch).result(10)
                    self.assertIn("bestätigter Warnung", str(fall.exception))
            geschrieben = s._port.steuergeraete[0x03].geschrieben
        finally:
            s.schliessen()
        self.assertEqual(geschrieben, [])

    def test_abs_nur_wenn_alle_raeder_stehen(self):
        s = sitzung()
        try:
            s.experte = True
            s.verbinden(0x03).result(5)
            fz = s._port.fahrzeug
            fz.fahrprofil, fz.t0 = True, time.monotonic() - 60   # Landstraße, 100 km/h
            pruefung = s.stellglied_pruefen().result(5)
            self.assertIs(pruefung.bedingungen[0].ok, False)
            self.assertIn("100", pruefung.bedingungen[0].wert)
            with self.assertRaises(Nichts) as fall:
                s.stellglieddiagnose(gefahr_bestaetigt="bremsen").result(10)
            self.assertIn("Räder", str(fall.exception))
            abs_geraet = s._port.steuergeraete[0x03]
        finally:
            s.schliessen()
        self.assertEqual(abs_geraet.geschrieben, [])

    def test_abgelehnt(self):
        s = sitzung()
        try:
            s._port.steuergeraete[0x17].stellglieder = None     # kennt keine
            s.experte = True
            s.verbinden(0x17).result(5)
            with self.assertLogs("vagdiag.proto", "WARNING") as protokoll:
                with self.assertRaises(Nak):
                    s.stellglieddiagnose().result(10)
            self.assertTrue(s.verbunden, "danach wieder verbunden")
            self.assertTrue(any("Stellglieddiagnose 17 nach 0 Schritten nicht fortgesetzt" in z
                                for z in protokoll.output), protokoll.output)
            self.assertFalse(any("Warnung (" in z for z in protokoll.output))
        finally:
            s.schliessen()


class Kwp2000Ablauf(unittest.TestCase):
    def test_kombi_experimentell(self):
        ereignisse = []
        s = sitzung(kwp2000_kombi=True)
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            s.experte = True
            s.verbinden(0x17).result(5)
            ergebnis, schritte = durchlaufen(s, ereignisse, weiter=30)
            kombi = s._port.steuergeraete[0x17]
        finally:
            s.schliessen()
        self.assertEqual(ergebnis.grund, "ende")
        self.assertTrue(ergebnis.kwp2000)
        codes = list(dict.fromkeys(x.code for x in ergebnis.schritte))
        self.assertEqual(codes, KOMBI_STELLGLIEDER[:-1])
        # jedes Stellglied zweimal: angezeigt, dann angesteuert
        self.assertEqual([d["gleich"] for d in schritte][:4], [False, True, False, True])
        self.assertIsNone(kombi.stellglied_aktiv)
        start = kombi.anfragen.index(bytes.fromhex("31 B8 01 02"))
        self.assertIn(bytes.fromhex("32 B8 01 02"), kombi.anfragen[start:])
        self.assertTrue(set(kombi.geschrieben) <= {bytes.fromhex("31 B9 01 02")})

    def test_haelt_wach_mit_statusabfrage(self):
        ereignisse = []
        s = sitzung(kwp2000_kombi=True)
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            s.experte = True
            s.verbinden(0x17).result(5)
            future = s.stellglieddiagnose()
            time.sleep(0.6)                           # länger als kwp_keepalive
            kombi = s._port.steuergeraete[0x17]
            anfragen = list(kombi.anfragen)
            s.stellglied_beenden()
            future.result(10)
        finally:
            s.schliessen()
        ab_start = anfragen[anfragen.index(bytes.fromhex("31 B8 01 02")):]
        self.assertGreater(ab_start.count(bytes.fromhex("31 BA 01 02")), 3)
        self.assertNotIn(b"\x3e", ab_start)

    def test_motor_laeuft(self):
        s = sitzung(kwp2000_motor=True)
        try:
            s.experte = True
            s.verbinden(0x01).result(10)
            with self.assertRaises(Nichts):
                s.stellglieddiagnose().result(10)
        finally:
            s.schliessen()

    def test_geraet_ohne_stellglieddiagnose(self):
        s = sitzung()
        try:
            s.experte = True
            s.verbinden(0x56).result(5)
            with self.assertRaises(NotAvailable):
                s.stellglieddiagnose().result(10)
        finally:
            s.schliessen()


class DieselNamen(unittest.TestCase):
    """Die Namen aus den EDC15/EDC16-Mitschnitten gelten nur an Dieselsteuergeräten – dieselbe
    Nummer bedeutet woanders etwas anderes."""

    def test_nur_an_edc(self):
        self.assertTrue(stellglied.ist_diesel("038906019FN", "1,9l R4 EDC  SG  2510"))
        self.assertTrue(stellglied.ist_diesel("03G906016", "R4 2,0L EDC16"))
        self.assertFalse(stellglied.ist_diesel("6K0906032M", "ME7.5.10"))
        self.assertFalse(stellglied.ist_diesel("", ""))
        self.assertEqual(stellglied.name(0x0243, diesel=True),
                         "Magnetventil Ladedruckbegrenzung (N75)")
        self.assertEqual(stellglied.name(0x0243), "Klopfregelung Zylinder 3")
        self.assertEqual(stellglied.Stellglied(0x04F2, diesel=True).name,
                         "Relais Glühkerzen (J52)")
        self.assertNotEqual(stellglied.Stellglied(0x04F2).name, "Relais Glühkerzen (J52)")
        # Kombi-Namen und „Ende“ gelten überall
        self.assertEqual(stellglied.Stellglied(0x0296).name, "Drehzahlmesser")
        self.assertEqual(stellglied.Stellglied(0x04AB, diesel=True).name, "Ende")

    def test_gemerkte_liste_eines_diesels(self):
        stellglied._SIM_LISTEN.clear()
        try:
            stellglied.liste_merken(0x01, "038906019FN", "1,9l R4 EDC G000SG", [0x0243],
                                    True, sim=True)
            liste = stellglied.liste_laden("038906019FN", "1,9l R4 EDC G000SG", sim=True)
            self.assertTrue(liste.diesel)
            self.assertEqual(liste.stellglieder[0].name, "Magnetventil Ladedruckbegrenzung (N75)")
            stellglied.liste_merken(0x01, "036906034", "ME7.5", [0x0243], True, sim=True)
            liste = stellglied.liste_laden("036906034", "ME7.5", sim=True)
            self.assertEqual(liste.stellglieder[0].name, "Klopfregelung Zylinder 3")
        finally:
            stellglied._SIM_LISTEN.clear()

    def test_kwp2000_diesel_meldet_diesel_namen(self):
        def fabrik():
            port = sim_port(echtzeit=False, fahrprofil=False)
            port.fahrzeug.motor_aus = True
            port.steuergeraete[0x01] = SimKwpEcu(
                0x01, "038906019FN", "1,9l R4 EDC  G000SG", software="2510",
                keybytes=(0xEF, 0x8F), kopf=0x10, stellglieder=[0x0243, 0x04F2])
            return port
        ereignisse = []
        s = DiagSession(fabrik, SCHNELL, keepalive=0.05).start()
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            s._port_oeffnen()
            s.experte = True
            s.verbinden(0x01, (10400,)).result(10)
            ergebnis, _ = durchlaufen(s, ereignisse, weiter=20, ohne_pruefung_ok=True)
        finally:
            s.schliessen()
        namen = list(dict.fromkeys(x.name for x in ergebnis.schritte))
        self.assertEqual(namen, ["Magnetventil Ladedruckbegrenzung (N75)",
                                 "Relais Glühkerzen (J52)"])


class Kwp2000Anpassung(unittest.TestCase):
    def test_lesen_mit_messwert_und_zugriffsschutz(self):
        s = sitzung()
        try:
            s.verbinden(0x56).result(5)
            self.assertEqual(s.anpassung_lesen(5).result(5).text,
                             "Kanal 05: 1380 (hex 0564) – 13,79 V")
            with self.assertRaises(Nak) as fall:
                s.anpassung_lesen(3).result(5)
            self.assertIn("Anmeldung", str(fall.exception))
            with self.assertRaises(NotAvailable):
                s.anpassung_lesen(2).result(5)
            self.assertEqual(sorted(s.anpassungen_suchen(1, 9).result(20)), [1, 5])
            geraet = s._port.steuergeraete[0x56]
        finally:
            s.schliessen()
        self.assertEqual(geraet.geschrieben, [])

    def test_service_reset(self):
        with tempfile.TemporaryDirectory() as ordner:
            s = sitzung(kwp2000_kombi=True)
            try:
                s.experte = True
                v = s.verbinden(0x17).result(5)
                alt = s.service_lesen().result(5)
                kombi = s._port.steuergeraete[0x17]
                vorher = len(kombi.anfragen)
                ergebnis = s.service_zuruecksetzen(alt.wert, ordner=Path(ordner)).result(10)
                anfragen = kombi.anfragen[vorher:]
            finally:
                s.schliessen()
            sicherung = json.loads(ergebnis.sicherung.read_text(encoding="utf-8"))
        wsc = kwp_werkstattcode(v)
        self.assertEqual(len(wsc), 6)
        self.assertEqual((ergebnis.alt, ergebnis.neu, kombi.anpassungen[2]), (3, 0, 0))
        self.assertEqual(sicherung["alter_wert"], 3)
        self.assertEqual(kombi.geschrieben, [bytes.fromhex("31 B9 01 03 00 00"),
                                             bytes.fromhex("31 BB 01 03 00 00") + wsc])
        schreiben = anfragen.index(bytes.fromhex("31 B9 01 03 00 00"))
        self.assertEqual(anfragen[schreiben - 2:schreiben + 5], [
            bytes.fromhex("31 B8 01 03"), bytes.fromhex("31 B9 01 03 02"),
            bytes.fromhex("31 B9 01 03 00 00"), bytes.fromhex("31 BA 01 03"),
            bytes.fromhex("31 BB 01 03 00 00") + wsc, bytes.fromhex("31 BA 01 03"),
            bytes.fromhex("32 B8 01 03")])

    def test_kein_speichern_wenn_test_abgelehnt(self):
        s = sitzung(kwp2000_kombi=True)
        try:
            s.experte = True
            s.verbinden(0x17).result(5)
            kombi = s._port.steuergeraete[0x17]
            kombi.anpassung_erlaubt[2] = lambda wert: False
            alt = s.service_lesen().result(5)
            with tempfile.TemporaryDirectory() as ordner:
                with self.assertRaises(Nak):
                    s.service_zuruecksetzen(alt.wert, ordner=Path(ordner)).result(10)
            self.assertEqual(kombi.anpassungen[2], 3)
            self.assertEqual(kombi.geschrieben, [bytes.fromhex("31 B9 01 03 00 00")])
            test = kombi.anfragen.index(bytes.fromhex("31 B9 01 03 00 00"))
            self.assertIn(bytes.fromhex("32 B8 01 03"), kombi.anfragen[test:])
        finally:
            s.schliessen()

    def test_kilometerstand_und_ohne_expertenmodus_gesperrt(self):
        s = sitzung(kwp2000_kombi=True)
        try:
            s.verbinden(0x17).result(5)
            proto = s._proto
            kombi = s._port.steuergeraete[0x17]

            def schreiben(kanal, wert):
                with proto.schreiben_freigeben(anpassung=[(kanal, wert)]):
                    return proto.anpassung_schreiben(kanal, wert)

            with self.assertRaises(SchreibenGesperrt):
                s.ausfuehren(schreiben, 2, 0).result(5)          # kein Expertenmodus
            s.experte = True
            with self.assertRaises(SchreibenGesperrt):
                s.ausfuehren(schreiben, 9, 0).result(5)          # Kilometerstand nie
            self.assertTrue(s.verbunden)
            self.assertEqual(kombi.anpassungen[9], 12345)
            self.assertEqual(kombi.geschrieben, [])
            wahl = kombi.anfragen.index(bytes.fromhex("31 B9 01 03 09"))
            self.assertIn(bytes.fromhex("32 B8 01 03"), kombi.anfragen[wahl:])
        finally:
            s.schliessen()


class Gefahren(unittest.TestCase):
    """Welche Steuergeräte eine Warnung brauchen – und wann die Kennung nicht passt."""

    def test_nach_adresse(self):
        for adresse, art in stellglied.GEFAHR.items():
            with self.subTest(adresse=hex(adresse)):
                gefahr, widerspruch = stellglied.gefahr(adresse)
                self.assertIsNone(widerspruch)
                self.assertEqual((gefahr.art, gefahr.adresse), (art, adresse))
                self.assertGreater(len(gefahr.schaeden), 100)
                self.assertIn("Mögliche Folgen", gefahr.schaeden)
                self.assertIn("Vorher", gefahr.schaeden)
                self.assertIn(art, stellglied.ARTEN)
        for adresse in (0x01, 0x17, 0x08, 0x09, 0x46, 0x56, None):
            with self.subTest(adresse=adresse):
                self.assertEqual(stellglied.gefahr(adresse), (None, None))

    def test_echte_kennungen_passen_zur_adresse(self):
        passend = [(0x03, "6X0907379 B", "ABS 30 IE CAN V004"), (0x03, "8E0614111", "ESP 5.7"),
                   (0x25, "6X0953257", "IMMO 0002"), (0x15, "1J0909609 Q", "AIRBAG VW3 SG"),
                   (0x44, "6Q0423156", "Lenkhilfe"), (0x53, "3C0907801", "EPB"),
                   (0x25, "1J0920806", "KOMBI+WEGFAHRSP VDO V01"),
                   (0x03, "6K0906032M", "ME7.5.10 S080")]      # unbekannt: Warnung nach Adresse
        for adresse, teil, name in passend:
            with self.subTest(teil=teil):
                gefahr, widerspruch = stellglied.gefahr(adresse, teil, name)
                self.assertIsNone(widerspruch)
                self.assertEqual(gefahr.art, stellglied.GEFAHR[adresse])
        frei = [(0x01, "6K0906032M", "ME7.5.10 S080"), (0x17, "6K9920806", "KOMBIINSTRUMENT"),
                (0x17, "1J0920806", "KOMBI+WEGFAHRSP VDO V01")]
        for adresse, teil, name in frei:
            with self.subTest(teil=teil):
                self.assertEqual(stellglied.gefahr(adresse, teil, name), (None, None))

    def test_kennung_passt_nicht_zur_adresse(self):
        falsch = [(0x17, "6X0907379 B", "ABS 30 IE CAN V004", "Bremsen"),
                  (0x01, "1J0909609 Q", "AIRBAG VW3 SG", "Airbag"),
                  (0x03, "1J0909609 Q", "AIRBAG VW3 SG", "Airbag"),
                  (0x15, "6X0907379 B", "ABS 30 IE", "Bremsen"),
                  (0x44, "6X0953257", "IMMO 0002", "Wegfahrsperre")]
        for adresse, teil, name, art in falsch:
            with self.subTest(adresse=hex(adresse), teil=teil):
                gefahr, widerspruch = stellglied.gefahr(adresse, teil, name)
                self.assertIsNone(gefahr)
                self.assertIn(art, widerspruch)
                self.assertIn(f"{adresse:02X}", widerspruch)
                self.assertIn("passt nicht zu dieser Adresse", widerspruch)

    def test_grundeinstellung_und_anpassung_nach_adresse_gesperrt(self):
        # auch wenn die Kennung nichts verrät (unbekanntes Gerät unter 34, 44 …)
        for adresse in stellglied.GEFAHR:
            with self.subTest(adresse=hex(adresse)):
                self.assertIn("gesperrt", KW1281._nur_stellglied(adresse, "1J0000000",
                                                                 "UNBEKANNT"))
        for adresse in (0x01, 0x17, 0x56):
            self.assertIsNone(KW1281._nur_stellglied(adresse, "6K0906032M", "ME7.5.10"))
        self.assertIn("gesperrt", KW1281._nur_stellglied(0x17, "6X0907379 B", "ABS 30 IE"))

    def test_hinweise_fuer_die_uebrigen(self):
        self.assertIn("Lüfter", stellglied.hinweis(0x01))
        self.assertIn("Zeiger", stellglied.hinweis(0x17))
        self.assertIsNone(stellglied.hinweis(0x03))
        self.assertIsNone(stellglied.hinweis(None))
        self.assertFalse(set(stellglied.HINWEISE) & set(stellglied.GEFAHR))


class GemerkteListen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.alt = stellglied.LISTEN_DATEI
        stellglied.LISTEN_DATEI = Path(self.ordner.name) / "daten" / "stellglieder.json"
        stellglied._SIM_LISTEN.clear()

    def tearDown(self):
        stellglied.LISTEN_DATEI = self.alt
        stellglied._SIM_LISTEN.clear()
        self.ordner.cleanup()

    def test_merken_und_laden(self):
        self.assertIsNone(stellglied.liste_laden("6K9920806", "KOMBIINSTRUMENT TRW V04"))
        stellglied.liste_merken(0x17, "6K9920806", "KOMBIINSTRUMENT  TRW V04",
                                [0x0296, 0x0296, 0x0295, 0x0298], True)
        liste = stellglied.liste_laden("6K9920806", "KOMBIINSTRUMENT TRW V04")
        self.assertEqual(liste.codes, [0x0296, 0x0295, 0x0298])     # doppelte nur einmal
        self.assertTrue(liste.vollstaendig)
        self.assertEqual(liste.adresse, 0x17)
        self.assertEqual([x.name for x in liste.stellglieder][0], "Drehzahlmesser")
        daten = json.loads(stellglied.LISTEN_DATEI.read_text(encoding="utf-8"))
        self.assertEqual(list(daten), ["6K9920806 KOMBIINSTRUMENT TRW V04"])
        # anderes Gerät, andere Liste
        self.assertIsNone(stellglied.liste_laden("6K9920806", "KOMBIINSTRUMENT TRW V05"))

    def test_abgebrochen_ersetzt_keine_laengere_liste(self):
        stellglied.liste_merken(0x17, "T", "B", [1, 2, 3, 4], True)
        self.assertEqual(stellglied.liste_merken(0x17, "T", "B", [1, 2], False).codes,
                         [1, 2, 3, 4])
        self.assertEqual(stellglied.liste_laden("T", "B").codes, [1, 2, 3, 4])
        # beginnt anders: dann gilt der neue Durchlauf
        stellglied.liste_merken(0x17, "T", "B", [9, 2], False)
        liste = stellglied.liste_laden("T", "B")
        self.assertEqual((liste.codes, liste.vollstaendig), ([9, 2], False))
        # ein vollständiger Durchlauf ersetzt immer
        stellglied.liste_merken(0x17, "T", "B", [5], True)
        self.assertEqual(stellglied.liste_laden("T", "B").codes, [5])
        # leerer Durchlauf ändert nichts
        self.assertEqual(stellglied.liste_merken(0x17, "T", "B", [], True).codes, [5])

    def test_simulator_nur_im_speicher(self):
        stellglied.liste_merken(0x03, "SIM907379", "ABS", [0xF0C1], True, sim=True)
        self.assertEqual(stellglied.liste_laden("SIM907379", "ABS", sim=True).codes, [0xF0C1])
        self.assertIsNone(stellglied.liste_laden("SIM907379", "ABS"))
        self.assertFalse(stellglied.LISTEN_DATEI.exists())

    def test_kaputte_datei(self):
        stellglied.LISTEN_DATEI.parent.mkdir(parents=True)
        for inhalt in ("kein json", "[1, 2]", '{"T B": {"codes": "x"}}', '{"T B": 5}'):
            with self.subTest(inhalt=inhalt):
                stellglied.LISTEN_DATEI.write_text(inhalt, encoding="utf-8")
                self.assertIsNone(stellglied.liste_laden("T", "B"))
        # danach lässt sich wieder speichern
        stellglied.liste_merken(0x17, "T", "B", [1], True)
        self.assertEqual(stellglied.liste_laden("T", "B").codes, [1])

    def test_nicht_speicherbar_ist_kein_fehler(self):
        stellglied.LISTEN_DATEI = Path(self.ordner.name) / "datei"
        stellglied.LISTEN_DATEI.write_text("x", encoding="utf-8")
        stellglied.LISTEN_DATEI = stellglied.LISTEN_DATEI / "stellglieder.json"   # unter einer Datei
        with self.assertLogs("vagdiag.proto", "WARNING"):
            liste = stellglied.liste_merken(0x17, "T", "B", [1], True)
        self.assertEqual(liste.codes, [1])


if __name__ == "__main__":
    unittest.main()

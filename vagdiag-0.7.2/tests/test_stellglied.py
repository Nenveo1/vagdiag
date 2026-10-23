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
from vagdiag.sim import KOMBI_STELLGLIEDER, SIM_STELLGLIEDER, sim_port

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


def durchlaufen(s, ereignisse, weiter=20, pause=0.05, ende_nach=None):
    """Stellglieddiagnose starten und „weiter“ geben, bis sie endet (oder nach ende_nach
    Stellgliedern beenden). Zurück: Ergebnis und gemeldete Stellglieder."""
    future = s.stellglieddiagnose()
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
    """Die Stellglieddiagnose geht nur mit Freigabe – und nie bei Bremsen, Airbag,
    Wegfahrsperre und Lenkung."""

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

    def test_gesperrte_steuergeraete(self):
        self.proto.experte = True
        for adresse in (0x03, 0x25):
            with self.subTest(adresse=hex(adresse)):
                self.proto.connect(adresse, (9600,))
                # gesperrt nach Adresse und – weil sich das Gerät als ABS bzw. Wegfahrsperre
                # meldet – schon nach der Kennung (dann gibt es gar keine Freigabe)
                with self.assertRaises(SchreibenGesperrt) as fall:
                    with self.proto.schreiben_freigeben(stellglied=True):
                        self.proto.stellglied_starten()
                self.assertIn("gesperrt", str(fall.exception))
                self.assertIn("gesperrt", KW1281.stellglied_gesperrt(adresse))
                self.assertEqual(self.port.steuergeraete[adresse].geschrieben, [])
                self.proto.trennen()
        self.assertEqual(set(stellglied.GESPERRT), {0x03, 0x15, 0x23, 0x25, 0x44, 0x53})

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
        kwp.adresse = 0x03
        with self.assertRaises(SchreibenGesperrt):                     # Bremsen nie
            kwp._schreibschutz(bytes.fromhex("31 B8 01 02"))

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

    def test_ohne_expertenmodus_und_bei_gesperrten(self):
        s = sitzung()
        try:
            s.verbinden(0x17).result(5)
            with self.assertRaises(SchreibenGesperrt):
                s.stellglieddiagnose().result(10)
            s.experte = True
            s.verbinden(0x03).result(5)
            with self.assertRaises(Nichts):
                s.stellglied_pruefen().result(5)
            geschrieben = [g.geschrieben for g in s._port.steuergeraete.values()
                           if hasattr(g, "geschrieben")]
        finally:
            s.schliessen()
        self.assertFalse(any(geschrieben))

    def test_abgelehnt(self):
        s = sitzung()
        try:
            s._port.steuergeraete[0x17].stellglieder = None     # kennt keine
            s.experte = True
            s.verbinden(0x17).result(5)
            with self.assertRaises(Nak):
                s.stellglieddiagnose().result(10)
            self.assertTrue(s.verbunden, "danach wieder verbunden")
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


if __name__ == "__main__":
    unittest.main()

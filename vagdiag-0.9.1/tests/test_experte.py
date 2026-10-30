# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Expertenmodus und Scan: Schreibsperre, Drosselklappe anlernen, Service-Reset.
Start: python -m unittest -v"""

import json
import tempfile
import time
import unittest
from pathlib import Path

from vagdiag import messwerte, scan, sprache, texte
from vagdiag.experte import Nichts, adp_status, drosselklappe_aufbau, verfuegbarkeit
from vagdiag.kline import KLine
from vagdiag.kw1281 import (EXPERTE, LESEND, KW1281, Nak, NotAvailable, SchreibenGesperrt,
                            Timing)
from vagdiag.kwp2000 import Kwp2000
from vagdiag.session import DiagSession
from vagdiag.sim import SIM_ADP_FEHLER, sim_port

# Zeitwächter großzügig: Der Simulator läuft hier nicht in Echtzeit, und Testrechner hängen
# manchmal selbst (virtuelle Maschinen bis 50 ms). Den Wächter mit den echten Fristen prüft
# test_sicherheit.Zeitwaechter.
SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0,
                 trenn_pause=0.05, wechsel_pause=0.05,
                 byte_frist=0.5, kwp_p4_frist=0.5)


def sitzung(motor_aus=False, kwp2000_motor=False, **sim):
    """Sitzung am Simulator. motor_aus: Zündung an, Motor aus (für die Grundeinstellung)."""
    def fabrik():
        port = sim_port(echtzeit=False, fahrprofil=False, kwp2000_motor=kwp2000_motor, **sim)
        port.fahrzeug.motor_aus = motor_aus
        return port
    s = DiagSession(fabrik, SCHNELL, keepalive=0.05).start()
    s._port_oeffnen()
    return s


class Schreibsperre(unittest.TestCase):
    def setUp(self):
        self.port = sim_port(echtzeit=False, fahrprofil=False)
        self.proto = KW1281(KLine(self.port), SCHNELL)

    def verbinden(self, adresse):
        self.proto.connect(adresse, (10400, 9600))
        return self.port.steuergeraete[adresse]

    def test_ohne_expertenmodus_geht_nichts_raus(self):
        motor = self.verbinden(0x01)
        with self.assertRaises(SchreibenGesperrt):
            self.proto.grundeinstellung(60)
        with self.assertRaises(SchreibenGesperrt):
            with self.proto.schreiben_freigeben(grundeinstellung=[60]):
                pass
        self.assertEqual(motor.geschrieben, [])
        self.assertTrue(self.proto.verbunden, "die Sperre greift vor dem Senden")

    def test_im_expertenmodus_nur_mit_passender_freigabe(self):
        motor = self.verbinden(0x01)
        self.proto.experte = True
        with self.assertRaises(SchreibenGesperrt):
            self.proto.grundeinstellung(60)          # ohne Freigabe
        with self.proto.schreiben_freigeben(grundeinstellung=[98]):
            with self.assertRaises(SchreibenGesperrt):
                self.proto.grundeinstellung(60)      # andere Gruppe
        with self.proto.schreiben_freigeben(grundeinstellung=[60]):
            self.assertEqual(len(self.proto.grundeinstellung(60)), 4)
            with self.assertRaises(SchreibenGesperrt):
                self.proto.anpassung_speichern(1, 128)   # Anpassung nicht freigegeben
        with self.assertRaises(SchreibenGesperrt):
            self.proto.grundeinstellung(60)          # Freigabe vorbei
        self.assertEqual([(t, d) for t, d in motor.geschrieben], [(0x28, b"\x3c")])

    def test_kanal_00_und_kilometerstand_immer_gesperrt(self):
        self.proto.experte = True
        self.verbinden(0x01)
        with self.proto.schreiben_freigeben(anpassung=[(0, 0)]):
            with self.assertRaises(SchreibenGesperrt):
                self.proto.anpassung_testen(0, 0)
        self.proto.trennen()
        kombi = self.verbinden(0x17)
        with self.proto.schreiben_freigeben(anpassung=[(9, 12345)]):
            with self.assertRaises(SchreibenGesperrt):
                self.proto.anpassung_testen(9, 12345)
            with self.assertRaises(SchreibenGesperrt):
                self.proto.anpassung_speichern(9, 12345)
        self.assertEqual(kombi.geschrieben, [])

    def test_alle_anderen_schreibenden_bloecke_gesperrt(self):
        self.proto.experte = True
        motor = self.verbinden(0x01)
        with self.proto.schreiben_freigeben(grundeinstellung=[60], anpassung=[(1, 0)]):
            for titel in (0x02, 0x04, 0x0C, 0x10, 0x1A, 0x1B, 0x27, 0x2B, 0x3D, 0x5C, 0xD7,
                          0x01, 0x03, 0x11, 0x12, 0x19):
                with self.subTest(titel=hex(titel)):
                    with self.assertRaises(SchreibenGesperrt):
                        self.proto.austausch(titel, b"\x00")
        self.assertEqual(motor.geschrieben, [])
        self.assertTrue(set(t for t, _ in motor.anfragen) <= LESEND)
        self.assertEqual(EXPERTE, {0x04, 0x22, 0x28, 0x2A})

    def test_kwp2000_nur_lesende_dienste(self):
        kwp = Kwp2000(KLine(self.port), SCHNELL, 0x01, 2031, 0xEF, 10400)
        for anfrage in (b"\x10\x85", b"\x10\x86", b"\x2e\x01\x00", b"\x31\x01", b"\x3b\x01\x00",
                        b"\x27\x01", b"\x34\x00", b"\x23\x00\x00\x00\x10", b"\x30\x01\x01"):
            with self.subTest(anfrage=anfrage.hex()):
                with self.assertRaises(SchreibenGesperrt):
                    kwp.senden(anfrage)


class Drosselklappe(unittest.TestCase):
    def test_bedingungen_nicht_erfuellt(self):
        s = sitzung()                 # Motor läuft, zwei Fehler gespeichert
        try:
            s.experte = True
            s.verbinden(0x01).result(5)
            pruefung = s.drosselklappe_pruefen(60).result(10)
            with self.assertRaises(Nichts) as fall:
                s.drosselklappe_anlernen(60, dauer=0.5).result(10)
            motor = s._port.steuergeraete[0x01]
        finally:
            s.schliessen()
        verletzt = [b.name for b in pruefung.verletzt]
        self.assertEqual(verletzt, ["Motor aus (Drehzahl 0)", "Kein Fehler im Motor-Fehlerspeicher"])
        self.assertIn("Motor aus (Drehzahl 0)", str(fall.exception))
        self.assertEqual(motor.geschrieben, [])

    def test_ohne_expertenmodus_gesperrt(self):
        s = sitzung(motor_aus=True)
        try:
            s._port.steuergeraete[0x01].fehler.clear()
            s.verbinden(0x01).result(5)
            with self.assertRaises(SchreibenGesperrt):
                s.drosselklappe_anlernen(60, dauer=0.5).result(10)
            motor = s._port.steuergeraete[0x01]
        finally:
            s.schliessen()
        self.assertEqual(motor.geschrieben, [])

    def test_anlernen(self):
        ereignisse = []
        s = sitzung(motor_aus=True, zeitfaktor=20.0)
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            s._port.steuergeraete[0x01].fehler.clear()
            s.experte = True
            s.verbinden(0x01).result(5)
            pruefung = s.drosselklappe_pruefen(60).result(10)
            ergebnis = s.drosselklappe_anlernen(60, dauer=0.6).result(10)
            motor = s._port.steuergeraete[0x01]
            titel = [t for t, _ in motor.anfragen]
        finally:
            s.schliessen()
        self.assertEqual(pruefung.verletzt, [])
        self.assertEqual([b.ok for b in pruefung.bedingungen], [True, True, True, True])
        self.assertEqual(pruefung.bedingungen[1].wert, "12,39 V")     # 0,07-V-Schritte
        self.assertEqual(ergebnis.status, "ok")
        self.assertFalse(ergebnis.abgebrochen)
        self.assertEqual(ergebnis.fehler_nachher, [])
        self.assertEqual([m.text for m in ergebnis.nachher][2:], ["8", "ADP i.O. (Simulator)"])
        self.assertEqual({(t, d) for t, d in motor.geschrieben}, {(0x28, b"\x3c")})
        # danach: einmal normal lesen (beendet die Grundeinstellung), dann Fehlerspeicher
        letzte_28 = max(i for i, t in enumerate(titel) if t == 0x28)
        self.assertEqual(titel[letzte_28 + 1], 0x29)
        self.assertIn(0x07, titel[letzte_28 + 1:])
        verlauf = [d for a, d in ereignisse if a == "grundeinstellung"]
        self.assertTrue(verlauf and verlauf[0]["gruppe"] == 60)
        self.assertEqual(verlauf[-1]["status"], "ok")

    def test_abbrechen(self):
        s = sitzung(motor_aus=True)
        try:
            s._port.steuergeraete[0x01].fehler.clear()
            s.experte = True
            s.verbinden(0x01).result(5)
            future = s.drosselklappe_anlernen(60, dauer=20.0)
            time.sleep(0.5)
            s.abbrechen()
            ergebnis = future.result(10)
            titel = [t for t, _ in s._port.steuergeraete[0x01].anfragen]
        finally:
            s.schliessen()
        self.assertTrue(ergebnis.abgebrochen)
        self.assertLess(ergebnis.dauer, 5)
        letzte_28 = max(i for i, t in enumerate(titel) if t == 0x28)
        self.assertEqual(titel[letzte_28 + 1], 0x29)

    def test_motor_springt_an(self):
        """Läuft der Motor während der Grundeinstellung, meldet das Steuergerät ERROR."""
        s = sitzung(motor_aus=True)
        try:
            s._port.steuergeraete[0x01].fehler.clear()
            s.experte = True
            s.verbinden(0x01).result(5)
            future = s.drosselklappe_anlernen(60, dauer=1.0)
            time.sleep(0.3)
            s._port.fahrzeug.motor_aus = False
            ergebnis = future.result(10)
        finally:
            s.schliessen()
        self.assertEqual(ergebnis.status, "fehler")
        self.assertEqual(ergebnis.nachher[3].textnummer, SIM_ADP_FEHLER)

    def test_abgelehnt_waehrend_der_grundeinstellung(self):
        """Lehnt das Steuergerät mitten im Ablauf ab: Fehler ins Protokoll, kein neuer
        Versuch, danach zurück zu den Messwerten."""
        s = sitzung(motor_aus=True)
        try:
            motor = s._port.steuergeraete[0x01]
            motor.fehler.clear()
            s.experte = True
            s.verbinden(0x01).result(5)
            original = s._proto.grundeinstellung
            aufrufe = []

            def grundeinstellung(gruppe):
                aufrufe.append(gruppe)
                if len(aufrufe) == 3:
                    raise Nak("abgelehnt (Test)")
                return original(gruppe)

            s._proto.grundeinstellung = grundeinstellung
            with self.assertLogs("vagdiag.proto", "WARNING") as protokoll:
                with self.assertRaises(Nak):
                    s.drosselklappe_anlernen(60, dauer=20.0).result(10)
            titel = [t for t, _ in motor.anfragen]
        finally:
            s.schliessen()
        self.assertEqual(len(aufrufe), 3, "nach der Ablehnung nicht weiter angefragt")
        self.assertTrue(any("Grundeinstellung 060 nach" in z and "abgelehnt (Test)" in z
                            for z in protokoll.output), protokoll.output)
        letzte_28 = max(i for i, t in enumerate(titel) if t == 0x28)
        self.assertEqual(titel[letzte_28 + 1], 0x29)

    def test_gruppe_fehlt_und_kwp2000(self):
        s = sitzung(motor_aus=True)
        try:
            s.experte = True
            s.verbinden(0x01).result(5)
            with self.assertRaises(Nichts) as fall:
                s.drosselklappe_anlernen(98, dauer=0.5).result(10)
            self.assertIn("098", str(fall.exception))
            self.assertEqual(s._port.steuergeraete[0x01].geschrieben, [])
            s.verbinden(0x17).result(5)
            with self.assertRaises(Nichts):
                s.drosselklappe_pruefen(60).result(5)     # falsches Steuergerät
        finally:
            s.schliessen()
        s = sitzung(motor_aus=True, kwp2000_motor=True)
        try:
            s.experte = True
            s.verbinden(0x01).result(10)
            with self.assertRaises(NotAvailable):
                s.drosselklappe_anlernen(60, dauer=0.5).result(10)
        finally:
            s.schliessen()

    def test_aufbau_der_gruppen(self):
        def werte(roh):
            return messwerte.gruppe_auswerten(bytes.fromhex(roh))
        # 060 E-Gas: %, %, Lernschritt, Status (wie im Simulator)
        self.assertIsNone(drosselklappe_aufbau(60, werte("21 FF 07 21 FF CF 08 0A 08 25 00 02")))
        # 060 mit Betriebszustand als Text (Ross-Tech: „ESB“)
        self.assertIsNone(drosselklappe_aufbau(60, werte("21 FF 07 21 FF CF 25 00 05 25 00 01")))
        # 098: zwei Spannungen, Betriebszustand, Status (Werkstatthandbuch: 4,420 V 3,880 V
        # Leerlauf ADP.läuft)
        self.assertIsNone(drosselklappe_aufbau(98, werte("06 64 2C 06 64 26 25 00 05 25 00 01")))
        # abweichend: Spannungen in 060, Prozent in 098, Zahl mit Einheit, zu wenig Felder,
        # Feld 4 kein Text
        for gruppe, roh in ((60, "06 64 2C 06 64 26 08 0A 08 25 00 01"),
                            (98, "21 FF 07 21 FF CF 25 00 05 25 00 01"),
                            (60, "21 FF 07 21 FF CF 01 C8 15 25 00 01"),
                            (60, "21 FF 07 21 FF CF 08 0A 08"),
                            (60, "21 FF 07 21 FF CF 08 0A 08 08 0A 01"),
                            (98, "06 64 2C 06 64 26 08 0A 08 25 00 01"),
                            (5, "21 FF 07 21 FF CF 08 0A 08 25 00 02")):
            with self.subTest(gruppe=gruppe, roh=roh):
                self.assertIsNotNone(drosselklappe_aufbau(gruppe, werte(roh)))

    def test_gruppe_anders_aufgebaut(self):
        """Ist 060 kein Anpassungskanal der Drosselklappe (andere Einheiten), startet nichts –
        das Steuergerät könnte mit derselben Gruppe etwas anderes anlernen."""
        s = sitzung(motor_aus=True)
        try:
            motor = s._port.steuergeraete[0x01]
            motor.fehler.clear()
            motor.gruppen[60] = lambda: [(6, 100, 120), (6, 100, 130), (1, 200, 21),
                                         (37, 0, 5)]
            s.experte = True
            s.verbinden(0x01).result(5)
            with self.assertRaises(Nichts) as fall:
                s.drosselklappe_pruefen(60).result(10)
            self.assertIn("anders aufgebaut", str(fall.exception))
            with self.assertRaises(Nichts):
                s.drosselklappe_anlernen(60, dauer=0.5, ohne_pruefung_ok=True).result(10)
            titel = [t for t, _ in motor.anfragen]
        finally:
            s.schliessen()
        self.assertEqual(motor.geschrieben, [])
        self.assertNotIn(0x28, titel)

    def test_098_mit_passendem_aufbau(self):
        s = sitzung(motor_aus=True)
        try:
            motor = s._port.steuergeraete[0x01]
            motor.fehler.clear()
            motor.gruppen[98] = lambda: [(6, 100, 44), (6, 100, 38), (37, 0, 5), (37, 0, 1)]
            motor.grundeinstellungen[98] = lambda: [(6, 100, 44), (6, 100, 38), (37, 0, 5),
                                                    (37, 0, 2)]
            s.experte = True
            s.verbinden(0x01).result(5)
            ergebnis = s.drosselklappe_anlernen(98, dauer=0.3).result(10)
        finally:
            s.schliessen()
        self.assertIsNone(ergebnis.abweichung)
        self.assertEqual(ergebnis.vorher[3].text, "ADP. läuft")      # Text 1 der Tabelle
        self.assertEqual({(t, d) for t, d in motor.geschrieben}, {(0x28, b"\x62")})

    def test_antwort_waehrend_der_grundeinstellung_anders(self):
        s = sitzung(motor_aus=True)
        try:
            motor = s._port.steuergeraete[0x01]
            motor.fehler.clear()
            original = motor.grundeinstellungen[60]
            aufrufe = []

            def grundeinstellung_060():
                aufrufe.append(1)
                if len(aufrufe) >= 2:
                    return [(1, 200, 21), (6, 100, 130), (5, 10, 130), (8, 10, 1)]
                return original()

            motor.grundeinstellungen[60] = grundeinstellung_060
            s.experte = True
            s.verbinden(0x01).result(5)
            with self.assertLogs("vagdiag.proto", "WARNING") as protokoll:
                ergebnis = s.drosselklappe_anlernen(60, dauer=20.0).result(10)
            titel = [t for t, _ in motor.anfragen]
        finally:
            s.schliessen()
        self.assertTrue(ergebnis.abgebrochen)
        self.assertIn("erwartet", ergebnis.abweichung)
        self.assertEqual(len(aufrufe), 2, "nach der abweichenden Antwort nichts mehr angefragt")
        self.assertLess(ergebnis.dauer, 5)
        self.assertTrue(any("antwortet anders" in z for z in protokoll.output))
        letzte_28 = max(i for i, t in enumerate(titel) if t == 0x28)
        self.assertEqual(titel[letzte_28 + 1], 0x29)

    def test_nicht_pruefbar_nur_mit_bestaetigung(self):
        s = sitzung(motor_aus=True, zeitfaktor=20.0)
        try:
            motor = s._port.steuergeraete[0x01]
            motor.fehler.clear()
            del motor.gruppen[1], motor.gruppen[4]     # keine Drehzahl, Spannung, Temperatur
            s.experte = True
            s.verbinden(0x01).result(5)
            pruefung = s.drosselklappe_pruefen(60).result(10)
            with self.assertRaises(Nichts):
                s.drosselklappe_anlernen(60, dauer=0.3).result(10)
            self.assertEqual(motor.geschrieben, [])
            ergebnis = s.drosselklappe_anlernen(60, dauer=0.3, ohne_pruefung_ok=True).result(10)
        finally:
            s.schliessen()
        self.assertEqual(len(pruefung.ungeprueft), 3)
        self.assertEqual(ergebnis.status, "ok")

    def test_status_aus_feld_4(self):
        class M:
            def __init__(self, text):
                self.text = text
                self.textnummer = None
        werte = [M("2,7 %"), M("82 %"), M("8")]
        self.assertEqual(adp_status(werte + [M("ADP i.O.")]), "ok")
        self.assertEqual(adp_status(werte + [M("ADP OK")]), "ok")
        self.assertEqual(adp_status(werte + [M("ADP. O.K.")]), "ok")
        self.assertEqual(adp_status(werte + [M("ADP läuft")]), "laeuft")
        self.assertEqual(adp_status(werte + [M("ADP ERROR")]), "fehler")
        self.assertIsNone(adp_status(werte + [M("Text Nr. 1234")]))
        self.assertIsNone(adp_status(werte))

    def test_status_nach_textnummer(self):
        # Texte 1 und 2 aus der Tabelle (KLineKWP1281Lib) – unabhängig von der Sprache
        werte = messwerte.gruppe_auswerten(bytes.fromhex("17 01 07 17 01 CF 08 01 08"))
        for nummer, status in ((1, "laeuft"), (2, "ok")):
            feld4 = messwerte.umrechnen(4, 37, 0, nummer)
            self.assertEqual(adp_status(werte + [feld4]), status)
            try:
                sprache.setzen("en")
                self.assertEqual(adp_status(werte + [feld4]), status)
            finally:
                sprache.setzen("de")
        # auch mit eigenen Texten für 1 und 2, in denen nichts von „ADP“ steht
        alt = texte.EIGENE_TEXTE
        with tempfile.TemporaryDirectory() as ordner:
            try:
                texte.EIGENE_TEXTE = Path(ordner) / "texte.json"
                texte.EIGENE_TEXTE.write_text('{"1": "Lernen", "2": "fertig"}', encoding="utf-8")
                texte.neu_laden()
                for nummer, status in ((1, "laeuft"), (2, "ok")):
                    feld4 = messwerte.umrechnen(4, 37, 0, nummer)
                    self.assertIn(feld4.text, ("Lernen", "fertig"))
                    self.assertEqual(adp_status(werte + [feld4]), status)
            finally:
                texte.EIGENE_TEXTE = alt
                texte.neu_laden()


class ServiceReset(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_zuruecksetzen(self):
        s = sitzung()
        try:
            s.experte = True
            s.verbinden(0x17).result(5)
            vorher = s.service_lesen().result(5)
            ergebnis = s.service_zuruecksetzen(vorher.wert, self.ordner).result(10)
            kombi = s._port.steuergeraete[0x17]
        finally:
            s.schliessen()
        self.assertEqual((vorher.wert, ergebnis.alt, ergebnis.neu), (3, 3, 0))
        self.assertEqual(kombi.anpassungen[2], 0)
        self.assertEqual(kombi.anpassungen[9], 12345, "Kilometerstand unberührt")
        self.assertEqual(kombi.geschrieben, [(0x22, b"\x02\x00\x00"),
                                             (0x2A, b"\x02\x00\x00\x00\xd4\x31")])
        sicherung = json.loads(ergebnis.sicherung.read_text(encoding="utf-8"))
        self.assertEqual((sicherung["adresse"], sicherung["kanal"], sicherung["alter_wert"],
                          sicherung["neuer_wert"], sicherung["teilenummer"]),
                         ("17", 2, 3, 0, "SIM920806"))

    def test_wert_geaendert_oder_abgelehnt(self):
        s = sitzung()
        try:
            s.experte = True
            s.verbinden(0x17).result(5)
            kombi = s._port.steuergeraete[0x17]
            with self.assertRaises(Nichts):
                s.service_zuruecksetzen(7, self.ordner).result(10)   # angezeigt war 7
            self.assertEqual(kombi.geschrieben, [])
            self.assertEqual(list(self.ordner.iterdir()), [])
            kombi.anpassung_erlaubt[2] = lambda wert: False         # Kombi lehnt ab
            with self.assertLogs("vagdiag.proto", "WARNING") as protokoll:
                with self.assertRaises(Nak):
                    s.service_zuruecksetzen(3, self.ordner).result(10)
            self.assertTrue(any("Service-Intervall nicht zurückgesetzt" in z
                                for z in protokoll.output), protokoll.output)
            self.assertEqual([t for t, _ in kombi.geschrieben], [0x22], "nach NAK kein Speichern")
            self.assertEqual(kombi.anpassungen[2], 3)
        finally:
            s.schliessen()

    def test_ohne_kanal_02_oder_falsches_steuergeraet(self):
        s = sitzung()
        try:
            s.experte = True
            s.verbinden(0x01).result(5)
            with self.assertRaises(Nichts):
                s.service_lesen().result(5)
            del s._port.steuergeraete[0x17].anpassungen[2]
            s.verbinden(0x17).result(5)
            with self.assertRaises(Nichts) as fall:
                s.service_lesen().result(5)
            self.assertIn("Knopf", str(fall.exception))
        finally:
            s.schliessen()


class Scan(unittest.TestCase):
    def test_scan_mit_uebersicht(self):
        ereignisse = []
        s = sitzung()
        s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        try:
            eintraege = s.scannen().result(120)
            schreibend = [g.adresse for g in s._port.steuergeraete.values()
                          if getattr(g, "geschrieben", [])]
        finally:
            s.schliessen()
        gefunden = {e.adresse: e for e in eintraege if e.status == "gefunden"}
        self.assertEqual(sorted(gefunden), [0x01, 0x03, 0x17, 0x25, 0x56])
        self.assertEqual(len(eintraege), 15)
        self.assertEqual(next(e for e in eintraege if e.adresse == 0x15).status, "gesperrt")
        self.assertEqual(len(gefunden[0x01].fehler), 2)
        self.assertEqual(gefunden[0x56].verbindung.protokoll, "KWP2000")
        self.assertEqual(schreibend, [])
        bericht = scan.bericht(eintraege, sim=True)
        self.assertIn("5 von 15 Adressen antworten", bericht[1])
        self.assertTrue(any(z.startswith("17 – Schalttafeleinsatz (Kombi): gefunden – 1 Fehler  "
                                         "SIM920806") for z in bericht), bericht[:20])
        self.assertTrue(any("16486" in z for z in bericht))
        start = [d for a, d in ereignisse if a == "scan" and d["eintrag"] is None]
        self.assertEqual(len(start), 15)

    def test_airbag_nur_mit_haekchen_und_freigabe(self):
        s = sitzung()
        try:
            s.airbag_freigeben()
            ohne = s.scannen([0x15], mit_fehlern=False).result(20)
            mit = s.scannen([0x15], mit_fehlern=False, mit_airbag=True).result(20)
        finally:
            s.schliessen()
        self.assertEqual(ohne[0].status, "gesperrt")
        self.assertEqual((mit[0].status, mit[0].fehler), ("gefunden", None))

    def test_alle_adressen(self):
        from vagdiag import adressen
        self.assertEqual(adressen.alle(), list(range(1, 0x80)))
        self.assertEqual(set(adressen.UEBERSPRINGEN), {0x33, 0x7C})
        self.assertEqual(adressen.text(0x5F), "5F – Informationselektronik")
        self.assertFalse(set(adressen.WEITERE) & set(adressen.ADRESSEN))
        s = sitzung()
        try:
            eintraege = s.scannen([0x15, 0x16, 0x17, 0x33, 0x7C], mit_fehlern=False).result(30)
            gereizt = list(s._port.reizungen)
        finally:
            s.schliessen()
        status = {e.adresse: e.status for e in eintraege}
        self.assertEqual(status, {0x15: "gesperrt", 0x16: "keine_antwort", 0x17: "gefunden",
                                  0x33: "uebersprungen", 0x7C: "uebersprungen"})
        self.assertNotIn(0x33, gereizt)
        self.assertNotIn(0x7C, gereizt)
        self.assertIn("OBD-II", next(e for e in eintraege if e.adresse == 0x33).meldung)
        bericht = scan.bericht(eintraege, sim=True, alle=True)
        self.assertIn("alle Adressen 01–7F", bericht[0])
        self.assertIn("Keine Antwort (1): 16", bericht)
        self.assertFalse(any(z.startswith("16 – ") for z in bericht))
        self.assertTrue(any(z.startswith("33 – OBD") or z.startswith("33 – unbekannt")
                            for z in bericht), bericht[:12])

    def test_gewaehlte_baudrate(self):
        # Wählt man in der Oberfläche eine feste Baudrate, fragt der Scan nur mit dieser
        s = sitzung()
        try:
            falsch = s.scannen([0x17], mit_fehlern=False, bauds=(4800,)).result(30)
            richtig = s.scannen([0x17], mit_fehlern=False).result(30)
        finally:
            s.schliessen()
        # das Kombi antwortet mit seiner eigenen Baudrate – bei 4800 kommt nur Unlesbares an
        self.assertEqual(falsch[0].status, "fehler")
        self.assertIn("4800", falsch[0].meldung)
        self.assertEqual(richtig[0].status, "gefunden")

    def test_abbrechen(self):
        s = sitzung()
        try:
            future = s.scannen()
            time.sleep(0.4)
            s.abbrechen()
            eintraege = future.result(30)
        finally:
            s.schliessen()
        self.assertLess(len(eintraege), 15)


class Verfuegbarkeit(unittest.TestCase):
    """Im Expertenreiter steht bei jeder Funktion, warum sie gerade nicht geht."""

    def setUp(self):
        self.port = sim_port(echtzeit=False, fahrprofil=False)
        self.proto = KW1281(KLine(self.port), SCHNELL)

    def test_gruende(self):
        v = self.proto.connect(0x01, (10400,))
        aus = verfuegbarkeit(False, v, False, None)
        for name in ("drosselklappe", "service", "stellglied"):
            self.assertFalse(aus[name].ok)
            self.assertIn("Expertenmodus ist aus", aus[name].text)
        laeuft = verfuegbarkeit(True, v, True, "Messwertblöcke")
        self.assertIn("Gerade läuft: Messwertblöcke", laeuft["stellglied"].text)
        beschaeftigt = verfuegbarkeit(True, v, True, None)
        self.assertIn("arbeitet gerade", beschaeftigt["service"].text)
        ohne = verfuegbarkeit(True, None, False, None)
        self.assertIn("Erst links mit 01", ohne["drosselklappe"].text)
        self.assertIn("Erst links mit 17", ohne["service"].text)
        self.assertIn("Erst links ein Steuergerät öffnen", ohne["stellglied"].text)
        motor = verfuegbarkeit(True, v, False, None)
        self.assertTrue(motor["drosselklappe"].ok)
        self.assertFalse(motor["service"].ok)
        self.assertIn("Verbunden ist 01", motor["service"].text)
        self.assertIn("links mit 17", motor["service"].text)
        self.assertTrue(motor["stellglied"].ok)
        self.assertIn("Bereit", motor["stellglied"].text)

    def test_gefaehrlich_und_widerspruch(self):
        v = self.proto.connect(0x03, (9600,))
        abs_ = verfuegbarkeit(True, v, False, None)
        self.assertTrue(abs_["stellglied"].ok)
        self.assertIn("Achtung, Bremsen", abs_["stellglied"].text)
        self.assertFalse(abs_["drosselklappe"].ok)
        # ABS unter 17: Service-Reset und Stellglieddiagnose gesperrt
        self.port.steuergeraete[0x17].kennung = [b"6X0907379 B ", b"ABS 30 IE CA", b"N V004",
                                                 b"\x00\x01\x1a\xd4\x31"]
        v = self.proto.connect(0x17, (10400, 9600))
        falsch = verfuegbarkeit(True, v, False, None)
        self.assertFalse(falsch["stellglied"].ok)
        self.assertIn("passt nicht zu dieser Adresse", falsch["stellglied"].text)
        self.assertFalse(falsch["service"].ok)
        self.assertIn("Airbag, Bremsen", falsch["service"].text)

    def test_kwp2000_ohne_drosselklappe(self):
        port = sim_port(echtzeit=False, fahrprofil=False, kwp2000_motor=True)
        proto = KW1281(KLine(port), SCHNELL)
        v = proto.connect(0x01, (10400,))
        stand = verfuegbarkeit(True, v, False, None)
        self.assertFalse(stand["drosselklappe"].ok)
        self.assertIn("KWP2000", stand["drosselklappe"].text)
        self.assertTrue(stand["stellglied"].ok)


if __name__ == "__main__":
    unittest.main()

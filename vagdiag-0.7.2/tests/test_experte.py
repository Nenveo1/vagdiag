"""Expertenmodus und Scan: Schreibsperre, Drosselklappe anlernen, Service-Reset.
Start: python -m unittest -v"""

import json
import tempfile
import time
import unittest
from pathlib import Path

from vagdiag import scan
from vagdiag.experte import Nichts, adp_status
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
        werte = [M("2,7 %"), M("82 %"), M("8")]
        self.assertEqual(adp_status(werte + [M("ADP i.O.")]), "ok")
        self.assertEqual(adp_status(werte + [M("ADP OK")]), "ok")
        self.assertEqual(adp_status(werte + [M("ADP läuft")]), "laeuft")
        self.assertEqual(adp_status(werte + [M("ADP ERROR")]), "fehler")
        self.assertIsNone(adp_status(werte + [M("Text Nr. 1234")]))
        self.assertIsNone(adp_status(werte))


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
            with self.assertRaises(Nak):
                s.service_zuruecksetzen(3, self.ordner).result(10)
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


if __name__ == "__main__":
    unittest.main()

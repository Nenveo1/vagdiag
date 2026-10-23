"""OBD-II-Test an Adresse 33 (obd2.py): nur lesende Anfragen, Auswertung, Ablauf im Simulator.
Start: python -m unittest -v"""

import dataclasses
import time
import unittest
from unittest import mock

from vagdiag import obd2, sprache
from vagdiag.kline import KLine
from vagdiag.kw1281 import ProtocolError, SchreibenGesperrt, Timing
from vagdiag.obd2 import (ERLAUBT, ISO9141, KWP_5BAUD, KWP_FAST, Obd2, ObdZeiten,
                          fin_zusammensetzen, iso9141_nachrichten, kwp_nachrichten,
                          readiness_auswerten, unterstuetzte)
from vagdiag.session import DiagSession
from vagdiag.sim import sim_port

SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05, block_timeout=0.3,
                 byte_timeout=0.1, w4=0.0, inter_byte=0.0, byte_frist=0.5, kwp_p4_frist=0.5,
                 trenn_pause=0.05, kwp_p3_max=0.5)
ZEITEN = ObdZeiten(p2=0.2, luecke=0.05, p3=0.0, p4=0.0, fast_init_antwort=0.2)


def h(text):
    return bytes.fromhex(text)


def pruefer(**sim):
    port = sim_port(echtzeit=False, fahrprofil=False, **sim)
    return port, Obd2(KLine(port), SCHNELL, ZEITEN)


class Auswertung(unittest.TestCase):
    def tearDown(self):
        sprache.setzen("de")

    def test_readiness_otto(self):
        r = readiness_auswerten(h("82 07 6D 04"))
        self.assertTrue(r.mil)
        self.assertEqual(r.fehler, 2)
        self.assertFalse(r.diesel)
        status = {m.name: m.status for m in r.monitore}
        self.assertEqual(status["Verbrennungsaussetzer"], "abgeschlossen")
        self.assertEqual(status["Katalysator"], "abgeschlossen")
        self.assertEqual(status["Katalysatorheizung"], "nicht vorhanden")
        self.assertEqual(status["Tankentlüftung"], "nicht abgeschlossen")
        self.assertEqual(status["Abgasrückführung"], "nicht vorhanden")
        self.assertEqual(len(r.monitore), 11)
        self.assertFalse(r.alle_fertig)
        self.assertTrue(readiness_auswerten(h("00 07 6D 00")).alle_fertig)
        sprache.setzen("en")
        self.assertEqual(r.monitore[5].status, "incomplete")

    def test_readiness_diesel_und_laufende_pruefungen(self):
        # B: Diesel (Bit 3), Aussetzer und Bauteile vorhanden, Bauteile noch offen (Bit 6)
        r = readiness_auswerten(h("00 4D 7F 08"))
        self.assertTrue(r.diesel)
        self.assertFalse(r.mil)
        namen = [m.name for m in r.monitore]
        self.assertEqual(len(namen), 9)                  # reservierte Bits 2 und 4 fehlen
        self.assertNotIn("Katalysator", namen)
        status = {m.name: (m.vorhanden, m.fertig) for m in r.monitore}
        self.assertEqual(status["Verbrennungsaussetzer"], (True, True))
        self.assertEqual(status["Kraftstoffsystem"], (False, True))
        self.assertEqual(status["Bauteile (umfassende Überwachung)"], (True, False))
        self.assertEqual(status["Ladedruck"], (True, False))
        self.assertEqual(status["Partikelfilter"], (True, True))

    def test_unterstuetzte_werte(self):
        self.assertEqual(unterstuetzte(0x00, h("BE 3F A8 13")),
                         {0x01, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
                          0x10, 0x11, 0x13, 0x15, 0x1C, 0x1F, 0x20})
        self.assertEqual(unterstuetzte(0x20, h("80 00 00 01")), {0x21, 0x40})
        self.assertEqual(unterstuetzte(0x00, h("40 00")), set())       # zu kurz

    def test_fin_aus_fuenf_nachrichten(self):
        teile = [h("03 5A 36 4B 5A"), h("01 00 00 00 57"), h("05 30 30 30 31"),
                 h("02 56 57 5A 5A"), h("04 31 53 49 4D")]
        self.assertEqual(fin_zusammensetzen(teile), "WVWZZZ6KZ1SIM0001")
        self.assertEqual(fin_zusammensetzen([b"\x01" + b"WVWZZZ6KZ1SIM0001"]), "WVWZZZ6KZ1SIM0001")
        self.assertIsNone(fin_zusammensetzen([h("01 00 00 00 00")]))

    def test_iso9141_ohne_laengenbyte(self):
        motor = h("48 6B 10 41 00 BE 3F A8 13") + bytes([sum(h("48 6B 10 41 00 BE 3F A8 13"))
                                                           & 0xFF])
        getriebe = h("48 6B 18 41 00 80 00 00 00")
        getriebe += bytes([sum(getriebe) & 0xFF])
        nachrichten = iso9141_nachrichten(b"\x00" + motor + getriebe)
        self.assertEqual(nachrichten, [(0x10, h("41 00 BE 3F A8 13")),
                                       (0x18, h("41 00 80 00 00 00"))])
        kaputt = motor[:-1] + bytes([(motor[-1] + 1) & 0xFF])
        self.assertEqual(iso9141_nachrichten(kaputt), [])

    def test_kwp_nacheinander(self):
        eins = h("86 F1 10 41 00 BE 3F A8 13")
        eins += bytes([sum(eins) & 0xFF])
        zwei = h("83 F1 10 7F 01 12")
        zwei += bytes([sum(zwei) & 0xFF])
        self.assertEqual(kwp_nachrichten(eins + zwei),
                         [(0xF1, 0x10, h("41 00 BE 3F A8 13")), (0xF1, 0x10, h("7F 01 12"))])


class NurLesend(unittest.TestCase):
    def test_nur_mode_01_und_09_mit_bekannten_pids(self):
        erlaubt = 0
        for mode in range(256):
            for pid in range(256):
                anfrage = bytes([mode, pid])
                if pid in ERLAUBT.get(mode, ()):
                    Obd2.pruefen(anfrage)
                    erlaubt += 1
                else:
                    with self.assertRaises(SchreibenGesperrt):
                        Obd2.pruefen(anfrage)
        self.assertEqual(erlaubt, 12)
        self.assertEqual(set(ERLAUBT), {0x01, 0x09})
        for anfrage in (b"\x04", b"\x01", b"\x01\x00\x00", b"", b"\x09\x02\x00"):
            with self.assertRaises(SchreibenGesperrt):
                Obd2.pruefen(anfrage)

    def test_gesperrte_anfrage_geht_nicht_hinaus(self):
        port, p = pruefer()
        self.assertTrue(p.verbinden())
        obd = port.steuergeraete[0x33]
        for mode, pid in ((0x04, 0x00), (0x01, 0x0C), (0x02, 0x00), (0x08, 0x01)):
            with self.assertRaises(SchreibenGesperrt):
                p.anfrage(mode, pid)
        self.assertEqual(obd.anfragen, [])
        self.assertEqual(obd.geschrieben, [])


class Ablauf(unittest.TestCase):
    def test_iso9141(self):
        port, p = pruefer()
        e = p.test()
        obd = port.steuergeraete[0x33]
        self.assertTrue(e.ok)
        self.assertEqual((e.protokoll, e.keybytes), (ISO9141, (0x08, 0x08)))
        self.assertEqual(sorted(e.steuergeraete), [0x10])
        sg = e.steuergeraete[0x10]
        self.assertIn(0x0C, sg.pids)
        self.assertIn(0x21, sg.pids)                   # zweiter Bereich (PID 20) gelesen
        self.assertEqual(sg.norm, 6)
        self.assertEqual(e.fin, "WVWZZZ6KZ1SIM0001")
        adresse, r = e.readiness
        self.assertEqual((adresse, r.mil, r.fehler), (0x10, True, 2))
        self.assertEqual([a[0] for a in obd.anfragen], [1, 1, 1, 1, 9, 9])
        self.assertEqual(obd.anfragen, [h("01 00"), h("01 20"), h("01 01"), h("01 1C"),
                                        h("09 00"), h("09 02")])
        self.assertEqual(obd.geschrieben, [])
        self.assertTrue(p.offen)
        self.assertEqual(port.reizungen, [0x33])

    def test_kwp2000_fuenf_baud_und_fast_init(self):
        port, p = pruefer(kwp2000_motor=True)
        e = p.test()
        self.assertEqual((e.protokoll, e.keybytes), (KWP_5BAUD, (0xE9, 0x8F)))
        self.assertEqual(e.fin, "WVWZZZ6KZ1SIM0001")
        self.assertEqual(e.readiness[1].fehler, 2)
        # nimmt die 5-Baud-Reizung nicht an: Fast-Init mit StartCommunication an 33
        port, p = pruefer(kwp2000_motor=True)
        port.steuergeraete[0x33].reizbar = lambda: False
        e = p.test()
        self.assertEqual((e.protokoll, e.keybytes), (KWP_FAST, (0xE9, 0x8F)))
        self.assertEqual(port.fast_inits, 1)
        self.assertEqual(port.steuergeraete[0x33].anfragen[0], b"\x81")
        self.assertTrue(e.ok)

    def test_kein_obd2(self):
        port, p = pruefer()
        del port.steuergeraete[0x33]
        e = p.test()
        self.assertFalse(e.ok)
        self.assertIsNone(e.protokoll)
        self.assertIn("Keine Antwort an Adresse 33", e.meldungen[0])
        self.assertFalse(p.offen, "niemand hat zugehört – keine Pause nötig")
        self.assertIn("Kein OBD-II gefunden", "\n".join(e.zeilen()))
        port, p = pruefer()
        port.zuendung = False
        self.assertFalse(p.test(fast_init=False).ok)

    def test_ohne_mode_09_und_ohne_echo(self):
        port, p = pruefer(echo=False)
        port.steuergeraete[0x33].stumm = {(0x09, 0x00)}
        e = p.test()
        self.assertTrue(e.ok)
        self.assertIsNone(e.fin)
        self.assertIn("keine Antwort auf Mode 09", e.fin_hinweis)
        self.assertNotIn(h("09 02"), port.steuergeraete[0x33].anfragen)

    def test_readiness_nach_dem_loeschen_offen(self):
        port, p = pruefer()
        motor = port.steuergeraete[0x01]
        motor.fehler.clear()
        motor.geloescht += 1
        r = p.test().readiness[1]
        self.assertFalse(r.mil)
        self.assertEqual(r.fehler, 0)
        self.assertFalse(any(m.fertig for m in r.monitore[3:] if m.vorhanden))

    def test_zeitwaechter_bricht_ab(self):
        port, p = pruefer()
        self.assertTrue(p.verbinden())
        p.timing = dataclasses.replace(SCHNELL, kwp_p4_frist=0.005)
        p.z = dataclasses.replace(ZEITEN, p4=0.001)
        with mock.patch.object(obd2, "_genau_warten", lambda s: time.sleep(0.03)):
            with self.assertRaises(ProtocolError):
                p.anfrage(0x01, 0x00)
        self.assertEqual(port.steuergeraete[0x33].anfragen, [], "nur ein Teil kam an")


class Sitzung(unittest.TestCase):
    def test_trennt_vorher_und_wartet_danach(self):
        ereignisse = []
        s = DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=False), SCHNELL,
                        keepalive=0.05,
                        ereignis=lambda art, daten: ereignisse.append((art, daten))).start()
        try:
            s.verbinden(0x01).result(5)
            e = s.obd2_test().result(20)
            self.assertFalse(s.verbunden)
            self.assertTrue(any(a == "getrennt" for a, _ in ereignisse))
            # die OBD-Sitzung hält bis P3 max – vorher reizt vagdiag nichts
            self.assertGreater(s._pause_vor_reizung(0x17), 0.5)
            beginn = time.monotonic()
            s.verbinden(0x17).result(10)
            self.assertGreaterEqual(time.monotonic() - beginn, 0.5)
            reizungen = list(s._port.reizungen)
        finally:
            s.schliessen()
        self.assertTrue(e.ok and e.sim)
        self.assertEqual(reizungen, [0x01, 0x33, 0x17])

    def test_ohne_antwort_keine_lange_pause(self):
        s = DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=False), SCHNELL,
                        keepalive=0.05).start()
        try:
            s._port_oeffnen()
            del s._port.steuergeraete[0x33]
            e = s.obd2_test(fast_init=False).result(20)
            self.assertFalse(e.ok)
            self.assertLess(s._pause_vor_reizung(0x01), 0.2)
        finally:
            s.schliessen()


if __name__ == "__main__":
    unittest.main()

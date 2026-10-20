"""Tests gegen den Byte-Simulator.  Start: python -m unittest -v"""

import time
import unittest

from vagdiag import fehler, messwerte
from vagdiag.kline import KLine
from vagdiag.kw1281 import (KW1281, NoResponse, NotAvailable, ProtocolError,
                            Timing, UnsupportedProtocol)
from vagdiag.port import bits_5baud
from vagdiag.session import DiagSession
from vagdiag.sim import sim_port

SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0)


def verbinden(adresse=0x01, echo=True, bauds=(10400, 9600)):
    port = sim_port(echo=echo)
    proto = KW1281(KLine(port), SCHNELL)
    info = proto.connect(adresse, bauds)
    return port, proto, info


class Reizung(unittest.TestCase):
    def test_adresse_01(self):
        # 0x01 hat ein gesetztes Bit → ungerade Parität = 0
        self.assertEqual(bits_5baud(0x01), [0, 1, 0, 0, 0, 0, 0, 0, 0, 1])

    def test_adresse_17(self):
        # 0x17 = 001 0111 (vier Einsen) → Paritätsbit 1 → 0x97
        self.assertEqual(bits_5baud(0x17), [0, 1, 1, 1, 0, 1, 0, 0, 1, 1])


class Verbindungsaufbau(unittest.TestCase):
    def test_mit_echo(self):
        _, proto, info = verbinden(echo=True)
        self.assertTrue(proto.verbunden)
        self.assertIs(info.echo, True)
        self.assertEqual(info.keyword, 1281)
        self.assertEqual(info.teilenummer, "SIM906032")
        self.assertIn("SIMULATION", info.bauteil)
        self.assertEqual(info.zusatzdaten, ["00 3E 0A 81 00"])

    def test_ohne_echo(self):
        _, proto, info = verbinden(echo=False)
        self.assertTrue(proto.verbunden)
        self.assertIs(info.echo, False)
        self.assertEqual(info.teilenummer, "SIM906032")

    def test_automatische_baudrate(self):
        # Kombi läuft mit 9600 Baud, erster Versuch mit 10400 muss scheitern
        _, proto, info = verbinden(0x17)
        self.assertEqual(info.baud, 9600)
        self.assertEqual(info.teilenummer, "SIM920800")

    def test_keine_antwort(self):
        with self.assertRaises(NoResponse):
            verbinden(0x46)

    def test_kwp2000_erkannt(self):
        with self.assertRaises(UnsupportedProtocol) as ctx:
            verbinden(0x15)
        self.assertEqual(ctx.exception.protocol, "KWP2000")


class Funktionen(unittest.TestCase):
    def setUp(self):
        self.port, self.proto, _ = verbinden()

    def test_fehler_lesen(self):
        liste = self.proto.fehler_lesen()
        self.assertEqual([f.code for f in liste], [16486, 16684])
        f = liste[0]
        self.assertEqual(f.p_code, "P0102")
        self.assertTrue(f.sporadisch)
        self.assertEqual(f.fehlerart_text, "35-10")
        self.assertEqual(f.beschreibung, "Luftmassenmesser: Signal zu klein")

    def test_fehler_loeschen(self):
        rest = self.proto.fehler_loeschen()
        self.assertEqual(rest, [])
        self.assertEqual(self.proto.fehler_lesen(), [])
        self.assertTrue(self.proto.verbunden)

    def test_messwerte_gruppe_4(self):
        werte = self.proto.gruppe_lesen(4)
        self.assertEqual(len(werte), 4)
        drehzahl, spannung, kuehlmittel, ansaugluft = werte
        self.assertEqual(drehzahl.einheit, "/min")
        self.assertTrue(750 <= drehzahl.wert <= 900, drehzahl)
        self.assertEqual(spannung.einheit, "V")
        self.assertTrue(13.5 <= spannung.wert <= 14.1, spannung)
        self.assertTrue(88 <= kuehlmittel.wert <= 92, kuehlmittel)
        self.assertTrue(23 <= ansaugluft.wert <= 27, ansaugluft)

    def test_gruppe_nicht_belegt_beendet_nichts(self):
        with self.assertRaises(NotAvailable):
            self.proto.gruppe_lesen(99)
        self.assertTrue(self.proto.verbunden)
        self.proto.keep_alive()
        self.assertEqual(len(self.proto.gruppe_lesen(1)), 4)

    def test_viele_bloecke_zaehler_ueberlauf(self):
        for _ in range(150):  # >255 Blöcke insgesamt
            self.proto.keep_alive()
        self.assertEqual(len(self.proto.gruppe_lesen(2)), 4)

    def test_verstummtes_steuergeraet(self):
        self.port.steuergeraete[0x01].gruppen[7] = None
        with self.assertRaises(ProtocolError):
            self.proto.gruppe_lesen(7)
        self.assertFalse(self.proto.verbunden)

    def test_trennen_und_neu(self):
        self.proto.trennen()
        self.assertFalse(self.proto.verbunden)
        info = self.proto.connect(0x01)
        self.assertEqual(info.teilenummer, "SIM906032")


class Kilometerstand(unittest.TestCase):
    def test_kombi_gruppe_2(self):
        _, proto, _ = verbinden(0x17)
        km = proto.gruppe_lesen(2)[0]
        self.assertEqual(km.einheit, "km")
        self.assertEqual(km.wert, 187430)
        self.assertEqual(km.text, "187430 km")


class Formeln(unittest.TestCase):
    def test_bekannte_werte(self):
        self.assertEqual(messwerte.umrechnen(1, 1, 200, 20).wert, 800)
        self.assertAlmostEqual(messwerte.umrechnen(1, 5, 10, 190).wert, 90.0)
        self.assertAlmostEqual(messwerte.umrechnen(1, 6, 100, 138).wert, 13.8)
        self.assertEqual(messwerte.umrechnen(1, 6, 100, 138).text, "13.8 V")
        self.assertEqual(messwerte.umrechnen(1, 44, 14, 7).text, "14:07 h:min")

    def test_unbekannter_typ_zeigt_rohwert(self):
        m = messwerte.umrechnen(2, 200, 5, 6)
        self.assertFalse(m.bekannt)
        self.assertEqual(m.text, "Typ 200: 5/6")

    def test_division_durch_null(self):
        self.assertEqual(messwerte.umrechnen(1, 61, 0, 140).text, "—")


class PCodes(unittest.TestCase):
    def test_umrechnung(self):
        self.assertEqual(fehler.p_code(16486), "P0102")
        self.assertEqual(fehler.p_code(16684), "P0300")
        self.assertEqual(fehler.p_code(17978), "P1570")
        self.assertEqual(fehler.p_code(18010), "P1602")
        self.assertIsNone(fehler.p_code(532))


class Sitzung(unittest.TestCase):
    def test_keepalive_und_auftraege(self):
        ereignisse = []
        s = DiagSession(sim_port, SCHNELL, keepalive=0.05,
                        ereignis=lambda art, d: ereignisse.append(art)).start()
        try:
            info = s.verbinden(0x01).result(5)
            self.assertEqual(info.teilenummer, "SIM906032")
            zaehler_vorher = s._proto.zaehler
            time.sleep(0.4)  # nur Keep-Alive
            self.assertNotEqual(s._proto.zaehler, zaehler_vorher)
            self.assertTrue(s.verbunden)
            werte = s.gruppe_lesen(4).result(5)
            self.assertEqual(werte[1].einheit, "V")
            self.assertEqual(len(s.fehler_lesen().result(5)), 2)
            s.trennen().result(5)
            self.assertFalse(s.verbunden)
            info17 = s.verbinden(0x17, (10400, 9600)).result(10)
            self.assertEqual(info17.baud, 9600)
        finally:
            s.schliessen()
        self.assertEqual(ereignisse.count("verbunden"), 2)
        self.assertIn("getrennt", ereignisse)

    def test_verlust_wird_gemeldet(self):
        ereignisse = []
        s = DiagSession(sim_port, SCHNELL, keepalive=0.05,
                        ereignis=lambda art, d: ereignisse.append(art)).start()
        try:
            s.verbinden(0x01).result(5)
            s._port.steuergeraete[0x01].gruppen[9] = None
            with self.assertRaises(ProtocolError):
                s.gruppe_lesen(9).result(5)
            self.assertFalse(s.verbunden)
            self.assertIn("getrennt", ereignisse)
        finally:
            s.schliessen()


if __name__ == "__main__":
    unittest.main()

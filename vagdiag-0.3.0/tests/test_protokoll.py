"""Tests gegen den Byte-Simulator und mit echten Daten aus dem Polo-Log.
Start: python -m unittest -v"""

import csv
import tempfile
import time
import unittest
from pathlib import Path

from vagdiag import beschriftung, einstellungen, fehler, kilometerstand, messwerte, texte
from vagdiag.aufzeichnung import CsvAufzeichnung
from vagdiag.kline import KLine
from vagdiag.kw1281 import (ASCII, KW1281, Abgebrochen, Block, Nak, NoResponse,
                            NotAvailable, ProtocolError, Timing, UnsupportedProtocol,
                            Verbindung)
from vagdiag.port import bits_5baud
from vagdiag.session import DiagSession
from vagdiag.sim import sim_port

SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0)


def schneller_port(echo=True):
    return sim_port(echo=echo, echtzeit=False)


def verbinden(adresse=0x01, echo=True, bauds=(10400, 9600)):
    port = schneller_port(echo)
    proto = KW1281(KLine(port), SCHNELL)
    info = proto.connect(adresse, bauds)
    return port, proto, info


def h(text):
    return bytes.fromhex(text)


class Reizung(unittest.TestCase):
    def test_adresse_01(self):
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
        self.assertEqual((info.codierung, info.werkstattcode), (31, 12345))
        self.assertEqual(info.zusatzdaten, [])

    def test_ohne_echo(self):
        _, proto, info = verbinden(echo=False)
        self.assertTrue(proto.verbunden)
        self.assertIs(info.echo, False)

    def test_automatische_baudrate(self):
        _, _, info = verbinden(0x03)        # ABS antwortet wie im Polo mit 9600 Baud
        self.assertEqual(info.baud, 9600)
        _, _, info = verbinden(0x17)        # Kombi wie im Polo mit 10400 Baud
        self.assertEqual(info.baud, 10400)

    def test_zusatzkennung_wegfahrsperre(self):
        _, proto, info = verbinden(0x25)
        self.assertTrue(info.hat_zusatzkennung)
        self.assertEqual(info.teilenummer, "SIM953257")   # Bit 7 entfernt
        self.assertEqual(info.zusatzkennung, "WVWZZZ6KZ1SIM0001VWZ7Z0S0000001")
        self.assertTrue(proto.verbunden)
        self.assertEqual(len(proto.gruppe_lesen(1)), 4)

    def test_keine_antwort(self):
        with self.assertRaises(NoResponse):
            verbinden(0x46)

    def test_kwp2000_erkannt(self):
        with self.assertRaises(UnsupportedProtocol) as ctx:
            verbinden(0x56)
        self.assertEqual(ctx.exception.protocol, "KWP2000")


class EchteKennungen(unittest.TestCase):
    """Bytes aus dem Log deines Polos (19.10.2026)."""

    def v(self, *bloecke):
        return Verbindung(1, "KW1281", 1281, 10400, True,
                          [Block(i, ASCII, h(b)) for i, b in enumerate(bloecke)])

    def test_motor(self):
        v = self.v("36 4B 30 39 30 36 30 33 32 4D 20 20",
                   "4D 45 37 2E 35 2E 31 30 20 20 20 20 20 20 20 20 20 20 20 20",
                   "53 30 38 30", "00 00 16 19 02")
        self.assertEqual(v.teilenummer, "6K0906032M")
        self.assertEqual(v.bauteil, "ME7.5.10            S080")
        self.assertEqual((v.codierung, v.werkstattcode), (11, 6402))
        self.assertFalse(v.hat_zusatzkennung)

    def test_wegfahrsperre_bit7(self):
        v = self.v("B6 58 30 39 35 33 32 35 37 20 20 20", "49 4D 4D 4F 20 20 20 20 20 20 20 20",
                   "20 20 20 20 20 20 20 20 30 30 30 32", "00 00 02 19 02")
        self.assertEqual(v.teilenummer, "6X0953257")
        self.assertTrue(v.hat_zusatzkennung)

    def test_kombi_und_abs(self):
        kombi = self.v("36 4B 39 39 32 30 38 30 36 20 20 20", "4B 4F 4D 42 49 49 4E 53 54 52 55 4D",
                       "45 4E 54 20 54 52 57 20 56 30 34", "00 01 1A D4 31")
        self.assertEqual(kombi.bauteil, "KOMBIINSTRUMENT TRW V04")
        self.assertEqual((kombi.codierung, kombi.werkstattcode), (141, 54321))
        abs_ = self.v("36 58 30 39 30 37 33 37 39 20 42 20", "41 42 53 20 20 20 20 20 33 30 20 49",
                      "45 20 43 41 4E 20 20 56 30 30 34", "00 31 44 2B 67")
        self.assertEqual((abs_.codierung, abs_.werkstattcode), (6306, 11111))


class EchteMesswerte(unittest.TestCase):
    def texte(self, hexdaten):
        return [w.text for w in messwerte.gruppe_auswerten(h(hexdaten))]

    def test_anlassen(self):
        # Gruppe 004 beim Anlassen, kurz vor dem Abbruch
        self.assertEqual(self.texte("01 C8 04 15 46 8D 05 0A 83 05 0A 7B"),
                         ["160 /min", "9,87 V", "31 °C", "23 °C"])

    def test_leerlauf(self):
        self.assertEqual(self.texte("01 C8 15 21 85 1D 0F 29 0E 12 FA 22"),
                         ["840 /min", "21,8 %", "5,7 ms", "340 mbar"])

    def test_kombi_kilometerstand_ungueltig(self):
        werte = messwerte.gruppe_auswerten(h("24 FF FF 13 64 15 40 54 54 25 00 00"))
        self.assertFalse(werte[0].gueltig)
        self.assertEqual(werte[0].text, "kein Wert (FF FF)")
        self.assertIsNone(werte[0].zahl)
        self.assertEqual(werte[1].text, "21 l")
        self.assertEqual(werte[2].text, "168 Ω")
        self.assertEqual(werte[3].text, "–")                 # Text 0 = leeres Feld
        self.assertIn("Text Nr. 0", werte[3].roh)

    def test_kombi_uhrzeit(self):
        werte = messwerte.gruppe_auswerten(h("07 64 00 01 C8 00 25 00 1E 2C 11 19"))
        self.assertEqual([w.text for w in werte],
                         ["0 km/h", "0 /min", "Öldruck 2 < min", "17:25"])

    def test_kombi_laufender_motor(self):
        # 18:24:05, Motor läuft: Text 31 = Öldruckschalter 2 in Ordnung
        werte = messwerte.gruppe_auswerten(h("07 64 00 01 C8 15 25 00 1F 2C 12 18"))
        self.assertEqual([w.text for w in werte],
                         ["0 km/h", "840 /min", "Öldruck 2 i. O.", "18:24"])
        werte = messwerte.gruppe_auswerten(h("05 0A 98 25 00 00 25 00 00"))
        self.assertEqual([w.text for w in werte], ["52 °C", "–", "–"])

    def test_wegfahrsperre(self):
        texte = self.texte
        self.assertEqual(texte("36 28 A0 11 20 31 11 20 31 11 20 31"), ["10400", "1", "1", "1"])
        self.assertEqual(texte("11 20 31 11 20 31 11 20 31 11 20 32"), ["1", "1", "1", "2"])
        self.assertEqual(texte("11 20 31 11 20 30 11 20 31 11 20 36"), ["1", "0", "1", "6"])

    def test_abs_platzhalter(self):
        self.assertEqual(self.texte("07 64 FF 07 64 FF 07 64 FF 07 64 FF"), ["255 km/h"] * 4)
        self.assertEqual(self.texte("07 64 00 07 64 00 07 64 00 07 64 00"), ["0 km/h"] * 4)

    def test_motor_beim_start(self):
        # 18:21:45: Anlasser dreht mit 200 /min, tiefster erfasster Wert
        self.assertEqual(self.texte("01 C8 05 15 46 95 05 0A 82 05 0A 78"),
                         ["200 /min", "10,43 V", "30 °C", "20 °C"])


class Formeln(unittest.TestCase):
    def test_bekannte_werte(self):
        self.assertEqual(messwerte.umrechnen(1, 1, 200, 20).zahl, 800)
        self.assertEqual(messwerte.umrechnen(1, 6, 100, 138).text, "13,8 V")
        self.assertEqual(messwerte.umrechnen(1, 36, 73, 55).text, "187430 km")

    def test_zuendwinkel_richtung(self):
        # Typ 4: b < 127 heißt vor OT
        self.assertEqual(messwerte.umrechnen(1, 4, 100, 115).text, "12 ° v.OT")
        self.assertEqual(messwerte.umrechnen(1, 4, 100, 130).text, "3 ° n.OT")
        # Typ 27: b > 128 heißt vor OT
        self.assertEqual(messwerte.umrechnen(1, 27, 75, 144).text, "12,0 ° v.OT")

    def test_bitfeld_mit_maske(self):
        self.assertEqual(messwerte.umrechnen(1, 16, 0x0F, 0xFF).text, "00001111")

    def test_unbekannter_typ_zeigt_rohwert(self):
        m = messwerte.umrechnen(2, 200, 5, 6)
        self.assertFalse(m.bekannt)
        self.assertEqual(m.text, "Typ 200: 5/6")

    def test_division_durch_null(self):
        self.assertEqual(messwerte.umrechnen(1, 61, 0, 140).text, "—")

    def test_minmax(self):
        mm = messwerte.MinMax()
        for b in (138, 99, 141):
            mm.erfassen("u", messwerte.umrechnen(2, 21, 100, b))
        self.assertEqual(mm.text("u"), "min 9,9 · max 14,1 V")


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

    def test_fehler_loeschen(self):
        self.assertEqual(self.proto.fehler_loeschen(), [])
        self.assertEqual(self.proto.fehler_lesen(), [])

    def test_messwerte_gruppe_4(self):
        drehzahl, spannung, kuehlmittel, ansaugluft = self.proto.gruppe_lesen(4)
        self.assertTrue(750 <= drehzahl.zahl <= 900, drehzahl)
        self.assertEqual(spannung.einheit, "V")
        self.assertTrue(13.5 <= spannung.zahl <= 14.1, spannung)
        self.assertTrue(88 <= kuehlmittel.zahl <= 92, kuehlmittel)

    def test_gruppe_nicht_belegt_beendet_nichts(self):
        with self.assertRaises((Nak, NotAvailable)):
            self.proto.gruppe_lesen(99)
        self.assertTrue(self.proto.verbunden)
        self.proto.keep_alive()
        self.assertEqual(len(self.proto.gruppe_lesen(1)), 4)

    def test_viele_bloecke_zaehler_ueberlauf(self):
        for _ in range(150):
            self.proto.keep_alive()
        self.assertEqual(len(self.proto.gruppe_lesen(2)), 4)

    def test_gestoertes_komplement_wird_toleriert(self):
        self.port.steuergeraete[0x01].stoerung_nach(1)
        with self.assertLogs("vagdiag.proto", "WARNING") as logs:
            werte = self.proto.gruppe_lesen(4)
        self.assertEqual(len(werte), 4)
        self.assertTrue(self.proto.verbunden)
        self.assertIn("Störung", logs.output[0])

    def test_ohne_toleranz_bricht_ab(self):
        self.proto.toleranz = False
        self.port.steuergeraete[0x01].stoerung_nach(1)
        with self.assertRaises(ProtocolError):
            self.proto.gruppe_lesen(4)
        self.assertFalse(self.proto.verbunden)

    def test_verstummtes_steuergeraet(self):
        self.port.steuergeraete[0x01].gruppen[7] = None
        with self.assertRaises(ProtocolError):
            self.proto.gruppe_lesen(7)
        self.assertFalse(self.proto.verbunden)

    def test_trennen_und_neu(self):
        self.proto.trennen()
        self.assertFalse(self.proto.verbunden)
        self.assertEqual(self.proto.connect(0x01).teilenummer, "SIM906032")


class PCodes(unittest.TestCase):
    def test_umrechnung(self):
        self.assertEqual(fehler.p_code(16486), "P0102")
        self.assertEqual(fehler.p_code(17978), "P1570")
        self.assertEqual(fehler.p_code(18010), "P1602")
        self.assertIsNone(fehler.p_code(532))


class Sitzung(unittest.TestCase):
    def neu(self, ereignisse, **kw):
        def merken(art, daten):
            ereignisse.append((art, daten))
        return DiagSession(schneller_port, SCHNELL, keepalive=0.05,
                           ereignis=merken, **kw).start()

    def test_keepalive_und_auftraege(self):
        ereignisse = []
        s = self.neu(ereignisse)
        try:
            self.assertEqual(s.verbinden(0x01).result(5).teilenummer, "SIM906032")
            zaehler = s._proto.zaehler
            time.sleep(0.4)
            self.assertNotEqual(s._proto.zaehler, zaehler)
            self.assertEqual(s.gruppe_lesen(4).result(5)[1].einheit, "V")
            s.trennen().result(5)
            self.assertEqual(s.verbinden(0x03).result(10).baud, 9600)
        finally:
            s.schliessen()
        arten = [a for a, _ in ereignisse]
        self.assertEqual(arten.count("verbunden"), 2)
        self.assertIn(("baud", (0x03, 9600)), ereignisse)

    def test_gemerkte_baudrate_zuerst(self):
        s = self.neu([], baudraten={0x03: 9600})
        try:
            with _kein_fehlversuch(self, 0x03, 9600):
                self.assertEqual(s.verbinden(0x03).result(5).baud, 9600)
        finally:
            s.schliessen()

    def test_wechsel_zu_fehlendem_steuergeraet(self):
        """Antwortet das neue Steuergerät nicht, ist das kein „Verbindungsverlust“."""
        ereignisse = []
        s = self.neu(ereignisse)
        try:
            s.verbinden(0x01).result(5)
            with self.assertLogs("vagdiag.proto", "INFO") as logs:
                with self.assertRaises(NoResponse):
                    s.verbinden(0x02).result(5)
                time.sleep(0.1)
        finally:
            s.schliessen()
        self.assertFalse([z for z in logs.output if "Verbindung verloren" in z], logs.output)
        self.assertTrue([z for z in logs.output if "Keine Verbindung zu 02" in z])
        getrennt = [d for a, d in ereignisse if a == "getrennt"]
        self.assertEqual(getrennt, [{"grund": "Verbindung beendet", "neu_verbinden": False}])

    def test_neuverbinden_nach_abbruch(self):
        ereignisse = []
        s = self.neu(ereignisse)
        try:
            s.verbinden(0x01).result(5)
            s._port.steuergeraete[0x01].ausfall_nach(1)   # zweite Abfrage verstummt
            s.messung_starten()
            self.assertEqual(len(s.gruppe_lesen(4, neu_verbinden=True).result(10)), 4)
            werte = s.gruppe_lesen(4, neu_verbinden=True).result(15)
            self.assertEqual(len(werte), 4)
            self.assertTrue(s.verbunden)
        finally:
            s.schliessen()
        getrennt = [d for a, d in ereignisse if a == "getrennt"]
        self.assertTrue(getrennt and getrennt[0]["neu_verbinden"])
        self.assertEqual([a for a, _ in ereignisse].count("verbunden"), 2)

    def test_abbruch_waehrend_neuverbinden(self):
        s = self.neu([])
        try:
            s.verbinden(0x01).result(5)
            port = s._port
            port.steuergeraete[0x01].ausfall_nach(0)
            del port.steuergeraete[0x01]   # kommt nicht wieder
            s.messung_starten()
            future = s.gruppe_lesen(4, neu_verbinden=True)
            time.sleep(1.5)
            s.abbrechen()
            with self.assertRaises(Abgebrochen):
                future.result(10)
        finally:
            s.schliessen()

    def test_gruppensuche(self):
        ereignisse = []
        s = self.neu(ereignisse)
        try:
            s.verbinden(0x01).result(5)
            gefunden = s.gruppen_suchen(1, 10).result(10)
        finally:
            s.schliessen()
        self.assertEqual(sorted(gefunden), [1, 2, 4])
        self.assertEqual(len([a for a, _ in ereignisse if a == "suche"]), 10)


class _kein_fehlversuch:
    """Prüft, dass keine Reizung mit der falschen Baudrate passiert."""

    def __init__(self, test, adresse=0x03, baud=9600):
        self.test = test
        self.adresse = adresse
        self.baud = baud

    def __enter__(self):
        self.ctx = self.test.assertLogs("vagdiag.proto", "INFO")
        self.logs = self.ctx.__enter__()

    def __exit__(self, *exc):
        self.ctx.__exit__(*exc)
        reizungen = [z for z in self.logs.output if f"Reize Adresse {self.adresse:02X}" in z]
        self.test.assertEqual(len(reizungen), 1, reizungen)
        self.test.assertIn(str(self.baud), reizungen[0])


class Echtzeit(unittest.TestCase):
    def test_zeitverhalten_wie_im_auto(self):
        port = sim_port(echtzeit=True)
        proto = KW1281(KLine(port))
        t0 = time.monotonic()
        proto.connect(0x01)
        dauer_verbinden = time.monotonic() - t0
        t1 = time.monotonic()
        for _ in range(3):
            proto.gruppe_lesen(4)
        pro_abfrage = (time.monotonic() - t1) / 3
        self.assertTrue(2.0 < dauer_verbinden < 4.5, dauer_verbinden)
        self.assertTrue(0.2 < pro_abfrage < 0.6, pro_abfrage)


class Aufzeichnung(unittest.TestCase):
    def test_csv_format(self):
        with tempfile.TemporaryDirectory() as ordner:
            a = CsvAufzeichnung(Path(ordner) / "test.csv")
            a.messwerte(4, messwerte.gruppe_auswerten(h("01 C8 04 15 46 8D 05 0A 83 05 0A 7B")))
            a.ereignis("Verbindung verloren: Test")
            a.schliessen()
            with open(a.pfad, encoding="utf-8") as datei:
                zeilen = list(csv.reader(datei, delimiter=";"))
        self.assertEqual(zeilen[0][:4], ["Zeit", "Sekunden", "Gruppe", "Feld 1"])
        self.assertEqual(zeilen[1][2:6], ["004", "160", "/min", "9,87"])
        self.assertEqual(zeilen[1][6], "V")
        self.assertEqual(zeilen[2][-1], "Verbindung verloren: Test")


class Einstellungen(unittest.TestCase):
    def test_speichern_und_laden(self):
        with tempfile.TemporaryDirectory() as ordner:
            alt = einstellungen.DATEI
            einstellungen._zuruecksetzen_fuer_tests(Path(ordner) / "e.json")
            try:
                self.assertTrue(einstellungen.laden()["csv_automatisch"])
                einstellungen.speichern(csv_ordner=str(Path(ordner) / "csv"))
                einstellungen.baud_merken(0x17, 9600)
                einstellungen._zuruecksetzen_fuer_tests(Path(ordner) / "e.json")
                self.assertEqual(einstellungen.baud_fuer(0x17), 9600)
                self.assertEqual(einstellungen.ordner("csv_ordner"), Path(ordner) / "csv")
            finally:
                einstellungen._zuruecksetzen_fuer_tests(alt)



class Anpassung(unittest.TestCase):
    """Anpassungskanäle – ausschließlich lesen."""

    def test_kanal_lesen(self):
        port, proto, _ = verbinden(0x17)
        a = proto.anpassung_lesen(9)
        self.assertEqual((a.kanal, a.wert, a.hex), (9, 12345, "3039"))
        self.assertEqual(a.text, "Kanal 09: 12345 (hex 3039)")
        self.assertTrue(proto.verbunden)

    def test_unbekannter_kanal_beendet_nichts(self):
        _, proto, _ = verbinden(0x17)
        with self.assertRaises(Nak):
            proto.anpassung_lesen(3)
        self.assertTrue(proto.verbunden)
        self.assertEqual(proto.anpassung_lesen(9).wert, 12345)

    def test_kanal_00_wird_nie_gesendet(self):
        port, proto, _ = verbinden(0x17)
        for kanal in (0, 256, -1):
            with self.assertRaises(ValueError):
                proto.anpassung_lesen(kanal)
        self.assertFalse([d for t, d in port.steuergeraete[0x17].anfragen if t == 0x21])

    def test_suche_schreibt_nie(self):
        ereignisse = []
        s = DiagSession(schneller_port, SCHNELL, keepalive=0.05,
                        ereignis=lambda a, d: ereignisse.append((a, d))).start()
        try:
            s.verbinden(0x17).result(5)
            gefunden = s.anpassungen_suchen(0, 20).result(20)
            anfragen = list(s._port.steuergeraete[0x17].anfragen)
            km = s.kilometerstand().result(5)
        finally:
            s.schliessen()
        self.assertEqual(list(gefunden), [9])
        gelesen = [d[0] for t, d in anfragen if t == 0x21]
        self.assertEqual(gelesen, list(range(1, 21)))          # 1–20, nie Kanal 00
        titel = {t for t, _ in anfragen}
        self.assertFalse(titel & {0x22, 0x2A, 0x2B, 0x28, 0x04, 0x10, 0x05},
                         "nur lesende Blöcke erlaubt")
        self.assertEqual(len([a for a, _ in ereignisse if a == "anpassung_suche"]), 20)
        self.assertEqual(km.km, 123450)

    def test_kilometerstand_aus_kanal_09(self):
        _, proto, _ = verbinden(0x17)
        km = kilometerstand.lesen(proto)
        self.assertEqual(km.km, 123450)
        self.assertFalse(km.bestaetigt)
        self.assertEqual(km.quelle, "Anpassungskanal 09")
        self.assertEqual(km.zeilen[0], "Kilometerstand: 123.450 km")
        self.assertIn("Messwertgruppe 002, Feld 1: kein Wert (FF FF)", km.geprueft)

    def test_kilometerstand_aus_gruppe_002(self):
        # Kombi, das den Kilometerstand im Messwertblock meldet (z. B. VDO)
        port = schneller_port()
        port.steuergeraete[0x17].gruppen[2] = lambda: [(36, 73, 55), (19, 100, 21),
                                                       (64, 81, 81), (5, 10, 110)]
        proto = KW1281(KLine(port), SCHNELL)
        proto.connect(0x17)
        km = kilometerstand.lesen(proto)
        self.assertEqual((km.km, km.bestaetigt), (187430, True))
        self.assertEqual(km.quelle, "Messwertgruppe 002, Feld 1")
        self.assertFalse([t for t, _ in port.steuergeraete[0x17].anfragen if t == 0x21])

    def test_kein_kilometerstand(self):
        port = schneller_port()
        port.steuergeraete[0x17].anpassungen.clear()
        proto = KW1281(KLine(port), SCHNELL)
        proto.connect(0x17)
        km = kilometerstand.lesen(proto)
        self.assertIsNone(km.km)
        self.assertIn("weder in Messwertgruppe 002", km.zeilen[0])
        self.assertTrue(proto.verbunden)


class Beschriftungen(unittest.TestCase):
    def setUp(self):
        self._alt = beschriftung.EIGENE_DATEI
        self._tmp = tempfile.TemporaryDirectory()
        beschriftung.EIGENE_DATEI = Path(self._tmp.name) / "beschriftungen.json"
        beschriftung.neu_laden()

    def tearDown(self):
        beschriftung.EIGENE_DATEI = self._alt
        beschriftung.neu_laden()
        self._tmp.cleanup()

    def motor(self, *bloecke):
        return Verbindung(1, "KW1281", 1281, 10400, True,
                          [Block(i, ASCII, h(b)) for i, b in enumerate(bloecke)])

    def echter_motor(self):
        return self.motor("36 4B 30 39 30 36 30 33 32 4D 20 20",
                          "4D 45 37 2E 35 2E 31 30 20 20 20 20 20 20 20 20 20 20 20 20")

    def test_motor_me75(self):
        werte = messwerte.gruppe_auswerten(h("01 C8 05 15 46 95 05 0A 82 05 0A 78"))
        self.assertEqual(beschriftung.namen(self.echter_motor(), 4, werte),
                         ["Motordrehzahl", "Bordspannung", "Kühlmitteltemperatur",
                          "Ansauglufttemperatur"])
        werte = messwerte.gruppe_auswerten(h("01 C8 15 21 85 1D 0F 29 0E 12 FA 22"))
        self.assertEqual(beschriftung.namen(self.echter_motor(), 2, werte)[3], "Saugrohrdruck")

    def test_einheiten_passen_nicht(self):
        # Gruppe 004 mit anderem Aufbau (z. B. anderes Steuergerät): lieber keine Namen
        werte = messwerte.gruppe_auswerten(h("01 C8 15 21 85 1D 0F 29 0E 12 FA 22"))
        self.assertEqual(beschriftung.namen(self.echter_motor(), 4, werte), [""] * 4)

    def test_anderes_steuergeraet(self):
        werte = messwerte.gruppe_auswerten(h("01 C8 05 15 46 95 05 0A 82 05 0A 78"))
        fremd = self.motor("30 33 32 39 30 36 30 33 32 20 20 20", "4D 4F 54 52 4F 4E 49 43 20 4D 35 2E")
        self.assertEqual(beschriftung.namen(fremd, 4, werte), [""] * 4)
        self.assertEqual(beschriftung.namen(None, 4, werte), [""] * 4)

    def test_kombi_und_abs(self):
        kombi = Verbindung(0x17, "KW1281", 1281, 10400, True, [])
        werte = messwerte.gruppe_auswerten(h("24 FF FF 13 64 15 40 51 51 25 00 00"))
        self.assertEqual(beschriftung.namen(kombi, 2, werte),
                         ["Kilometerstand", "Tankinhalt", "Tankgeber", ""])
        self.assertEqual(beschriftung.mit_namen(beschriftung.namen(kombi, 2, werte), werte)[:2],
                         ["Kilometerstand = kein Wert (FF FF)", "Tankinhalt = 21 l"])
        abs_ = Verbindung(0x03, "KW1281", 1281, 9600, True, [])
        werte = messwerte.gruppe_auswerten(h("07 64 00 07 64 00 07 64 00 07 64 00"))
        self.assertEqual(beschriftung.namen(abs_, 1, werte)[0], "Rad vorn links")
        self.assertEqual(beschriftung.namen(abs_, 2, werte), [""] * 4)

    def test_eigene_bezeichnungen(self):
        beschriftung.EIGENE_DATEI.write_text(
            '{"25": {"2": ["Start erlaubt", null, "Schlüssel lesbar", "Schlüssel"]}}',
            encoding="utf-8")
        beschriftung.neu_laden()
        immo = Verbindung(0x25, "KW1281", 1281, 9600, True, [])
        werte = messwerte.gruppe_auswerten(h("11 20 31 11 20 31 11 20 31 11 20 32"))
        self.assertEqual(beschriftung.namen(immo, 2, werte),
                         ["Start erlaubt", "", "Schlüssel lesbar", "Schlüssel"])

    def test_kaputte_datei(self):
        beschriftung.EIGENE_DATEI.write_text("{kaputt", encoding="utf-8")
        beschriftung.neu_laden()
        werte = messwerte.gruppe_auswerten(h("01 C8 05 15 46 95 05 0A 82 05 0A 78"))
        with self.assertLogs("vagdiag.proto", "WARNING"):
            self.assertEqual(beschriftung.namen(self.echter_motor(), 4, werte)[1], "Bordspannung")


class Klartexte(unittest.TestCase):
    def setUp(self):
        self._alt = texte.EIGENE_TEXTE
        self._tmp = tempfile.TemporaryDirectory()
        texte.EIGENE_TEXTE = Path(self._tmp.name) / "texte.json"
        texte.neu_laden()

    def tearDown(self):
        texte.EIGENE_TEXTE = self._alt
        texte.neu_laden()
        self._tmp.cleanup()

    def test_tabelle_und_unbekannt(self):
        self.assertEqual(messwerte.umrechnen(1, 37, 0, 0x1F).text, "Öldruck 2 i. O.")
        self.assertEqual(messwerte.umrechnen(1, 37, 3, 0xE7).text, "Text Nr. 999")

    def test_eigene_texte(self):
        texte.EIGENE_TEXTE.write_text('{"999": "Testtext", "0x1F": "Öl ok"}', encoding="utf-8")
        texte.neu_laden()
        self.assertEqual(messwerte.umrechnen(1, 37, 3, 0xE7).text, "Testtext")
        self.assertEqual(messwerte.umrechnen(1, 37, 0, 0x1F).text, "Öl ok")


class SimulatorAufzeichnung(unittest.TestCase):
    def test_dateiname_und_beschriftung(self):
        with tempfile.TemporaryDirectory() as ordner:
            a = CsvAufzeichnung.neu(0x01, Path(ordner), sim=True)
            werte = messwerte.gruppe_auswerten(h("01 C8 05 15 46 95 05 0A 82 05 0A 78"))
            namen = ["Motordrehzahl", "Bordspannung", "", "Ansauglufttemperatur"]
            a.messwerte(4, werte, namen)
            a.messwerte(4, werte, namen)
            a.schliessen()
            self.assertTrue(a.pfad.name.startswith("sim-messwerte-01-"))
            with open(a.pfad, encoding="utf-8") as datei:
                zeilen = list(csv.reader(datei, delimiter=";"))
        self.assertEqual(zeilen[1][-1], "Simulator – keine echten Fahrzeugdaten")
        self.assertEqual(zeilen[2][-1], "Gruppe 004: Motordrehzahl | Bordspannung | Feld 3 | "
                                        "Ansauglufttemperatur")
        self.assertEqual([z[2] for z in zeilen[3:]], ["004", "004"])   # Namen nur einmal

    def test_echte_aufzeichnung_ohne_vorsilbe(self):
        with tempfile.TemporaryDirectory() as ordner:
            a = CsvAufzeichnung.neu(0x17, Path(ordner))
            a.schliessen()
            self.assertTrue(a.pfad.name.startswith("messwerte-17-"))
            with open(a.pfad, encoding="utf-8") as datei:
                self.assertEqual(len(list(csv.reader(datei, delimiter=";"))), 1)


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Tests gegen den Byte-Simulator und mit echten Daten aus dem Polo-Log.
Start: python -m unittest -v"""

import csv
import dataclasses
import tempfile
import threading
import time
import unittest
from pathlib import Path

from vagdiag import (aufzeichnung, beschriftung, einstellungen, fehler, kilometerstand,
                     messwerte, protokolldatei, sprache, texte)
from vagdiag.airbag import AirbagFremd, AirbagGesperrt, AirbagRisiko
from vagdiag.aufzeichnung import CsvAufzeichnung
from vagdiag.kline import KLine
from vagdiag.fahrtenschreiber import FAHRT, Besuch, FahrtPlan, Probe
from vagdiag.fahrtenschreiber import Fahrtenschreiber as Schreiber
from vagdiag.kw1281 import (ASCII, KW1281, Abgebrochen, Block, Nak, NoResponse,
                            NotAvailable, ProtocolError, Stoerung, Timing, Verbindung)
from vagdiag.port import bits_5baud
from vagdiag.session import DiagSession
from vagdiag.sim import SimEcu, SimFahrzeug, sim_port

# Zeitwächter großzügig: Der Simulator läuft hier nicht in Echtzeit, und Testrechner hängen
# manchmal selbst (virtuelle Maschinen bis 50 ms). Den Wächter mit den echten Fristen prüft
# test_sicherheit.Zeitwaechter.
SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0,
                 byte_frist=0.5, kwp_p4_frist=0.5)
# kurze Ruhe der Leitung nach dem Trennen – für Tests, in denen Besuche dicht folgen
KURZ_GETRENNT = dataclasses.replace(SCHNELL, trenn_pause=0.05)


def schneller_port(echo=True):
    return sim_port(echo=echo, echtzeit=False, fahrprofil=False)


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
        # Ausführliche Tests: test_kwp2000.py
        _, proto, info = verbinden(0x56)
        self.assertEqual((info.protokoll, info.keyword), ("KWP2000", 2027))
        self.assertTrue(proto.ist_kwp2000)
        self.assertEqual(info.teilenummer, "SIMKWP2000")


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

    def test_masse_pro_hub(self):
        # Typ 49 (Luftmasse) und 39/51 (Einspritzmenge) sind „pro Hub“, nicht „pro Stunde“
        self.assertEqual(messwerte.umrechnen(1, 49, 100, 200).text, "500 mg/Hub")
        self.assertEqual(messwerte.umrechnen(1, 39, 255, 20).einheit, "mg/Hub")
        self.assertEqual(messwerte.umrechnen(1, 51, 255, 148).einheit, "mg/Hub")
        try:
            sprache.setzen("en")
            self.assertEqual(messwerte.umrechnen(1, 49, 100, 200).text, "500 mg/stroke")
        finally:
            sprache.setzen("de")


class LangeFelder(unittest.TestCase):
    """Felder mit anderer Länge als drei Bytes (Aufbau wie in KLineKWP1281Lib)."""

    def texte(self, hexdaten):
        return [w.text for w in messwerte.gruppe_auswerten(h(hexdaten))]

    def test_text_mit_laenge(self):
        werte = messwerte.gruppe_auswerten(h("01 C8 15 5F 05 48 41 4C 4C 4F 05 0A 83"))
        self.assertEqual([w.text for w in werte], ["840 /min", "HALLO", "31 °C"])
        self.assertEqual([w.feld for w in werte], [1, 2, 3])
        self.assertEqual(werte[1].roh, "Typ 95, 5 Bytes: 48 41 4C 4C 4F")
        self.assertEqual(self.texte("5F 00 01 C8 15"), ["", "840 /min"])

    def test_bytes_mit_laenge(self):
        self.assertEqual(self.texte("76 03 01 AB FF 01 C8 15"), ["01 AB FF", "840 /min"])

    def test_text_bis_zum_ende(self):
        self.assertEqual(self.texte("01 C8 15 3F 54 45 58 54"), ["840 /min", "TEXT"])
        # endet wie ein C-Text am Nullbyte; Zeichen außerhalb von ASCII werden zu „?“
        self.assertEqual(self.texte("3F 41 42 25 00 00 25 00 00"), ["AB%"])
        self.assertEqual(self.texte("3F 4D B0 43"), ["M?C"])

    def test_variable_einheit(self):
        # a=1, Wort 123, d=11 (×1, eine Kommastelle), e=01 (V)
        self.assertEqual(self.texte("A0 01 00 7B 11 01 01 C8 15"), ["12,3 V", "840 /min"])
        self.assertEqual(self.texte("A0 01 00 7B 91 01"), ["-12,3 V"])     # Bit 7: negativ
        self.assertEqual(self.texte("A0 01 00 7B 11 81"), ["12,3 mV"])     # Vorsatz m
        self.assertEqual(self.texte("A0 02 01 F4 03 24"), ["3000 /min"])   # 2·500·3
        self.assertEqual(self.texte("A0 01 00 0A 01 3F"), ["10"])          # Einheit unbekannt
        # Kommastellen nennt das Feld selbst (d = 41: vier), mit Vorzeichen (d = C1)
        self.assertEqual(self.texte("A0 01 30 3A 41 01"), ["1,2346 V"])
        self.assertEqual(self.texte("A0 01 30 3A C1 01"), ["-1,2346 V"])
        self.assertEqual(self.texte("A0 03 00 0B 72 15"), ["0,0000066 s"])   # 3·11·2·10⁻⁷
        self.assertEqual(self.texte("A0 00 00 0B 72 15"), ["0,0000000 s"])   # a = 0
        werte = messwerte.gruppe_auswerten(h("A0 01 00 7B 11 01"))
        self.assertAlmostEqual(werte[0].zahl, 12.3)
        self.assertEqual(werte[0].roh, "Typ 160, 5 Bytes: 01 00 7B 11 01")

    def test_variable_einheit_zuendwinkel(self):
        # Einheit 23: Richtung im Vorzeichenbit, der Wert bleibt positiv
        self.assertEqual(self.texte("A0 01 00 64 91 23"), ["10,0 ° v.OT"])
        self.assertEqual(self.texte("A0 01 00 64 11 23"), ["10,0 ° n.OT"])
        try:
            sprache.setzen("en")
            self.assertEqual(self.texte("A0 01 00 64 91 23"), ["10.0 ° BTDC"])
            self.assertEqual(self.texte("A0 01 00 7B 11 82"), ["12.3 mVpp"])
            self.assertEqual(self.texte("A0 01 00 7B 11 9A"), ["12.3 mmg/stroke"])
        finally:
            sprache.setzen("de")

    def test_unbekanntes_format_rest_roh(self):
        # Typ C8 gibt es nicht (höchster ist B5) – die Länge ist unbekannt, also ab dort roh
        werte = messwerte.gruppe_auswerten(h("01 C8 15 C8 01 02 05 0A 83"))
        self.assertEqual([w.text for w in werte], ["840 /min", "roh: C8 01 02 05 0A 83"])
        self.assertEqual(werte[1].typ, messwerte.ROH_REST)
        self.assertIn("Typ 200 hat kein bekanntes Format", werte[1].roh)
        self.assertIsNone(werte[1].zahl)
        self.assertEqual(self.texte("01 C8 15 00 00 00 05 0A 83"),
                         ["840 /min", "roh: 00 00 00 05 0A 83"])
        self.assertEqual(self.texte("6C 01 02"), ["roh: 6C 01 02"])

    def test_unvollstaendiges_feld_rest_roh(self):
        werte = messwerte.gruppe_auswerten(h("01 C8 15 05 0A"))
        self.assertEqual([w.text for w in werte], ["840 /min", "roh: 05 0A"])
        self.assertIn("Feld unvollständig", werte[1].roh)
        self.assertEqual(self.texte("5F 09 41 42"), ["roh: 5F 09 41 42"])
        self.assertEqual(self.texte("A0 01 00"), ["roh: A0 01 00"])
        self.assertEqual(self.texte("5F"), ["roh: 5F"])

    def test_teilen(self):
        self.assertTrue(messwerte.sauber_teilbar(h("01 C8 15 5F 01 41")))
        self.assertFalse(messwerte.sauber_teilbar(h("01 C8 15 5F 01 41"), nur_dreier=True))
        self.assertTrue(messwerte.sauber_teilbar(b""))
        self.assertFalse(messwerte.sauber_teilbar(h("01 C8")))

    def test_bisherige_gruppen_unveraendert(self):
        # nur Felder zu drei Bytes: wie bisher genau vier Werte
        self.assertEqual(self.texte("01 C8 04 15 46 8D 05 0A 83 05 0A 7B"),
                         ["160 /min", "9,87 V", "31 °C", "23 °C"])

    def test_csv_mit_langen_feldern(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = aufzeichnung.CsvAufzeichnung(Path(tmp) / "m.csv")
            a.messwerte(7, messwerte.gruppe_auswerten(h("A0 01 00 7B 11 01 5F 02 4F 4B "
                                                        "01 C8 15 C8 01")))
            a.schliessen()
            with open(Path(tmp) / "m.csv", encoding="utf-8-sig") as datei:
                zeilen = list(csv.reader(datei, delimiter=";"))
        self.assertEqual(zeilen[1][3:11], ["12,3", "V", "OK", "", "840", "/min",
                                           "roh: C8 01", ""])


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

    def test_gruppe_000_zehn_rohwerte(self):
        """Gruppe 000: Block 12 ohne Daten, Antwort F4 mit zehn Rohwerten (seit 0.9.0)."""
        motor = self.port.steuergeraete[0x01]
        werte = self.proto.gruppe_lesen(0)
        self.assertEqual(len(werte), 10)
        self.assertEqual([w.feld for w in werte], list(range(1, 11)))
        self.assertTrue(all(w.typ == messwerte.ROHWERT and 0 <= w.b <= 255 for w in werte))
        self.assertEqual(werte[2].text, str(werte[2].b))           # ohne Einheit
        self.assertEqual(werte[0].roh, f"Rohwert {werte[0].b} (hex {werte[0].b:02X}) ohne "
                                       "Umrechnung")
        self.assertIn((0x12, b""), motor.anfragen)
        self.assertNotIn(0x12, {t for t, d in motor.anfragen if d})
        # danach normale Gruppen wie gewohnt
        self.assertEqual(self.proto.gruppe_lesen(4)[1].einheit, "V")
        self.assertTrue(self.proto.verbunden)

    def test_gruppe_000_abgelehnt_und_kwp2000(self):
        port, proto, _ = verbinden(0x17)                  # Kombi kennt keine Gruppe 000
        with self.assertRaises(Nak):
            proto.gruppe_lesen(0)
        self.assertTrue(proto.verbunden)
        kwp_port = sim_port(echtzeit=False, fahrprofil=False)
        kwp = KW1281(KLine(kwp_port), SCHNELL)
        kwp.connect(0x56, (10400,))
        geraet = kwp_port.steuergeraete[0x56]
        vorher = list(geraet.anfragen)
        with self.assertRaises(NotAvailable) as fall:
            kwp.gruppe_lesen(0)
        self.assertIn("nur bei KW1281", str(fall.exception))
        self.assertEqual(geraet.anfragen, vorher, "bei KWP2000 nichts gesendet")

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

    def test_gestoertes_komplement_bricht_den_block_ab(self):
        # Ein falsches Komplement heißt: das Steuergerät hat ein anderes Byte bekommen.
        # Nie weitersenden – lieber die Verbindung verlieren als einen verfälschten Block.
        motor = self.port.steuergeraete[0x01]
        vorher = len(motor.anfragen)
        motor.stoerung_nach(1)
        with self.assertRaises(ProtocolError) as fall:
            self.proto.gruppe_lesen(4)
        self.assertIn("abgebrochen", str(fall.exception))
        self.assertFalse(self.proto.verbunden)
        self.assertEqual(len(motor.anfragen), vorher, "der Block kam nie vollständig an")
        self.assertEqual(len(motor._rx), 2, "nach dem gestörten Byte nichts mehr gesendet")

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

    def test_lange_pause_nur_fuer_dasselbe_steuergeraet(self):
        """Nach einem Fehlversuch wartet nur dasselbe Steuergerät die volle Pause ab."""
        timing = dataclasses.replace(SCHNELL, reconnect_pause=1.0, wechsel_pause=0.1,
                                     trenn_pause=0.05)
        s = DiagSession(schneller_port, timing, keepalive=0.05).start()
        try:
            with self.assertRaises(NoResponse):
                s.verbinden(0x02).result(5)
            t0 = time.monotonic()
            s.verbinden(0x01).result(5)
            anderes = time.monotonic() - t0
            s.trennen().result(5)
            with self.assertRaises(NoResponse):
                s.verbinden(0x02).result(5)
            t0 = time.monotonic()
            with self.assertRaises(NoResponse):
                s.verbinden(0x02).result(5)
            dasselbe = time.monotonic() - t0
        finally:
            s.schliessen()
        self.assertLess(anderes, 0.6)
        self.assertGreaterEqual(dasselbe, 1.0)

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
        self.assertEqual(sorted(gefunden), [1, 2, 3, 4, 5])
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
        # Mit den Zeiten wie im Programm. Hängt der Testrechner selbst kurz, bricht der
        # Zeitwächter zu Recht ab – deshalb bis zu drei Versuche.
        gruende = []
        for _ in range(3):
            port = sim_port(echtzeit=True)
            proto = KW1281(KLine(port))
            try:
                t0 = time.monotonic()
                proto.connect(0x01)
                dauer_verbinden = time.monotonic() - t0
                t1 = time.monotonic()
                for _ in range(3):
                    proto.gruppe_lesen(4)
                pro_abfrage = (time.monotonic() - t1) / 3
            except ProtocolError as exc:
                gruende.append(str(exc))
                continue
            self.assertTrue(2.0 < dauer_verbinden < 4.5, dauer_verbinden)
            self.assertTrue(0.2 < pro_abfrage < 0.6, pro_abfrage)
            return
        self.fail(f"in drei Versuchen abgebrochen: {gruende}")


class Aufzeichnung(unittest.TestCase):
    def test_csv_format(self):
        with tempfile.TemporaryDirectory() as ordner:
            a = CsvAufzeichnung(Path(ordner) / "test.csv")
            a.messwerte(4, messwerte.gruppe_auswerten(h("01 C8 04 15 46 8D 05 0A 83 05 0A 7B")))
            a.ereignis("Verbindung verloren: Test")
            a.schliessen()
            with open(a.pfad, encoding="utf-8-sig") as datei:
                zeilen = list(csv.reader(datei, delimiter=";"))
        self.assertEqual(zeilen[0][:4], ["Zeit", "Sekunden", "Gruppe", "Feld 1"])
        self.assertEqual(zeilen[1][2:6], ["004", "160", "/min", "9,87"])
        self.assertEqual(zeilen[1][6], "V")
        self.assertEqual(zeilen[2][-1], "Verbindung verloren: Test")

    def test_csv_gruppe_000_zehn_spalten(self):
        with tempfile.TemporaryDirectory() as ordner:
            a = CsvAufzeichnung(Path(ordner) / "test.csv")
            a.messwerte(0, messwerte.rohwerte_auswerten(bytes(range(10, 20))))
            a.messwerte(4, messwerte.gruppe_auswerten(h("01 C8 04 15 46 8D 05 0A 83 05 0A 7B")))
            a.ereignis("Marker 1")
            a.schliessen()
            with open(a.pfad, encoding="utf-8-sig") as datei:
                zeilen = list(csv.reader(datei, delimiter=";"))
        kopf = zeilen[0]
        self.assertEqual(kopf[11:18], ["Feld 5", "Feld 6", "Feld 7", "Feld 8", "Feld 9",
                                       "Feld 10", "Ereignis"])
        self.assertTrue(all(len(z) == len(kopf) for z in zeilen))
        roh = zeilen[1]
        self.assertEqual(roh[2], "000")
        self.assertEqual([roh[i] for i in (3, 5, 7, 9)], ["10", "11", "12", "13"])
        self.assertEqual([roh[i] for i in (4, 6, 8, 10)], ["", "", "", ""])   # ohne Einheit
        self.assertEqual(roh[11:17], ["14", "15", "16", "17", "18", "19"])
        self.assertEqual(zeilen[2][11:17], [""] * 6)                    # andere Gruppen leer
        self.assertEqual(zeilen[3][-1], "Marker 1")


class Einstellungen(unittest.TestCase):
    def test_speichern_und_laden(self):
        with tempfile.TemporaryDirectory() as ordner:
            alt = einstellungen.DATEI
            einstellungen._zuruecksetzen_fuer_tests(Path(ordner) / "e.json")
            try:
                werte = einstellungen.laden()
                # seit 0.4: keine Dateien ohne ausdrücklichen Wunsch
                self.assertFalse(werte["csv_automatisch"])
                self.assertFalse(werte["log_datei"])
                self.assertEqual(werte["sprache"], "de")
                einstellungen.speichern(csv_ordner=str(Path(ordner) / "csv"))
                einstellungen.baud_merken(0x17, 9600)
                einstellungen._zuruecksetzen_fuer_tests(Path(ordner) / "e.json")
                self.assertEqual(einstellungen.baud_fuer(0x17), 9600)
                self.assertEqual(einstellungen.ordner("csv_ordner"), Path(ordner) / "csv")
            finally:
                einstellungen._zuruecksetzen_fuer_tests(alt)

    def test_alte_einstellungen_csv_wird_aus(self):
        """Bis 0.3 stand „csv_automatisch: true“ in jeder Datei – das gilt nicht mehr,
        ein danach bewusst gesetzter Wert aber schon."""
        with tempfile.TemporaryDirectory() as ordner:
            alt = einstellungen.DATEI
            datei = Path(ordner) / "e.json"
            datei.write_text('{"csv_automatisch": true, "neu_verbinden": false, '
                             '"baudraten": {"01": 10400}}', encoding="utf-8")
            einstellungen._zuruecksetzen_fuer_tests(datei)
            try:
                werte = einstellungen.laden()
                self.assertFalse(werte["csv_automatisch"])
                self.assertFalse(werte["neu_verbinden"])
                self.assertEqual(einstellungen.baud_fuer(0x01), 10400)
                einstellungen.speichern(csv_automatisch=True)
                einstellungen._zuruecksetzen_fuer_tests(datei)
                self.assertTrue(einstellungen.laden()["csv_automatisch"])
            finally:
                einstellungen._zuruecksetzen_fuer_tests(alt)



class Anpassung(unittest.TestCase):
    """Anpassungskanäle – ausschließlich lesen."""

    def test_kanal_lesen(self):
        port, proto, _ = verbinden(0x17)
        a = proto.anpassung_lesen(9)
        self.assertEqual((a.kanal, a.wert, a.hex), (9, 12345, "3039"))
        self.assertEqual(a.text, "Kanal 09: 12345 (hex 3039) – Kilometerstand in 10 km alte")
        self.assertEqual(a.beschreibung, "Kilometerstand in 10 km alte")
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
        self.assertEqual(list(gefunden), [2, 9])       # 02 Service-Intervall, 09 km
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

    @staticmethod
    def geraet(adresse, teilenummer, bauteil="TEST"):
        return Verbindung(adresse, "KW1281", 1281, 10400, True, [
            Block(0, ASCII, teilenummer.ljust(12).encode("ascii")),
            Block(1, ASCII, bauteil.ljust(12).encode("ascii"))])

    def test_kombi_und_abs(self):
        kombi = self.geraet(0x17, "6K9920806", "KOMBIINSTRUMENT TRW V04")
        werte = messwerte.gruppe_auswerten(h("24 FF FF 13 64 15 40 51 51 25 00 00"))
        self.assertEqual(beschriftung.namen(kombi, 2, werte),
                         ["Kilometerstand", "Tankinhalt", "Tankgeber", ""])
        self.assertEqual(beschriftung.mit_namen(beschriftung.namen(kombi, 2, werte), werte)[:2],
                         ["Kilometerstand = kein Wert (FF FF)", "Tankinhalt = 21 l"])
        abs_ = self.geraet(0x03, "6X0907379 B", "ABS 30 IE CAN V004")
        werte = messwerte.gruppe_auswerten(h("07 64 00 07 64 00 07 64 00 07 64 00"))
        self.assertEqual(beschriftung.namen(abs_, 1, werte)[0], "Rad vorn links")
        self.assertEqual(beschriftung.anzeige(beschriftung.namen(abs_, 1, werte)[0]),
                         "Rad vorn links")
        self.assertEqual(beschriftung.namen(abs_, 2, werte), [""] * 4)

    def test_andere_kombis_und_abs_nicht_geprueft(self):
        # Namen bleiben (intern gleich, der Fahrtenschreiber wertet nach ihnen aus), angezeigt
        # mit dem Zusatz „(nicht geprüft)“
        werte = messwerte.gruppe_auswerten(h("24 FF FF 13 64 15 40 51 51 25 00 00"))
        for kombi in (self.geraet(0x17, "1J0920806C", "KOMBI VDO"),
                      Verbindung(0x17, "KW1281", 1281, 10400, True, [])):
            namen = beschriftung.namen(kombi, 2, werte)
            self.assertEqual(namen, ["Kilometerstand", "Tankinhalt", "Tankgeber", ""])
            self.assertFalse(namen[0].geprueft)
            self.assertEqual(beschriftung.anzeige(namen[1]), "Tankinhalt (nicht geprüft)")
            self.assertEqual(beschriftung.mit_namen(namen, werte)[1],
                             "Tankinhalt (nicht geprüft) = 21 l")
        abs_ = self.geraet(0x03, "6Q0907379 L", "ABS MK60")
        werte = messwerte.gruppe_auswerten(h("07 64 00 07 64 00 07 64 00 07 64 00"))
        self.assertEqual(beschriftung.anzeige(beschriftung.namen(abs_, 1, werte)[3]),
                         "Rad hinten rechts (nicht geprüft)")
        try:
            sprache.setzen("en")
            self.assertEqual(beschriftung.anzeige(beschriftung.namen(abs_, 1, werte)[3]),
                             "Rear right wheel (not tested)")
        finally:
            sprache.setzen("de")

    def test_anderer_me75_motor_nicht_geprueft(self):
        werte = messwerte.gruppe_auswerten(h("01 C8 05 15 46 95 05 0A 82 05 0A 78"))
        anderer = self.geraet(0x01, "036906034AM", "ME7.5.10")
        namen = beschriftung.namen(anderer, 4, werte)
        self.assertEqual(namen[1], "Bordspannung")
        self.assertEqual(beschriftung.anzeige(namen[1]), "Bordspannung (nicht geprüft)")
        self.assertTrue(beschriftung.namen(self.echter_motor(), 4, werte)[1].geprueft)
        # die Erklärung des Bitfelds gilt nur am 6K0 906 032 M (und seinem Simulator)
        self.assertEqual(beschriftung.bitfeld_erklaerung(anderer, 1, 4, "11101011"), "")
        sim = self.geraet(0x01, "SIM906032", "ME7.5 SIMULATION")
        self.assertIn("Kühlmittel über 80 °C",
                      beschriftung.bitfeld_erklaerung(sim, 1, 4, "11101011"))
        self.assertTrue(beschriftung.namen(sim, 4, werte)[1].geprueft)

    def test_csv_mit_zusatz(self):
        werte = messwerte.gruppe_auswerten(h("01 C8 05 15 46 95 05 0A 82 05 0A 78"))
        namen = beschriftung.namen(self.geraet(0x01, "036906034AM", "ME7.5.10"), 4, werte)
        a = CsvAufzeichnung(Path(self._tmp.name) / "m.csv")
        a.messwerte(4, werte, namen)
        a.schliessen()
        with open(Path(self._tmp.name) / "m.csv", encoding="utf-8-sig") as datei:
            inhalt = datei.read()
        self.assertIn("Motordrehzahl (nicht geprüft) | Bordspannung (nicht geprüft)", inhalt)

    def test_eigene_bezeichnungen(self):
        beschriftung.EIGENE_DATEI.write_text(
            '{"25": {"2": ["Start erlaubt", null, "Schlüssel lesbar", "Schlüssel"]}}',
            encoding="utf-8")
        beschriftung.neu_laden()
        immo = Verbindung(0x25, "KW1281", 1281, 9600, True, [])
        werte = messwerte.gruppe_auswerten(h("11 20 31 11 20 31 11 20 31 11 20 32"))
        self.assertEqual(beschriftung.namen(immo, 2, werte),
                         ["Start erlaubt", "", "Schlüssel lesbar", "Schlüssel"])
        # eigene Namen tragen keinen Zusatz
        self.assertEqual(beschriftung.anzeige(beschriftung.namen(immo, 2, werte)[0]),
                         "Start erlaubt")

    def test_eigene_bezeichnungen_je_teilenummer(self):
        beschriftung.EIGENE_DATEI.write_text(
            '{"01": {"4": ["A", "B", "C", "D"]}, "01:036 906 034 AM": {"4": ["W", "X", null, '
            '"Z"]}}', encoding="utf-8")
        beschriftung.neu_laden()
        werte = messwerte.gruppe_auswerten(h("01 C8 05 15 46 95 05 0A 82 05 0A 78"))
        anderer = self.geraet(0x01, "036906034AM", "ME7.5.10")
        self.assertEqual(beschriftung.namen(anderer, 4, werte), ["W", "X", "", "Z"])
        self.assertEqual(beschriftung.namen(self.echter_motor(), 4, werte), ["A", "B", "C", "D"])

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
        # nicht bei vagdiag, aber in der Tabelle aus KLineKWP1281Lib
        self.assertEqual(messwerte.umrechnen(1, 37, 3, 0xE7).text, "WSC")
        self.assertEqual(messwerte.umrechnen(1, 37, 0, 0x02).text, "ADP. i.O.")
        # eingebaute Texte von vagdiag haben Vorrang (Bibliothek: „Vollast“, „-“)
        self.assertEqual(messwerte.umrechnen(1, 37, 0, 0x07).text, "Volllast")
        self.assertEqual(messwerte.umrechnen(1, 37, 0, 0x00).text, "–")
        # nirgends bekannt
        self.assertEqual(messwerte.umrechnen(1, 37, 0x0F, 0xFF).text, "Text Nr. 4095")
        try:
            sprache.setzen("en")
            self.assertEqual(messwerte.umrechnen(1, 37, 0, 0x02).text, "ADP. O.K.")
        finally:
            sprache.setzen("de")

    def test_eigene_texte(self):
        texte.EIGENE_TEXTE.write_text('{"999": "Testtext", "0x1F": "Öl ok"}', encoding="utf-8")
        texte.neu_laden()
        self.assertEqual(messwerte.umrechnen(1, 37, 3, 0xE7).text, "Testtext")
        self.assertEqual(messwerte.umrechnen(1, 37, 0, 0x1F).text, "Öl ok")


class SimulatorFahrzeug(unittest.TestCase):
    def test_kurve_nur_waehrend_der_fahrt(self):
        """Seit 0.8.1: geparkt oder mit stehendem Motor melden alle Räder 0 km/h – auch an
        der Stelle der Runde mit der Rechtskurve (177–183 s)."""
        fz = SimFahrzeug(fahrprofil=True)
        fz.t0 = time.monotonic() - (1.2 + 180)          # mitten in der Kurve
        z = fz.zustand()
        self.assertGreater(z.v, 3)
        self.assertEqual(z.kurve, 2.0)
        fz.geparkt = True
        z = fz.zustand()
        self.assertEqual((z.v, z.kurve), (0.0, 0.0))
        fz.geparkt = False
        fz.motor_aus = True
        z = fz.zustand()
        self.assertEqual((z.v, z.kurve), (0.0, 0.0))


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
            with open(a.pfad, encoding="utf-8-sig") as datei:
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
            with open(a.pfad, encoding="utf-8-sig") as datei:
                self.assertEqual(len(list(csv.reader(datei, delimiter=";"))), 1)


class Robustheit(unittest.TestCase):
    """Fälle aus deiner Fahrt vom 19.10. (19:16:47, 19:37:18, Anlassen)."""

    def test_muellblock_ist_leitungsfehler(self):
        port, proto, _ = verbinden()
        port.steuergeraete[0x01].naechste_gruppenantwort("muell")
        with self.assertRaises(ProtocolError) as ctx:
            proto.gruppe_lesen(1)
        self.assertIn("Blocklänge FF", str(ctx.exception))
        self.assertFalse(proto.verbunden)

    def test_falscher_blockzaehler_wird_verworfen(self):
        port, proto, _ = verbinden()
        proto.gruppe_lesen(4)
        port.steuergeraete[0x01].naechste_gruppenantwort("zaehler")
        with self.assertLogs("vagdiag.proto", "WARNING"):
            with self.assertRaises(Stoerung) as ctx:
                proto.gruppe_lesen(1)
        self.assertEqual(ctx.exception.art, "zaehler")
        self.assertTrue(proto.verbunden)
        self.assertEqual([w.typ for w in proto.gruppe_lesen(1)], [1, 5, 20, 16])

    def test_anderes_format_verworfen_dann_uebernommen(self):
        port, proto, _ = verbinden()
        proto.gruppe_lesen(1)
        ecu = port.steuergeraete[0x01]
        ecu.naechste_gruppenantwort("format")
        with self.assertRaises(Stoerung) as ctx:
            proto.gruppe_lesen(1)
        self.assertEqual(ctx.exception.art, "format")
        self.assertEqual([w.typ for w in proto.gruppe_lesen(1)], [1, 5, 20, 16])
        ecu.gruppen[1] = ecu.gruppen[4]          # Format ändert sich dauerhaft
        with self.assertRaises(Stoerung):
            proto.gruppe_lesen(1)
        self.assertEqual([w.typ for w in proto.gruppe_lesen(1)], [1, 21, 5, 5])

    def test_unerwarteter_titel(self):
        port, proto, _ = verbinden()
        port.steuergeraete[0x01].naechste_gruppenantwort("titel")
        with self.assertRaises(Stoerung) as ctx:
            proto.gruppe_lesen(2)
        self.assertEqual(ctx.exception.art, "titel")
        self.assertEqual(len(proto.gruppe_lesen(2)), 4)

    def test_fehlendes_echo_einmal_hingenommen(self):
        port, proto, _ = verbinden()
        port.echo_auslassen_nach(2)
        with self.assertLogs("vagdiag.proto", "WARNING") as logs:
            self.assertEqual(len(proto.gruppe_lesen(4)), 4)
        self.assertIn("Echo", logs.output[0])
        self.assertTrue(proto.verbunden)

    def test_ohne_toleranz_bricht_ab_ohne_doppelte_meldung(self):
        port, proto, _ = verbinden()
        proto.toleranz = False
        port.echo_auslassen_nach(2)
        with self.assertRaises(ProtocolError) as ctx:
            proto.gruppe_lesen(4)
        self.assertNotIn("Verbindung verloren", str(ctx.exception))
        self.assertIn("Echo", str(ctx.exception))


class SitzungRobust(unittest.TestCase):
    def neu(self, ereignisse=None):
        return DiagSession(schneller_port, SCHNELL, keepalive=0.05,
                           ereignis=(lambda a, d: ereignisse.append((a, d)))
                           if ereignisse is not None else None).start()

    def test_gestoerte_antworten_werden_wiederholt(self):
        s = self.neu()
        try:
            s.verbinden(0x01).result(5)
            ecu = s._port.steuergeraete[0x01]
            for art in ("zaehler", "titel", "format"):
                s.gruppe_lesen(1).result(5)
                ecu.naechste_gruppenantwort(art)
                werte = s.gruppe_lesen(1).result(5)
                self.assertEqual([w.typ for w in werte], [1, 5, 20, 16], art)
            self.assertTrue(s.verbunden)
        finally:
            s.schliessen()

    def test_dauerhaft_fremder_titel_gilt_als_nicht_belegt(self):
        s = self.neu()
        try:
            s.verbinden(0x01).result(5)
            s._port.steuergeraete[0x01].titel_gruppen.add(2)
            with self.assertRaises(NotAvailable):
                s.gruppe_lesen(2).result(5)
            self.assertTrue(s.verbunden)
        finally:
            s.schliessen()

    def test_muell_fuehrt_zur_neuverbindung(self):
        ereignisse = []
        s = self.neu(ereignisse)
        try:
            s.verbinden(0x01).result(5)
            s.messung_starten()
            s._port.steuergeraete[0x01].naechste_gruppenantwort("muell")
            self.assertEqual(len(s.gruppe_lesen(1, neu_verbinden=True).result(15)), 4)
        finally:
            s.schliessen()
        self.assertEqual([a for a, _ in ereignisse].count("verbunden"), 2)

    def test_kanal_09_ohne_wert_mit_beschreibung(self):
        port = schneller_port()
        port.steuergeraete[0x17].anpassungen[9] = 0xFFFF
        proto = KW1281(KLine(port), SCHNELL)
        proto.connect(0x17)
        km = kilometerstand.lesen(proto)
        self.assertIsNone(km.km)
        self.assertTrue(any("„Kilometerstand in 10 km alte“" in g for g in km.geprueft),
                        km.geprueft)


class NeueBeschriftungen(unittest.TestCase):
    def motor(self):
        return Verbindung(1, "KW1281", 1281, 10400, True, [
            Block(0, ASCII, h("36 4B 30 39 30 36 30 33 32 4D 20 20")),
            Block(1, ASCII, h("4D 45 37 2E 35 2E 31 30 20 20 20 20 20 20 20 20 20 20 20 20"))])

    def test_motor_gruppe_003(self):
        werte = messwerte.gruppe_auswerten(h("01 C8 42 12 FA 3A 21 FF 31 1B 4B AB"))
        self.assertEqual([w.text for w in werte], ["2640 /min", "580 mbar", "19,2 %", "32,2 ° v.OT"])
        self.assertEqual(beschriftung.namen(self.motor(), 3, werte),
                         ["Motordrehzahl", "Saugrohrdruck", "Drosselklappenwinkel", "Zündwinkel"])

    def test_abs_bremslichtschalter(self):
        abs_ = Verbindung(0x03, "KW1281", 1281, 9600, True, [])
        for roh, text in (("25 00 C1", "betätigt"), ("25 00 A7", "unbetätigt")):
            werte = messwerte.gruppe_auswerten(h(roh))
            self.assertEqual(werte[0].text, text)
            self.assertEqual(beschriftung.namen(abs_, 3, werte), ["Bremslichtschalter"])

    def test_bitfeld_erklaerung(self):
        text = beschriftung.bitfeld_erklaerung(self.motor(), 1, 4, "11101011")
        self.assertIn("1. Stelle von rechts: Kühlmittel über 80 °C – ja", text)
        self.assertIn("2. Stelle von rechts: Drehzahl unter 2000/min – ja", text)
        self.assertIn("4. Stelle von rechts: Lambdaregelung aktiv – ja", text)
        self.assertEqual(beschriftung.bitfeld_erklaerung(self.motor(), 2, 4, "11101011"), "")


def _fahrt_csv(pfad):
    with open(pfad, encoding="utf-8-sig") as datei:
        return list(csv.reader(datei, delimiter=";"))


class Fahrtenschreiber(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def plan(self, **aenderungen):
        # ABS alle 0,5 s: der erste Besuch fällt in den Leerlauf nach dem Anlassen (im Stand).
        # Der Simulator läuft schneller als die Uhr – den Stand deshalb schon nach 0,1 s
        # bestätigen (die Regel selbst prüft test_stand_erst_nach_zwei_werten)
        plan = FahrtPlan(besuche=[Besuch(0x17, (1, 2, 3), 1.0, 0.3),
                                  Besuch(0x03, (1, 3), 0.5, 0.3)],
                         stand_dauer=0.2, volle_runde_nach=0.3, stand_bestaetigt=0.1)
        for name, wert in aenderungen.items():
            setattr(plan, name, wert)
        return plan

    def sitzung(self, ereignisse=None, timing=SCHNELL, oeffnen=True, **sim):
        # der Motor springt erst nach 80 s Fahrprofil (4 s) an – Startprüfung und Fahrtbeginn
        # laufen im Stand
        einstellungen_sim = {"fahrprofil": True, "zeitfaktor": 20.0, "motor_start_nach": 80.0,
                             **sim}

        def fabrik():
            return sim_port(echtzeit=False, **einstellungen_sim)
        s = DiagSession(fabrik, timing, keepalive=0.05,
                        ereignis=(lambda a, d: ereignisse.append((a, d)))
                        if ereignisse is not None else None).start()
        if oeffnen:
            s._port_oeffnen()
        return s

    def besuchsplan(self, **aenderungen):
        return self.plan(besuche=[Besuch(0x17, (1, 2, 3), 0.8, 0.15),
                                  Besuch(0x03, (1, 3), 0.6, 0.15)], **aenderungen)

    def gesteuerte_fahrt(self, plan, skript):
        """Fahrt mit Tempo aus dem Test. skript(n, sitzung, tempo) läuft zu Beginn des
        n-ten Besuchs beim Kombi im Diagnose-Thread: Dort stellt es das Tempo um (der
        Besuch liest es gleich mit, danach kennt der Fahrtenschreiber das neue Tempo) und
        setzt Ereignisse. Gibt es True zurück, endet die Fahrt."""
        tempo = [0.0]
        genug = threading.Event()
        kombi = [0]
        box = {}

        def ereignis(art, daten):
            if (art == "fahrt" and "kurzer Besuch" in daten["text"]
                    and "(Kombi)" in daten["text"]):
                kombi[0] += 1
                if skript(kombi[0], box["s"], tempo):
                    genug.set()

        s = DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=True),
                        KURZ_GETRENNT, keepalive=0.05, ereignis=ereignis).start()
        box["s"] = s
        s._port_oeffnen()
        port = s._port
        port.fahrzeug._tempo = lambda tz: (tempo[0], "ort" if tempo[0] else "leerlauf")
        try:
            future = s.fahrt_starten(plan, self.ordner, sim=True)
            self.assertTrue(genug.wait(40), "Skript nicht zu Ende gekommen")
            s.fahrt_beenden()
            z = future.result(30)
        finally:
            s.schliessen()
        return z, port

    def test_ganze_fahrt(self):
        ereignisse = []
        # langsameres Profil: nach dem Anlassen 2 s Leerlauf im Stand – Zeit für den ABS-Besuch
        s = self.sitzung(ereignisse, zeitfaktor=10.0, motor_start_nach=40.0)
        s.airbag_freigeben()
        try:
            future = s.fahrt_starten(self.plan(mit_airbag=True), self.ordner, sim=True)
            time.sleep(6.0)
            s.fahrt_ereignis("Test")
            time.sleep(3.0)
            s.fahrt_beenden()
            z = future.result(30)
            anfragen = {a: [t for t, _ in g.anfragen] for a, g in s._port.steuergeraete.items()}
        finally:
            s.schliessen()
        text = "\n".join(z.zeilen)
        self.assertFalse(z.abgebrochen)
        self.assertIn("SIMULATOR", z.zeilen[0])
        # nach Adressen geordnet – gelesen wird beim Start 25, 17, 15, 03, 01
        self.assertRegex(text, r"Start: 01 2 Fehler.*03 kein Fehler.*15 kein Fehler.*"
                               r"17 1 Fehler: 00771.*25 kein Fehler")
        self.assertRegex(text, r"Ende: 01 .*25 kein Fehler")
        self.assertRegex(text, r"Ereignis \d\d:\d\d:\d\d \(Test\): 01 2 Fehler.*03 kein Fehler")
        self.assertIn("Tankanzeige: Stand am Anfang 21 l", text)
        self.assertIn("Kühlmittel (Motor): Anfang", text)
        self.assertIn("Bordspannung:", text)
        self.assertIn("Tempo höchstens:", text)
        zeilen = _fahrt_csv(z.csv_datei)
        self.assertEqual(zeilen[0][:5], ["Zeit", "Sekunden", "Steuergerät", "Gruppe", "Phase"])
        self.assertTrue({"Start", "Fahrt", "Ereignis", "Ende"} <= {r[4] for r in zeilen[1:]})
        self.assertTrue({"01", "03", "17"} <= {r[2] for r in zeilen[1:] if r[3]})
        self.assertTrue(z.csv_datei.name.startswith("sim-fahrt-"))
        self.assertTrue(z.txt_datei.exists())
        arten = {a for a, _ in ereignisse}
        self.assertTrue({"fahrt", "fahrt_werte", "fahrt_notiz"} <= arten)
        # nur lesende Blöcke: Gruppen, Fehler lesen, Kennung, ACK, Ende
        for adresse, titel in anfragen.items():
            self.assertTrue(set(titel) <= {0x09, 0x06, 0x07, 0x29, 0x00}, (adresse, set(titel)))

    def test_abbrechen_ohne_abschluss(self):
        s = self.sitzung()
        try:
            future = s.fahrt_starten(self.plan(), self.ordner, sim=True)
            time.sleep(1.0)
            s.abbrechen()
            z = future.result(20)
        finally:
            s.schliessen()
        self.assertTrue(z.abgebrochen)
        self.assertIn("abgebrochen", z.zeilen[0])
        self.assertNotIn("Ende:", "\n".join(z.zeilen))

    def test_anlassen_wird_mit_gruppe_004_erfasst(self):
        s = self.sitzung(zeitfaktor=1.0, motor_start_nach=1.5)
        try:
            future = s.fahrt_starten(self.plan(pruefung=False, besuche=[]), self.ordner, sim=True)
            time.sleep(4.0)
            s.fahrt_beenden()
            z = future.result(20)
        finally:
            s.schliessen()
        text = "\n".join(z.zeilen)
        self.assertIn("Motor aus 12,11 V", text)
        self.assertIn("beim Anlassen min. 10,01 V", text)
        zeilen = [r for r in _fahrt_csv(z.csv_datei)[1:] if r[2] == "01" and r[3]]
        erste_laufend = next(i for i, r in enumerate(zeilen) if r[5] not in ("0", "200"))
        self.assertEqual({r[3] for r in zeilen[:erste_laufend]}, {"004"})
        self.assertTrue({"001", "002", "003", "005"} <= {r[3] for r in zeilen[erste_laufend:]})

    def test_startpruefung_wegfahrsperre_zuerst_motor_bleibt_verbunden(self):
        """Start: Wegfahrsperre zuerst, Motor zuletzt – danach kein neuer Verbindungsaufbau
        zum Motor; die Aufforderung zum Anlassen kommt erst nach den ersten Motorwerten."""
        ereignisse = []
        s = self.sitzung(ereignisse, zeitfaktor=1.0, motor_start_nach=6.0)
        try:
            future = s.fahrt_starten(self.plan(besuche=[]), self.ordner, sim=True)
            ende = time.monotonic() + 30
            while time.monotonic() < ende and not any(
                    a == "fahrt_notiz" and "Motor läuft" in d for a, d in ereignisse):
                time.sleep(0.05)
            time.sleep(0.5)
            s.fahrt_beenden()
            z = future.result(30)
            roh = list(s._port.reizungen)
            # gereizte Adressen ohne Wiederholungen derselben (zweite Baudrate)
            reizungen = [a for i, a in enumerate(roh) if i == 0 or roh[i - 1] != a]
        finally:
            s.schliessen()
        self.assertEqual(reizungen[:4], [0x25, 0x17, 0x03, 0x01])
        self.assertEqual(reizungen[4:], [0x17, 0x01, 0x03, 0x25])   # Abschluss wie bisher
        # ohne Besuche: nach der Startprüfung kein zweiter Verbindungsaufbau zum Motor –
        # als Nächstes kommt erst die Abschlussprüfung
        motor = roh.index(0x01)
        self.assertEqual(roh[motor + 1], 0x17, roh)
        notizen = [d.split("  ", 1)[1] for a, d in ereignisse if a == "fahrt_notiz"]
        i_start = notizen.index("Startprüfung fertig")
        i_auff = notizen.index("Aufzeichnung läuft – jetzt Motor starten und losfahren")
        i_laeuft = notizen.index("Motor läuft")
        self.assertLess(i_start, i_auff)
        self.assertLess(i_auff, i_laeuft)
        zeilen = _fahrt_csv(z.csv_datei)[1:]
        erste_motorwerte = next(i for i, r in enumerate(zeilen)
                                if r[2] == "01" and r[3] == "004" and r[4] == "Fahrt")
        aufforderung = next(i for i, r in enumerate(zeilen) if r[13].startswith(
            "Aufzeichnung läuft – jetzt Motor starten"))
        self.assertLess(erste_motorwerte, aufforderung)
        text = "\n".join(z.zeilen)
        self.assertRegex(text, r"Bordspannung: Motor aus \d+,\d\d V · beim Anlassen min\.")

    def test_motor_lief_schon_steht_in_der_zusammenfassung(self):
        ereignisse = []
        s = self.sitzung(ereignisse, fahrprofil=False)      # Motor läuft schon im Leerlauf
        try:
            future = s.fahrt_starten(self.plan(pruefung=False, besuche=[]), self.ordner,
                                     sim=True)
            time.sleep(2.0)
            s.fahrt_beenden()
            z = future.result(20)
        finally:
            s.schliessen()
        notizen = [d for a, d in ereignisse if a == "fahrt_notiz"]
        self.assertTrue(any("Der Motor lief schon beim ersten Messwert" in n for n in notizen))
        self.assertFalse(any("jetzt Motor starten" in n for n in notizen))
        self.assertIn("Anlassen nicht aufgezeichnet (Motor lief schon beim ersten Messwert)",
                      "\n".join(z.zeilen))

    def test_abs_nicht_erreichbar_und_fehlende_gruppe(self):
        s = self.sitzung(motor_start_nach=0.0)
        try:
            del s._port.steuergeraete[0x03]
            del s._port.steuergeraete[0x01].gruppen[3]
            future = s.fahrt_starten(self.plan(pruefung=False,
                                               besuche=[Besuch(0x03, (1, 3), 0.5, 0.3)]),
                                     self.ordner, sim=True)
            time.sleep(3.5)
            s.fahrt_beenden()
            z = future.result(20)
        finally:
            s.schliessen()
        text = "\n".join(z.zeilen)
        self.assertIn("Nicht erreicht:", text)
        self.assertIn("Bremsenelektronik (ABS)", text)
        ereignisse = [r[-1] for r in _fahrt_csv(z.csv_datei)[1:] if r[-1]]
        self.assertTrue(any("01/003 gibt es nicht" in e for e in ereignisse), ereignisse)

    def test_stoerung_waehrend_der_fahrt(self):
        s = self.sitzung()
        try:
            future = s.fahrt_starten(self.plan(pruefung=False, besuche=[]), self.ordner, sim=True)
            time.sleep(1.0)
            s._port.steuergeraete[0x01].naechste_gruppenantwort("muell")
            time.sleep(2.0)
            s.fahrt_beenden()
            z = future.result(20)
        finally:
            s.schliessen()
        self.assertRegex("\n".join(z.zeilen), r"Störungen: [1-9]\d*")
        ereignisse = [r[-1] for r in _fahrt_csv(z.csv_datei)[1:] if r[-1]]
        self.assertTrue(any("Verbindung zum Motor verloren" in e for e in ereignisse))
        nach = [r for r in _fahrt_csv(z.csv_datei)[1:] if r[2] == "01" and r[3]]
        self.assertGreater(len(nach), 50)

    def test_abs_nur_im_stand_ereignis_beim_naechsten_halt(self):
        """Wie das ABS im Polo (Mark 20 IE): Verbindung nur im Stand. Ein Ereignis
        während der Fahrt liest den Motor sofort, das ABS beim nächsten Halt bzw. bei
        der Abschlussprüfung."""
        def skript(n, s, tempo):
            if n == 1:
                tempo[0] = 50.0                     # losfahren
            elif n == 2:
                s.fahrt_ereignis("Test 1")          # während der Fahrt
            elif n == 3:
                tempo[0] = 0.0                      # Halt an der Ampel
            elif n == 4:
                tempo[0] = 50.0                     # weiter – und gleich das nächste
                s.fahrt_ereignis("Test 2")
            return n >= 5

        z, port = self.gesteuerte_fahrt(self.besuchsplan(), skript)
        text = "\n".join(z.zeilen)
        self.assertEqual(port.abgewiesen, [], "ABS während der Fahrt gereizt")
        self.assertRegex(text, r"Ereignis \d\d:\d\d:\d\d \(Test 1\): 01 2 Fehler.* · 03 kein "
                               r"Fehler \(im Stand gelesen um \d\d:\d\d:\d\d\)")
        self.assertRegex(text, r"Ereignis \d\d:\d\d:\d\d \(Test 2\): 01 2 Fehler.* · 03 kein "
                               r"Fehler \(bei der Abschlussprüfung gelesen\)")
        self.assertRegex(text, r"Besuche: Kombi [5-9], ABS [2-9] \(nur im Stand\)")
        self.assertRegex(text, r"Tempo höchstens: .*Kombi 50 km/h")
        self.assertNotRegex(text, r"Tempo höchstens: .*ABS")    # im Stand gelesen – sagt nichts
        zeilen = _fahrt_csv(z.csv_datei)[1:]
        notizen = [r[-1] for r in zeilen if r[-1]]
        self.assertEqual(sum("Fehlerspeicher wird beim nächsten Halt gelesen" in n
                             for n in notizen), 2, notizen)
        # das ABS war nur verbunden, solange das Auto stand
        raeder = [float(r[i].replace(",", ".")) for r in zeilen
                  if r[2] == "03" and r[3] == "001" and r[4] == "Fahrt" for i in (5, 7, 9, 11)]
        self.assertTrue(raeder)
        self.assertEqual(set(raeder), {0.0})

    def test_abs_waehrend_der_fahrt_lehnt_ab(self):
        """Gegenprobe: ohne die Regel versucht der Fahrtenschreiber das ABS auch beim
        Fahren – der Simulator lehnt dann ab wie das echte Steuergerät."""
        def skript(n, s, tempo):
            if n == 1:
                tempo[0] = 50.0
            return n >= 3

        z, port = self.gesteuerte_fahrt(self.besuchsplan(nur_im_stand=()), skript)
        text = "\n".join(z.zeilen)
        self.assertIn(0x03, port.abgewiesen)
        self.assertRegex(text, r"Bremsenelektronik \(ABS\) bei etwa 50 km/h")
        self.assertNotIn("(nur im Stand)", text)

    def test_simulator_steht_zur_startpruefung(self):
        """Im Simulator steht das Auto, bis die Startprüfung fertig ist – sonst wäre das
        ABS (nur im Stand) im schnellen Profil schon unterwegs. Wie beim Start aus der
        Oberfläche ist der Port dabei noch gar nicht offen."""
        ereignisse = []
        s = self.sitzung(ereignisse, oeffnen=False, zeitfaktor=40.0, motor_start_nach=0.0)
        self.assertIsNone(s._port)
        try:
            future = s.fahrt_starten(self.plan(besuche=[]), self.ordner, sim=True)
            ende = time.monotonic() + 20
            while time.monotonic() < ende and not any(
                    a == "fahrt_notiz" and "Fahrt beginnt" in d for a, d in ereignisse):
                time.sleep(0.05)
            time.sleep(1.5)
            s.fahrt_beenden()
            z = future.result(30)
            port = s._port
        finally:
            s.schliessen()
        text = "\n".join(z.zeilen)
        self.assertRegex(text, r"Start: 01 .*03 kein Fehler.*17 ")
        self.assertRegex(text, r"Ende: 01 .*03 kein Fehler.*17 ")
        self.assertRegex(text, r"Tempo höchstens: .*km/h")       # dazwischen ist er gefahren
        self.assertEqual(port.abgewiesen, [])

    def test_besuche_ohne_leere_motorverbindung(self):
        """Steht der nächste Besuch schon an, geht es direkt dorthin – ohne den Motor
        dazwischen zu verbinden und gleich wieder zu trennen."""
        ereignisse = []
        s = self.sitzung(ereignisse, timing=KURZ_GETRENNT, fahrprofil=False)
        try:
            plan = self.plan(pruefung=False, besuche=[Besuch(0x17, (1,), 0.3, 0.1),
                                                      Besuch(0x03, (1,), 0.3, 0.1)])
            future = s.fahrt_starten(plan, self.ordner, sim=True)
            time.sleep(4.0)
            s.fahrt_beenden()
            future.result(20)
        finally:
            s.schliessen()
        folge = [("verbunden", d.adresse) if a == "verbunden" else ("gelesen", d["adresse"])
                 for a, d in ereignisse if a in ("verbunden", "fahrt_werte")]
        leer = [i for i, ((art, adresse), (art2, _)) in enumerate(zip(folge, folge[1:]))
                if art == "verbunden" and adresse == 0x01 and art2 == "verbunden"]
        self.assertEqual(leer, [], folge)
        self.assertGreater(folge.count(("verbunden", 0x17)), 3)
        self.assertGreater(folge.count(("verbunden", 0x03)), 3)
        self.assertGreater(folge.count(("gelesen", 0x01)), 10)

    def test_abschluss_bei_ausgeschalteter_zuendung(self):
        ereignisse = []
        s = self.sitzung(ereignisse, timing=KURZ_GETRENNT, fahrprofil=False)
        try:
            future = s.fahrt_starten(self.plan(besuche=[], zuendung_warten=1.0), self.ordner,
                                     sim=True)
            time.sleep(2.0)
            s._port.zuendung = False
            time.sleep(0.5)
            s.fahrt_beenden()
            z = future.result(30)
        finally:
            s.schliessen()
        text = "\n".join(z.zeilen)
        self.assertIn("Ende: nicht geprüft – die Zündung war aus", text)
        self.assertRegex(text, r"Start: 01 2 Fehler.*17 1 Fehler")
        self.assertRegex(text, r"Tankanzeige: Stand am Anfang .* · Stand am Ende nicht gemessen "
                               r"\(Zündung aus\)")
        notizen = [d for a, d in ereignisse if a == "fahrt_notiz"]
        self.assertTrue(any("ist die Zündung aus?" in n for n in notizen), notizen)
        self.assertTrue(any("Zündung aus – Ende nicht möglich" in n for n in notizen), notizen)
        self.assertFalse(any("nicht erreichbar" in n for n in notizen
                             if "Ende" in n or "17 –" in n), notizen)

    def test_zuendung_waehrend_des_wartens_wieder_an(self):
        ereignisse = []
        s = self.sitzung(ereignisse, timing=KURZ_GETRENNT, fahrprofil=False)
        try:
            future = s.fahrt_starten(self.plan(besuche=[], zuendung_warten=20.0), self.ordner,
                                     sim=True)
            time.sleep(2.0)
            s._port.zuendung = False
            time.sleep(0.5)
            s.fahrt_beenden()
            ende = time.monotonic() + 15
            while time.monotonic() < ende and not any(
                    a == "fahrt_notiz" and "ist die Zündung aus?" in d for a, d in ereignisse):
                time.sleep(0.05)
            s._port.zuendung = True
            z = future.result(40)
        finally:
            s.schliessen()
        text = "\n".join(z.zeilen)
        notizen = [d for a, d in ereignisse if a == "fahrt_notiz"]
        self.assertTrue(any("Zündung ist wieder an" in n for n in notizen), notizen)
        self.assertRegex(text, r"Ende: 01 2 Fehler.*03 kein Fehler.*17 1 Fehler.*25 kein Fehler")
        self.assertNotIn("nicht geprüft", text)

    def test_zuendung_aus_waehrend_der_fahrt_ist_keine_stoerung(self):
        """Wie am 22.10. am Ziel: Zündung aus, nach ein paar Sekunden wieder an (für die
        Abschlussprüfung). Das ist keine Störung, steht aber mit Uhrzeit in der Zusammenfassung."""
        ereignisse = []
        s = self.sitzung(ereignisse, timing=KURZ_GETRENNT, fahrprofil=False)
        try:
            future = s.fahrt_starten(self.plan(pruefung=False, besuche=[]), self.ordner, sim=True)
            time.sleep(1.5)
            s._port.zuendung = False
            time.sleep(1.5)
            s._port.zuendung = True
            time.sleep(1.5)
            s.fahrt_beenden()
            z = future.result(30)
        finally:
            s.schliessen()
        text = "\n".join(z.zeilen)
        self.assertIn("Störungen: 0", text)
        self.assertRegex(text, r"Zündung zwischendurch aus \(keine Störung\): "
                               r"\d\d:\d\d:\d\d–\d\d:\d\d:\d\d")
        notizen = [d for a, d in ereignisse if a == "fahrt_notiz"]
        self.assertTrue(any("Verbindung zum Motor verloren" in n for n in notizen), notizen)
        self.assertTrue(any("Zündung aus?" in n for n in notizen), notizen)
        self.assertTrue(any("Motor antwortet wieder" in n for n in notizen), notizen)

    def test_gestoerter_verbindungsaufbau_zaehlt_und_steht_ueberall(self):
        """Wie am 22.10. um 06:55: Der Motor antwortet auf die Reizung, schickt aber keine
        Kennung. Das ist eine Störung – und steht in CSV und Protokoll."""
        s = self.sitzung(timing=KURZ_GETRENNT, fahrprofil=False)
        try:
            s._port.steuergeraete[0x01].kennung_verweigern()
            with self.assertLogs("vagdiag.proto", level="INFO") as protokoll:
                future = s.fahrt_starten(self.plan(pruefung=False, besuche=[]), self.ordner,
                                         sim=True)
                time.sleep(2.0)
                s.fahrt_beenden()
                z = future.result(30)
        finally:
            s.schliessen()
        self.assertIn("Störungen: 1", "\n".join(z.zeilen))
        self.assertNotIn("Zündung zwischendurch aus", "\n".join(z.zeilen))
        csv_notizen = [r[-1] for r in _fahrt_csv(z.csv_datei)[1:] if r[-1]]
        self.assertTrue(any("Verbindungsaufbau zum Motor gestört" in n for n in csv_notizen),
                        csv_notizen)
        self.assertTrue(any("Verbindungsaufbau zum Motor gestört" in z_ for z_ in protokoll.output))
        motor = [r for r in _fahrt_csv(z.csv_datei)[1:] if r[2] == "01" and r[3]]
        self.assertGreater(len(motor), 5, "danach weiter aufgezeichnet")


class _Stumm:
    """Sitzung, die nur Meldungen schluckt (für Tests ohne Steuergerät)."""

    def _melden(self, art, daten):
        pass


class ZusammenfassungEchteWerte(unittest.TestCase):
    """Zusammenfassung mit Werten wie in der echten Fahrt vom 20.10.2026: das Anlassen
    zählt nicht zum laufenden Motor, die Lambdaregelung erst mit warmem Motor."""

    def test_startphase_ausgeklammert(self):
        with tempfile.TemporaryDirectory() as ordner:
            fs = Schreiber(None, FahrtPlan(), Path(ordner))
            try:
                reihen = fs.sammler.reihen

                def probe(name, zeit, zahl):
                    reihen.setdefault((0x01, name), []).append(Probe(zeit, FAHRT, zahl, ""))

                # Gruppe 004: Drehzahl und Bordspannung aus derselben Abfrage
                for zeit, n, u in ((10.0, 0, 11.97), (10.4, 160, 9.87), (10.8, 240, 10.22),
                                   (11.2, 1080, 10.50), (12.0, 1240, 12.62), (17.0, 900, 13.23),
                                   (60.0, 850, 13.90), (300.0, 2400, 14.06)):
                    probe("Motordrehzahl", zeit, n)
                    probe("Bordspannung", zeit, u)
                fs.motorstarts.append(11.2)
                # Gruppe 001: kalt schwingt die Regelung weit aus, warm nur wenig
                for zeit, kmt, lam in ((40.0, 45, 18.0), (41.0, 46, -15.0), (42.0, 47, 12.0),
                                       (100.0, 85, -2.0), (101.0, 85, 1.0), (102.0, 86, 3.0),
                                       (103.0, 86, -1.0), (104.0, 86, 0.5), (105.0, 87, 2.0)):
                    probe("Kühlmitteltemperatur", zeit, kmt)
                    probe("Lambdaregelung", zeit, lam)
                zeilen = fs.zusammenfassung()
            finally:
                fs.datei.schliessen()
        text = "\n".join(zeilen)
        self.assertIn("Bordspannung: Motor aus 11,97 V · beim Anlassen min. 9,87 V · "
                      "bei laufendem Motor Median 13,90 V (13,23–14,06 V)", text)
        self.assertIn("Lambdaregelung (warmer Motor): Mittel 0,6 %, meist -2,0 bis 3,0 %, "
                      "äußerste Werte -2,0 bis 3,0 %", text)

    def test_bremse_je_besuch(self):
        """Im Stand steht der Fuß oft die ganze Zeit auf der Bremse – gezählt wird je
        Besuch, nicht nur der Wechsel von „unbetätigt“ zu „betätigt“."""
        from vagdiag.fahrtenschreiber import BREMSE_BETAETIGT
        with tempfile.TemporaryDirectory() as ordner:
            fs = Schreiber(None, FahrtPlan(), Path(ordner))
            try:
                reihe = fs.sammler.reihen.setdefault((0x03, "Bremslichtschalter"), [])
                for zeit, nummer in ((100, 0xC1), (101, 0xC1), (102, 0xC1), (103, 0xC1),
                                     (200, 0xA7), (201, 0xA7), (202, 0xA7), (203, 0xA7),
                                     (300, 0xA7), (301, 0xA7), (302, 0xC1), (303, 0xC1)):
                    reihe.append(Probe(float(zeit), FAHRT, None, "", nummer))
                self.assertEqual(BREMSE_BETAETIGT, 0xC1)
                text = "\n".join(fs.zusammenfassung())
            finally:
                fs.datei.schliessen()
        self.assertIn("Bremslichtschalter (ABS-Besuche): 12 Werte, bei 2 von 3 Besuchen "
                      "betätigt", text)

    def test_kuehlmittel_merker_nur_am_geprueften_motor(self):
        """Die Bedeutung der Stellen im Bitfeld (Gruppe 001, Feld 4) ist nur am
        6K0 906 032 M geprüft – an anderen Motoren keine Auswertung des Merkers."""
        ergebnisse = {}
        for teilenummer in ("6K0906032M", "036906034AM", None):
            with tempfile.TemporaryDirectory() as ordner:
                fs = Schreiber(None, FahrtPlan(), Path(ordner))
                try:
                    if teilenummer:
                        fs.teilenummern[0x01] = teilenummer
                    reihen = fs.sammler.reihen
                    for zeit, kmt, bits in ((100.0, 75, "11101010"), (200.0, 85, "11101011")):
                        reihen.setdefault((0x01, "Kühlmitteltemperatur"), []).append(
                            Probe(zeit, FAHRT, kmt, ""))
                        reihen.setdefault((0x01, "Grundeinstellungsbedingungen"), []).append(
                            Probe(zeit, FAHRT, None, bits))
                    ergebnisse[teilenummer] = "\n".join(fs.zusammenfassung())
                finally:
                    fs.datei.schliessen()
        self.assertIn("Merker „Kühlmittel über 80 °C“ (Gruppe 001): 50 % der Zeit",
                      ergebnisse["6K0906032M"])
        self.assertNotIn("Merker", ergebnisse["036906034AM"])
        self.assertNotIn("Merker", ergebnisse[None])
        self.assertIn("Kühlmittel (Motor): Anfang 75 °C", ergebnisse["036906034AM"])

    def test_stand_erst_nach_zwei_werten(self):
        """22.10., 06:55:11: Der Motor meldete einmal 0 km/h, als es schon wieder losging –
        das ABS nahm die Verbindung dann nicht an. Stand erst nach zwei Werten 0 km/h, die
        mindestens stand_bestaetigt auseinanderliegen."""
        with tempfile.TemporaryDirectory() as ordner:
            fs = Schreiber(_Stumm(), FahrtPlan(stand_bestaetigt=1.0), Path(ordner))
            try:
                fs._tempo_merken(6.0)
                fs._tempo_merken(0.0)
                self.assertFalse(fs._steht(), "ein Wert genügt nicht")
                self.assertFalse(fs._darf(0x03))
                fs._stand_seit -= 1.5
                fs._tempo_merken(4.0)                # schon wieder unterwegs
                self.assertFalse(fs._steht())
                fs._tempo_merken(0.0)
                fs._tempo_merken(0.0)
                self.assertFalse(fs._steht(), "zwei Werte, aber zu kurz hintereinander")
                fs._stand_seit -= 1.5
                fs._tempo_merken(0.0)
                self.assertTrue(fs._steht())
                self.assertTrue(fs._darf(0x03))
                self.assertTrue(fs._darf(0x17), "der Kombi darf immer")
            finally:
                fs.datei.schliessen()

    def test_lief_der_motor_schon_zaehlt_kein_anlassen(self):
        """Läuft der Motor schon beim Beginn der Fahrt, ist das erste „Motor läuft“
        kein Start – sonst stünden die ersten Sekunden als „beim Anlassen“ da."""
        with tempfile.TemporaryDirectory() as ordner:
            fs = Schreiber(_Stumm(), FahrtPlan(), Path(ordner))
            try:
                for n in (850, 860):
                    fs.letzte_drehzahl = n
                    fs._motorzustand()
                self.assertEqual(fs.motorstarts, [])
                self.assertIsNotNone(fs.motor_laeuft_seit)
                for n in (0, 200, 900):          # abgewürgt, angelassen, läuft
                    fs.letzte_drehzahl = n
                    fs._motorzustand()
                self.assertEqual(len(fs.motorstarts), 1)
            finally:
                fs.datei.schliessen()



class Airbag(unittest.TestCase):
    """Adresse 15 nur nach Freigabe; ein 6Q0 909 605 A wird sofort getrennt."""

    def test_ohne_freigabe_keine_verbindung(self):
        s = DiagSession(schneller_port, SCHNELL, keepalive=0.05).start()
        try:
            with self.assertRaises(AirbagGesperrt):
                s.verbinden(0x15).result(5)
            self.assertIsNone(s._port, "ohne Freigabe wird nicht einmal das Kabel geöffnet")
            s.airbag_freigeben()
            v = s.verbinden(0x15).result(10)
            self.assertEqual(v.adresse, 0x15)
            self.assertEqual(s.fehler_lesen().result(5), [])
        finally:
            s.schliessen()

    def test_betroffenes_steuergeraet_wird_sofort_getrennt(self):
        def fabrik():
            port = schneller_port()
            port.steuergeraete[0x15] = SimEcu(
                0x15, [b"6Q0909605A  ", b"AIRBAG VW5  ", b"   0004", b"\x00\x00\x2a\x30\x39"],
                baud=9600)
            return port
        s = DiagSession(fabrik, SCHNELL, keepalive=0.05).start()
        s.airbag_freigeben()
        try:
            with self.assertRaises(AirbagRisiko) as fall:
                s.verbinden(0x15).result(10)
            self.assertIn("65535", str(fall.exception))
            self.assertFalse(s.verbunden)
            titel = [t for t, _ in s._port.steuergeraete[0x15].anfragen]
        finally:
            s.schliessen()
        # nur die Quittungen der Kennung und das Ende – sonst nichts
        self.assertEqual(titel[-1], 0x06)
        self.assertTrue(set(titel) <= {0x09, 0x06}, titel)

    def verbinden_mit_kennung(self, adresse, kennung, ausnahme):
        """Unter `adresse` meldet sich ein Gerät mit `kennung` – etwa weil eine Störung die
        Reizung verfälscht hat. Zurück: Fehlertext und die Titel aller Anfragen."""
        def fabrik():
            port = schneller_port()
            port.steuergeraete[adresse].kennung = list(kennung)
            return port
        s = DiagSession(fabrik, SCHNELL, keepalive=0.05).start()
        try:
            with self.assertRaises(ausnahme) as fall:
                s.verbinden(adresse).result(10)
            self.assertFalse(s.verbunden)
            titel = [t for t, _ in s._port.steuergeraete[adresse].anfragen]
        finally:
            s.schliessen()
        # nur die Quittungen der Kennung und das Ende – sonst nichts
        self.assertEqual(titel[-1], 0x06)
        self.assertTrue(set(titel) <= {0x09, 0x06}, titel)
        return str(fall.exception)

    def test_airbag_unter_fremder_adresse_wird_sofort_getrennt(self):
        # ohne Freigabe – der Airbag (hier wie im Polo) meldet sich unter 17
        text = self.verbinden_mit_kennung(
            0x17, [b"1J0909609 Q ", b"AIRBAG VW3 S", b"G 0002", b"\x00\x00\x2a\x30\x39"],
            AirbagFremd)
        self.assertIn("Adresse 17", text)
        self.assertIn("1J0909609 Q AIRBAG VW3 SG 0002", text)

    def test_betroffenes_steuergeraet_unter_fremder_adresse(self):
        text = self.verbinden_mit_kennung(
            0x01, [b"6Q0909605A  ", b"AIRBAG VW5  ", b"   0004", b"\x00\x00\x2a\x30\x39"],
            AirbagRisiko)
        self.assertIn("65535", text)

    def test_kennungen_der_echten_geraete_sind_kein_airbag(self):
        from vagdiag import airbag
        for teil, bauteil in (("6K0906032M", "ME7.5.10 S080"),
                              ("6K9920806", "KOMBIINSTRUMENT TRW V04"),
                              ("6X0907379 B", "ABS 30 IE CAN V004"),
                              ("6X0953257", "IMMO 0002")):
            self.assertFalse(airbag.ist_airbag(teil, bauteil), teil)
            airbag.pruefen(0x01, teil, bauteil)          # keine Ausnahme
        self.assertTrue(airbag.ist_airbag("1J0909609 Q", "AIRBAG VW3 SG 0002"))
        airbag.pruefen(0x15, "1J0909609 Q", "AIRBAG VW3 SG 0002")   # unter 15 erlaubt

    def test_scan_meldet_fremden_airbag_als_getrennt(self):
        def fabrik():
            port = schneller_port()
            port.steuergeraete[0x17].kennung = [b"1J0909609 Q ", b"AIRBAG VW3 S", b"G 0002",
                                                b"\x00\x00\x2a\x30\x39"]
            return port
        s = DiagSession(fabrik, KURZ_GETRENNT, keepalive=0.05).start()
        try:
            eintraege = s.scannen((0x01, 0x17)).result(30)
        finally:
            s.schliessen()
        status = {e.adresse: e.status for e in eintraege}
        self.assertEqual(status, {0x01: "gefunden", 0x17: "getrennt"})

    def fahrt(self, plan):
        with tempfile.TemporaryDirectory() as ordner:
            s = DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=False), SCHNELL,
                            keepalive=0.05).start()
            try:
                future = s.fahrt_starten(plan, ordner, sim=True)
                time.sleep(1.5)
                s.fahrt_beenden()
                z = future.result(20)
                anfragen_airbag = s._port.steuergeraete[0x15].anfragen
            finally:
                s.schliessen()
        return "\n".join(z.zeilen), anfragen_airbag

    def test_fahrtenschreiber_standardmaessig_ohne_airbag(self):
        plan = FahrtPlan(besuche=[], stand_dauer=0.1, volle_runde_nach=0.1)
        self.assertEqual(plan.pruef_adressen(), (0x01, 0x03, 0x17, 0x25))
        text, anfragen_airbag = self.fahrt(plan)
        # nach Adressen sortiert (seit 0.8.1) – der Airbag fehlt
        self.assertRegex(text, r"Start: 01 .* · 03 .* · 17 .* · 25 kein Fehler")
        fehlerzeilen = [z for z in text.splitlines() if z.strip().startswith(("Start:", "Ende:"))]
        self.assertTrue(fehlerzeilen)
        self.assertFalse(any(" 15 " in z for z in fehlerzeilen), fehlerzeilen)
        self.assertEqual(anfragen_airbag, [])

    def test_fahrtenschreiber_airbag_gewaehlt_aber_nicht_freigegeben(self):
        plan = FahrtPlan(besuche=[], stand_dauer=0.1, volle_runde_nach=0.1, mit_airbag=True)
        self.assertEqual(plan.pruef_adressen(), (0x01, 0x03, 0x15, 0x17, 0x25))
        text, anfragen_airbag = self.fahrt(plan)
        self.assertIn("15 nicht gelesen (Airbag nicht freigegeben)", text)
        self.assertEqual(anfragen_airbag, [])


class Protokoll(unittest.TestCase):
    """Ohne Einstellung keine Protokolldatei – der Speicher lässt sich trotzdem sichern."""

    def tearDown(self):
        protokolldatei.datei_ausschalten()

    def test_standard_ohne_datei_und_nachtraeglich_speichern(self):
        import logging
        with tempfile.TemporaryDirectory() as ordner:
            self.assertIsNone(protokolldatei.einrichten(schreiben=False))
            logging.getLogger("vagdiag.proto").info("Testzeile 1")
            ziel = protokolldatei.speichern(Path(ordner) / "sicherung.log")
            inhalt = ziel.read_text(encoding="utf-8")
            self.assertIn("Protokoll gestartet", inhalt)
            self.assertIn("Testzeile 1", inhalt)
            self.assertEqual(list(Path(ordner).glob("vagdiag-*.log")), [])

    def test_puffer_behaelt_die_kopfzeile(self):
        import logging
        self.assertEqual(protokolldatei.PUFFER_ZEILEN, 256_000)
        puffer = protokolldatei.Puffer(zeilen=3)
        puffer.setFormatter(logging.Formatter("%(message)s"))
        for i in range(3):
            puffer.emit(logging.makeLogRecord({"msg": f"Zeile {i}"}))
        self.assertEqual(puffer.kopie(), ["Zeile 0", "Zeile 1", "Zeile 2"])
        for i in range(3, 6):
            puffer.emit(logging.makeLogRecord({"msg": f"Zeile {i}"}))
        self.assertEqual(puffer.kopie(), ["Zeile 0", "(ältere Zeilen nicht mehr im Speicher)",
                                          "Zeile 3", "Zeile 4", "Zeile 5"])

    def test_datei_einschalten_uebernimmt_den_anfang(self):
        import logging
        with tempfile.TemporaryDirectory() as ordner:
            protokolldatei.einrichten(schreiben=False)
            logging.getLogger("vagdiag.proto").info("vor dem Einschalten")
            datei = protokolldatei.datei_einschalten(ordner=Path(ordner))
            logging.getLogger("vagdiag.proto").info("nach dem Einschalten")
            protokolldatei.datei_ausschalten()
            logging.getLogger("vagdiag.proto").info("nach dem Ausschalten")
            inhalt = datei.read_text(encoding="utf-8")
        self.assertIn("vor dem Einschalten", inhalt)
        self.assertIn("nach dem Einschalten", inhalt)
        self.assertNotIn("nach dem Ausschalten", inhalt)
        self.assertIsNone(protokolldatei.aktuelle_datei())

    def test_langsame_datei_haelt_niemanden_auf(self):
        # Im Auto wartete der Diagnose-Thread alle 30,72 s bis zu 47 ms auf das
        # Dateisystem. Jetzt schreibt ein eigener Thread – wer protokolliert, wartet nie.
        import logging
        import time

        class Langsam(logging.FileHandler):
            def emit(self, record):
                time.sleep(0.05)
                super().emit(record)

        alt = protokolldatei._handler
        protokolldatei._handler = lambda pfad: Langsam(pfad, encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory() as ordner:
                protokolldatei.einrichten(schreiben=False)
                datei = protokolldatei.datei_einschalten(ordner=Path(ordner))
                log = logging.getLogger("vagdiag.bytes")
                dauer = []
                for i in range(10):
                    start = time.perf_counter()
                    log.debug("TX %02X", i)
                    dauer.append(time.perf_counter() - start)
                protokolldatei.datei_ausschalten()   # wartet, bis alles geschrieben ist
                inhalt = datei.read_text(encoding="utf-8")
        finally:
            protokolldatei._handler = alt
        self.assertLess(max(dauer), 0.01, dauer)
        for i in range(10):
            self.assertIn(f"TX {i:02X}", inhalt)

    def test_langsame_konsole_haelt_niemanden_auf(self):
        # Unter Windows hält schon ein Klick ins Konsolenfenster jede Ausgabe an. Mit -v
        # oder --bytes schreibt deshalb ein eigener Thread auf die Konsole.
        import io
        import logging
        import sys

        class Langsam(io.StringIO):
            def write(self, text):
                time.sleep(0.05)
                return super().write(text)

        konsole = Langsam()
        alt = sys.stderr
        sys.stderr = konsole
        try:
            protokolldatei.einrichten(konsole=True, bytes_in_konsole=True, schreiben=False)
        finally:
            sys.stderr = alt
        log = logging.getLogger("vagdiag.bytes")
        dauer = []
        for i in range(10):
            start = time.perf_counter()
            log.debug("TX %02X", i)
            dauer.append(time.perf_counter() - start)
        protokolldatei.einrichten(schreiben=False)    # wartet, bis alles ausgegeben ist
        self.assertLess(max(dauer), 0.01, dauer)
        for i in range(10):
            self.assertIn(f"TX {i:02X}", konsole.getvalue())

    def test_konsole_ohne_einzelbytes(self):
        import io
        import logging
        import sys
        konsole = io.StringIO()
        alt = sys.stderr
        sys.stderr = konsole
        try:
            protokolldatei.einrichten(konsole=True, schreiben=False)
        finally:
            sys.stderr = alt
        logging.getLogger("vagdiag.bytes").debug("TX 5A")
        logging.getLogger("vagdiag.proto").info("Verbunden mit 01")
        protokolldatei.einrichten(schreiben=False)
        self.assertNotIn("TX 5A", konsole.getvalue())
        self.assertIn("Verbunden mit 01", konsole.getvalue())
        self.assertNotIn("Verbunden mit 01", konsole.getvalue().split("Verbunden mit 01", 1)[1])

    def test_in_stuecken_schreiben(self):
        # Ein einziger riesiger Schreibaufruf (256.000 Zeilen) hielte den Interpreter – und
        # damit den Diagnose-Thread – viele Millisekunden fest
        class Zaehler:
            def __init__(self):
                self.zeilen = []

            def write(self, text):
                self.zeilen.append(text.count("\n"))

        z = Zaehler()
        stueck = protokolldatei.STUECK
        protokolldatei._in_stuecken(z, [f"Zeile {i}" for i in range(stueck * 2 + 7)])
        self.assertEqual(z.zeilen, [stueck, stueck, 7])

    def test_speichern_in_stuecken(self):
        import logging
        with tempfile.TemporaryDirectory() as ordner:
            protokolldatei.einrichten(schreiben=False)
            log = logging.getLogger("vagdiag.proto")
            for i in range(protokolldatei.STUECK * 2 + 7):
                log.info("Zeile %d", i)
            ziel = protokolldatei.speichern(Path(ordner) / "s.log")
            zeilen = ziel.read_text(encoding="utf-8").splitlines()
        self.assertIn("Protokoll gestartet", zeilen[0])
        self.assertTrue(zeilen[1].endswith("Zeile 0"))
        self.assertTrue(zeilen[-1].endswith(f"Zeile {protokolldatei.STUECK * 2 + 6}"))


if __name__ == "__main__":
    unittest.main()

"""Eingebaute Fehlertexte (fehlercodes.py): sauber, eindeutig, richtig nachgeschlagen.
Start: python -m unittest -v"""

import unittest

from vagdiag import sprache, stellglied
from vagdiag.fehler import Fehler, p_code
from vagdiag.fehlercodes import SAE_P, VAG, VAG_P


class Tabellen(unittest.TestCase):
    def tearDown(self):
        sprache.setzen("de")

    def test_texte_sauber(self):
        for name, tabelle in (("VAG", VAG), ("VAG_P", VAG_P), ("SAE_P", SAE_P)):
            for code, texte in tabelle.items():
                with self.subTest(tabelle=name, code=code):
                    self.assertEqual(len(texte), 2)
                    for text in texte:
                        self.assertTrue(text and text == text.strip(), text)
                        self.assertNotIn("  ", text)
                        self.assertNotIn("{", text)          # Vorlage nicht ausgefüllt
        self.assertGreater(len(VAG), 150)
        self.assertGreater(len(VAG_P), 100)
        self.assertGreater(len(SAE_P), 180)

    def test_schluessel_und_bereiche(self):
        # fünfstellige VAG-Codes liegen außerhalb der OBD-Bereiche – sonst würden sie die
        # P-Code-Texte verdecken
        for code in VAG:
            self.assertTrue(0 < code < 16384 or code == 65535, code)
        for code in VAG_P:
            self.assertRegex(code, r"^P1\d{3}$")
            self.assertEqual(p_code(16408 + int(code[1:])), code)
        for code in SAE_P:
            self.assertRegex(code, r"^P0\d{3}$")
            self.assertEqual(p_code(16384 + int(code[1:])), code)
        self.assertFalse(set(VAG_P) & set(SAE_P))

    def test_lambdasonden_reihen(self):
        self.assertEqual(SAE_P["P0130"][0], "Lambdasonde vor Kat (Bank 1, Sonde 1): Stromkreis")
        self.assertEqual(SAE_P["P0141"][0], "Lambdasonde nach Kat (Bank 1, Sonde 2): Heizung Stromkreis")
        self.assertEqual(SAE_P["P0155"][1],
                         "Oxygen Sensor before Catalyst (Bank 2, Sensor 1): Heater Circuit")
        self.assertEqual(SAE_P["P0262"][0], "Einspritzventil Zylinder 1: Stromkreis Signal zu groß")
        self.assertEqual(VAG_P["P1240"][1], "Fuel Injector Cylinder 4 (N33): Open Circuit")
        self.assertEqual(SAE_P["P0770"][0], "Schaltmagnetventil E: Fehlfunktion")


class Nachschlagen(unittest.TestCase):
    def tearDown(self):
        sprache.setzen("de")

    def test_p1650_aus_dem_polo(self):
        f = Fehler(18058, 0xA3)
        self.assertEqual(f.p_code, "P1650")
        self.assertEqual(f.beschreibung, "Datenbus Antrieb: Botschaft vom Kombiinstrument fehlt")
        self.assertEqual(f.zeile(), "18058 – P1650 – Datenbus Antrieb: Botschaft vom Kombiinstrument "
                                    "fehlt – 35-10 – sporadisch")
        sprache.setzen("en")
        self.assertEqual(f.beschreibung,
                         "Powertrain Data Bus: Missing Message from Instrument Cluster")

    def test_stichproben(self):
        erwartet = {16486: "Luftmassenmesser: Signal zu klein",          # P0102
                    17978: "Motorsteuergerät durch Wegfahrsperre gesperrt",  # P1570
                    18010: "Spannungsversorgung Klemme 30: Spannung zu klein",  # P1602
                    17544: "Gemischadaption Bank 1 (additiv): System zu mager",  # P1136
                    16512: "Kühlmitteltemperatur unter der Regeltemperatur des Thermostats",  # P0128
                    283: "ABS-Drehzahlfühler vorn links (G47)",
                    1312: "Datenbus Antrieb",
                    1176: "Schlüssel",
                    532: "Versorgungsspannung B+",
                    65535: "Steuergerät defekt (interner Speicherfehler)"}
        for code, text in erwartet.items():
            with self.subTest(code=code):
                self.assertEqual(Fehler(code, 0).beschreibung, text)
        self.assertEqual(Fehler(12345, 0).beschreibung, "(kein Klartext hinterlegt)")
        self.assertEqual(Fehler(17000, 0).beschreibung, "(kein Klartext hinterlegt)")   # P0616

    def test_stellglied_namen_vor_fehlertexten(self):
        # 0x0243 = 00579: als Fehler „Klopfregelung Zylinder 3“, als Stellglied beim EDC15 N75
        self.assertEqual(Fehler(579, 0).beschreibung, "Klopfregelung Zylinder 3")
        self.assertEqual(stellglied.Stellglied(0x0243).name,
                         "Magnetventil Ladedruckbegrenzung (N75)")
        self.assertEqual(stellglied.Stellglied(0x0296).name, "Drehzahlmesser")
        # ohne eigenen Stellglied-Namen hilft der Fehlertext (00625 Geschwindigkeitssignal)
        self.assertEqual(stellglied.Stellglied(625).name, "Geschwindigkeitssignal")


if __name__ == "__main__":
    unittest.main()

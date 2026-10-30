# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Verlaufskurve: Reihen, Ausschnitt, Bildpunkte, Zeitachse und das Zeichnen
über einen aufzeichnenden Maler. Start: python -m unittest -v"""

import tempfile
import time
import unittest
from pathlib import Path

from vagdiag import einstellungen, messwerte, sprache, verlauf
from vagdiag.verlauf import Verlauf


class Aufzeichner:
    """Maler, der jeden Aufruf festhält."""

    def __init__(self):
        self.aufrufe = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: self.aufrufe.append((name, a))

    def texte(self):
        return [a[4] for n, a in self.aufrufe if n == "text"]

    def kurven(self):
        return [a for n, a in self.aufrufe if n == "kurve"]


class Reihen(unittest.TestCase):
    def test_neu_bei_anderer_gruppe_oder_einheit(self):
        v = Verlauf()
        v.hinzufuegen((0, 1), 4, "004/2 Bordspannung", "V", 0.0, 13.8, 2)
        v.hinzufuegen((0, 1), 4, None, "V", 1.0, 13.9, 2)          # Name bleibt
        self.assertEqual(v.reihen[(0, 1)].name, "004/2 Bordspannung")
        self.assertEqual(len(v.reihen[(0, 1)].punkte), 2)
        v.hinzufuegen((0, 1), 1, "001/2 Kühlmitteltemperatur", "°C", 2.0, 90.0, 0)
        self.assertEqual(list(v.reihen[(0, 1)].punkte), [(2.0, 90.0)])
        v.hinzufuegen((0, 1), 1, "001/2 Kühlmitteltemperatur", "%", 3.0, 5.0)
        self.assertEqual(v.reihen[(0, 1)].einheit, "%")
        self.assertEqual(len(v.reihen[(0, 1)].punkte), 1)

    def test_ungueltiges_und_rueckwaerts_bleibt_draussen(self):
        v = Verlauf()
        for wert in (None, float("nan"), float("inf")):
            v.hinzufuegen("a", 1, "a", "", 0.0, wert)
        self.assertEqual(v.reihen, {})
        v.hinzufuegen("a", 1, "a", "", 5.0, 1.0)
        v.hinzufuegen("a", 1, "a", "", 4.0, 2.0)
        self.assertEqual(list(v.reihen["a"].punkte), [(5.0, 1.0)])

    def test_nur_die_laengste_spanne_bleibt(self):
        v = Verlauf(max_sekunden=60)
        for s in range(200):
            v.hinzufuegen("a", 1, "a", "", float(s), float(s))
        punkte = v.reihen["a"].punkte
        self.assertEqual(punkte[0][0], 139.0)
        self.assertEqual(punkte[-1][0], 199.0)

    def test_farbe_folgt_der_reihe(self):
        v = Verlauf()
        for schluessel in ((0, 0), (0, 1), (1, 0)):
            v.hinzufuegen(schluessel, 1, "x", "", 0.0, 1.0)
        vorher = v.farbe((1, 0))
        v.entfernen(lambda s: s[0] == 0)
        self.assertEqual(v.farbe((1, 0)), vorher)
        v.hinzufuegen((1, 0), 2, "y", "", 1.0, 1.0)        # neu begonnen: gleiche Farbe
        self.assertEqual(v.farbe((1, 0)), vorher)
        self.assertNotEqual(v.farbe((0, 0)), v.farbe((0, 1)))
        self.assertNotEqual(v.farbe((0, 0), dunkel=False), v.farbe((0, 0), dunkel=True))

    def test_sichtbar_geordnet(self):
        v = Verlauf()
        v.hinzufuegen((2, 0), 1, "c", "", 10.0, 1.0)
        v.hinzufuegen((0, 1), 1, "b", "", 10.0, 1.0)
        v.hinzufuegen((0, 0), 1, "a", "", 1.0, 1.0)
        self.assertEqual([r.name for r in v.sichtbar(10.0, 30)], ["a", "b", "c"])
        self.assertEqual([r.name for r in v.sichtbar(100.0, 30)], [])
        self.assertEqual([r.name for r in v.sichtbar(10.0, 5)], ["b", "c"])


class Rechnung(unittest.TestCase):
    def test_ausschnitt(self):
        r = verlauf.Reihe("a", 1, "a", "")
        r.punkte.extend((float(s), float(s)) for s in range(0, 100, 10))
        self.assertEqual(verlauf.ausschnitt(r, 50.0, 20.0),
                         [(20.0, 20.0), (30.0, 30.0), (40.0, 40.0), (50.0, 50.0)])
        self.assertEqual(verlauf.ausschnitt(r, 200.0, 20.0), [])

    def test_bildpunkte(self):
        punkte = [(0.0, 10.0), (5.0, 20.0), (10.0, 15.0)]
        (linie,) = verlauf.linien(punkte, 10.0, 10.0, 100, 50, 200, 80, (10.0, 20.0))
        self.assertEqual(linie, [(100.0, 130.0), (200.0, 50.0), (300.0, 90.0)])
        # vor dem linken Rand: auf den Rand gezogen
        (linie,) = verlauf.linien([(-2.0, 10.0), (2.0, 10.0)], 10.0, 10.0, 0, 0, 100, 10,
                                  (0.0, 20.0))
        self.assertEqual(linie, [(0.0, 5.0), (20.0, 5.0)])

    def test_luecke_trennt_die_linie(self):
        punkte = [(0.0, 1.0), (1.0, 2.0), (10.0, 3.0), (11.0, 4.0), (30.0, 5.0)]
        teile = verlauf.linien(punkte, 30.0, 30.0, 0, 0, 300, 100)
        self.assertEqual([len(t) for t in teile], [2, 2, 1])

    def test_verdichten_behaelt_spitzen(self):
        # 1000 Werte in 10 Bildpunkten: höchstens vier je Spalte, Spitze und Tal bleiben
        punkte = [(i / 100, 0.0) for i in range(1000)]
        punkte[555] = (5.55, 100.0)
        punkte[777] = (7.77, -100.0)
        (linie,) = verlauf.linien(punkte, 10.0, 10.0, 0, 0, 10, 100, (-100.0, 100.0))
        self.assertLessEqual(len(linie), 4 * 11)
        ys = [y for _, y in linie]
        self.assertEqual((min(ys), max(ys)), (0.0, 100.0))
        self.assertEqual(linie, sorted(linie))          # zeitlich geordnet

    def test_schnell_genug_fuer_eine_stunde(self):
        v = Verlauf()
        for feld in range(12):
            for i in range(20000):
                v.hinzufuegen(feld, 1, str(feld), "", i * 0.18, (i * 7 + feld) % 50)
        maler = Aufzeichner()
        start = time.perf_counter()
        verlauf.zeichnen(maler, v, 3600.0, 3600, 1200, 900)
        dauer = time.perf_counter() - start
        self.assertLess(dauer, 2.0)
        self.assertEqual(len(maler.kurven()), 12)
        self.assertTrue(all(len(k[0]) <= 4 * 1200 for k in maler.kurven()))

    def test_stufen_fuer_lange_zeitachsen(self):
        self.assertIsNone(verlauf.stufe_fuer(60, 1000))
        self.assertEqual(verlauf.stufe_fuer(600, 1000), 1.0)
        self.assertEqual(verlauf.stufe_fuer(3600, 1000), 5.0)
        r = verlauf.Reihe("a", 1, "a", "")
        for i in range(100):                          # 10 Werte je Sekunde, Spitze bei 4,2 s
            r.anhaengen(i / 10, 100.0 if i == 42 else -50.0 if i == 77 else float(i % 3), -1)
        gebuendelt = verlauf.ausschnitt(r, 9.9, 9.9, 1.0)
        self.assertLess(len(gebuendelt), 50)
        self.assertEqual(max(w for _, w in gebuendelt), 100.0)
        self.assertEqual(min(w for _, w in gebuendelt), -50.0)
        self.assertEqual(gebuendelt, sorted(gebuendelt, key=lambda p: p[0]))
        self.assertEqual(gebuendelt[-1], (9.9, float(99 % 3)))
        self.assertTrue(all(0 <= z <= 9.9 for z, _ in gebuendelt))
        # fünf Sekunden: zwei Bündel
        self.assertEqual(len(r.buendel[5.0]), 2)

    def test_alte_werte_aus_den_buendeln(self):
        v = Verlauf()
        for i in range(20000):
            v.hinzufuegen("a", 1, "a", "", i * 0.1, float(i))
        r = v.reihen["a"]
        r.punkte = type(r.punkte)(list(r.punkte)[-100:], maxlen=verlauf.MAX_PUNKTE)
        self.assertEqual(verlauf.wert_bei(r, 50.05), 509.0)      # letzter Wert der Sekunde 50
        self.assertEqual(verlauf.wert_bei(r, 1999.9), 19999.0)
        self.assertEqual(len(v.sichtbar(1999.9, 3600)), 1)

    def test_zeitmarken(self):
        for spanne, _ in verlauf.ZEITACHSEN:
            marken = verlauf.zeitmarken(spanne)
            with self.subTest(spanne=spanne):
                self.assertLessEqual(len(marken), 7)
                self.assertGreaterEqual(len(marken), 4)
                self.assertEqual(marken[0], (0.0, "jetzt"))
                self.assertLessEqual(marken[-1][0], spanne)
        self.assertEqual([m[1] for m in verlauf.zeitmarken(30)][:3], ["jetzt", "−5 s", "−10 s"])
        self.assertEqual(verlauf.zeitmarken(3600)[-1], (3600.0, "−60 min"))
        self.assertEqual(verlauf.zeitmarken(60, "14:03:22")[0][1], "14:03:22")

    def test_wert_zur_zeit(self):
        r = verlauf.Reihe("a", 1, "a", "V", 2)
        r.punkte.extend([(0.0, 12.0), (1.0, 13.5), (20.0, 14.0)])
        self.assertIsNone(verlauf.wert_bei(r, -1.0))
        self.assertEqual(verlauf.wert_bei(r, 1.5), 13.5)
        self.assertIsNone(verlauf.wert_bei(r, 10.0))              # Lücke
        self.assertEqual(verlauf.wert_text_bei(r, 20.0), "14,00 V")
        self.assertEqual(verlauf.wert_text(r), "14,00 V")

    def test_zuendwinkel_mit_richtung(self):
        r = verlauf.Reihe("a", 1, "a", verlauf.VOR_OT, 1)
        r.punkte.append((0.0, -3.0))
        self.assertEqual(verlauf.wert_text(r), "3,0 ° n.OT")
        r.punkte.append((1.0, 12.0))
        self.assertEqual(verlauf.wert_text(r), "12,0 ° v.OT")
        sprache.setzen("en")
        try:
            self.assertEqual(verlauf.wert_text(r), "12.0 ° BTDC")
            self.assertEqual(verlauf.abstand_text(12.34), "−12.3 s")
        finally:
            sprache.setzen("de")
        self.assertEqual(verlauf.abstand_text(270), "−4,5 min")


class Kurvenwert(unittest.TestCase):
    def test_zahlen_texte_und_ungueltige(self):
        zahl, einheit, stellen = verlauf.kurvenwert(messwerte.umrechnen(1, 21, 70, 198))
        self.assertEqual((round(zahl, 6), einheit, stellen), (13.86, "V", 2))
        self.assertIsNone(verlauf.kurvenwert(messwerte.umrechnen(1, 37, 0, 5)))       # Text
        self.assertIsNone(verlauf.kurvenwert(messwerte.umrechnen(1, 36, 0xFF, 0xFF)))  # FF FF
        self.assertIsNone(verlauf.kurvenwert(messwerte.umrechnen(1, 61, 0, 140)))     # NaN

    def test_zuendwinkel_vor_ot_positiv(self):
        for typ, a, b, wert in ((4, 100, 115, 12.0), (4, 100, 130, -3.0), (27, 75, 144, 12.0),
                                (0x83, 1, 20, 20.0), (0x83, 2, 40, -10.0)):
            with self.subTest(typ=typ, b=b):
                zahl, einheit, _ = verlauf.kurvenwert(messwerte.umrechnen(1, typ, a, b))
                self.assertEqual((round(zahl, 6), einheit), (wert, verlauf.VOR_OT))

    def test_gruppe_000(self):
        roh = messwerte.rohwerte_auswerten(bytes([190]))[0]
        self.assertEqual(verlauf.kurvenwert(roh), (190.0, "", 0))
        self.assertEqual(verlauf.kurvenwert(roh, (90.0, "°C", 0)), (90.0, "°C", 0))


class Zeichnen(unittest.TestCase):
    def verlauf_(self):
        v = Verlauf()
        for i in range(30):
            v.hinzufuegen((0, 0), 4, "004/1 Motordrehzahl", "/min", float(i), 800 + i, 0)
            v.hinzufuegen((0, 1), 4, "004/2 Bordspannung", "V", float(i), 13.8, 2)
        return v

    def test_streifen_je_reihe(self):
        maler = Aufzeichner()
        verlauf.zeichnen(maler, self.verlauf_(), 29.0, 30, 800, 400)
        texte = maler.texte()
        self.assertIn("004/1 Motordrehzahl", texte)
        self.assertIn("829 /min", texte)
        self.assertIn("13,80 V", texte)
        self.assertIn("jetzt", texte)
        self.assertEqual(len(maler.kurven()), 2)
        self.assertEqual(maler.aufrufe[0][0], "flaeche")             # Hintergrund zuerst
        # alle Linien innerhalb des Bildes
        for punkte, _farbe, _breite in maler.kurven():
            for x, y in punkte:
                self.assertTrue(0 <= x <= 800 and 0 <= y <= 400, (x, y))

    def test_mauszeiger_zeigt_werte_dieser_zeit(self):
        maler = Aufzeichner()
        links, rechts = verlauf.RAND, 800 - verlauf.RAND - verlauf.SKALA
        mitte = links + (rechts - links) * (14.0 + 1) / 30       # 14 s nach Beginn (−1 … 29)
        verlauf.zeichnen(maler, self.verlauf_(), 29.0, 30, 800, 400, zeiger=mitte)
        texte = maler.texte()
        self.assertIn("814 /min", texte)
        self.assertIn("−15,0 s", texte)

    def test_ohne_werte_ein_hinweis(self):
        maler = Aufzeichner()
        verlauf.zeichnen(maler, Verlauf(), 0.0, 60, 800, 300, dunkel=True)
        self.assertTrue(any(t.startswith("Noch keine Werte") for t in maler.texte()))
        self.assertEqual(maler.aufrufe[0][1][4], verlauf.GRUND[True]["flaeche"])

    def test_zu_klein_zeichnet_nur_den_grund(self):
        maler = Aufzeichner()
        verlauf.zeichnen(maler, self.verlauf_(), 29.0, 30, 60, 30)
        self.assertEqual([n for n, _ in maler.aufrufe], ["flaeche"])

    def test_mindesthoehe(self):
        self.assertEqual(verlauf.mindesthoehe(0), verlauf.mindesthoehe(1))
        self.assertGreater(verlauf.mindesthoehe(10), 10 * verlauf.STREIFEN_MIN)


class Einstellung(unittest.TestCase):
    """Die Kurve ist abschaltbar und standardmäßig aus – auch wenn der Eintrag in
    einstellungen.json fehlt."""

    def test_standardmaessig_aus(self):
        self.assertIs(einstellungen.STANDARD["verlauf_an"], False)
        alt = einstellungen.DATEI
        with tempfile.TemporaryDirectory() as ordner:
            datei = Path(ordner) / "einstellungen.json"
            datei.write_text('{"version": 2, "verlauf_spanne": 600}', encoding="utf-8")
            try:
                einstellungen._zuruecksetzen_fuer_tests(datei)
                werte = einstellungen.laden()
                self.assertIs(werte["verlauf_an"], False)
                self.assertEqual(werte["verlauf_spanne"], 600)
                einstellungen.speichern(verlauf_an=True)
                einstellungen._zuruecksetzen_fuer_tests(datei)
                self.assertIs(einstellungen.laden()["verlauf_an"], True)
            finally:
                einstellungen._zuruecksetzen_fuer_tests(alt)


if __name__ == "__main__":
    unittest.main()

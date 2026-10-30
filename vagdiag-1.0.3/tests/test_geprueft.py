# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Hinweis „nicht geprüft“: nach Teilenummer, nur ein Text – gesperrt wird dadurch nichts.
Start: python -m unittest -v"""

import unittest

from vagdiag import berichte, geprueft, ident, scan, sprache
from vagdiag.experte import verfuegbarkeit
from vagdiag.kw1281 import ASCII, Block, Verbindung

HINWEIS = "An diesem Steuergerät ist vagdiag nicht geprüft"


def verbindung(teilenummer: str, bauteil: str = "TEST", adresse: int = 0x03) -> Verbindung:
    """Wie nach der Reizung: erster Kennungsblock die Teilenummer (12 Zeichen), dann das
    Bauteil – ohne Teilenummer gar kein Kennungsblock."""
    bloecke = ([Block(0, ASCII, teilenummer.ljust(12).encode("ascii")),
                Block(1, ASCII, bauteil.ljust(12).encode("ascii"))] if teilenummer else [])
    return Verbindung(adresse, "KW1281", 1281, 10400, True, bloecke)


class Teilenummern(unittest.TestCase):
    def tearDown(self):
        sprache.setzen("de")

    def test_die_sechs_geprueften(self):
        for nummer in ("6K0906032M", "6K9920806", "6X0907379 B", "6X0953257", "1J0909609 Q",
                       "6N0909901", "6x0 907 379 b", "6K0-906-032.M"):
            with self.subTest(nummer=nummer):
                self.assertTrue(geprueft.ist_geprueft(nummer))
                self.assertIsNone(geprueft.hinweis(verbindung(nummer)))

    def test_andere_index_und_fremde(self):
        # anderer Index (C statt B) zählt als anderes Steuergerät
        for nummer in ("6X0907379 C", "6K0906032", "036906034AM", "1J0920806"):
            with self.subTest(nummer=nummer):
                self.assertFalse(geprueft.ist_geprueft(nummer))
                self.assertTrue(geprueft.hinweis(verbindung(nummer)).startswith(HINWEIS))

    def test_ohne_teilenummer(self):
        # z. B. das Kombi unter 3F, das ohne Identifikation antwortet
        text = geprueft.hinweis(verbindung("", "", 0x3F))
        self.assertIn("Keine Teilenummer", text)
        self.assertIsNone(geprueft.hinweis(None))

    def test_simulator_wie_sein_vorbild(self):
        self.assertIsNone(geprueft.hinweis(verbindung("SIM906032")))
        self.assertIsNone(geprueft.hinweis(verbindung("SIM953257")))
        # KWP2000-Simulatoren haben kein geprüftes Vorbild
        self.assertTrue(geprueft.hinweis(verbindung("SIM906032KWP")).startswith(HINWEIS))
        self.assertTrue(geprueft.hinweis(verbindung("SIMKWP2000")).startswith(HINWEIS))

    def test_kennung_und_englisch(self):
        self.assertIsNone(geprueft.hinweis_kennung((0x17, "6K9920806", "KOMBI")))
        self.assertTrue(geprueft.hinweis_kennung((0x17, "6K9920806A", "KOMBI")))
        self.assertIsNone(geprueft.hinweis_kennung(()))
        sprache.setzen("en")
        self.assertIn("has not been tested", geprueft.hinweis(verbindung("6X0907379 C")))
        self.assertIn("6K0906032M (Engine electronics ME7.5.10)", geprueft.liste())


class Anzeige(unittest.TestCase):
    def test_identifikation(self):
        self.assertIn(HINWEIS, "\n".join(ident.zeilen(verbindung("6X0907379 C"))))
        self.assertNotIn(HINWEIS, "\n".join(ident.zeilen(verbindung("6X0907379 B"))))

    def test_berichte(self):
        fremd, eigen = (0x03, "6X0907379 C", "ABS"), (0x03, "6X0907379 B", "ABS")
        self.assertTrue(any(z.startswith(HINWEIS)
                            for z in berichte.fehlerspeicher(fremd, [], "12:00", False)))
        self.assertFalse(any(z.startswith(HINWEIS)
                             for z in berichte.fehlerspeicher(eigen, [], "12:00", False)))
        self.assertTrue(any(z.startswith(HINWEIS) for z in berichte.anpassung(fremd, [], False)))
        self.assertTrue(any(z.startswith(HINWEIS)
                            for z in berichte.identifikation(verbindung("6X0907379 C"), False)))

    def test_scan(self):
        fremd = scan.ScanEintrag(0x03, "gefunden", verbindung("6X0907379 C"), [])
        eigen = scan.ScanEintrag(0x17, "gefunden", verbindung("6K9920806", adresse=0x17), [])
        stumm = scan.ScanEintrag(0x08)
        self.assertEqual(fremd.status_text, "gefunden – nicht geprüft")
        self.assertEqual(eigen.status_text, "gefunden")
        self.assertEqual(stumm.status_text, "keine Antwort")
        self.assertIsNone(stumm.hinweis)
        text = "\n".join(scan.bericht([fremd, eigen, stumm]))
        self.assertIn("03 – Bremsenelektronik (ABS): gefunden – nicht geprüft", text)
        self.assertEqual(text.count(HINWEIS), 1)


class NichtsGesperrt(unittest.TestCase):
    """Der Hinweis ist nur ein Text: Lesen, Löschen und Expertenfunktionen hängen nicht davon
    ab (die Sperren in experte.py prüfen andere Dinge)."""

    def test_verfuegbarkeit_gleich(self):
        geprueft_ = verfuegbarkeit(True, verbindung("6K0906032M", "ME7.5.10", 0x01), False, None)
        fremd = verfuegbarkeit(True, verbindung("036906034AM", "MOTRONIC", 0x01), False, None)
        self.assertEqual({k: v.ok for k, v in geprueft_.items()},
                         {k: v.ok for k, v in fremd.items()})


if __name__ == "__main__":
    unittest.main()

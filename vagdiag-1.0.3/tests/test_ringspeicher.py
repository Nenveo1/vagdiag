# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Passiver Fahrtenschreiber: Ringspeicher über Fahrten und Neustarts, Export
genau der Zeitspanne, Zusammenfassung dieser Zeitspanne. Start: python -m unittest -v"""

import csv
import tempfile
import time
import unittest
from pathlib import Path

from vagdiag import einstellungen, fahrtenschreiber, messwerte, ringspeicher, sprache
from vagdiag.fahrtenschreiber import (FAHRT, KOPF, Besuch, FahrtPlan, RingDatei,
                                      fenster_zusammenfassung, passiv_exportieren)
from vagdiag.kw1281 import Timing
from vagdiag.port import PortError
from vagdiag.ringspeicher import Ring, RingBelegt
from vagdiag.session import DiagSession
from vagdiag.sim import sim_port
from vagdiag.sprache import t

SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0,
                 byte_frist=0.5, kwp_p4_frist=0.5)

GRUPPE_4 = messwerte.gruppe_auswerten(bytes.fromhex("01 C8 05 15 46 95 05 0A 82 05 0A 78"))
NAMEN_4 = ["Motordrehzahl", "Bordspannung", "Kühlmitteltemperatur", "Ansauglufttemperatur"]
GRUPPE_3 = messwerte.gruppe_auswerten(bytes.fromhex("01 C8 05 12 FA 1D 21 FF 07 1B 4B 90"))
NAMEN_3 = ["Motordrehzahl", "Saugrohrdruck", "Drosselklappenwinkel", "Zündwinkel"]


class Uhr:
    def __init__(self):
        self.jetzt = 1000.0

    def __call__(self):
        return self.jetzt


def lesen(pfad: Path) -> list[list[str]]:
    with open(pfad, encoding="utf-8-sig") as datei:
        erste = datei.readline()
        datei.seek(0)
        return list(csv.reader(datei, delimiter=";" if ";" in erste else ","))


class Grundlagen(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self._tmp.name) / "passiv"

    def tearDown(self):
        sprache.setzen("de")
        self._tmp.cleanup()

    def fahren(self, datei: RingDatei, uhr: Uhr, sekunden: float, takt: float = 0.5,
               gruppen=((4, GRUPPE_4, NAMEN_4), (3, GRUPPE_3, NAMEN_3))) -> None:
        ende = uhr.jetzt + sekunden
        i = 0
        while uhr.jetzt < ende - 1e-9:
            gruppe, werte, namen = gruppen[i % len(gruppen)]
            datei.messwerte(0x01, gruppe, FAHRT, werte, namen, "6K0906032M")
            uhr.jetzt += takt
            i += 1

    def test_fenster_namen(self):
        self.assertEqual([ringspeicher.fenster_aus_name(n) for n in ("5min", "20min", "1h", "5h",
                                                                     "20", "60min", "1H")],
                         [300, 1200, 3600, 18000, 1200, 3600, 3600])
        with self.assertRaises(ValueError):
            ringspeicher.fenster_aus_name("10min")
        self.assertEqual(ringspeicher.fenster_text(1200), "20 Minuten")
        self.assertEqual(ringspeicher.fenster_text(6), "6 s")

    def test_stuecke_und_aufraeumen(self):
        uhr = Uhr()
        datei = RingDatei(self.ordner, 180, uhr)
        self.addCleanup(datei.schliessen)
        self.fahren(datei, uhr, 400, takt=1.0)
        stuecke = datei.ring.stuecke
        gesamt = sum(s.fahrzeit for s in stuecke)
        # aufgeräumt wird beim Wechsel des Stücks: höchstens ein Stück zu viel
        self.assertGreaterEqual(gesamt, 180)
        self.assertLess(gesamt - stuecke[0].fahrzeit, 180 + ringspeicher.STUECK)
        self.assertLess(sum(s.fahrzeit for s in stuecke[:-1]) - stuecke[0].fahrzeit, 180)
        self.assertTrue(all(abs(s.fahrzeit - 59.5) < 0.51 for s in stuecke[:-1]),
                        [s.fahrzeit for s in stuecke])
        self.assertEqual(sorted(p.name for p in self.ordner.glob("stueck-*.csv")),
                         [s.pfad.name for s in stuecke])
        # Stücke zu 59 s (das nächste Messwert-Paar hätte 60 s erreicht): 7 Stücke, beim
        # Beginn des siebten sind 1 und 2 überzählig
        self.assertEqual([s.nummer for s in stuecke], [3, 4, 5, 6, 7])
        # auf der Platte steht dieselbe Fahrzeit wie im Speicher
        self.assertEqual([round(s.fahrzeit, 3) for s in ringspeicher.stuecke(self.ordner)],
                         [round(s.fahrzeit, 3) for s in stuecke])
        datei.schliessen()
        # Feldnamen stehen am Anfang jedes Stücks
        zeilen = lesen(stuecke[1].pfad)
        self.assertEqual(zeilen[0][-2:], ringspeicher.INTERN)
        self.assertTrue(zeilen[1][13].startswith("01/004: Motordrehzahl | Bordspannung"))

    def test_ueber_neustart_hinweg(self):
        uhr = Uhr()
        erste = RingDatei(self.ordner, 300, uhr)
        self.fahren(erste, uhr, 150)
        erste.schliessen()
        vorher = ringspeicher.stuecke(self.ordner)
        uhr.jetzt += 7200                                         # zwei Stunden geparkt
        zweite = RingDatei(self.ordner, 300, uhr)
        self.assertEqual(zweite.ring.aktuell.nummer, vorher[-1].nummer + 1)
        self.assertAlmostEqual(zweite.fahrzeit_gesamt, sum(s.fahrzeit for s in vorher), 3)
        self.fahren(zweite, uhr, 100)
        zweite.schliessen()
        gesamt = sum(s.fahrzeit for s in ringspeicher.stuecke(self.ordner))
        self.assertAlmostEqual(gesamt, 249.0, delta=1.5)          # nichts gelöscht, Parken zählt nicht

    def test_parken_zaehlt_hoechstens_zehn_sekunden(self):
        uhr = Uhr()
        datei = RingDatei(self.ordner, 3600, uhr)
        self.fahren(datei, uhr, 30)
        uhr.jetzt += 3600                                         # Zündung aus, Programm läuft
        self.fahren(datei, uhr, 30)
        self.assertAlmostEqual(datei.fahrzeit_gesamt, 29.5 + 10 + 29.5, delta=0.6)
        datei.schliessen()

    def test_nur_ein_schreiber(self):
        erste = Ring(self.ordner, 300, [t(k) for k in KOPF])
        with self.assertRaises(RingBelegt):
            Ring(self.ordner, 300, [t(k) for k in KOPF])
        erste.schliessen()
        zweite = Ring(self.ordner, 300, [t(k) for k in KOPF])
        zweite.schliessen()

    def test_export_genau_die_zeitspanne(self):
        uhr = Uhr()
        datei = RingDatei(self.ordner, 120, uhr)
        datei.ereignis("Fahrtenschreiber gestartet", art=ringspeicher.LAUF)
        self.fahren(datei, uhr, 250)
        datei.ereignis("Fehlerspeicher 01 – Motorelektronik: kein Fehler", 0x01, FAHRT,
                       ringspeicher.FEHLERSPEICHER)
        datei.schliessen()
        ziel = Path(self._tmp.name) / "export.csv"
        auszug = ringspeicher.exportieren(self.ordner, 120, ziel, [t(k) for k in KOPF])
        zeilen = lesen(ziel)
        self.assertEqual(zeilen[0], [t(k) for k in KOPF])
        self.assertEqual(len(zeilen[0]), len(zeilen[-1]))         # interne Spalten weg
        sekunden = [float(z[1].replace(",", ".")) for z in zeilen[1:]]
        self.assertGreaterEqual(min(sekunden), 0)
        self.assertAlmostEqual(max(sekunden), 120, delta=0.01)
        self.assertEqual(sekunden, sorted(sekunden))
        daten = [z for z in zeilen[1:] if z[3]]
        self.assertAlmostEqual(len(daten), 240, delta=2)
        self.assertEqual(len(auszug.daten), len(daten))
        self.assertAlmostEqual(auszug.fahrzeit, 120, delta=0.01)
        # vor den ersten Werten jeder Gruppe ihre Feldnamen
        erste = {}
        for i, z in enumerate(zeilen[1:]):
            if z[3]:
                erste.setdefault(z[3], i)
        for gruppe, name in (("004", "01/004: Motordrehzahl"), ("003", "01/003: Motordrehzahl")):
            vorher = [z[13] for z in zeilen[1:erste[gruppe] + 1] if z[13]]
            self.assertTrue(any(v.startswith(name) for v in vorher), (gruppe, vorher))
        self.assertEqual([n.art for n in auszug.notizen], [ringspeicher.FEHLERSPEICHER])
        self.assertEqual(auszug.laeufe, 1)
        gruppe_4 = next(d for d in auszug.daten if d.gruppe == 4)
        self.assertEqual([f[0] for f in gruppe_4.felder], NAMEN_4)
        self.assertEqual(gruppe_4.felder[1][1:], [10.43, "", None])
        self.assertEqual((gruppe_4.adresse, gruppe_4.phase, gruppe_4.teil),
                         (0x01, FAHRT, "6K0906032M"))

    def test_noch_nicht_voll(self):
        uhr = Uhr()
        datei = RingDatei(self.ordner, 1200, uhr)
        self.fahren(datei, uhr, 90)
        datei.schliessen()
        auszug = ringspeicher.exportieren(self.ordner, 1200, Path(self._tmp.name) / "e.csv",
                                          [t(k) for k in KOPF])
        self.assertAlmostEqual(auszug.fahrzeit, 89.5, delta=0.01)
        zeilen = fenster_zusammenfassung(auszug, FahrtPlan(), 1200)
        self.assertIn("Die Zeitspanne ist noch nicht voll.", zeilen)
        self.assertTrue(zeilen[0].startswith("Passiver Fahrtenschreiber – die letzten 20 Minuten"))
        self.assertTrue(any(z.startswith("Bordspannung:") for z in zeilen), zeilen)

    def test_sprache_gewechselt(self):
        uhr = Uhr()
        datei = RingDatei(self.ordner, 600, uhr)
        self.fahren(datei, uhr, 61)                               # deutsch
        datei.schliessen()
        sprache.setzen("en")
        datei = RingDatei(self.ordner, 600, uhr)
        self.fahren(datei, uhr, 61)                               # englisch
        datei.schliessen()
        ziel = Path(self._tmp.name) / "en.csv"
        ringspeicher.exportieren(self.ordner, 600, ziel, [t(k) for k in KOPF])
        zeilen = lesen(ziel)
        self.assertEqual(zeilen[0][:2], ["Time", "Seconds"])
        daten = [z for z in zeilen[1:] if z[3]]
        self.assertTrue(all("," not in z[1] and "," not in z[7] for z in daten))
        self.assertEqual({z[4] for z in daten}, {"Drive"})
        zuendwinkel = {z[12] for z in daten if z[3] == "003"}
        self.assertEqual(zuendwinkel, {"° BTDC"})
        self.assertTrue(all("." in z[0][19:] for z in daten), daten[0][0])
        # und zurück
        sprache.setzen("de")
        ziel = Path(self._tmp.name) / "de.csv"
        ringspeicher.exportieren(self.ordner, 600, ziel, [t(k) for k in KOPF])
        daten = [z for z in lesen(ziel)[1:] if z[3]]
        self.assertEqual({z[12] for z in daten if z[3] == "003"}, {"° v.OT"})
        self.assertEqual({z[4] for z in daten}, {"Fahrt"})
        self.assertTrue(all("." not in z[7] for z in daten))

    def test_abgeschnittene_zeile_und_fremde_dateien(self):
        uhr = Uhr()
        datei = RingDatei(self.ordner, 600, uhr)
        self.fahren(datei, uhr, 20)
        datei.schliessen()
        stueck = ringspeicher.stuecke(self.ordner)[-1]
        with open(stueck.pfad, "a", encoding="utf-8") as d:
            d.write('2026-10-28 14:00:00,000;1,0;01;004;Fahrt;8')     # Absturz mitten im Schreiben
        (self.ordner / "notiz.txt").write_text("x")
        (self.ordner / "stueck-abc.csv").write_text("x")
        self.assertAlmostEqual(ringspeicher.stuecke(self.ordner)[-1].fahrzeit, 19.5, delta=0.01)
        auszug = ringspeicher.exportieren(self.ordner, 600, Path(self._tmp.name) / "x.csv",
                                          [t(k) for k in KOPF])
        self.assertEqual(len(auszug.daten), 40)

    def test_leerer_ordner(self):
        self.assertFalse(ringspeicher.vorhanden(self.ordner))
        self.assertFalse(ringspeicher.vorhanden(Path(self._tmp.name)))
        auszug = ringspeicher.exportieren(self.ordner, 300, Path(self._tmp.name) / "leer.csv",
                                          [t(k) for k in KOPF])
        self.assertEqual((auszug.zeilen, auszug.daten), (0, []))
        zeilen = fenster_zusammenfassung(auszug, FahrtPlan(), 300)
        self.assertIn("Im Ringspeicher sind noch keine Messwerte.", zeilen)


class MitSimulator(unittest.TestCase):
    """Zwei Läufe hintereinander (wie zwei Fahrten mit Neustart dazwischen), im zweiten ein
    Ereignis: fahrt-passiv.csv enthält beide, die Sicherung bleibt."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self._tmp.name)
        self._alt = einstellungen.DATEI
        einstellungen._zuruecksetzen_fuer_tests(self.ordner / "e.json")
        self._stueck = ringspeicher.STUECK
        ringspeicher.STUECK = 2.0

    def tearDown(self):
        ringspeicher.STUECK = self._stueck
        einstellungen._zuruecksetzen_fuer_tests(self._alt)
        self._tmp.cleanup()

    def lauf(self, sekunden: float, ereignis: bool = False):
        s = DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=True, zeitfaktor=20.0),
                        SCHNELL, keepalive=0.05).start()
        try:
            plan = FahrtPlan(besuche=[Besuch(0x17, (1, 2, 3), 1.0, 0.3)], stand_dauer=0.2,
                             volle_runde_nach=0.3, stand_bestaetigt=0.1, pruefung=False,
                             passiv=6.0)
            future = s.fahrt_starten(plan, self.ordner, sim=True)
            time.sleep(sekunden / 2)
            if ereignis:
                s.fahrt_ereignis("Test")
            time.sleep(sekunden / 2)
            s.fahrt_beenden()
            return future.result(30)
        finally:
            s.schliessen()

    def test_zwei_fahrten_und_ereignis(self):
        erste = self.lauf(4.0)
        self.assertEqual(erste.csv_datei.name, "sim-fahrt-passiv.csv")
        self.assertTrue(erste.txt_datei.name.endswith("-zusammenfassung.txt"))
        self.assertIn("Fahrten: 1", erste.zeilen[1])
        zweite = self.lauf(4.0, ereignis=True)
        self.assertEqual(zweite.csv_datei, erste.csv_datei)      # bei jedem Ende neu
        self.assertIn("Fahrten: 2", zweite.zeilen[1])
        self.assertEqual(len(zweite.sicherungen), 1)
        gesichert = zweite.sicherungen[0]
        self.assertTrue(gesichert.name.startswith("sim-fahrt-passiv-gesichert-"))
        self.assertTrue(gesichert.exists())
        self.assertTrue(gesichert.with_name(gesichert.stem + "-zusammenfassung.txt").exists())
        self.assertTrue(any("EREIGNIS (Test)" in z for z in zweite.zeilen), zweite.zeilen)
        self.assertTrue(any("Fehlerspeicher 01 – Motorelektronik" in z for z in zweite.zeilen))
        self.assertIn(str(gesichert), "\n".join(zweite.zeilen))
        zeilen = lesen(zweite.csv_datei)
        sekunden = [float(z[1].replace(",", ".")) for z in zeilen[1:]]
        self.assertAlmostEqual(max(sekunden), 6.0, delta=0.01)
        self.assertTrue((self.ordner / "passiv-sim").is_dir())
        self.assertFalse((self.ordner / "passiv").exists(), "Simulator nie im echten Ring")

    def test_nach_einem_fehler_frei(self):
        """Endet ein Lauf unerwartet (z. B. Kabel gezogen), ist der Ringspeicher danach
        wieder frei – auch im selben Programm, solange der Fahrtenschreiber noch lebt."""
        s = DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=False), SCHNELL,
                        keepalive=0.05)
        plan = FahrtPlan(besuche=[], pruefung=False, passiv=6.0)
        schreiber = fahrtenschreiber.Fahrtenschreiber(s, plan, self.ordner, sim=True)
        with self.assertRaises(RingBelegt):
            Ring(ringspeicher.ordner(self.ordner, True), 6.0, [t(k) for k in KOPF])

        def kaputt():
            raise PortError("Kabel gezogen (Test)")
        schreiber._fahrt = kaputt
        with self.assertRaises(PortError):
            schreiber.ausfuehren()
        ring = Ring(ringspeicher.ordner(self.ordner, True), 6.0, [t(k) for k in KOPF])
        ring.schliessen()
        self.assertIsNotNone(schreiber)

    def test_export_spaeter_ohne_lauf(self):
        self.lauf(3.0)
        ergebnis = passiv_exportieren(self.ordner, 6.0, sim=True, gesichert=True)
        self.assertTrue(ergebnis.csv_datei.name.startswith("sim-fahrt-passiv-gesichert-"))
        self.assertTrue(ergebnis.zeilen[0].startswith("Passiver Fahrtenschreiber"))
        self.assertTrue(len(lesen(ergebnis.csv_datei)) > 10)


if __name__ == "__main__":
    unittest.main()

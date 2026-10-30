# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Expertenfunktionen auf der Kommandozeile: nur mit --experte, nur an einer
Konsole, nach dem Hinweis „ja“ eintippen, vor jedem Schreiben noch eine Rückfrage (Vorgabe
Nein) – dieselben Prüfungen wie in der Oberfläche. Start: python -m unittest -v"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from vagdiag import cli, einstellungen, experte, sprache
from vagdiag.kw1281 import Timing
from vagdiag.session import DiagSession
from vagdiag.sim import sim_port

# Zeitwächter großzügig (der Simulator läuft hier nicht in Echtzeit, Testrechner hängen
# manchmal selbst) – den Wächter mit den echten Fristen prüft test_sicherheit.Zeitwaechter
SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0,
                 trenn_pause=0.05, wechsel_pause=0.05, byte_frist=0.5, kwp_p4_frist=0.5)


class Konsole(io.StringIO):
    """Eingabe wie von einer Konsole (isatty), Zeile für Zeile vorgegeben."""

    def isatty(self):
        return True


class Ohne(io.StringIO):
    def isatty(self):
        return False


class Experte(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._alt = einstellungen.DATEI
        einstellungen._zuruecksetzen_fuer_tests(Path(self._tmp.name) / "e.json")
        einstellungen.speichern(csv_ordner=str(Path(self._tmp.name) / "csv"),
                                log_ordner=str(Path(self._tmp.name) / "logs"))
        self._sim = cli.sim_port
        self._sitzung = cli.DiagSession
        cli.DiagSession = lambda fabrik, **art: DiagSession(fabrik, SCHNELL, keepalive=0.05,
                                                            **art)
        self._dauer = experte.DAUER
        experte.DAUER = 1.0
        self._sicherungen = experte.SICHERUNGEN
        experte.SICHERUNGEN = Path(self._tmp.name) / "sicherungen"
        self.ports = []
        self.motor_aus = True

        def fabrik(**art):
            port = sim_port(echtzeit=False, fahrprofil=False, zeitfaktor=20.0, **art)
            port.fahrzeug.motor_aus = self.motor_aus
            port.steuergeraete[0x01].fehler.clear()
            self.ports.append(port)
            return port
        cli.sim_port = fabrik

    def tearDown(self):
        cli.sim_port = self._sim
        cli.DiagSession = self._sitzung
        experte.DAUER = self._dauer
        experte.SICHERUNGEN = self._sicherungen
        einstellungen._zuruecksetzen_fuer_tests(self._alt)
        sprache.setzen("de")
        self._tmp.cleanup()

    def lauf(self, eingabe: str | None, *argv) -> tuple[int, str]:
        ausgabe = io.StringIO()
        stdin = cli.sys.stdin
        cli.sys.stdin = Konsole(eingabe) if eingabe is not None else Ohne("")
        try:
            with contextlib.redirect_stdout(ausgabe), contextlib.redirect_stderr(ausgabe):
                try:
                    code = cli.main(list(argv))
                except SystemExit as exc:
                    code = exc.code
        finally:
            cli.sys.stdin = stdin
        return code, ausgabe.getvalue()

    def geschrieben(self, adresse=0x01):
        return [g for port in self.ports for g in port.steuergeraete[adresse].geschrieben]

    def test_nur_mit_experte_und_konsole(self):
        code, text = self.lauf("ja\nj\n", "--sim", "drosselklappe")
        self.assertEqual(code, 4)
        self.assertIn("nur mit --experte", text)
        code, text = self.lauf(None, "--sim", "--experte", "drosselklappe")
        self.assertEqual(code, 4)
        self.assertIn("nur mit Rückfrage an einer Konsole", text)
        code, text = self.lauf("j\n", "--sim", "--experte", "drosselklappe")   # „j“ reicht nicht
        self.assertEqual(code, 4)
        self.assertIn("Im Expertenmodus kann vagdiag Werte", text)
        code, text = self.lauf("ja\n", "--sim", "--experte", "--adresse", "17", "drosselklappe")
        self.assertEqual(code, 4)
        self.assertIn("gilt 01 – Motorelektronik", text)
        self.assertEqual(self.ports, [], "ohne Freigabe nicht einmal verbunden")

    def test_drosselklappe(self):
        code, text = self.lauf("ja\nn\n", "--sim", "--experte", "drosselklappe")
        self.assertEqual(code, 0, text)
        self.assertIn("Nicht gestartet.", text)
        self.assertIn("✓  Motor aus (Drehzahl 0)", text)
        self.assertIn("Ziel: Simulator – kein Auto", text)
        self.assertEqual(self.geschrieben(), [])
        code, text = self.lauf("ja\nj\n", "--sim", "--experte", "drosselklappe")
        self.assertEqual(code, 0, text)
        self.assertIn("Laut Steuergerät erfolgreich (ADP i.O. (Simulator)).", text)
        self.assertIn("Kein Fehler gespeichert", text)
        self.assertEqual(set(self.geschrieben()), {(0x28, b"\x3c")})   # je Abfrage ein 28-Block

    def test_drosselklappe_bedingung_verletzt(self):
        self.motor_aus = False
        code, text = self.lauf("ja\nj\n", "--sim", "--experte", "drosselklappe", "--gruppe", "60")
        self.assertEqual(code, 1)
        self.assertIn("✗  Motor aus (Drehzahl 0)", text)
        self.assertIn("vagdiag startet die Grundeinstellung nicht", text)
        self.assertEqual(self.geschrieben(), [])

    def test_service_reset(self):
        code, text = self.lauf("ja\nn\n", "--sim", "--experte", "service-reset")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.geschrieben(0x17), [])
        code, text = self.lauf("ja\nj\n", "--sim", "--experte", "service-reset")
        self.assertEqual(code, 0, text)
        self.assertIn("Kanal 02: vorher 3, jetzt 0. Sicherung:", text)
        self.assertEqual(len(list(experte.SICHERUNGEN.glob("anpassung-17-kanal02-*.json"))), 1)

    def test_stellglieder(self):
        code, text = self.lauf("ja\nj\n\n\nq\n", "--sim", "--experte", "stellglieder")
        self.assertEqual(code, 0, text)
        self.assertIn("Stellglied 1:", text)
        self.assertIn("Stellglieddiagnose beendet:", text)
        self.assertTrue(self.geschrieben(), "Stellglieder angesteuert")

    def test_stellglieder_abs_nur_nach_warnung(self):
        code, text = self.lauf("ja\nn\n", "--sim", "--experte", "--adresse", "03",
                               "stellglieder")
        self.assertEqual(code, 0, text)
        self.assertIn("Mögliche Schäden:", text)
        self.assertIn("Warnung gelesen – weiter zur Rückfrage? [j/N]", text)
        self.assertNotIn("starten? [j/N]", text)                          # keine zweite Frage
        self.assertIn("Nicht gestartet.", text)
        self.assertEqual(self.geschrieben(0x03), [])
        # Warnung bestätigt, dann die Rückfrage – erst danach steuert es an
        code, text = self.lauf("ja\nj\nj\nq\n", "--sim", "--experte", "--adresse", "03",
                               "stellglieder")
        self.assertEqual(code, 0, text)
        self.assertLess(text.index("Warnung gelesen"), text.index("starten? [j/N]"))
        self.assertTrue(self.geschrieben(0x03), text)

    def test_englisch(self):
        code, text = self.lauf("yes\ny\n", "--language", "en", "--sim", "--expert",
                               "throttle-adaptation")
        self.assertEqual(code, 0, text)
        self.assertIn("Successful according to the control module", text)
        self.assertNotIn("Grundeinstellung", text)


if __name__ == "__main__":
    unittest.main()

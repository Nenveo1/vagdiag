# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Installer im Ordner installation: je System eine Datei, die Linux-Skripte in reinem sh
(Alpine hat kein bash), Startdateien als Vorlagen, die die Installer in den Ordner vagdiag
legen. Die Linux-Installer sind zweizeilige Hüllen, die auch die fish-Shell versteht (Standard
unter CachyOS); der Ablauf steht in teile/pacman.sh, apt.sh und apk.sh. Die Abläufe selbst
prüft ein Trockenlauf mit Platzhaltern für apt, pacman und apk außerhalb dieser Tests.
Start: python -m unittest -v"""

import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HAUPT = Path(__file__).resolve().parent.parent
INST = HAUPT / "installation"
LINUX = ("installieren-cachyos-archlinux-archlinuxarm.sh",
         "installieren-debian-ubuntu-linuxmint-armbian.sh",
         "installieren-alpine.sh")
ABLAUF = {"installieren-cachyos-archlinux-archlinuxarm.sh": "teile/pacman.sh",
          "installieren-debian-ubuntu-linuxmint-armbian.sh": "teile/apt.sh",
          "installieren-alpine.sh": "teile/apk.sh"}
WINDOWS = "installieren-windows-10-11.bat"
SH_DATEIEN = LINUX + tuple(ABLAUF.values()) + ("teile/gemeinsam.sh", "teile/start/vagdiag.sh",
                                               "teile/start/vagdiag-cli.sh")
FISH_ZEILE = """test -z "$FISH_VERSION" || test -z "$status" || eval 'sh (status filename){argv}'"""
SCHLUSS = ["pyftdi_installieren", "oberflaeche_pruefen", "udev_regel", "gruppe_uucp",
           "startdateien_legen", "alte_dateien_entfernen", "autostart_fragen", "ende"]


class Installer(unittest.TestCase):
    def test_eine_datei_je_system(self):
        namen = sorted(p.name for p in INST.iterdir() if p.is_file())
        self.assertEqual(namen, sorted(LINUX + (WINDOWS,)))
        alle = " ".join(namen)
        for system in ("windows-10-11", "cachyos", "archlinux", "archlinuxarm", "debian",
                       "ubuntu", "linuxmint", "armbian", "alpine"):
            self.assertIn(system, alle)

    def test_linux_skripte_in_reinem_sh(self):
        for name in SH_DATEIEN:
            text = (INST / name).read_text(encoding="utf-8")
            if not name.startswith("teile/") or name.startswith("teile/start/"):
                self.assertTrue(text.startswith("#!/bin/sh\n"), name)   # die übrigen: nur mit sh
            for bash in ("[[", "function ", "local ", "$'", "source "):
                self.assertNotIn(bash, text, f"{name}: {bash}")

    @unittest.skipIf(sys.platform == "win32" or not shutil.which("sh"), "kein sh")
    def test_syntax(self):
        for name in SH_DATEIEN:
            erg = subprocess.run(["sh", "-n", str(INST / name)], capture_output=True, text=True)
            self.assertEqual(erg.returncode, 0, f"{name}: {erg.stderr}")

    @unittest.skipIf(sys.platform == "win32", "Ausführungsrechte gibt es nur unter Linux")
    def test_ausfuehrbar(self):
        for name in LINUX + ("teile/start/vagdiag.sh", "teile/start/vagdiag-cli.sh"):
            self.assertTrue(os.access(INST / name, os.X_OK), name)

    def test_gemeinsamer_schluss(self):
        """Jeder Ablauf endet gleich: pyftdi, udev, Gruppe, Startdateien, Aufräumen,
        Autostart."""
        for name in ABLAUF.values():
            text = (INST / name).read_text(encoding="utf-8")
            self.assertIn('HIER=$(cd "$(dirname "$0")/.." && pwd)\n. "$HIER/teile/gemeinsam.sh"',
                          text)
            zeilen = [z.strip() for z in text.splitlines() if z.strip()]
            self.assertEqual(zeilen[-len(SCHLUSS):], SCHLUSS, name)

    def test_huelle_versteht_auch_fish(self):
        """CachyOS startet fish – wer den Installer dort mit „.“ startet, liest ihn mit fish.
        Die Hülle darf nur diese zwei Befehle haben: Sie sind gültiges
        sh und gültiges fish (fish liest die ganze Datei, bevor es etwas ausführt). In fish
        sind $FISH_VERSION und $status gesetzt – dann startet die Datei sich mit sh neu; sh
        führt den Ablauf aus."""
        for name, ablauf in ABLAUF.items():
            befehle = [z for z in (INST / name).read_text(encoding="utf-8").splitlines()
                       if z.strip() and not z.startswith("#")]
            self.assertEqual(befehle, [
                FISH_ZEILE.format(argv=""),
                f"""test -n "$FISH_VERSION" && test -n "$status" || eval 'sh "$(dirname "${{BASH_SOURCE:-$0}}")/{ablauf}"'"""],
                name)
            self.assertTrue((INST / ablauf).exists(), ablauf)

    def test_startdateien_verstehen_auch_fish(self):
        """Dasselbe für die Startdateien: erst die fish-Zeile, dann ein einziges
        eval mit dem sh-Teil in einfachen Anführungszeichen – darin keine weiteren."""
        for name in ("vagdiag.sh", "vagdiag-cli.sh"):
            text = (INST / "teile" / "start" / name).read_text(encoding="utf-8")
            befehle = [z for z in text.splitlines() if z.strip() and not z.startswith("#")]
            self.assertEqual(befehle[0], FISH_ZEILE.format(argv=" $argv"), name)
            self.assertEqual(befehle[1],
                             """test -n "$FISH_VERSION" && test -n "$status" || eval '""", name)
            self.assertEqual(befehle[-1], "'", name)
            self.assertNotIn("'", "".join(befehle[2:-1]), name)

    def test_startdateien(self):
        start = INST / "teile" / "start"
        self.assertEqual(sorted(p.name for p in start.iterdir()),
                         ["vagdiag-cli.bat", "vagdiag-cli.sh", "vagdiag.bat", "vagdiag.sh"])
        gemeinsam = (INST / "teile" / "gemeinsam.sh").read_text(encoding="utf-8")
        self.assertIn("for datei in vagdiag.sh vagdiag-cli.sh; do", gemeinsam)
        # die Kommandozeile findet das Programm auch aus einem anderen Ordner (Dienst)
        self.assertIn('PYTHONPATH="$HIER', (start / "vagdiag-cli.sh").read_text(encoding="utf-8"))
        self.assertIn('set "PYTHONPATH=%~dp0.;%PYTHONPATH%"',
                      (start / "vagdiag-cli.bat").read_text(encoding="ascii"))

    def test_paketversionen_wie_requirements(self):
        gemeinsam = (INST / "teile" / "gemeinsam.sh").read_text(encoding="utf-8")
        requirements = (INST / "teile" / "requirements.txt").read_text(encoding="utf-8")
        for name in ("PYFTDI", "PYSIDE"):
            wert = re.search(rf'^{name}="([^"]+)"$', gemeinsam, re.M).group(1)
            self.assertIn(wert, requirements)

    def test_autostart_nur_auf_nachfrage(self):
        """Autostart fragt der Installer nur am Terminal und nur mit Oberfläche, Vorauswahl
        Nein; als root nicht (der Eintrag landete bei root). Eingerichtet wird er von vagdiag
        selbst – dieselbe Funktion wie Datei → Beim Anmelden starten."""
        gemeinsam = (INST / "teile" / "gemeinsam.sh").read_text(encoding="utf-8")
        funktion = gemeinsam.split("autostart_fragen() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('if [ "$OBERFLAECHE" != ja ] || [ ! -t 0 ]; then', funktion)
        self.assertIn('[ "$(id -u)" -eq 0 ]', funktion)
        self.assertIn("[j/N]", funktion)
        self.assertIn("[jJyY]*)", funktion)
        self.assertIn('"$VENV/bin/python" -m vagdiag.autostart an', funktion)
        self.assertEqual(funktion.count("vagdiag.autostart"), 1)
        windows = (INST / WINDOWS).read_text(encoding="ascii")
        self.assertIn('set /p "antwort=vagdiag beim Anmelden automatisch starten? [j/N] "',
                      windows)
        self.assertIn('".venv\\Scripts\\python.exe" -m vagdiag.autostart an', windows)

    def test_udev_regel(self):
        regel = (INST / "teile" / "70-kkl-ftdi.rules").read_text(encoding="utf-8")
        self.assertIn('ATTR{idVendor}=="0403", ATTR{idProduct}=="6001"', regel)
        self.assertIn('GROUP="uucp"', regel)
        gemeinsam = (INST / "teile" / "gemeinsam.sh").read_text(encoding="utf-8")
        self.assertIn('"$TEILE/70-kkl-ftdi.rules" /etc/udev/rules.d/70-kkl-ftdi.rules', gemeinsam)


if __name__ == "__main__":
    unittest.main()

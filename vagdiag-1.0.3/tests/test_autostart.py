# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Autostart beim Anmelden: .desktop-Datei (Linux) bzw. Run-Eintrag (Windows), und
vagdiag/__main__.py startet auch als Datei aus einem fremden Ordner.
Start: python -m unittest -v"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from vagdiag import autostart, einstellungen, sprache

HAUPT = Path(__file__).resolve().parent.parent
MAIN = HAUPT / "vagdiag" / "__main__.py"


def exec_zerlegen(wert: str) -> list[str]:
    """Exec= so lesen, wie es die Desktop Entry Specification vorschreibt: erst die Regel für
    Zeichenketten (\\\\ → \\), dann Anführungszeichen und Escapes, dann %% → %."""
    wert = wert.replace("\\\\", "\0")
    wert = wert.replace("\\s", " ").replace("\\n", "\n").replace("\\t", "\t")
    wert = wert.replace("\0", "\\")
    argumente, aktuell, in_zitat, i, angefangen = [], "", False, 0, False
    while i < len(wert):
        z = wert[i]
        if in_zitat:
            if z == "\\" and i + 1 < len(wert) and wert[i + 1] in '"`$\\':
                aktuell += wert[i + 1]
                i += 2
                continue
            if z == '"':
                in_zitat = False
            else:
                aktuell += z
        elif z == '"':
            in_zitat, angefangen = True, True
        elif z == " ":
            if aktuell or angefangen:
                argumente.append(aktuell)
            aktuell, angefangen = "", False
        else:
            aktuell += z
        i += 1
    if aktuell or angefangen:
        argumente.append(aktuell)
    return [a.replace("%%", "%") for a in argumente]


class Linux(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.konfig = Path(self._tmp.name) / "konfig"
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.konfig)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(autostart, "WINDOWS", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    @unittest.skipIf(sys.platform in ("win32", "darwin"), "nur Linux/BSD")
    def test_an_und_aus(self):
        self.assertFalse(autostart.ist_an())
        ort = autostart.einschalten()
        datei = self.konfig / "autostart" / "vagdiag.desktop"
        self.assertEqual(ort, str(datei))
        self.assertTrue(autostart.ist_an())
        inhalt = datei.read_text(encoding="utf-8")
        self.assertTrue(inhalt.startswith("[Desktop Entry]\nType=Application\n"))
        exec_zeile = next(z for z in inhalt.splitlines() if z.startswith("Exec="))
        self.assertEqual(exec_zerlegen(exec_zeile[5:]), autostart.befehl())
        self.assertEqual(autostart.befehl()[1], str(MAIN))
        autostart.einschalten()                       # noch einmal: ersetzt, nicht doppelt
        self.assertEqual(sorted(p.name for p in datei.parent.iterdir()), ["vagdiag.desktop"])
        autostart.ausschalten()
        self.assertFalse(datei.exists())
        self.assertFalse(autostart.ist_an())
        autostart.ausschalten()                       # schon aus: kein Fehler

    @unittest.skipIf(sys.platform in ("win32", "darwin"), "nur Linux/BSD")
    def test_in_der_arbeitsumgebung_abgeschaltet(self):
        autostart.einschalten()
        datei = self.konfig / "autostart" / "vagdiag.desktop"
        for zeile in ("Hidden=true", "X-GNOME-Autostart-enabled=false"):
            datei.write_text(autostart.desktop_inhalt().replace(
                "X-GNOME-Autostart-enabled=true", zeile), encoding="utf-8")
            self.assertFalse(autostart.ist_an(), zeile)
        autostart.einschalten()
        self.assertTrue(autostart.ist_an())

    def test_sonderzeichen_im_pfad(self):
        befehl = ["/home/max mustermann/vag$diag/.venv/bin/python",
                  '/opt/a "b" `c` \\d 100%/vagdiag/__main__.py']
        with mock.patch.object(autostart, "befehl", lambda: befehl):
            exec_zeile = next(z for z in autostart.desktop_inhalt().splitlines()
                              if z.startswith("Exec="))
        self.assertEqual(exec_zerlegen(exec_zeile[5:]), befehl)
        self.assertIn("%%", exec_zeile)
        with mock.patch.object(autostart, "befehl", lambda: ["/a\nb"]):
            with self.assertRaises(autostart.AutostartFehler):
                autostart.desktop_inhalt()

    @unittest.skipIf(sys.platform == "win32", "Verknüpfung nur unter POSIX")
    def test_python_der_venv_nicht_aufgeloest(self):
        """In .venv/bin ist python eine Verknüpfung auf das System-Python. Aufgelöst fehlten
        dem Autostart pyftdi und die übrigen Pakete der .venv."""
        venv = Path(self._tmp.name) / ".venv" / "bin"
        venv.mkdir(parents=True)
        python = venv / "python"
        python.symlink_to(sys.executable)
        with mock.patch.object(sys, "executable", str(python)):
            self.assertEqual(autostart.befehl()[0], str(python))

    def test_ohne_eigenen_autostart(self):
        with mock.patch.object(autostart, "verfuegbar", lambda: False):
            with self.assertRaises(autostart.AutostartFehler):
                autostart.einschalten()
            self.assertFalse(autostart.ist_an())
        self.assertIn(autostart.befehl()[1], autostart.anleitung())

    @unittest.skipIf(sys.platform in ("win32", "darwin"), "nur Linux/BSD")
    def test_aufruf_fuer_die_installer(self):
        ausgabe = io.StringIO()
        self.addCleanup(sprache.setzen, "de")
        with contextlib.redirect_stdout(ausgabe), \
                mock.patch.object(einstellungen, "laden", lambda: {"sprache": "de"}):
            self.assertEqual(autostart.main(["status"]), 0)
            self.assertEqual(autostart.main(["an"]), 0)
            self.assertEqual(autostart.main(["status"]), 0)
            self.assertEqual(autostart.main(["aus"]), 0)
        self.assertEqual(ausgabe.getvalue().splitlines()[0], "Autostart aus.")
        self.assertTrue(ausgabe.getvalue().splitlines()[1].startswith("Autostart an: "))
        self.assertEqual(ausgabe.getvalue().splitlines()[2:], ["Autostart an.", "Autostart aus."])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(autostart.main(["unsinn"]), 2)


class _Schluessel:
    def __init__(self, reg, pfad):
        self.reg, self.pfad = reg, pfad

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _winreg(reg: dict):
    """Ein Ausschnitt von winreg über einem dict {Pfad: {Name: (Wert, Art)}}."""
    w = types.ModuleType("winreg")
    w.HKEY_CURRENT_USER, w.KEY_SET_VALUE, w.REG_SZ, w.REG_BINARY = "HKCU", 2, 1, 3

    def oeffnen(_wurzel, pfad, *_):
        if pfad not in reg:
            raise FileNotFoundError(pfad)
        return _Schluessel(reg, pfad)

    def anlegen(_wurzel, pfad, *_):
        reg.setdefault(pfad, {})
        return _Schluessel(reg, pfad)

    def lesen(k, name):
        if name not in reg[k.pfad]:
            raise FileNotFoundError(name)
        return reg[k.pfad][name]

    def setzen(k, name, _reserviert, art, wert):
        reg[k.pfad][name] = (wert, art)

    def loeschen(k, name):
        if name not in reg[k.pfad]:
            raise FileNotFoundError(name)
        del reg[k.pfad][name]
    w.OpenKey, w.CreateKeyEx, w.QueryValueEx = oeffnen, anlegen, lesen
    w.SetValueEx, w.DeleteValue = setzen, loeschen
    return w


class Windows(unittest.TestCase):
    def setUp(self):
        self.reg: dict = {}
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        skripte = Path(self._tmp.name) / "vag diag" / ".venv" / "Scripts"
        skripte.mkdir(parents=True)
        for name in ("python.exe", "pythonw.exe"):
            (skripte / name).write_bytes(b"")
        for patcher in (mock.patch.object(autostart, "WINDOWS", True),
                        mock.patch.dict(sys.modules, {"winreg": _winreg(self.reg)}),
                        mock.patch.object(sys, "executable", str(skripte / "python.exe"))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.skripte = skripte

    def test_run_eintrag_ohne_konsole(self):
        self.assertFalse(autostart.ist_an())
        ort = autostart.einschalten()
        self.assertEqual(ort, "HKEY_CURRENT_USER\\" + autostart.RUN)
        wert, art = self.reg[autostart.RUN]["vagdiag"]
        self.assertEqual(art, 1)
        self.assertTrue(wert.startswith(f'"{self.skripte / "pythonw.exe"}" '), wert)
        self.assertTrue(wert.endswith(str(MAIN)) or wert.endswith(f'"{MAIN}"'), wert)
        self.assertTrue(autostart.ist_an())
        autostart.ausschalten()
        self.assertFalse(autostart.ist_an())
        self.assertNotIn("vagdiag", self.reg[autostart.RUN])

    def test_im_task_manager_abgeschaltet(self):
        autostart.einschalten()
        self.reg[autostart.FREIGABE] = {"vagdiag": (b"\x03\x00\x00\x00" + bytes(8), 3)}
        self.assertFalse(autostart.ist_an())
        autostart.einschalten()                    # wieder an: Vermerk weg
        self.assertNotIn("vagdiag", self.reg[autostart.FREIGABE])
        self.assertTrue(autostart.ist_an())
        self.reg[autostart.FREIGABE]["vagdiag"] = (b"\x02" + bytes(11), 3)
        self.assertTrue(autostart.ist_an())

    def test_anleitung(self):
        self.assertIn("shell:startup", autostart.anleitung())
        self.assertIn("pythonw.exe", autostart.anleitung())


class AlsDateiGestartet(unittest.TestCase):
    def test_findet_das_paket_aus_fremdem_ordner(self):
        """Der Autostart ruft …/vagdiag/__main__.py direkt auf – aus irgendeinem Ordner."""
        probe = ("import runpy, sys; runpy.run_path(sys.argv[1], run_name='probe'); "
                 "import vagdiag; print(vagdiag.__file__)")
        with tempfile.TemporaryDirectory() as fremd:
            erg = subprocess.run([sys.executable, "-I", "-c", probe, str(MAIN)], cwd=fremd,
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(erg.returncode, 0, erg.stderr)
        self.assertEqual(Path(erg.stdout.strip()), HAUPT / "vagdiag" / "__init__.py")


if __name__ == "__main__":
    unittest.main()

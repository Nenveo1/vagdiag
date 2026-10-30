# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Lizenz: GPL-3.0-or-later mit Kopfzeilen in jeder Quelldatei, Lizenztext, Hinweise,
„Über vagdiag“ und --version. Start: python -m unittest -v"""

import contextlib
import io
import unittest
from pathlib import Path

from vagdiag import cli, lizenz, sprache, texttabellen

HAUPT = Path(__file__).resolve().parent.parent
SPDX = "SPDX-License-Identifier: GPL-3.0-or-later"
COPYRIGHT = "Copyright (C) 2026 Nenveo"


def quelldateien() -> list[Path]:
    # Installer und Startdateien liegen im Ordner installation
    inst = HAUPT / "installation"
    return sorted([*HAUPT.glob("vagdiag/*.py"), *HAUPT.glob("tests/*.py"),
                   *HAUPT.glob("werkzeuge/*.py"), *inst.glob("*.sh"), *inst.glob("*.bat"),
                   *inst.glob("teile/*.sh"), *inst.glob("teile/*.txt"),
                   *inst.glob("teile/start/*"), inst / "teile" / "70-kkl-ftdi.rules"])


class Dateien(unittest.TestCase):
    def test_kopfzeilen_in_jeder_quelldatei(self):
        dateien = quelldateien()
        self.assertGreater(len(dateien), 40)
        for pfad in dateien:
            with self.subTest(datei=pfad.name):
                anfang = pfad.read_text(encoding="utf-8").splitlines()[:4]
                self.assertTrue(any(SPDX in z for z in anfang), anfang)
                self.assertTrue(any(COPYRIGHT in z for z in anfang), anfang)

    def test_lizenztext_und_hinweise(self):
        text = (HAUPT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(text.lstrip().startswith("GNU GENERAL PUBLIC LICENSE"))
        self.assertIn("Version 3, 29 June 2007", text)
        self.assertIn("END OF TERMS AND CONDITIONS", text)
        hinweise = (HAUPT / "NOTICE.txt").read_text(encoding="utf-8")
        self.assertIn("Additional permission under GNU GPL version 3 section 7", hinweise)
        self.assertIn("FTDI D2XX driver library", hinweise)
        self.assertIn("KLineKWP1281Lib", hinweise)
        self.assertIn("Copyright © 2021 Greg Menounos", hinweise)
        self.assertIn(COPYRIGHT, hinweise)

    def test_tabellen_mit_herkunft(self):
        tabellen = sorted(texttabellen.ORDNER.glob("*.tsv"))
        self.assertEqual(len(tabellen), 8)
        for pfad in tabellen:
            with self.subTest(datei=pfad.name):
                kopf = pfad.read_text(encoding="utf-8").splitlines()[:5]
                self.assertTrue(any("SPDX-License-Identifier: GPL-3.0-only" in z for z in kopf))
                self.assertTrue(any("domnulvlad" in z for z in kopf))
        self.assertTrue((texttabellen.ORDNER / "LIESMICH.txt").exists())


class Anzeige(unittest.TestCase):
    def tearDown(self):
        sprache.setzen("de")

    def test_kurz_nennt_urheber_lizenz_und_gewaehrleistung(self):
        text = "\n".join(lizenz.kurz())
        self.assertIn(COPYRIGHT, text)
        self.assertIn("GPL-3.0-or-later", text)
        self.assertIn("OHNE JEDE GEWÄHRLEISTUNG", text)
        self.assertIn(str(lizenz.LIZENZ_DATEI), "\n".join(lizenz.hinweise()))
        self.assertIn("GNU GENERAL PUBLIC LICENSE", lizenz.lizenztext())
        sprache.setzen("en")
        self.assertIn("WITHOUT ANY WARRANTY", "\n".join(lizenz.kurz()))

    def test_fehlende_dateien(self):
        alt = lizenz.LIZENZ_DATEI, lizenz.HINWEIS_DATEI
        try:
            lizenz.LIZENZ_DATEI = HAUPT / "gibt-es-nicht"
            lizenz.HINWEIS_DATEI = HAUPT / "gibt-es-auch-nicht"
            self.assertIn(lizenz.GPL_URL, lizenz.lizenztext())
            self.assertIn("GPL-3.0-or-later", lizenz.hinweistext())
        finally:
            lizenz.LIZENZ_DATEI, lizenz.HINWEIS_DATEI = alt

    def ausgabe(self, *argv) -> tuple[int | None, str]:
        puffer = io.StringIO()
        code = None
        with contextlib.redirect_stdout(puffer):
            try:
                code = cli.main(list(argv))
            except SystemExit as exc:
                code = exc.code
        return code, puffer.getvalue()

    def test_kommandozeile(self):
        code, text = self.ausgabe("--version")
        self.assertIn(code, (0, None))
        self.assertIn(COPYRIGHT, text)
        self.assertIn("GEWÄHRLEISTUNG", text)
        code, text = self.ausgabe("lizenz")
        self.assertEqual(code, 0)
        self.assertIn("NOTICE.txt", text)
        code, text = self.ausgabe("--language", "en", "license", "--full-text")
        self.assertEqual(code, 0)
        self.assertIn("TERMS AND CONDITIONS", text)


if __name__ == "__main__":
    unittest.main()

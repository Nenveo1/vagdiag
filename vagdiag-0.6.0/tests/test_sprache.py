"""Übersetzung: jeder Text, der durch t() oder N_() läuft, hat eine englische
Fassung mit denselben Platzhaltern – und die englische Ausgabe enthält keine
deutschen Reste.  Start: python -m unittest -v"""

import ast
import contextlib
import csv
import io
import re
import string
import tempfile
import time
import unittest
from pathlib import Path

from vagdiag import cli, einstellungen, fehler, ident, kilometerstand, messwerte, sprache
from vagdiag.fahrtenschreiber import Besuch, FahrtPlan
from vagdiag.kw1281 import KW1281, Timing
from vagdiag.kline import KLine
from vagdiag.session import DiagSession
from vagdiag.sim import sim_port
from vagdiag.sprache_en import EN

SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0)

# Zeichen und Wörter, die in englischer Ausgabe nichts zu suchen haben
DEUTSCH = re.compile(r"[äöüÄÖÜß]|\b(der|die|das|und|nicht|kein|keine|mit|bei|Fehler|Gruppe|"
                     r"Kanal|Steuergerät|Verbindung|lesen|bitte|Bitte|Datei|Ordner|wird|ist|"
                     r"auf|für|oder|noch|nach|Zündung|Messwert\w*|Anpassung\w*)\b")


def deutsche_reste(zeilen) -> list[str]:
    return [z for z in zeilen if DEUTSCH.search(z)]

PAKET = Path(__file__).resolve().parent.parent / "vagdiag"
MARKER = {"t", "N_", "_f"}          # _f: Feldnamen in beschriftung.py
PROZENT = re.compile(r"%[-#0+]*\d*(?:\.\d+)?[sdifxXr%]")


def _ist_marker(knoten: ast.Call) -> bool:
    f = knoten.func
    if isinstance(f, ast.Name):
        return f.id in MARKER
    return (isinstance(f, ast.Attribute) and f.attr in ("t", "N_")
            and isinstance(f.value, ast.Name) and f.value.id == "sprache")


def texte_im_code() -> tuple[dict[str, list[str]], list[str]]:
    """Alle übersetzbaren Texte (Text → Fundstellen) und Aufrufe mit f-Strings."""
    gefunden: dict[str, list[str]] = {}
    fstrings: list[str] = []
    for datei in sorted(PAKET.glob("*.py")):
        if datei.name == "sprache_en.py":
            continue
        baum = ast.parse(datei.read_text(encoding="utf-8"), str(datei))
        for knoten in ast.walk(baum):
            if not (isinstance(knoten, ast.Call) and _ist_marker(knoten) and knoten.args):
                continue
            arg = knoten.args[0]
            stelle = f"{datei.name}:{knoten.lineno}"
            if isinstance(arg, ast.JoinedStr):
                fstrings.append(stelle)
            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                gefunden.setdefault(arg.value, []).append(stelle)
    return gefunden, fstrings


def _felder(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


class Vollstaendig(unittest.TestCase):
    def test_keine_f_strings_in_t(self):
        _, fstrings = texte_im_code()
        self.assertEqual(fstrings, [], "t()/N_() mit f-String – Platzhalter benutzen")

    def test_alles_uebersetzt(self):
        gefunden, _ = texte_im_code()
        fehlt = {text: stellen for text, stellen in gefunden.items() if text not in EN}
        self.assertEqual(fehlt, {}, f"{len(fehlt)} Texte ohne englische Fassung")

    def test_platzhalter_passen(self):
        gefunden, _ = texte_im_code()
        falsch = []
        for text in gefunden:
            if text not in EN:
                continue
            en = EN[text]
            if _felder(text) != _felder(en):
                falsch.append((text, en, "Platzhalter {…}"))
            if PROZENT.findall(text) != PROZENT.findall(en):
                falsch.append((text, en, "Platzhalter %…"))
        self.assertEqual(falsch, [])

    def test_keine_verwaisten_eintraege(self):
        gefunden, _ = texte_im_code()
        verwaist = sorted(set(EN) - set(gefunden))
        self.assertEqual(verwaist, [], "Einträge in sprache_en.py, die niemand benutzt")


class Umschalten(unittest.TestCase):
    def tearDown(self):
        sprache.setzen("de")

    def test_zahlen_und_einheiten(self):
        sprache.setzen("de")
        self.assertEqual((sprache.zahl(13.856, 2), sprache.tausender(123450)),
                         ("13,86", "123.450"))
        sprache.setzen("en")
        self.assertEqual((sprache.zahl(13.856, 2), sprache.tausender(123450)),
                         ("13.86", "123,450"))
        self.assertEqual(sprache.einheit("° v.OT"), "° BTDC")
        self.assertEqual(sprache.csv_trenner(), ",")

    def test_unbekannte_sprache_ergibt_deutsch(self):
        self.assertEqual(sprache.setzen("fr"), "de")
        self.assertEqual(sprache.setzen("EN"), "en")

    def test_unbekannter_text_bleibt(self):
        sprache.setzen("en")
        self.assertEqual(sprache.t("Mein eigener Name"), "Mein eigener Name")
        self.assertEqual(sprache.t("Text Nr. {nummer}", nummer=5), "Text no. 5")



class EnglischeAusgabe(unittest.TestCase):
    def setUp(self):
        sprache.setzen("en")

    def tearDown(self):
        sprache.setzen("de")

    def test_messwerte_fehler_kennung(self):
        werte = messwerte.gruppe_auswerten(bytes.fromhex("01 C8 04 15 46 8D 05 0A 83 05 0A 7B"))
        self.assertEqual(werte[1].text, "9.87 V")
        zuendung = messwerte.umrechnen(3, 27, 75, 150)
        self.assertTrue(zuendung.text.endswith("° BTDC"), zuendung.text)
        self.assertEqual(messwerte.umrechnen(1, 37, 0, 0xC1).text, "pressed")
        self.assertEqual(fehler.Fehler(771, 0x9E).zeile(),
                         "00771 – Fuel Level Sensor (G) – 30-10 Open or Short to Plus – "
                         "intermittent")
        port = sim_port(echtzeit=False, fahrprofil=False)
        proto = KW1281(KLine(port), SCHNELL)
        zeilen = ident.zeilen(proto.connect(0x01, (10400,)), sim=True)
        self.assertEqual(zeilen[0], "Address:       01 – Engine electronics")
        self.assertIn("Workshop code: 12345", zeilen)
        self.assertEqual(deutsche_reste(zeilen), [])

    def test_kilometerstand(self):
        port = sim_port(echtzeit=False, fahrprofil=False)
        proto = KW1281(KLine(port), SCHNELL)
        proto.connect(0x17, (10400, 9600))
        zeilen = kilometerstand.lesen(proto).zeilen
        self.assertEqual(zeilen[0], "Odometer: 123,450 km")
        self.assertEqual(deutsche_reste(zeilen), [])

    def test_fahrt_auf_englisch(self):
        with tempfile.TemporaryDirectory() as ordner:
            s = DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=True, zeitfaktor=20.0),
                            SCHNELL, keepalive=0.05).start()
            s.airbag_freigeben()
            try:
                plan = FahrtPlan(besuche=[Besuch(0x17, (1, 2, 3), 1.0, 0.3),
                                          Besuch(0x03, (1, 3), 1.5, 0.3)],
                                 stand_dauer=0.2, volle_runde_nach=0.3)
                future = s.fahrt_starten(plan, ordner, sim=True)
                time.sleep(4.0)
                s.fahrt_ereignis("Test")
                time.sleep(2.0)
                s.fahrt_beenden()
                z = future.result(30)
            finally:
                s.schliessen()
            with open(z.csv_datei, encoding="utf-8-sig") as datei:
                zeilen = list(csv.reader(datei, delimiter=","))
            text = z.txt_datei.read_text(encoding="utf-8")
        self.assertTrue(z.zeilen[0].startswith("Drive on "), z.zeilen[0])
        self.assertIn("Fault codes", z.zeilen)
        self.assertRegex(text, r"Start: 17 1 fault\(s\): 00771 – Fuel Level Sensor")
        self.assertIn("Supply voltage:", text)
        self.assertIn("Fuel gauge: standing at the start 21 l", text)
        self.assertTrue(z.txt_datei.name.endswith("-summary.txt"))
        self.assertEqual(deutsche_reste(z.zeilen), [])
        self.assertEqual(zeilen[0][:5], ["Time", "Seconds", "Control module", "Group", "Phase"])
        self.assertTrue({"Start", "Drive", "Event", "End"} <= {r[4] for r in zeilen[1:]})
        ereignisse = [r[-1] for r in zeilen[1:] if r[-1]]
        self.assertEqual(deutsche_reste(ereignisse), [])
        werte = [r[5] for r in zeilen[1:] if r[2] == "01" and r[3] == "004"]
        self.assertTrue(werte and all("," not in w for w in werte), werte[:3])


class Kommandozeile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._alt = einstellungen.DATEI
        einstellungen._zuruecksetzen_fuer_tests(Path(self._tmp.name) / "e.json")
        einstellungen.speichern(csv_ordner=str(Path(self._tmp.name) / "csv"),
                                log_ordner=str(Path(self._tmp.name) / "logs"))
        self._sim = cli.sim_port
        cli.sim_port = lambda **art: sim_port(echtzeit=False, fahrprofil=False, **art)

    def tearDown(self):
        cli.sim_port = self._sim
        einstellungen._zuruecksetzen_fuer_tests(self._alt)
        sprache.setzen("de")
        self._tmp.cleanup()

    def lauf(self, *argv) -> tuple[int, str]:
        ausgabe = io.StringIO()
        with contextlib.redirect_stdout(ausgabe), contextlib.redirect_stderr(ausgabe):
            try:
                code = cli.main(list(argv))
            except SystemExit as exc:
                code = exc.code
        return code, ausgabe.getvalue()

    def test_englisch_mit_englischem_befehl(self):
        code, text = self.lauf("--language", "en", "--sim", "--address", "01", "faults")
        self.assertEqual(code, 0, text)
        self.assertIn("Address:       01 – Engine electronics", text)
        self.assertIn("2 fault code(s) stored:", text)
        self.assertEqual(deutsche_reste(text.splitlines()), [])
        self.assertEqual(list(Path(self._tmp.name).rglob("*.log")), [], "ohne --log keine Datei")
        self.assertEqual(list(Path(self._tmp.name).rglob("*.csv")), [])

    def test_deutsch_mit_englischem_befehl_und_log(self):
        code, text = self.lauf("--sim", "--log", "faults")
        self.assertEqual(code, 0, text)
        self.assertIn("2 Fehler gespeichert:", text)
        self.assertEqual(len(list((Path(self._tmp.name) / "logs").glob("vagdiag-*.log"))), 1)

    def test_hilfe_auf_englisch(self):
        code, text = self.lauf("--sprache", "en", "--help")
        self.assertEqual(code, 0)
        self.assertIn("--address", text)
        self.assertIn("odometer", text)
        for befehl in ("", "drive", "group", "group-scan", "adaptation", "clear", "settings"):
            code, text = self.lauf("--language", "en", *([befehl] if befehl else []), "--help")
            self.assertEqual(code, 0, befehl)
            ohne_optionen = [re.sub(r"--\S+", "", z) for z in text.splitlines()]
            self.assertEqual(deutsche_reste(ohne_optionen), [], befehl)
            for wort in ("ADRESSE", "ORDNER", "DATEI", "GRUPPE", "KANAL", "LISTE", "BEFEHL",
                         "VON", "BIS", "ja|nein"):
                self.assertNotIn(wort, text, befehl)
        # die deutschen Namen der Optionen dürfen als Zweitnamen dastehen
        ohne_optionen = [re.sub(r"--\S+", "", z) for z in text.splitlines()]
        self.assertEqual(deutsche_reste(ohne_optionen), [])

    def test_airbag_nur_mit_freigabe(self):
        code, text = self.lauf("--sim", "--adresse", "15", "ident")
        self.assertEqual(code, 4)
        self.assertIn("6Q0 909 605 A", text)
        code, text = self.lauf("--sim", "--mit-airbag", "--adresse", "15", "ident")
        self.assertEqual(code, 0, text)
        self.assertIn("Adresse:       15 – Airbag", text)

    def test_csv_nur_auf_wunsch(self):
        code, _ = self.lauf("--sim", "gruppe", "4", "--wiederholen", "2")
        self.assertEqual(code, 0)
        self.assertEqual(list(Path(self._tmp.name).rglob("*.csv")), [])
        code, text = self.lauf("--sim", "gruppe", "4", "--wiederholen", "2", "--csv")
        self.assertEqual(code, 0)
        self.assertEqual(len(list(Path(self._tmp.name).rglob("sim-messwerte-01-*.csv"))), 1)

    def test_einstellungen_setzen(self):
        code, text = self.lauf("settings", "--set-language", "en", "--csv-auto", "yes")
        self.assertEqual(code, 0)
        self.assertIn("Language:", text)
        werte = einstellungen.laden()
        self.assertEqual((werte["sprache"], werte["csv_automatisch"]), ("en", True))


if __name__ == "__main__":
    unittest.main()

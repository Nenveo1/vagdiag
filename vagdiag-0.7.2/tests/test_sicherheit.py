"""Schreibsperre unter Störungen: was die Sicherheitsprüfung von 0.7.1 gefunden hat.

- KW1281: Ein falsches Komplement heißt, das Steuergerät hat ein anderes Byte empfangen.
  vagdiag sendet dann nie weiter (sonst würde aus „Messwerte lesen“ eine Grundeinstellung,
  aus „Fehler lesen“ „Fehler löschen“, aus Kanal 02 Kanal 00).
- Nach Testen/Speichern muss das Steuergerät genau Kanal und Wert zurückmelden.
- KWP2000: Schreiben und Ansteuern werden nie wiederholt; die Antwort muss zur Routine
  passen; lässt sich die Anpassung nach einem Schreibversuch nicht beenden, endet die
  Verbindung.
- Stellglieddiagnose: ohne „Weiter“ endet sie nach SCHRITT_MAX Sekunden.
- Freigaben gelten nur für das geöffnete Steuergerät; Kanal 00 auch lesend nie; jeder
  andere Block bzw. Dienst bleibt gesperrt – auch im Expertenmodus mit voller Freigabe.

Start: python -m unittest -v tests.test_sicherheit"""

import time
import unittest

from vagdiag.kline import KLine
from vagdiag.kw1281 import (EXPERTE, LESEND, KW1281, DiagError, Freigabe, Nak, ProtocolError,
                            SchreibenGesperrt, Stoerung, Timing)
from vagdiag.kwp2000 import ANPASSUNG, ERLAUBTE_DIENSTE, SITZUNGEN, STELLGLIED, Kwp2000
from vagdiag.experte import Nichts
from vagdiag.session import DiagSession
from vagdiag.sim import sim_port

# Zeitwächter großzügig: Der Simulator läuft hier nicht in Echtzeit, und Testrechner hängen
# manchmal selbst (virtuelle Maschinen bis 50 ms). Den Wächter mit den echten Fristen prüft
# test_sicherheit.Zeitwaechter.
SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0,
                 trenn_pause=0.05, wechsel_pause=0.05, abbruch_ruhe=0.05,
                 kwp_beruhigen=0.0, kwp_p2=0.3, kwp_p3=0.0, kwp_p4=0.0, kwp_keepalive=0.1,
                 kwp_p3_max=0.1, byte_frist=0.5, kwp_p4_frist=0.5)
# … für die Tests des Zeitwächters: die Fristen wie im Programm
WAECHTER = Timing(**{**SCHNELL.__dict__, "byte_frist": Timing.byte_frist,
                     "kwp_p4_frist": Timing.kwp_p4_frist})


def kw1281(adresse, experte=False, timing=SCHNELL):
    port = sim_port(echtzeit=False, fahrprofil=False)
    proto = KW1281(KLine(port), timing)
    proto.experte = experte
    proto.connect(adresse, (10400, 9600))
    return port, proto, port.steuergeraete[adresse]


def sitzung(motor_aus=False, **sim):
    def fabrik():
        port = sim_port(echtzeit=False, fahrprofil=False, **sim)
        port.fahrzeug.motor_aus = motor_aus
        return port
    s = DiagSession(fabrik, SCHNELL, keepalive=0.05).start()
    s._port_oeffnen()
    return s


def schreiben(proto, kanal, wert):
    """Wie eine Expertenfunktion: Freigabe für genau diesen Kanal und Wert, dann schreiben."""
    with proto.schreiben_freigeben(anpassung=[(kanal, wert)]):
        return proto.anpassung_schreiben(kanal, wert)


def antwort_aendern(ecu, anfrage_titel, daten):
    """Die nächste Anpassungsantwort (E6) auf einen Block mit diesem Titel trägt andere Daten."""
    original = ecu._starte_block
    offen = [True]

    def starten(titel, inhalt=b"", versatz=1):
        if offen[0] and titel == 0xE6 and ecu.anfragen and ecu.anfragen[-1][0] == anfrage_titel:
            offen[0] = False
            inhalt = daten
        original(titel, inhalt, versatz)
    ecu._starte_block = starten


def warten_bis(bedingung, sekunden=5.0):
    ende = time.monotonic() + sekunden
    while not bedingung():
        if time.monotonic() > ende:
            raise AssertionError("Bedingung nicht erreicht")
        time.sleep(0.02)


def bis_zum_ende(anfragen, start):
    """KW1281-Titel nach dem letzten Stellgliedblock bis zum Endeblock 06 (ohne ihn)."""
    titel = [t for t, _ in anfragen]
    letzte = len(titel) - 1 - titel[::-1].index(start)
    rest = titel[letzte + 1:]
    return rest[:rest.index(0x06)] if 0x06 in rest else None


class Komplement(unittest.TestCase):
    """Das Steuergerät empfängt ein verfälschtes Byte und quittiert es (richtig) mit
    dessen Komplement – vagdiag darf den Block dann nie zu Ende senden."""

    def test_messwerte_werden_nie_zur_grundeinstellung(self):
        _, proto, motor = kw1281(0x01)
        motor.empfangsfehler(2, 0x01, titel=0x29)           # 29 kommt als 28 an
        with self.assertRaises(ProtocolError):
            proto.gruppe_lesen(4)
        self.assertFalse(proto.verbunden)
        proto.trennen()                                     # schickt jetzt kein 06 mehr
        self.assertEqual(motor.geschrieben, [])
        self.assertEqual(len(motor._rx), 3, "nach dem gestörten Byte nichts mehr gesendet")
        self.assertEqual(motor._rx[2], 0x28)

    def test_fehler_lesen_wird_nie_zum_loeschen(self):
        _, proto, motor = kw1281(0x01)
        vorher = (list(motor.fehler), motor.geloescht)
        motor.empfangsfehler(2, 0x02, titel=0x07)           # 07 kommt als 05 an
        with self.assertRaises(ProtocolError):
            proto.fehler_lesen()
        self.assertEqual((motor.fehler, motor.geloescht), vorher)
        self.assertTrue(motor.fehler, "der Simulator-Motor hat gespeicherte Fehler")

    def test_service_reset_schreibt_nie_kanal_00(self):
        _, proto, kombi = kw1281(0x17, experte=True)
        kombi.anpassungen[0] = 1                            # als gäbe es Kanal 00
        kombi.empfangsfehler(3, 0x02, titel=0x2A)           # Kanal 02 kommt als 00 an
        with proto.schreiben_freigeben(anpassung=[(2, 0)]):
            with self.assertRaises(ProtocolError):
                proto.anpassung_schreiben(2, 0, 0)
        self.assertEqual(kombi.geschrieben, [(0x22, b"\x02\x00\x00")])   # nur der Test
        self.assertEqual((kombi.anpassungen[0], kombi.anpassungen[2]), (1, 3))

    def test_stellglied_nur_mit_datenbyte_00(self):
        _, proto, kombi = kw1281(0x17, experte=True)
        kombi.empfangsfehler(3, 0x01, titel=0x04)           # 04 00 kommt als 04 01 an
        with proto.schreiben_freigeben(stellglied=True):
            with self.assertRaises(ProtocolError):
                proto.stellglied_starten()
        self.assertEqual(kombi.geschrieben, [])
        self.assertIsNone(kombi.stellglied_aktiv)

    def test_gestoertes_echo_nur_mit_richtigem_komplement(self):
        port, proto, motor = kw1281(0x01)
        port.echo_auslassen_nach(3)                         # Echo des Titels fehlt, aber
        with self.assertLogs("vagdiag.proto", "WARNING"):  # das Komplement stimmt: weiter
            self.assertEqual(len(proto.gruppe_lesen(4)), 4)
        port.echo_auslassen_nach(3)
        motor.empfangsfehler(2, 0x01, titel=0x29)           # diesmal kam das Byte falsch an
        with self.assertLogs("vagdiag.proto", "WARNING"):
            with self.assertRaises(ProtocolError):
                proto.gruppe_lesen(4)
        self.assertEqual(motor.geschrieben, [])
        self.assertEqual(len(motor._rx), 3)

    def test_ruhe_nach_dem_abbruch(self):
        port, proto, motor = kw1281(0x01)
        proto.timing = Timing(**{**SCHNELL.__dict__, "abbruch_ruhe": 0.3})
        motor.empfangsfehler(3, 0x01, titel=0x29)           # Gruppe 04 kommt als 05 an
        start = time.monotonic()
        with self.assertRaises(ProtocolError):
            proto.gruppe_lesen(4)
        self.assertGreaterEqual(time.monotonic() - start, 0.3)
        self.assertEqual(len(motor._rx), 4)


class Schreibantwort(unittest.TestCase):
    """KW1281: nach Testen und Speichern genau dieser Kanal mit genau diesem Wert."""

    def test_testwert_nicht_uebernommen(self):
        _, proto, kombi = kw1281(0x17, experte=True)
        antwort_aendern(kombi, 0x22, b"\x02\x00\x05")       # zeigt 5 statt 0
        with self.assertRaises(Nak):
            schreiben(proto, 2, 0)
        self.assertNotIn(0x2A, [t for t, _ in kombi.anfragen])
        self.assertTrue(proto.verbunden)
        self.assertEqual(kombi.anpassungen[2], 3)

    def test_test_meldet_anderen_kanal(self):
        _, proto, kombi = kw1281(0x17, experte=True)
        antwort_aendern(kombi, 0x22, b"\x03\x00\x00")
        with self.assertRaises(ProtocolError) as fall:
            schreiben(proto, 2, 0)
        self.assertIn("nichts gespeichert", str(fall.exception))
        titel = [t for t, _ in kombi.anfragen]
        self.assertNotIn(0x2A, titel)
        self.assertEqual(titel[-1], 0x06, "Verbindung beendet")
        self.assertFalse(proto.verbunden)

    def test_speichern_meldet_anderen_wert(self):
        _, proto, kombi = kw1281(0x17, experte=True)
        antwort_aendern(kombi, 0x2A, b"\x02\x00\x07")
        with self.assertRaises(ProtocolError) as fall:
            schreiben(proto, 2, 0)
        self.assertIn("neu lesen", str(fall.exception))
        self.assertEqual([t for t, _ in kombi.anfragen][-1], 0x06)
        self.assertFalse(proto.verbunden)


class Sperren(unittest.TestCase):
    def test_kanal_00_auch_lesend_nie(self):
        _, proto, motor = kw1281(0x01)
        vorher = len(motor.anfragen)
        for daten in (b"\x00", b"", b"\x01\x00"):
            with self.subTest(daten=daten.hex()):
                with self.assertRaises(SchreibenGesperrt):
                    proto.austausch(0x21, daten)
        with self.assertRaises(ValueError):
            proto.anpassung_lesen(0)
        self.assertEqual(len(motor.anfragen), vorher)
        self.assertTrue(proto.verbunden)

    def test_ohne_geoeffnetes_steuergeraet_nichts(self):
        port = sim_port(echtzeit=False, fahrprofil=False)
        proto = KW1281(KLine(port), SCHNELL)
        proto.experte = True
        with self.assertRaises(SchreibenGesperrt):
            with proto.schreiben_freigeben(stellglied=True):
                pass
        proto._freigabe = Freigabe(grundeinstellung=frozenset({60}), stellglied=True)
        for titel, daten in ((0x04, b"\x00"), (0x28, b"\x3c")):
            with self.subTest(titel=hex(titel)):
                with self.assertRaises(SchreibenGesperrt):
                    proto._sende_block(titel, daten)
        self.assertIsNone(proto.zaehler, "nichts gesendet")

    def test_freigabe_nur_fuer_dieses_steuergeraet(self):
        port, proto, _ = kw1281(0x17, experte=True)
        motor = port.steuergeraete[0x01]
        motor.stellglied_bedingung = None                   # Motor dürfte sonst
        with proto.schreiben_freigeben(stellglied=True, anpassung=[(1, 128)],
                                       grundeinstellung=[60]):
            proto.connect(0x01, (10400,))                   # neuer Verbindungsaufbau
            for versuch in (proto.stellglied_starten, lambda: proto.grundeinstellung(60),
                            lambda: proto.anpassung_schreiben(1, 128)):
                with self.assertRaises(SchreibenGesperrt):
                    versuch()
        proto._freigabe = Freigabe(stellglied=True, grundeinstellung=frozenset({60}),
                                   adresse=0x17)            # ausgestellt fürs Kombi
        with self.assertRaises(SchreibenGesperrt):
            proto.stellglied_starten()
        with self.assertRaises(SchreibenGesperrt):
            proto.grundeinstellung(60)
        self.assertEqual(motor.geschrieben, [])
        self.assertTrue(proto.verbunden)

    def test_kw1281_jeder_andere_block_gesperrt(self):
        _, proto, motor = kw1281(0x01, experte=True)
        self.assertEqual(LESEND, {0x00, 0x05, 0x06, 0x07, 0x09, 0x0A, 0x21, 0x29})
        self.assertEqual(EXPERTE, {0x04, 0x22, 0x28, 0x2A})
        with proto.schreiben_freigeben(grundeinstellung=range(1, 256), stellglied=True,
                                       anpassung=[(1, 0), (2, 0), (1, 1)]):
            for titel in sorted(set(range(256)) - LESEND - EXPERTE):
                with self.subTest(titel=f"{titel:02X}"):
                    with self.assertRaises(SchreibenGesperrt):
                        proto._schreibschutz(titel, b"\x01\x00\x00")
        self.assertEqual(motor.geschrieben, [])

    def test_kwp2000_jeder_andere_dienst_gesperrt(self):
        port = sim_port(echtzeit=False, fahrprofil=False)
        kwp = Kwp2000(KLine(port), SCHNELL, 0x17, 2027, 0x6B, 10400)
        voll = Freigabe(grundeinstellung=frozenset(range(1, 256)), stellglied=True,
                        anpassung=frozenset({(2, 0), (2, 1)}), adresse=0x17)
        kwp.schutz = lambda: (True, voll)
        kwp._anp_kanal = 2
        for dienst in sorted(set(range(256)) - ERLAUBTE_DIENSTE - {0x31, 0x32}):
            for anfrage in (bytes([dienst]), bytes([dienst, 0x01, 0x03, 0x00, 0x00])):
                with self.subTest(anfrage=anfrage.hex(" ")):
                    with self.assertRaises(SchreibenGesperrt):
                        kwp._schreibschutz(anfrage)
        for sitzung_ in range(256):                       # nur die Diagnosesitzungen
            anfrage = bytes([0x10, sitzung_])
            if sitzung_ in SITZUNGEN:
                self.assertIsNone(kwp._schreibschutz(anfrage))
            else:
                with self.assertRaises(SchreibenGesperrt):
                    kwp._schreibschutz(anfrage)
        with self.assertRaises(SchreibenGesperrt):
            kwp._schreibschutz(b"\x10")
        for routine in range(256):
            for unter in (ANPASSUNG, STELLGLIED, b"\x00\x00", b"\x01\x01", b"\x02\x03"):
                erlaubt = {   # ohne weitere Daten: nur diese Routinen (Werte siehe oben)
                    0x31: (unter == ANPASSUNG and routine in (0xB8, 0xBA))
                    or (unter == STELLGLIED and routine in (0xB8, 0xB9, 0xBA)),
                    0x32: routine == 0xB8 and unter in (ANPASSUNG, STELLGLIED),
                }
                for dienst, ja in erlaubt.items():
                    anfrage = bytes([dienst, routine]) + unter
                    with self.subTest(anfrage=anfrage.hex(" ")):
                        if ja:
                            kwp._schreibschutz(anfrage)
                        else:
                            with self.assertRaises(SchreibenGesperrt):
                                kwp._schreibschutz(anfrage)


class Kwp2000Schreiben(unittest.TestCase):
    def setUp(self):
        self.s = sitzung(kwp2000_kombi=True)
        self.s.experte = True
        self.s.verbinden(0x17).result(5)
        self.kombi = self.s._port.steuergeraete[0x17]

    def tearDown(self):
        self.s.schliessen()

    def schreiben(self, kanal=2, wert=0):
        return self.s.ausfuehren(schreiben, self.s._proto, kanal, wert).result(10)

    def anzahl(self, anfrage):
        return sum(1 for a in self.kombi.anfragen if a.startswith(bytes.fromhex(anfrage)))

    def test_beschaeftigt_beim_testen_nie_wiederholt(self):
        self.kombi.sonderfall("31 B9 01 03 00 00", "beschaeftigt")
        with self.assertRaises(Nak):
            self.schreiben()
        self.assertEqual(self.anzahl("31 B9 01 03 00 00"), 1)
        self.assertEqual(self.anzahl("31 BB"), 0)
        test = self.kombi.anfragen.index(bytes.fromhex("31 B9 01 03 00 00"))
        self.assertIn(bytes.fromhex("32 B8 01 03"), self.kombi.anfragen[test:])
        self.assertEqual(self.kombi.anpassungen[2], 3)
        self.assertTrue(self.s.verbunden)

    def test_beschaeftigt_beim_speichern_nie_wiederholt(self):
        self.kombi.sonderfall("31 BB 01 03", "beschaeftigt")
        with self.assertRaises(Nak):
            self.schreiben()
        self.assertEqual(self.anzahl("31 BB 01 03"), 1)
        self.assertEqual(self.kombi.anpassungen[2], 3)

    def test_lesen_wird_bei_beschaeftigt_wiederholt(self):
        vorher = self.anzahl("31 BA 01 03")
        self.kombi.sonderfall("31 BA 01 03", "beschaeftigt")
        self.assertEqual(self.s.anpassung_lesen(2).result(5).wert, 3)
        self.assertEqual(self.anzahl("31 BA 01 03") - vorher, 2)

    def test_beschaeftigt_beim_ansteuern_nie_wiederholt(self):
        ereignisse = []
        self.s._ereignis = lambda art, daten: ereignisse.append((art, daten))
        self.kombi.sonderfall("31 B9 01 02", "beschaeftigt")
        future = self.s.stellglieddiagnose()
        warten_bis(lambda: any(a == "stellglied" for a, _ in ereignisse))
        self.s.stellglied_weiter()
        with self.assertRaises(Nak):
            future.result(10)
        self.assertEqual(self.anzahl("31 B9 01 02"), 1)
        self.assertIsNone(self.kombi.stellglied_aktiv)

    def test_ende_der_anpassung_scheitert_nach_dem_schreiben(self):
        for art in ("ablehnen", "stumm"):
            with self.subTest(art=art):
                if not self.s.verbunden:
                    self.s.verbinden(0x17).result(5)
                start = len(self.kombi.anfragen)
                self.kombi.sonderfall("31 BB 01 03", "ablehnen")     # Speichern abgelehnt …
                self.kombi.sonderfall("32 B8 01 03", art)            # … Ende klappt nicht
                with self.assertRaises(ProtocolError) as fall:
                    self.schreiben()
                self.assertIn("Verbindung beendet", str(fall.exception))
                self.assertIn("speichert", str(fall.exception))     # erster Grund bleibt
                self.assertFalse(self.s.verbunden)
                anfragen = self.kombi.anfragen[start:]
                stopp = anfragen.index(bytes.fromhex("32 B8 01 03"))
                self.assertEqual(anfragen[stopp + 1:], [b"\x82"])
                self.assertIsNone(self.kombi._anp_test, "kein Testwert mehr aktiv")
                self.assertEqual(self.kombi.anpassungen[2], 3)

    def test_ende_scheitert_beim_lesen_bleibt_verbunden(self):
        self.kombi.sonderfall("32 B8 01 03", "ablehnen")
        self.assertEqual(self.s.anpassung_lesen(2).result(5).wert, 3)
        self.assertTrue(self.s.verbunden)
        self.assertNotIn(b"\x82", self.kombi.anfragen)

    def test_antwort_einer_anderen_routine(self):
        self.kombi.sonderfall("31 B9 01 03 00 00", "andere_routine")
        with self.assertRaises(Stoerung):
            self.schreiben()
        self.assertEqual(self.anzahl("31 BB"), 0)
        self.assertEqual(self.anzahl("31 B9 01 03 00 00"), 1)
        self.assertEqual(self.kombi.anpassungen[2], 3)


class Stellgliedzeit(unittest.TestCase):
    """Ohne „Weiter“ bleibt kein Stellglied länger als stellglied_schritt_max an."""

    def ablauf(self, **sim):
        s = sitzung(**sim)
        try:
            s.experte = True
            s.stellglied_schritt_max = 0.4
            s.verbinden(0x17).result(5)
            start = time.monotonic()
            ergebnis = s.stellglieddiagnose().result(10)
            dauer = time.monotonic() - start
            kombi = s._port.steuergeraete[0x17]
            verbunden = s.verbunden
        finally:
            s.schliessen()
        self.assertEqual(ergebnis.grund, "zeit")
        self.assertTrue(ergebnis.wieder_verbunden and verbunden)
        self.assertIsNone(kombi.stellglied_aktiv)
        self.assertLess(dauer, 5)
        return ergebnis, kombi

    def test_kw1281(self):
        ergebnis, kombi = self.ablauf()
        self.assertEqual(len(ergebnis.schritte), 1)
        zwischen = bis_zum_ende(kombi.anfragen, 0x04)
        self.assertIsNotNone(zwischen, "Endeblock 06 gesendet")
        self.assertEqual(set(zwischen), {0x09}, "bis dahin nur Keep-Alive")

    def test_kwp2000(self):
        ergebnis, kombi = self.ablauf(kwp2000_kombi=True)
        start = kombi.anfragen.index(bytes.fromhex("31 B8 01 02"))
        rest = kombi.anfragen[start:]
        ende = rest.index(bytes.fromhex("32 B8 01 02"))
        self.assertEqual(rest[ende + 1], b"\x82")
        self.assertEqual(len(ergebnis.schritte), 1)


def haengt_beim_senden(port, nummer, sekunden):
    """Der Rechner hängt beim Senden: das n-te ab jetzt geschriebene Byte geht erst nach
    einer Pause hinaus – vagdiags Prüfung davor hat noch nichts gemerkt."""
    original = port.write
    zaehler = [0]

    def write(daten):
        zaehler[0] += 1
        if zaehler[0] == nummer:
            time.sleep(sekunden)
        original(daten)
    port.write = write


def haengt_nach_dem_lesen(kl, nummer, sekunden):
    """Der Rechner hängt, nachdem das n-te ab jetzt gelesene Byte schon da ist (so wie
    im Auto beim Protokollieren in die Datei)."""
    original = kl.read_byte
    zaehler = [0]

    def read_byte(timeout):
        byte = original(timeout)
        zaehler[0] += 1
        if zaehler[0] == nummer:
            time.sleep(sekunden)
        return byte
    kl.read_byte = read_byte


def echtzeit_motor(versuche: int = 3):
    """Echtzeit-Simulator mit verbundenem Motor, eine Gruppe schon gelesen.

    Auch der Rechner, auf dem die Tests laufen, hängt manchmal kurz (in virtuellen
    Maschinen bis 50 ms) – dann bricht der Zeitwächter zu Recht ab. Deshalb bis zu drei
    Versuche; ein Wächter, der im normalen Betrieb anschlägt, fiele in allen auf."""
    gruende = []
    for _ in range(versuche):
        port = sim_port(echtzeit=True, fahrprofil=False)
        proto = KW1281(KLine(port), Timing())
        try:
            proto.connect(0x01, (10400,))
            proto.gruppe_lesen(1)
        except DiagError as exc:
            gruende.append(str(exc))
            continue
        return port, proto
    raise AssertionError(f"in {versuche} Versuchen abgebrochen: {gruende}")


class Zeitwaechter(unittest.TestCase):
    """Im Auto wartete das ME7.5 nach seinem Komplement etwa 45 ms auf das nächste Byte.
    Kommt es später, nimmt es das späte Byte als Anfang eines neuen Blocks. Mit dem
    Blockzähler 03 wird so aus „Gruppe 005 lesen“ [04 03 29 05 03] beim Steuergerät
    [03 29 05 03] – „Fehlerspeicher löschen“. Der Zeitwächter darf das nie zulassen."""

    def motor(self, **sim):
        port, proto, motor = kw1281(0x01, timing=WAECHTER)
        motor.empfang_timeout = 0.045            # wie das ME7.5 im Auto
        proto.zaehler = 2                        # der nächste Block bekommt den Zähler 03
        return port, proto, motor

    def ungeloescht(self, motor, vorher):
        self.assertEqual((motor.fehler, motor.geloescht), vorher, "Fehlerspeicher gelöscht!")
        self.assertEqual(motor.geschrieben, [])
        self.assertNotIn(0x05, [t for t, _ in motor.anfragen])

    def abgebrochen(self, aufruf):
        """Aufruf muss mit ProtocolError („zu spät“) enden – zurück der Fehler."""
        try:
            aufruf()
        except DiagError as exc:
            return exc
        return None

    def zu_spaet(self, fehler):
        self.assertIsInstance(fehler, ProtocolError)
        self.assertIn("zu spät", str(fehler))

    def mitschreiben(self, port):
        """Alles, was ab jetzt aufs Kabel geht."""
        geschrieben = []
        original = port.write
        port.write = lambda daten: (geschrieben.append(bytes(daten)), original(daten))
        return geschrieben

    def test_haengt_nach_dem_ersten_komplement(self):
        port, proto, motor = self.motor()
        vorher = (list(motor.fehler), motor.geloescht)
        geschrieben = self.mitschreiben(port)
        haengt_nach_dem_lesen(proto.kl, 1, 0.08)   # nach dem Komplement auf das Längenbyte
        fehler = self.abgebrochen(lambda: proto.gruppe_lesen(5))
        self.ungeloescht(motor, vorher)
        self.zu_spaet(fehler)
        self.assertEqual(geschrieben, [b"\x04"], "das späte Byte ging gar nicht erst hinaus")

    def test_byte_geht_zu_spaet_hinaus(self):
        port, proto, motor = self.motor()
        vorher = (list(motor.fehler), motor.geloescht)
        haengt_beim_senden(port, 2, 0.08)          # das Zählerbyte geht 80 ms zu spät
        fehler = self.abgebrochen(lambda: proto.gruppe_lesen(5))
        self.ungeloescht(motor, vorher)
        self.zu_spaet(fehler)
        self.assertEqual(motor.verworfen[-1], b"\x04", "halben Block verworfen")
        self.assertEqual(motor._rx, [0x03], "danach nichts hinterhergeschickt")

    def test_vor_dem_blockende(self):
        port, proto, motor = kw1281(0x01, timing=WAECHTER)
        motor.empfang_timeout = 0.045
        haengt_beim_senden(port, 5, 0.08)          # wie um 07:00:34 im Auto
        fehler = self.abgebrochen(lambda: proto.gruppe_lesen(4))
        self.assertEqual(motor.geschrieben, [])
        self.zu_spaet(fehler)                      # erkannt, nicht erst an der Antwort FC
        self.assertFalse(proto.verbunden)

    def test_haengt_waehrend_das_komplement_ankommt(self):
        """Echtzeit: vagdiag wartet auf das Komplement, hängt aber, nachdem es angekommen
        ist (noch im Lesen am Kabel). Dann zählt, wie schnell dieses Steuergerät sonst
        quittiert."""
        port, proto = echtzeit_motor()
        motor = port.steuergeraete[0x01]
        motor.empfang_timeout = 0.045
        vorher = (list(motor.fehler), motor.geloescht)
        proto.zaehler = 2
        original = port.read
        scharf = [True]

        def read(anzahl, timeout):
            daten = original(anzahl, timeout)
            if scharf[0] and daten[:1] == b"\xfb":     # Komplement auf das Längenbyte 04
                scharf[0] = False
                time.sleep(0.08)
            return daten
        port.read = read
        fehler = self.abgebrochen(lambda: proto.gruppe_lesen(5))
        self.assertFalse(scharf[0], "Pause wirklich ausgelöst")
        self.ungeloescht(motor, vorher)
        self.zu_spaet(fehler)

    def test_komplement_lag_schon_im_puffer(self):
        """Echtzeit: vagdiag hängt nach dem Senden, bevor es das Komplement liest – das liegt
        dann schon im Puffer, seine Ankunft ist unbekannt. Ohne Erfahrungswerte (wie gleich
        nach dem Verbinden) zählt vorsichtshalber der Zeitpunkt des eigenen Bytes."""
        port, proto = echtzeit_motor()
        motor = port.steuergeraete[0x01]
        motor.empfang_timeout = 0.045
        vorher = (list(motor.fehler), motor.geloescht)
        proto.zaehler = 2
        proto._verzug.clear()
        original = proto.kl.write_byte
        scharf = [True]

        def write_byte(byte):
            original(byte)
            if scharf[0] and byte == 0x04:         # nach dem Längenbyte samt Echo
                scharf[0] = False
                time.sleep(0.08)
        proto.kl.write_byte = write_byte
        geschrieben = self.mitschreiben(port)
        fehler = self.abgebrochen(lambda: proto.gruppe_lesen(5))
        self.assertFalse(scharf[0], "Pause wirklich ausgelöst")
        self.ungeloescht(motor, vorher)
        self.zu_spaet(fehler)
        self.assertEqual(geschrieben, [b"\x04"], "das späte Byte ging gar nicht erst hinaus")

    def test_speicherbereinigung_waehrend_eines_blocks_aus(self):
        import gc
        _, proto, _ = kw1281(0x01)
        zustand = []
        original = proto.kl.write_byte

        def write_byte(byte):
            zustand.append(gc.isenabled())
            original(byte)
        proto.kl.write_byte = write_byte
        self.assertTrue(gc.isenabled())
        proto.gruppe_lesen(1)
        self.assertTrue(zustand and not any(zustand), zustand)
        self.assertTrue(gc.isenabled(), "danach wieder an")

    def test_kurzes_umschaltintervall(self):
        import sys
        alt = sys.getswitchinterval()
        try:
            sys.setswitchinterval(0.005)
            DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=False), SCHNELL,
                        keepalive=0.05).start().schliessen()
            self.assertLessEqual(sys.getswitchinterval(), 0.001)
        finally:
            sys.setswitchinterval(alt)

    def kwp2000_kombi(self):
        port = sim_port(echtzeit=False, fahrprofil=False, kwp2000_kombi=True)
        proto = KW1281(KLine(port), WAECHTER)
        proto.connect(0x17, (10400,))
        self.assertTrue(proto.ist_kwp2000)
        return port, proto, port.steuergeraete[0x17]

    def test_kwp2000_byte_geht_zu_spaet_hinaus(self):
        port, proto, kombi = self.kwp2000_kombi()
        anfragen = list(kombi.anfragen)
        geschrieben = []
        haengt_beim_senden(port, 3, 0.08)          # drittes Byte der Anfrage 80 ms zu spät
        original = port.write
        port.write = lambda daten: (geschrieben.append(bytes(daten)), original(daten))
        fehler = self.abgebrochen(proto.fehler_lesen)
        self.zu_spaet(fehler)
        self.assertEqual(len(geschrieben), 3, "nach dem späten Byte nichts mehr gesendet")
        self.assertEqual(kombi.anfragen, anfragen, "keine vollständige Anfrage angekommen")
        self.assertFalse(proto.verbunden)
        self.assertTrue(proto.verloren_kwp2000)

    def test_kwp2000_haengt_zwischen_zwei_bytes(self):
        from unittest import mock
        from vagdiag import kwp2000
        port, proto, kombi = self.kwp2000_kombi()
        proto._kwp.timing = Timing(**{**WAECHTER.__dict__, "kwp_p4": 0.001})
        anfragen = list(kombi.anfragen)
        geschrieben = []
        original = port.write
        port.write = lambda daten: (geschrieben.append(bytes(daten)), original(daten))
        aufrufe = [0]
        echt = kwp2000._genau_warten

        def warten(sekunden):
            aufrufe[0] += 1
            echt(0.08 if aufrufe[0] == 2 else sekunden)   # hängt vor dem dritten Byte
        with mock.patch.object(kwp2000, "_genau_warten", warten):
            fehler = self.abgebrochen(proto.fehler_lesen)
        self.zu_spaet(fehler)
        self.assertIn("nicht zu Ende gesendet", str(fehler))
        self.assertEqual(len(geschrieben), 2, "das dritte Byte ging nie hinaus")
        self.assertEqual(kombi.anfragen, anfragen)
        self.assertFalse(proto.verbunden)

    def test_normaler_betrieb_in_echtzeit(self):
        gruende = []
        for _ in range(3):          # siehe echtzeit_motor: der Testrechner hängt manchmal
            _, proto = echtzeit_motor()
            try:
                for gruppe in (2, 3, 4, 5, 1, 4):
                    self.assertTrue(proto.gruppe_lesen(gruppe))
            except DiagError as exc:
                gruende.append(str(exc))
                continue
            if not all(0.0 < v < 0.03 for v in proto._verzug):
                gruende.append(f"Verzug {proto._verzug}")
                continue
            self.assertTrue(proto.verbunden)
            return
        self.fail(f"in drei Versuchen abgebrochen: {gruende}")


class PauseNachAbbruch(unittest.TestCase):
    """Bricht eine Sitzung ohne Ende ab, hört ihr Steuergerät womöglich noch zu – ein
    anderes erst reizen, wenn sie sicher vorbei ist."""

    TIMING = Timing(**{**SCHNELL.__dict__, "reconnect_pause": 0.5, "wechsel_pause": 0.05,
                       "trenn_pause": 0.05, "kwp_p3_max": 0.6})

    def sitzung(self, **sim):
        s = DiagSession(lambda: sim_port(echtzeit=False, fahrprofil=False, **sim),
                        self.TIMING, keepalive=0.05).start()
        s._port_oeffnen()
        return s

    def dauer(self, future):
        start = time.monotonic()
        future.result(10)
        return time.monotonic() - start

    def test_kw1281_abbruch_dann_anderes_steuergeraet(self):
        s = self.sitzung()
        try:
            s.verbinden(0x01).result(5)
            s._port.steuergeraete[0x01].empfangsfehler(2, 0x01, titel=0x29)
            with self.assertRaises(ProtocolError):
                s.gruppe_lesen(1).result(5)
            self.assertGreaterEqual(self.dauer(s.verbinden(0x17)), 0.4)
            s.trennen().result(5)            # sauber beendet: nur die kurze Pause
            self.assertLess(self.dauer(s.verbinden(0x03)), 0.4)
        finally:
            s.schliessen()

    def test_kwp2000_abbruch_wartet_bis_p3(self):
        s = self.sitzung(kwp2000_kombi=True)
        try:
            s.verbinden(0x17).result(5)
            s._port.steuergeraete[0x17].naechste_antwort("stumm")
            s.ausfuehren(lambda: s._proto.verloren()).result(5)
            self.assertTrue(s._proto.verloren_kwp2000)
            self.assertGreaterEqual(self.dauer(s.verbinden(0x01)), 1.0)
        finally:
            s.schliessen()

    def test_messung_verbindet_dasselbe_steuergeraet_eilig(self):
        s = self.sitzung()
        try:
            s.verbinden(0x01).result(5)
            s._proto.verloren()
            s._eilig = True
            self.assertLess(s._pause_vor_reizung(0x01), 0.1)
            self.assertGreater(s._pause_vor_reizung(0x17), 0.3)
            s._eilig = False
            self.assertGreater(s._pause_vor_reizung(0x01), 0.3)
        finally:
            s.schliessen()


ABS_KENNUNG = [b"6X0907379 B ", b"ABS 30 IE CA", b"N V004", b"\x00\x01\x1a\xd4\x31"]


class Kennung(unittest.TestCase):
    """Rückfragen gelten nur für genau das bestätigte Gerät; Airbag, Bremsen, Wegfahrsperre
    und Lenkung bleiben auch unter fremder Adresse gesperrt."""

    def test_abs_unter_der_adresse_des_kombis(self):
        # z. B. wenn eine Störung die Reizung 17 verfälscht hätte und das ABS antwortet
        s = sitzung()
        try:
            kombi = s._port.steuergeraete[0x17]
            kombi.kennung = list(ABS_KENNUNG)
            s.experte = True
            v = s.verbinden(0x17).result(5)
            self.assertIn("Bremsen", KW1281.stellglied_gesperrt(0x17, v))
            for aufruf in (s.stellglied_pruefen, s.service_lesen,
                           lambda: s.stellglieddiagnose(ohne_pruefung_ok=True)):
                with self.assertRaises(Exception) as fall:
                    aufruf().result(10)
                self.assertIn("Airbag, Bremsen", str(fall.exception))
            with self.assertRaises(SchreibenGesperrt):
                s.ausfuehren(lambda: s._proto.schreiben_freigeben(stellglied=True)
                             .__enter__()).result(5)
            self.assertEqual(kombi.geschrieben, [])
        finally:
            s.schliessen()

    def test_kennung_der_echten_geraete(self):
        from vagdiag.stellglied import gesperrt_nach_kennung
        gesperrt = [("6X0907379 B", "ABS 30 IE CAN V004"), ("6X0953257", "IMMO 0002"),
                    ("1J0909609 Q", "AIRBAG VW3 SG 0002"), ("8E0959655B", "AIRBAG"),
                    ("8E0614111", "ESP 5.7"), ("6Q0423156", "Lenkhilfe")]
        frei = [("6K0906032M", "ME7.5.10 S080"), ("6K9920806", "KOMBIINSTRUMENT TRW V04"),
                ("1J0920806", "KOMBI+WEGFAHRSP VDO V01"), ("038906019KP", "1,9l R4 EDC  G000SG")]
        for teil, name in gesperrt:
            self.assertIsNotNone(gesperrt_nach_kennung(teil, name), teil)
        for teil, name in frei:
            self.assertIsNone(gesperrt_nach_kennung(teil, name), teil)

    def test_fehler_loeschen_nur_am_bestaetigten_geraet(self):
        s = sitzung()
        try:
            motor = s.verbinden(0x01).result(5)
            kombi = s._port.steuergeraete[0x17]
            vorher = list(kombi.fehler)
            s.verbinden(0x17).result(5)          # inzwischen ein anderes Gerät
            with self.assertRaises(Nichts) as fall:
                s.fehler_loeschen(motor.kennung).result(5)
            self.assertIn("nichts gelöscht", str(fall.exception))
            self.assertEqual(kombi.fehler, vorher)
            self.assertEqual(kombi.geloescht, 0)
            v = s._proto.verbindung
            s.fehler_loeschen(v.kennung).result(5)    # genau dieses: geht
            self.assertEqual(kombi.geloescht, 1)
        finally:
            s.schliessen()

    def test_expertenfunktion_nur_am_bestaetigten_geraet(self):
        s = sitzung(motor_aus=True)
        try:
            s.experte = True
            s.verbinden(0x17).result(5)
            pruefung = s.stellglied_pruefen().result(5)
            s.verbinden(0x01).result(5)          # der Motor ist jetzt dran
            with self.assertRaises(Nichts) as fall:
                s.stellglieddiagnose(kennung=pruefung.kennung).result(10)
            self.assertIn("anderes Steuergerät", str(fall.exception))
            with self.assertRaises(Nichts):
                s.drosselklappe_anlernen(60, dauer=0.2, kennung=pruefung.kennung).result(10)
            motor = s._port.steuergeraete[0x01]
            self.assertEqual(motor.geschrieben, [])
            s.verbinden(0x17).result(5)          # wieder das bestätigte Kombi: geht
            s.stellglied_schritt_max = 0.2
            ergebnis = s.stellglieddiagnose(kennung=pruefung.kennung).result(10)
            self.assertEqual(ergebnis.grund, "zeit")
        finally:
            s.schliessen()

    def test_freigabe_gilt_nur_fuer_die_kennung(self):
        # Doppelte Sicherung im Protokoll: Eine Freigabe endet mit jedem Verbindungsaufbau –
        # und gälte auch sonst nur, solange dasselbe Gerät (gleiche Kennung) verbunden ist.
        from unittest import mock
        port, proto, kombi = kw1281(0x17, experte=True)
        with proto.schreiben_freigeben(anpassung=[(2, 0)]):
            anderes = (0x17, "6K0920800", "KOMBI ANDERES")
            with mock.patch.object(type(proto.verbindung), "kennung",
                                   new_callable=mock.PropertyMock, return_value=anderes):
                with self.assertRaises(SchreibenGesperrt) as fall:
                    proto.anpassung_schreiben(2, 0)
        self.assertIn("anderes Steuergerät", str(fall.exception))
        self.assertEqual(kombi.geschrieben, [])

    def test_drehzahl_aus_allen_gruppen(self):
        s = sitzung()                            # Motor läuft
        try:
            motor = s._port.steuergeraete[0x01]
            original = motor.gruppen[1]
            motor.gruppen[1] = lambda: [(1, 200, 0)] + list(original())[1:]   # 001: 0 /min
            s.experte = True
            s.verbinden(0x01).result(5)
            pruefung = s.stellglied_pruefen().result(5)
        finally:
            s.schliessen()
        self.assertIs(pruefung.bedingungen[0].ok, False, pruefung.bedingungen)
        self.assertNotEqual(pruefung.bedingungen[0].wert, "0 /min")


if __name__ == "__main__":
    unittest.main()

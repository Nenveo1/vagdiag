# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Kabel weg und wieder da: Nach einem USB-Fehler (Kabel gezogen, Rechner im Ruhezustand)
öffnet der Port das Kabel beim nächsten Zugriff neu – den fehlgeschlagenen Zugriff wiederholt
er nicht. Der Fahrtenschreiber wartet dann still auf das Kabel, passiv auch schon beim Start.
Start: python -m unittest -v"""

import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from vagdiag import einstellungen, fahrtenschreiber, ringspeicher
from vagdiag.fahrtenschreiber import FahrtPlan
from vagdiag.kw1281 import ProtocolError, Timing
from vagdiag.port import D2xxPort, FtdiPort, PortError, RawPort, fehlertext, kabelfehler
from vagdiag.session import DiagSession
from vagdiag.sim import sim_port

SCHNELL = Timing(sync_timeout=0.2, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0,
                 byte_frist=0.5, kwp_p4_frist=0.5)


class Fehlertexte(unittest.TestCase):
    def test_pyftdi_meldung_mit_grund(self):
        """pyftdi 0.57 meldet „UsbError: {exc}“ wörtlich – der Grund steht in __cause__."""
        try:
            try:
                raise OSError(19, "No such device (it may have been disconnected)")
            except OSError as usb:
                raise RuntimeError("UsbError: {exc}") from usb
        except RuntimeError as exc:
            text = fehlertext(exc)
        self.assertEqual(text, "UsbError: [Errno 19] No such device (it may have been "
                               "disconnected)")
        self.assertEqual(fehlertext(ValueError("normal")), "normal")
        self.assertEqual(fehlertext(TimeoutError()), "TimeoutError")

    def test_kabelfehler_in_der_kette(self):
        try:
            try:
                raise PortError("Baudrate 10400 nicht einstellbar")
            except PortError as exc:
                raise ProtocolError("Verbindungsaufbau abgebrochen") from exc
        except ProtocolError as exc:
            gefunden = kabelfehler(exc)
        self.assertIsInstance(gefunden, PortError)
        self.assertIsNone(kabelfehler(ProtocolError("Falsches Komplement")))
        self.assertIsNone(kabelfehler(None))
        try:
            try:
                raise PortError("weg")
            except PortError:
                raise ProtocolError("gestört") from None      # bewusst ohne Kette
        except ProtocolError as exc:
            self.assertIsNone(kabelfehler(exc))


# ---------------------------------------------------------------- pyftdi nachgebildet
class _UsbTools:
    geleert = 0

    @classmethod
    def flush_cache(cls):
        cls.geleert += 1


class _Ftdi:
    """Ein FT232R: offen, bis `stirbt()` – danach scheitert jeder Zugriff wie nach dem
    Ruhezustand. `fehlt` (Klasse): kein Kabel am USB."""
    fehlt = False
    geoeffnet: list = []

    class BitMode:
        BITBANG = 1
        RESET = 0

    def __init__(self):
        self.tot = False
        self.geschlossen = False
        self.baud = None
        self.geschrieben: list[bytes] = []
        self.versuche = 0

    def _pruefen(self):
        if self.tot:
            try:
                raise OSError(19, "No such device (it may have been disconnected)")
            except OSError as exc:
                raise RuntimeError("UsbError: {exc}") from exc

    def open_from_url(self, url):
        if _Ftdi.fehlt:
            raise OSError("Device not found")
        _Ftdi.geoeffnet.append(self)

    def set_line_property(self, *_):
        self._pruefen()

    def set_flowctrl(self, *_):
        self._pruefen()

    def set_latency_timer(self, *_):
        self._pruefen()

    def set_baudrate(self, baud):
        self._pruefen()
        self.baud = baud
        return baud

    def purge_buffers(self):
        self._pruefen()

    def write_data(self, daten):
        self.versuche += 1
        self._pruefen()
        self.geschrieben.append(bytes(daten))

    def read_data_bytes(self, *_a, **_k):
        self._pruefen()
        return b""

    def set_break(self, *_):
        self._pruefen()

    def set_bitmode(self, *_):
        self._pruefen()

    def close(self):
        self.geschlossen = True


def _pyftdi_module():
    paket = types.ModuleType("pyftdi")
    ftdi = types.ModuleType("pyftdi.ftdi")
    ftdi.Ftdi = _Ftdi
    usbtools = types.ModuleType("pyftdi.usbtools")
    usbtools.UsbTools = _UsbTools
    paket.ftdi, paket.usbtools = ftdi, usbtools
    return {"pyftdi": paket, "pyftdi.ftdi": ftdi, "pyftdi.usbtools": usbtools}


class FtdiNeuOeffnen(unittest.TestCase):
    def setUp(self):
        _Ftdi.fehlt = False
        _Ftdi.geoeffnet = []
        _UsbTools.geleert = 0
        patcher = mock.patch.dict(sys.modules, _pyftdi_module())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_nach_usb_fehler_neu_geoeffnet(self):
        port = FtdiPort("ftdi:///1")
        erstes = _Ftdi.geoeffnet[-1]
        self.assertEqual((len(_Ftdi.geoeffnet), _UsbTools.geleert, erstes.baud), (1, 1, 10400))
        erstes.tot = True                                  # Ruhezustand
        with self.assertRaises(PortError) as fehler:
            port.set_baudrate(9600)
        self.assertIn("No such device", str(fehler.exception))
        self.assertNotIn("{exc}", str(fehler.exception))
        self.assertTrue(erstes.geschlossen)
        port.set_baudrate(9600)                            # nächster Zugriff: neu geöffnet
        zweites = _Ftdi.geoeffnet[-1]
        self.assertIsNot(zweites, erstes)
        self.assertEqual(_UsbTools.geleert, 2, "alte USB-Adresse vergessen")
        self.assertEqual(zweites.baud, 9600)
        port.close()

    def test_fehlgeschlagenes_schreiben_nicht_wiederholt(self):
        port = FtdiPort("ftdi:///1")
        erstes = _Ftdi.geoeffnet[-1]
        erstes.tot = True
        with self.assertRaises(PortError):
            port.write(b"\x55")
        self.assertEqual(erstes.versuche, 1)
        self.assertEqual(len(_Ftdi.geoeffnet), 1, "nicht im selben Zugriff neu geöffnet")
        port.write(b"\xAA")                                # erst der nächste Zugriff
        self.assertEqual(_Ftdi.geoeffnet[-1].geschrieben, [b"\xAA"])

    def test_kabel_fehlt_bis_es_wieder_steckt(self):
        port = FtdiPort("ftdi:///1")
        _Ftdi.geoeffnet[-1].tot = True
        _Ftdi.fehlt = True                                 # gezogen
        for _ in range(2):
            with self.assertRaises(PortError):
                port.purge_rx()
        with self.assertRaises(PortError) as fehler:
            port.purge_rx()
        self.assertIn("KKL-Kabel konnte nicht geöffnet werden", str(fehler.exception))
        _Ftdi.fehlt = False                                # wieder gesteckt
        port.purge_rx()
        self.assertEqual(len(_Ftdi.geoeffnet), 2)

    def test_geschlossen_bleibt_zu(self):
        port = FtdiPort("ftdi:///1")
        port.close()
        with self.assertRaises(PortError):
            port.write(b"\x55")
        self.assertEqual(len(_Ftdi.geoeffnet), 1)

    def test_baudrate_bleibt_nach_dem_neu_oeffnen(self):
        """Neu geöffnet gilt die zuletzt gesetzte Baudrate, nicht die Voreinstellung."""
        port = FtdiPort("ftdi:///1")
        port.set_baudrate(9600)
        _Ftdi.geoeffnet[-1].tot = True
        with self.assertRaises(PortError):
            port.write(b"\x55")
        port.write(b"\x55")
        self.assertEqual(len(_Ftdi.geoeffnet), 2)
        self.assertEqual(_Ftdi.geoeffnet[-1].baud, 9600)
        port.close()


# ---------------------------------------------------------------- ftd2xx nachgebildet
class _D2xx:
    fehlt = False
    geoeffnet: list = []

    def __init__(self):
        self.tot = False
        self.geschlossen = False
        self.baud = None

    def _pruefen(self):
        if self.tot:
            raise OSError("DEVICE_NOT_FOUND")

    def setBaudRate(self, baud):          # noqa: N802 (Name von ftd2xx)
        self._pruefen()
        self.baud = baud

    def setDataCharacteristics(self, *_):     # noqa: N802
        self._pruefen()

    def setFlowControl(self, *_):             # noqa: N802
        self._pruefen()

    def setLatencyTimer(self, *_):            # noqa: N802
        self._pruefen()

    def purge(self, *_):
        self._pruefen()

    def write(self, daten):
        self._pruefen()

    def close(self):
        self.geschlossen = True


def _ftd2xx_modul():
    modul = types.ModuleType("ftd2xx")

    def oeffnen(_nummer):
        if _D2xx.fehlt:
            raise OSError("DEVICE_NOT_FOUND")
        dev = _D2xx()
        _D2xx.geoeffnet.append(dev)
        return dev
    modul.open = oeffnen
    return modul


class D2xxNeuOeffnen(unittest.TestCase):
    def setUp(self):
        _D2xx.fehlt = False
        _D2xx.geoeffnet = []
        patcher = mock.patch.dict(sys.modules, {"ftd2xx": _ftd2xx_modul()})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_nach_usb_fehler_neu_geoeffnet(self):
        port = D2xxPort("d2xx:0")
        erstes = _D2xx.geoeffnet[-1]
        erstes.tot = True
        with self.assertRaises(PortError):
            port.set_baudrate(9600)
        self.assertTrue(erstes.geschlossen)
        _D2xx.fehlt = True
        with self.assertRaises(PortError):
            port.write(b"\x55")
        _D2xx.fehlt = False
        port.write(b"\x55")
        self.assertEqual(len(_D2xx.geoeffnet), 2)
        self.assertEqual(_D2xx.geoeffnet[-1].baud, 10400)
        port.close()
        with self.assertRaises(PortError):
            port.write(b"\x55")
        self.assertEqual(len(_D2xx.geoeffnet), 2)

    def test_baudrate_bleibt_nach_dem_neu_oeffnen(self):
        port = D2xxPort("d2xx:0")
        port.set_baudrate(9600)
        _D2xx.geoeffnet[-1].tot = True
        with self.assertRaises(PortError):
            port.write(b"\x55")
        port.write(b"\x55")
        self.assertEqual(len(_D2xx.geoeffnet), 2)
        self.assertEqual(_D2xx.geoeffnet[-1].baud, 9600)
        port.close()


# ---------------------------------------------------------------- Fahrtenschreiber
class Wackelkabel(RawPort):
    """Simulator hinter einem Kabel, das sich ziehen lässt: Solange `weg`, scheitert jeder
    Zugriff mit PortError (wie nach dem Ruhezustand)."""
    simulator = True

    def __init__(self):
        self.innen = sim_port(echtzeit=False, fahrprofil=True, zeitfaktor=20.0)
        self.weg = False
        self.description = "Wackelkabel"

    def __getattr__(self, name):
        return getattr(self.innen, name)

    def _pruefen(self):
        if self.weg:
            raise PortError("Lesen vom Kabel fehlgeschlagen: [Errno 19] No such device")

    def set_baudrate(self, baud):
        self._pruefen()
        return self.innen.set_baudrate(baud)

    def send_5baud(self, adresse):
        self._pruefen()
        self.innen.send_5baud(adresse)

    def fast_init_puls(self):
        self._pruefen()
        self.innen.fast_init_puls()

    def write(self, daten):
        self._pruefen()
        self.innen.write(daten)

    def read(self, anzahl, timeout):
        self._pruefen()
        return self.innen.read(anzahl, timeout)

    def purge_rx(self):
        self._pruefen()
        self.innen.purge_rx()


class FahrtOhneKabel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self._tmp.name)
        self._alt = einstellungen.DATEI
        einstellungen._zuruecksetzen_fuer_tests(self.ordner / "e.json")
        self._stueck, ringspeicher.STUECK = ringspeicher.STUECK, 2.0
        self._pause, fahrtenschreiber.KABEL_PAUSE = fahrtenschreiber.KABEL_PAUSE, 0.05
        self.notizen: list[str] = []

    def tearDown(self):
        ringspeicher.STUECK = self._stueck
        fahrtenschreiber.KABEL_PAUSE = self._pause
        einstellungen._zuruecksetzen_fuer_tests(self._alt)
        self._tmp.cleanup()

    def ereignis(self, art, daten):
        if art == "fahrt_notiz":
            self.notizen.append(daten)

    def test_passiv_wartet_beim_start_auf_das_kabel(self):
        """Automatisch gestartet, aber noch kein Kabel: still warten, dann aufzeichnen."""
        versuche = []

        def fabrik():
            versuche.append(time.monotonic())
            if len(versuche) <= 3:
                raise PortError("KKL-Kabel konnte nicht geöffnet werden (ftdi:///1): Device "
                                "not found")
            return sim_port(echtzeit=False, fahrprofil=True, zeitfaktor=20.0)
        s = DiagSession(fabrik, SCHNELL, keepalive=0.05, ereignis=self.ereignis).start()
        try:
            plan = FahrtPlan(besuche=[], pruefung=False, passiv=6.0, volle_runde_nach=0.3)
            future = s.fahrt_starten(plan, self.ordner)
            time.sleep(2.5)
            s.fahrt_beenden()
            ergebnis = future.result(30)
        finally:
            s.schliessen()
        self.assertGreaterEqual(len(versuche), 4)
        weg = [n for n in self.notizen if "Kabel nicht erreichbar" in n]
        self.assertEqual(len(weg), 1, self.notizen)
        self.assertEqual(sum("Kabel wieder da" in n for n in self.notizen), 1, self.notizen)
        self.assertTrue(any("Fahrt beginnt" in n for n in self.notizen))
        self.assertIn("Nicht erreicht:", ergebnis.zeilen)
        self.assertTrue(any("Kabel nicht erreichbar" in z for z in ergebnis.zeilen))

    def test_passiv_ende_ohne_kabel(self):
        def fabrik():
            raise PortError("KKL-Kabel konnte nicht geöffnet werden: Device not found")
        s = DiagSession(fabrik, SCHNELL, keepalive=0.05, ereignis=self.ereignis).start()
        try:
            future = s.fahrt_starten(FahrtPlan(besuche=[], passiv=6.0), self.ordner)
            time.sleep(0.5)
            s.fahrt_beenden()
            ergebnis = future.result(30)
        finally:
            s.schliessen()
        self.assertFalse(ergebnis.abgebrochen)
        self.assertEqual(sum("Kabel nicht erreichbar" in n for n in self.notizen), 1)
        self.assertFalse(any("Startprüfung" in n for n in self.notizen), self.notizen)

    def test_kabel_waehrend_der_fahrt_gezogen(self):
        """Eine Notiz statt einer alle paar Sekunden, keine Störung – und es geht weiter."""
        kabel = Wackelkabel()
        s = DiagSession(lambda: kabel, SCHNELL, keepalive=0.05, ereignis=self.ereignis).start()
        try:
            plan = FahrtPlan(besuche=[], pruefung=False, volle_runde_nach=0.3)
            future = s.fahrt_starten(plan, self.ordner)
            time.sleep(1.5)
            kabel.weg = True
            time.sleep(1.5)
            kabel.weg = False
            time.sleep(1.5)
            werte_vorher = sum("Kabel wieder da" in n for n in self.notizen)
            s.fahrt_beenden()
            ergebnis = future.result(30)
        finally:
            s.schliessen()
        self.assertEqual(sum("Kabel nicht erreichbar" in n for n in self.notizen), 1,
                         self.notizen)
        self.assertEqual(werte_vorher, 1, self.notizen)
        self.assertFalse(any("Verbindungsaufbau zum Motor gestört" in n
                             for n in self.notizen), self.notizen)
        text = "\n".join(ergebnis.zeilen)
        self.assertIn("Störungen: 0", text)
        self.assertRegex(text, r"Kabel zwischendurch nicht erreichbar: \d\d:\d\d:\d\d–"
                               r"\d\d:\d\d:\d\d")


if __name__ == "__main__":
    unittest.main()

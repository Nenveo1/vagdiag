"""Windows-Weg: Kabel über den FTDI-Treiber (D2XX). Ohne Windows und ohne Kabel
läuft das gegen einen nachgebauten ftd2xx-Treiber, an dem der Simulator hängt –
so wird die ganze Kette bis zum Steuergerät geprüft.  Start: python -m unittest -v"""

import io
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from vagdiag import cli, pfade, port
from vagdiag.aufzeichnung import CsvAufzeichnung
from vagdiag.kline import KLine
from vagdiag.kw1281 import KW1281, Timing
from vagdiag.port import D2xxPort, PortError, bits_5baud
from vagdiag.sim import sim_port

SCHNELL = Timing(sync_timeout=0.3, retry_pause=0.01, reconnect_pause=0.05,
                 block_timeout=0.3, byte_timeout=0.1, w4=0.0, inter_byte=0.0)
SERIENNUMMER = b"A50285BI"


def _adresse(bits: list[int]) -> int:
    """Adresse aus Startbit, 8 Bits (LSB zuerst) und Stoppbit."""
    if len(bits) != 10 or bits[0] != 0 or bits[-1] != 1:
        raise AssertionError(f"keine gültige Reizung: {bits}")
    return sum(b << i for i, b in enumerate(bits[1:9])) & 0x7F


class FakeGeraet:
    """Verhält sich wie ein FTD2XX-Objekt; dahinter steckt der Simulator."""

    def __init__(self, **sim):
        self.sim = sim_port(echtzeit=False, fahrprofil=False, **sim)
        self.einstellungen: dict[str, object] = {}
        self.bits: list[int] = []
        self.low_seit: float | None = None
        self.fast_inits = 0
        self.bitbang = False
        self.bitbang_daten = bytearray()
        self.reizung: int | None = None
        self.reizungen: list[int] = []
        self.lese_ms = 0
        self.offen = True

    # -- Einstellungen
    def setBaudRate(self, baud):
        self.einstellungen["baud"] = baud
        self.sim.set_baudrate(baud)

    def setDataCharacteristics(self, wortlaenge, stoppbits, paritaet):
        self.einstellungen["format"] = (wortlaenge, stoppbits, paritaet)

    def setFlowControl(self, art, xon, xoff):
        self.einstellungen["fluss"] = art

    def setLatencyTimer(self, ms):
        self.einstellungen["latenz"] = ms

    def setTimeouts(self, lesen, schreiben):
        self.lese_ms = lesen

    def purge(self, maske):
        self.sim.purge_rx()

    # -- Reizung per Break
    def setBreakOn(self):
        self.low_seit = time.perf_counter()
        self._bit(0)

    def setBreakOff(self):
        if not self.bits:
            return                      # Ruhepegel, keine Reizung im Gang
        dauer = time.perf_counter() - (self.low_seit or 0.0)
        if self.bits == [0] and 0.020 <= dauer <= 0.040:
            # 25 ms Low: Weckmuster des Fast-Init, keine 5-Baud-Bitfolge
            self.bits = []
            self.fast_inits += 1
            self.sim.fast_init_puls()
            return
        self._bit(1)

    def _bit(self, bit):
        self.bits.append(bit)
        if len(self.bits) == 10:
            self.reizung = _adresse(self.bits)
            self.bits = []

    # -- Reizung per Bitbang
    def setBitMode(self, maske, modus):
        if modus == 0x01:
            self.bitbang = True
            self.bitbang_daten.clear()
        else:
            if self.bitbang:
                pegel = [1 if b & 0x01 else 0 for b in self.bitbang_daten]
                if pegel == [1, 0, 1]:          # Weckmuster des Fast-Init
                    self.fast_inits += 1
                    self.sim.fast_init_puls()
                else:
                    self.reizung = _adresse(pegel[-10:])
            self.bitbang = False

    def _reizen(self):
        # erst beim ersten Lesen – wie im Auto antwortet das Steuergerät nach dem Leeren
        if self.reizung is not None:
            adresse, self.reizung = self.reizung, None
            self.reizungen.append(adresse)
            self.sim.send_5baud(adresse)

    # -- Daten
    def write(self, daten):
        if self.bitbang:
            self.bitbang_daten.extend(daten)
        else:
            self.sim.write(bytes(daten))
        return len(daten)

    def getQueueStatus(self):
        self._reizen()
        jetzt = time.monotonic()
        return sum(1 for zeit, _, _ in self.sim._rx if zeit <= jetzt)

    def read(self, anzahl):
        self._reizen()
        ende = time.monotonic() + self.lese_ms / 1000
        daten = b""
        while len(daten) < anzahl:
            stueck = self.sim.read(anzahl - len(daten), max(0.0, ende - time.monotonic()))
            if not stueck:
                break
            daten += stueck
        return daten

    def close(self):
        self.offen = False


def fake_ftd2xx(geraet: FakeGeraet) -> types.ModuleType:
    modul = types.ModuleType("ftd2xx")

    class DeviceError(Exception):
        pass

    def oeffnen(index=0, update=True):
        if index != 0:
            raise DeviceError("DEVICE_NOT_FOUND")
        return geraet

    def oeffnen_ex(seriennummer, flags=1, update=True):
        if seriennummer != SERIENNUMMER:
            raise DeviceError("DEVICE_NOT_FOUND")
        return geraet

    modul.DeviceError = DeviceError
    modul.open = oeffnen
    modul.openEx = oeffnen_ex
    modul.createDeviceInfoList = lambda: 1
    modul.getDeviceInfoDetail = lambda index=0, update=True: {
        "index": index, "flags": 0, "type": 5, "id": 0x04036001, "location": 0,
        "serial": SERIENNUMMER, "description": b"FT232R USB UART", "handle": None}
    return modul


class D2xx(unittest.TestCase):
    def setUp(self):
        self.geraet = FakeGeraet()
        self._module = mock.patch.dict(sys.modules, {"ftd2xx": fake_ftd2xx(self.geraet)})
        self._module.start()
        self._bitzeit = mock.patch.object(D2xxPort, "BIT_TIME", 0.002)
        self._bitzeit.start()

    def tearDown(self):
        self._bitzeit.stop()
        self._module.stop()

    def verbinden(self, url="d2xx:0", reizung="break", adresse=0x01):
        kabel = port.kabel_oeffnen(url, reizung)
        self.assertIsInstance(kabel, D2xxPort)
        proto = KW1281(KLine(kabel), SCHNELL)
        return kabel, proto, proto.connect(adresse, (10400, 9600))

    def test_ganze_kette_ueber_den_treiber(self):
        kabel, proto, v = self.verbinden()
        self.assertEqual(self.geraet.einstellungen["latenz"], 1)
        self.assertEqual(self.geraet.einstellungen["format"], (8, 0, 0))
        self.assertEqual(self.geraet.reizungen, [0x01])
        self.assertEqual(v.teilenummer, "SIM906032")
        self.assertIs(v.echo, True)
        self.assertEqual(len(proto.fehler_lesen()), 2)
        werte = proto.gruppe_lesen(4)
        self.assertEqual(werte[1].einheit, "V")
        proto.trennen()
        kabel.close()
        self.assertFalse(self.geraet.offen)

    def test_fast_init_ueber_den_treiber(self):
        self.geraet = FakeGeraet(kwp2000_motor=True)
        with mock.patch.dict(sys.modules, {"ftd2xx": fake_ftd2xx(self.geraet)}):
            kabel = port.kabel_oeffnen("d2xx:0")
            proto = KW1281(KLine(kabel), SCHNELL)
            v = proto.connect(0x01, (10400,), fast_init=True)
        self.assertEqual(self.geraet.fast_inits, 1)
        self.assertEqual(self.geraet.reizungen, [], "keine 5-Baud-Reizung nötig")
        self.assertEqual((v.protokoll, v.fast_init, v.kopf), ("KWP2000", True, 0x10))
        self.assertEqual(len(proto.fehler_lesen()), 2)
        proto.trennen()

    def test_fast_init_per_bitbang(self):
        self.geraet = FakeGeraet(kwp2000_motor=True)
        with mock.patch.dict(sys.modules, {"ftd2xx": fake_ftd2xx(self.geraet)}):
            kabel = port.kabel_oeffnen("d2xx:0", "bitbang")
            v = KW1281(KLine(kabel), SCHNELL).connect(0x01, (10400,), fast_init=True)
        self.assertEqual((self.geraet.fast_inits, v.fast_init), (1, True))
        self.assertEqual(self.geraet.einstellungen["baud"], 10400)

    def test_seriennummer_und_9600_baud(self):
        _, _, v = self.verbinden(f"d2xx:{SERIENNUMMER.decode()}", adresse=0x03)
        self.assertEqual((v.adresse, v.baud), (0x03, 9600))

    def test_bitbang(self):
        _, _, v = self.verbinden(reizung="bitbang", adresse=0x17)
        self.assertEqual(self.geraet.reizungen, [0x17])
        self.assertEqual(self.geraet.einstellungen["baud"], 10400)
        self.assertEqual(v.adresse, 0x17)

    def test_reizungs_bits(self):
        kabel = port.kabel_oeffnen("d2xx:0")
        kabel.send_5baud(0x25)
        self.assertEqual(self.geraet.reizung, 0x25)
        self.assertEqual(bits_5baud(0x25)[0], 0)

    def test_lesen_ohne_daten_wartet_nur_bis_zum_timeout(self):
        kabel = port.kabel_oeffnen("d2xx:0")
        beginn = time.monotonic()
        self.assertEqual(kabel.read(8, 0.05), b"")
        self.assertLess(time.monotonic() - beginn, 0.5)

    def test_unbekannte_seriennummer(self):
        with self.assertRaises(PortError) as fall:
            port.kabel_oeffnen("d2xx:XYZ")
        self.assertIn("d2xx:XYZ", str(fall.exception))

    def test_kabel_suchen_unter_windows(self):
        with mock.patch.object(port, "WINDOWS", True):
            self.assertEqual(port.standard_url(), "d2xx:0")
            self.assertEqual(port.list_ftdi_devices(), [("d2xx:A50285BI", "FT232R USB UART")])
            self.assertIn("FTDI-Treiber", port.einrichtungs_hinweis())
        with mock.patch.object(port, "WINDOWS", False):
            self.assertEqual(port.standard_url(), "ftdi:///1")


class OhneTreiber(unittest.TestCase):
    def test_paket_fehlt(self):
        with mock.patch.dict(sys.modules, {"ftd2xx": None}):
            with self.assertRaises(PortError) as fall:
                port.kabel_oeffnen("d2xx:0")
        self.assertIn("ftd2xx", str(fall.exception))

    def test_unbekannte_kabel_adresse(self):
        with self.assertRaises(PortError):
            port.kabel_oeffnen("COM3")


class Windowsdetails(unittest.TestCase):
    def test_einstellungsordner(self):
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {"APPDATA": r"C:\Users\Test\AppData\Roaming"}):
            self.assertEqual(pfade._konfig_ordner(),
                             Path(r"C:\Users\Test\AppData\Roaming") / "vagdiag")
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(pfade._konfig_ordner(), Path.home() / ".config" / "vagdiag")

    def test_csv_mit_bom_fuer_excel(self):
        with tempfile.TemporaryDirectory() as ordner:
            a = CsvAufzeichnung(Path(ordner) / "test.csv")
            a.ereignis("Kühlmitteltemperatur")
            a.schliessen()
            self.assertTrue((Path(ordner) / "test.csv").read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_ausgabe_ohne_unicode_stuerzt_nicht_ab(self):
        roh = io.BytesIO()
        strom = io.TextIOWrapper(roh, encoding="cp1252")
        with mock.patch.object(sys, "stdout", strom):
            cli._ausgabe_absichern()
            print("→ Ereignis markiert")
            strom.flush()
        self.assertEqual(roh.getvalue().replace(b"\r\n", b"\n"), b"? Ereignis markiert\n")


class Windowsskripte(unittest.TestCase):
    ORDNER = Path(__file__).resolve().parent.parent

    def test_batchdateien_ascii_und_crlf(self):
        for name in ("installieren.bat", "vagdiag.bat", "vagdiag-cli.bat"):
            daten = (self.ORDNER / name).read_bytes()
            self.assertTrue(all(b < 128 for b in daten), name)
            self.assertEqual(daten.count(b"\n"), daten.count(b"\r\n"), name)

    def test_pakete_je_betriebssystem(self):
        zeilen = (self.ORDNER / "requirements.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn('ftd2xx>=1.3.1; sys_platform == "win32"', zeilen)
        self.assertIn('pyftdi>=0.55; sys_platform != "win32"', zeilen)


if __name__ == "__main__":
    unittest.main()

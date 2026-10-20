"""Zugriff auf das KKL-Kabel (FTDI FT232R/FT232RL).

Zwei Wege, gewählt über die Kabel-Adresse:

  ftdi:///1   Linux (und macOS): pyftdi spricht den Chip direkt über libusb an.
              Die 5-Baud-Reizung lässt sich so exakt per Break-Signal erzeugen,
              was über /dev/ttyUSB0 nicht sauber geht. Solange das Programm
              läuft, verschwindet /dev/ttyUSB0 – das ist normal.
  d2xx:0      Windows: über den FTDI-Treiber (D2XX, Paket ftd2xx), den Windows
              beim Einstecken selbst installiert. Statt 0 (erstes Kabel) geht
              auch die Seriennummer des Kabels, z. B. d2xx:A50285BI.
"""

from __future__ import annotations

import logging
import sys
import time

from .sprache import t

log = logging.getLogger("vagdiag.port")


class PortError(Exception):
    """Problem mit dem Interface (nicht gefunden, keine Rechte, USB-Fehler)."""


class RawPort:
    """Schnittstelle, die die K-Leitungs-Schicht von einem Interface erwartet."""

    description = "?"

    def set_baudrate(self, baud: int) -> int:
        raise NotImplementedError

    def send_5baud(self, address: int) -> None:
        """Adresse mit 5 Baud senden (7 Datenbits, ungerade Parität)."""
        raise NotImplementedError

    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def read(self, max_bytes: int, timeout: float) -> bytes:
        """Sobald mindestens ein Byte da ist, zurückgeben; nach timeout b''."""
        raise NotImplementedError

    def purge_rx(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


def address_byte_7o1(address: int) -> int:
    """Adresse als 7 Datenbits plus ungerades Paritätsbit."""
    data = address & 0x7F
    parity = 0 if bin(data).count("1") % 2 == 1 else 1
    return data | (parity << 7)


def bits_5baud(address: int) -> list[int]:
    """Bitfolge der Reizung: Startbit, 8 Bits (LSB zuerst), Stoppbit."""
    byte = address_byte_7o1(address)
    return [0] + [(byte >> i) & 1 for i in range(8)] + [1]


def _sleep_until(deadline: float) -> None:
    while True:
        rest = deadline - time.perf_counter()
        if rest <= 0:
            return
        time.sleep(min(rest, 0.01))


WINDOWS = sys.platform == "win32"


def standard_url() -> str:
    """Kabel-Adresse für das erste FTDI-Kabel auf diesem Betriebssystem."""
    return "d2xx:0" if WINDOWS else "ftdi:///1"


def einrichtungs_hinweis() -> str:
    if WINDOWS:
        return t("Ist der FTDI-Treiber installiert (README)?")
    return t("Ist die udev-Regel eingerichtet (README)?")


def kabel_oeffnen(url: str | None, reizung: str = "break") -> "RawPort":
    """Kabel nach Adresse öffnen: ftdi:… über pyftdi, d2xx:… über den FTDI-Treiber."""
    url = (url or "").strip() or standard_url()
    if url.lower().startswith("d2xx:"):
        return D2xxPort(url, reizung)
    if url.lower().startswith("ftdi:"):
        return FtdiPort(url, reizung)
    raise PortError(t("Unbekannte Kabel-Adresse „{url}“ – erwartet z. B. ftdi:///1 (Linux) "
                      "oder d2xx:0 (Windows).", url=url))


def list_ftdi_devices() -> list[tuple[str, str]]:
    """Angeschlossene FTDI-Geräte als (Kabel-Adresse, Beschreibung)."""
    if WINDOWS:
        return _d2xx_geraete()
    try:
        from pyftdi.ftdi import Ftdi
        from pyftdi.usbtools import UsbTools
    except ImportError as exc:
        raise PortError(t("pyftdi ist nicht installiert (siehe README)")) from exc
    try:
        devices = Ftdi.list_devices()
    except Exception as exc:  # libusb fehlt, keine Rechte …
        raise PortError(t("USB-Geräte konnten nicht gelesen werden: {fehler}",
                          fehler=exc)) from exc
    return UsbTools.build_dev_strings("ftdi", Ftdi.VENDOR_IDS,
                                      Ftdi.PRODUCT_IDS, devices)


class FtdiPort(RawPort):
    """KKL-Kabel mit FT232RL (oder kompatiblem Klon).

    reizung="break":   TXD per Break-Signal auf Low ziehen (Standard).
    reizung="bitbang": TXD im Bitbang-Modus direkt schalten – Ausweichweg für
                       Klon-Chips, die den Break nicht sauber umsetzen.
    """

    BIT_TIME = 0.2  # 5 Baud

    def __init__(self, url: str = "ftdi:///1", reizung: str = "break"):
        if reizung not in ("break", "bitbang"):
            raise ValueError(t("reizung muss 'break' oder 'bitbang' sein"))
        self.reizung = reizung
        self._baud = 10400
        try:
            from pyftdi.ftdi import Ftdi
        except ImportError as exc:
            raise PortError(t("pyftdi ist nicht installiert (siehe README)")) from exc
        # Der Break bei der Reizung erzeugt im FTDI-Status Fehlerbits, die
        # pyftdi sonst als „FTDI error“ meldet. Das ist hier normal.
        logging.getLogger("pyftdi").setLevel(logging.CRITICAL)
        self._ftdi = Ftdi()
        self.url = url
        try:
            self._ftdi.open_from_url(url)
        except Exception as exc:
            raise PortError(t(
                "KKL-Kabel konnte nicht geöffnet werden ({url}): {fehler}. Steckt das Kabel? "
                "udev-Regel eingerichtet (README)?", url=url, fehler=exc)) from exc
        try:
            self._ftdi.set_line_property(8, 1, "N")
            self._ftdi.set_flowctrl("")
            self._ftdi.set_latency_timer(1)
            self._ftdi.set_baudrate(10400)
            self._ftdi.purge_buffers()
        except Exception as exc:
            self.close()
            raise PortError(t("KKL-Kabel ließ sich nicht einstellen: {fehler}",
                              fehler=exc)) from exc
        self.description = f"FTDI {url}" + (" " + t("(Reizung per Bitbang)")
                                            if reizung == "bitbang" else "")
        log.info(t("Interface geöffnet: %s, Reizung per %s"), url, reizung)

    def set_baudrate(self, baud: int) -> int:
        try:
            real = self._ftdi.set_baudrate(baud)
        except Exception as exc:
            raise PortError(t("Baudrate {baud} nicht einstellbar: {fehler}", baud=baud,
                              fehler=exc)) from exc
        self._baud = baud
        return real

    def send_5baud(self, address: int) -> None:
        if self.reizung == "bitbang":
            self._send_5baud_bitbang(address)
        else:
            self._send_5baud_break(address)

    def _send_5baud_bitbang(self, address: int) -> None:
        from pyftdi.ftdi import Ftdi
        bits = bits_5baud(address)
        try:
            self._ftdi.set_bitmode(0x01, Ftdi.BitMode.BITBANG)  # D0 = TXD als Ausgang
            self._ftdi.write_data(b"\x01")                      # Ruhepegel high
            time.sleep(0.01)
            start = time.perf_counter()
            for i, bit in enumerate(bits):
                self._ftdi.write_data(b"\x01" if bit else b"\x00")
                if i == len(bits) - 1:
                    break
                _sleep_until(start + (i + 1) * self.BIT_TIME)
            # zurück in den UART-Betrieb, solange das Stoppbit läuft
            self._ftdi.set_bitmode(0x00, Ftdi.BitMode.RESET)
            self._ftdi.set_line_property(8, 1, "N")
            self._ftdi.set_baudrate(self._baud)
            self._nach_reizung_leeren()
        except Exception as exc:
            try:
                self._ftdi.set_bitmode(0x00, Ftdi.BitMode.RESET)
            except Exception:
                pass
            raise PortError(t("5-Baud-Reizung (Bitbang) fehlgeschlagen: {fehler}",
                              fehler=exc)) from exc

    def _nach_reizung_leeren(self) -> None:
        """Reste der Reizung verwerfen. Das Stoppbit dauert 200 ms, und das
        Steuergerät antwortet frühestens 20 ms danach – zweimal Leeren mit
        kurzer Pause ist also gefahrlos und fängt nachlaufende USB-Pakete ab.

        purge_buffers() statt purge_rx_buffer(): Die FTDI-Benennung ist aus
        Chip-Sicht; empfangene Leitungsdaten liegen im „TX-Puffer“ des Chips
        (Richtung Host). purge_buffers() leert beide Puffer plus pyftdis
        eigenen Lesepuffer."""
        self._ftdi.purge_buffers()
        time.sleep(0.02)
        self._ftdi.purge_buffers()

    def _send_5baud_break(self, address: int) -> None:
        bits = bits_5baud(address)
        try:
            self._ftdi.purge_buffers()
            start = time.perf_counter()
            for i, bit in enumerate(bits):
                self._ftdi.set_break(bit == 0)
                if i == len(bits) - 1:
                    break  # Stoppbit läuft, Steuergerät antwortet gleich
                _sleep_until(start + (i + 1) * self.BIT_TIME)
            # Während des Breaks empfängt das Kabel sein eigenes Low-Signal
            # als Müll-Bytes. Die werden hier verworfen.
            self._nach_reizung_leeren()
        except Exception as exc:
            try:
                self._ftdi.set_break(False)
            except Exception:
                pass
            raise PortError(t("5-Baud-Reizung fehlgeschlagen: {fehler}", fehler=exc)) from exc

    def write(self, data: bytes) -> None:
        try:
            self._ftdi.write_data(data)
        except Exception as exc:
            raise PortError(t("Schreiben auf das Kabel fehlgeschlagen: {fehler}",
                              fehler=exc)) from exc

    def read(self, max_bytes: int, timeout: float) -> bytes:
        deadline = time.perf_counter() + timeout
        while True:
            try:
                chunk = self._ftdi.read_data_bytes(max_bytes, attempt=1)
            except Exception as exc:
                raise PortError(t("Lesen vom Kabel fehlgeschlagen: {fehler}",
                                  fehler=exc)) from exc
            if chunk:
                return bytes(chunk)
            if time.perf_counter() >= deadline:
                return b""

    def purge_rx(self) -> None:
        try:
            self._ftdi.purge_buffers()
        except Exception as exc:
            raise PortError(t("Empfangspuffer ließ sich nicht leeren: {fehler}",
                              fehler=exc)) from exc

    def close(self) -> None:
        try:
            self._ftdi.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Windows: FTDI-Treiber (D2XX)
# ---------------------------------------------------------------------------
def _ftd2xx():
    try:
        import ftd2xx
    except ImportError as exc:
        raise PortError(t("Das Paket ftd2xx ist nicht installiert (siehe README).")) from exc
    except OSError as exc:      # ftd2xx.dll fehlt
        raise PortError(t("Der FTDI-Treiber (ftd2xx.dll) fehlt: {fehler}. Treiber installieren "
                          "(README).", fehler=exc)) from exc
    return ftd2xx


def _text(wert) -> str:
    if isinstance(wert, bytes):
        return wert.decode("ascii", errors="replace").strip()
    return str(wert or "").strip()


def _d2xx_geraete() -> list[tuple[str, str]]:
    ftd2xx = _ftd2xx()
    try:
        anzahl = ftd2xx.createDeviceInfoList()
        geraete = []
        for i in range(anzahl):
            info = ftd2xx.getDeviceInfoDetail(i, False)
            seriennummer = _text(info.get("serial"))
            beschreibung = _text(info.get("description")) or "FTDI"
            url = f"d2xx:{seriennummer}" if seriennummer else f"d2xx:{i}"
            geraete.append((url, beschreibung))
        return geraete
    except Exception as exc:
        raise PortError(t("USB-Geräte konnten nicht gelesen werden: {fehler}",
                          fehler=exc)) from exc


class D2xxPort(RawPort):
    """KKL-Kabel über den FTDI-Treiber (D2XX) – der Weg unter Windows.

    Gleiches Verhalten wie FtdiPort: Latenz-Timer 1 ms, Reizung per Break
    (oder Bitbang als Ausweichweg für Klon-Chips)."""

    BIT_TIME = 0.2   # 5 Baud
    PURGE_RX_TX = 1 | 2

    def __init__(self, url: str = "d2xx:0", reizung: str = "break"):
        if reizung not in ("break", "bitbang"):
            raise ValueError(t("reizung muss 'break' oder 'bitbang' sein"))
        self.reizung = reizung
        self.url = url
        self._baud = 10400
        self._lese_ms: int | None = None
        ftd2xx = _ftd2xx()
        kennung = url.split(":", 1)[1].strip() if ":" in url else ""
        try:
            if not kennung:
                self._dev = ftd2xx.open(0)
            elif kennung.isdigit():
                self._dev = ftd2xx.open(int(kennung))
            else:
                self._dev = ftd2xx.openEx(kennung.encode("ascii"))   # Seriennummer
        except Exception as exc:
            raise PortError(t(
                "KKL-Kabel konnte nicht geöffnet werden ({url}): {fehler}. Steckt das Kabel? "
                "Ist es in einem anderen Programm geöffnet? Ist der FTDI-Treiber installiert?",
                url=url, fehler=exc)) from exc
        try:
            self._leitung_einstellen()
            self._dev.setLatencyTimer(1)
            self._dev.purge(self.PURGE_RX_TX)
        except Exception as exc:
            self.close()
            raise PortError(t("KKL-Kabel ließ sich nicht einstellen: {fehler}",
                              fehler=exc)) from exc
        self.description = f"FTDI D2XX {url}" + (" " + t("(Reizung per Bitbang)")
                                                 if reizung == "bitbang" else "")
        log.info(t("Interface geöffnet: %s, Reizung per %s"), url, reizung)

    def _leitung_einstellen(self) -> None:
        self._dev.setBaudRate(self._baud)
        self._dev.setDataCharacteristics(8, 0, 0)    # 8 Datenbits, 1 Stoppbit, keine Parität
        self._dev.setFlowControl(0, 0, 0)            # keine Flusssteuerung

    def set_baudrate(self, baud: int) -> int:
        try:
            self._dev.setBaudRate(baud)
        except Exception as exc:
            raise PortError(t("Baudrate {baud} nicht einstellbar: {fehler}", baud=baud,
                              fehler=exc)) from exc
        self._baud = baud
        return baud

    def send_5baud(self, address: int) -> None:
        if self.reizung == "bitbang":
            self._send_5baud_bitbang(address)
        else:
            self._send_5baud_break(address)

    def _nach_reizung_leeren(self) -> None:
        """Reste der Reizung verwerfen (siehe FtdiPort._nach_reizung_leeren)."""
        self._dev.purge(self.PURGE_RX_TX)
        time.sleep(0.02)
        self._dev.purge(self.PURGE_RX_TX)

    def _send_5baud_break(self, address: int) -> None:
        bits = bits_5baud(address)
        try:
            self._dev.purge(self.PURGE_RX_TX)
            start = time.perf_counter()
            for i, bit in enumerate(bits):
                if bit == 0:
                    self._dev.setBreakOn()
                else:
                    self._dev.setBreakOff()
                if i == len(bits) - 1:
                    break  # Stoppbit läuft, Steuergerät antwortet gleich
                _sleep_until(start + (i + 1) * self.BIT_TIME)
            self._nach_reizung_leeren()
        except Exception as exc:
            try:
                self._dev.setBreakOff()
            except Exception:
                pass
            raise PortError(t("5-Baud-Reizung fehlgeschlagen: {fehler}", fehler=exc)) from exc

    def _send_5baud_bitbang(self, address: int) -> None:
        bits = bits_5baud(address)
        try:
            self._dev.setBitMode(0x01, 0x01)     # asynchrones Bitbang, D0 = TXD als Ausgang
            self._dev.write(b"\x01")             # Ruhepegel high
            time.sleep(0.01)
            start = time.perf_counter()
            for i, bit in enumerate(bits):
                self._dev.write(b"\x01" if bit else b"\x00")
                if i == len(bits) - 1:
                    break
                _sleep_until(start + (i + 1) * self.BIT_TIME)
            # zurück in den UART-Betrieb, solange das Stoppbit läuft
            self._dev.setBitMode(0x00, 0x00)
            self._leitung_einstellen()
            self._nach_reizung_leeren()
        except Exception as exc:
            try:
                self._dev.setBitMode(0x00, 0x00)
            except Exception:
                pass
            raise PortError(t("5-Baud-Reizung (Bitbang) fehlgeschlagen: {fehler}",
                              fehler=exc)) from exc

    def write(self, data: bytes) -> None:
        try:
            self._dev.write(bytes(data))
        except Exception as exc:
            raise PortError(t("Schreiben auf das Kabel fehlgeschlagen: {fehler}",
                              fehler=exc)) from exc

    def read(self, max_bytes: int, timeout: float) -> bytes:
        try:
            vorhanden = self._dev.getQueueStatus()
            if not vorhanden:
                # auf das erste Byte wartet der Treiber selbst (meldet sich sofort)
                ms = max(1, int(timeout * 1000 + 0.999))
                if ms != self._lese_ms:
                    self._dev.setTimeouts(ms, 1000)
                    self._lese_ms = ms
                erstes = bytes(self._dev.read(1))
                if not erstes or max_bytes <= 1:
                    return erstes
                vorhanden = self._dev.getQueueStatus()
                rest = bytes(self._dev.read(min(vorhanden, max_bytes - 1))) if vorhanden else b""
                return erstes + rest
            return bytes(self._dev.read(min(vorhanden, max_bytes)))
        except Exception as exc:
            raise PortError(t("Lesen vom Kabel fehlgeschlagen: {fehler}", fehler=exc)) from exc

    def purge_rx(self) -> None:
        try:
            self._dev.purge(self.PURGE_RX_TX)
        except Exception as exc:
            raise PortError(t("Empfangspuffer ließ sich nicht leeren: {fehler}",
                              fehler=exc)) from exc

    def close(self) -> None:
        try:
            self._dev.close()
        except Exception:
            pass

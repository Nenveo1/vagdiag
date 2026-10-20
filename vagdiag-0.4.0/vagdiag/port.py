"""Zugriff auf das KKL-Kabel (FT232RL) über pyftdi.

pyftdi spricht den FTDI-Chip direkt über libusb an. Dadurch lässt sich die
5-Baud-Reizung exakt per Break-Signal erzeugen, was über /dev/ttyUSB0 unter
Linux nicht sauber geht. Solange das Programm läuft, verschwindet deshalb
/dev/ttyUSB0 – das ist normal.
"""

from __future__ import annotations

import logging
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


def list_ftdi_devices() -> list[tuple[str, str]]:
    """Angeschlossene FTDI-Geräte als (URL, Beschreibung)."""
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

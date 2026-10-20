"""Grafische Oberfläche (PySide6), angelehnt an den Ablauf von VCDS:
Interface wählen → Steuergerät öffnen → Funktionen.
"""

from __future__ import annotations

import csv
import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDockWidget, QFileDialog, QFormLayout,
                               QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from . import __version__, adressen, protokolldatei
from .kw1281 import DiagError, Nak, NotAvailable, UnsupportedProtocol, Verbindung
from .port import FtdiPort, PortError, list_ftdi_devices
from .session import DiagSession
from .sim import sim_port

log = logging.getLogger("vagdiag")

BAUD_AUSWAHL = [
    ("Automatisch (10400, dann 9600)", (10400, 9600)),
    ("10400", (10400,)),
    ("9600", (9600,)),
    ("4800", (4800,)),
    ("1200", (1200,)),
]

TAB_IDENT, TAB_FEHLER, TAB_MWB = 0, 1, 2


class Bruecke(QObject):
    """Leitet Ergebnisse aus dem Diagnose-Thread in den GUI-Thread."""
    fertig = Signal(str, object, object, object)   # Aufgabe, Kontext, Ergebnis, Fehler
    ereignis = Signal(str, object)
    logzeile = Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, bruecke: Bruecke):
        super().__init__(logging.DEBUG)
        self.bruecke = bruecke
        self.bloecke = False
        self.einzelbytes = False
        self.setFormatter(protokolldatei.RelativeZeit())

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.INFO:
            if record.name == "vagdiag.bytes":
                if not self.einzelbytes:
                    return
            elif not self.bloecke:
                return
        try:
            self.bruecke.logzeile.emit(self.format(record))
        except RuntimeError:
            pass  # Fenster bereits geschlossen


class Hauptfenster(QMainWindow):
    def __init__(self, logdatei: Path):
        super().__init__()
        self.logdatei = logdatei
        self.setWindowTitle(f"VAG-Diagnose {__version__} – KW1281 über KKL-Kabel")
        self.resize(1150, 780)

        self.bruecke = Bruecke()
        self.bruecke.fertig.connect(self._fertig)
        self.bruecke.ereignis.connect(self._ereignis)
        self.bruecke.logzeile.connect(self._logzeile)
        self._loghandler = QtLogHandler(self.bruecke)
        log.addHandler(self._loghandler)

        self.sitzung: DiagSession | None = None
        self._sitzung_schluessel = None
        self._verbindung: Verbindung | None = None
        self._beschaeftigt = False
        self._mwb_laeuft = False
        self._mwb_index = 0
        self._mwb_zaehler = 0
        self._mwb_zeit = time.monotonic()
        self._csv_datei = None
        self._csv = None

        self._baue_oberflaeche()
        self._aktualisiere_knoepfe()
        self.statusBar().showMessage("Bereit – Zündung an, Kabel stecken, Steuergerät wählen.")

    # ================================================================ Aufbau
    def _baue_oberflaeche(self) -> None:
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

        # ---------------- linke Spalte
        links = QWidget()
        lv = QVBoxLayout(links)

        gb_if = QGroupBox("Interface")
        form = QFormLayout(gb_if)
        self.cb_interface = QComboBox()
        self.cb_interface.addItems(["KKL-Kabel (FTDI)", "Simulator (ohne Auto)"])
        self.le_url = QLineEdit("ftdi:///1")
        self.le_url.setToolTip("pyftdi-URL. ftdi:///1 nimmt das einzige angeschlossene FTDI-Kabel.")
        self.cb_baud = QComboBox()
        for text, _ in BAUD_AUSWAHL:
            self.cb_baud.addItem(text)
        self.cb_reizung = QComboBox()
        self.cb_reizung.addItems(["Break (Standard)", "Bitbang (für Klon-Chips)"])
        self.cb_reizung.setToolTip("Wie die 5-Baud-Reizung erzeugt wird. Bitbang nur "
                                   "probieren, wenn mit Break nichts antwortet.")
        knoepfe_if = QHBoxLayout()
        self.bt_suchen = QPushButton("Kabel suchen")
        self.bt_kabeltest = QPushButton("Kabel testen")
        knoepfe_if.addWidget(self.bt_suchen)
        knoepfe_if.addWidget(self.bt_kabeltest)
        form.addRow("Interface:", self.cb_interface)
        form.addRow("Kabel-URL:", self.le_url)
        form.addRow("Baudrate:", self.cb_baud)
        form.addRow("Reizung:", self.cb_reizung)
        form.addRow(knoepfe_if)
        lv.addWidget(gb_if)

        gb_sg = QGroupBox("Steuergerät")
        sv = QVBoxLayout(gb_sg)
        self.lw_adressen = QListWidget()
        for adresse, name in adressen.ADRESSEN.items():
            eintrag = QListWidgetItem(f"{adresse:02X}   {name}")
            eintrag.setData(Qt.ItemDataRole.UserRole, adresse)
            self.lw_adressen.addItem(eintrag)
        self.lw_adressen.setCurrentRow(0)
        zeile_adr = QHBoxLayout()
        zeile_adr.addWidget(QLabel("oder Adresse (hex):"))
        self.le_adresse = QLineEdit()
        self.le_adresse.setPlaceholderText("z. B. 01")
        self.le_adresse.setMaxLength(2)
        zeile_adr.addWidget(self.le_adresse)
        zeile_kn = QHBoxLayout()
        self.bt_verbinden = QPushButton("Öffnen")
        self.bt_trennen = QPushButton("Schließen")
        zeile_kn.addWidget(self.bt_verbinden)
        zeile_kn.addWidget(self.bt_trennen)
        sv.addWidget(self.lw_adressen)
        sv.addLayout(zeile_adr)
        sv.addLayout(zeile_kn)
        lv.addWidget(gb_sg, 1)

        gb_fn = QGroupBox("Funktionen")
        fv = QVBoxLayout(gb_fn)
        self.bt_fehler = QPushButton("Fehlerspeicher lesen")
        self.bt_loeschen = QPushButton("Fehlerspeicher löschen …")
        self.bt_mwb = QPushButton("Messwertblöcke")
        for knopf in (self.bt_fehler, self.bt_loeschen, self.bt_mwb):
            fv.addWidget(knopf)
        lv.addWidget(gb_fn)

        # ---------------- Reiter rechts
        self.tabs = QTabWidget()

        self.tx_ident = QPlainTextEdit()
        self.tx_ident.setReadOnly(True)
        self.tx_ident.setFont(mono)
        self.tx_ident.setPlaceholderText("Noch kein Steuergerät geöffnet.")
        self.tabs.addTab(self.tx_ident, "Identifikation")

        seite_fehler = QWidget()
        fl = QVBoxLayout(seite_fehler)
        self.lb_fehler = QLabel("Noch nicht gelesen.")
        self.tb_fehler = QTableWidget(0, 5)
        self.tb_fehler.setHorizontalHeaderLabels(
            ["Code", "P-Code", "Beschreibung", "Fehlerart", "Sporadisch"])
        self.tb_fehler.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tb_fehler.verticalHeader().setVisible(False)
        self.tb_fehler.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        fl.addWidget(self.lb_fehler)
        fl.addWidget(self.tb_fehler)
        self.tabs.addTab(seite_fehler, "Fehlerspeicher")

        seite_mwb = QWidget()
        mv = QVBoxLayout(seite_mwb)
        gross = self.font()
        gross.setPointSize(max(gross.pointSize(), 9) + 4)
        gross.setBold(True)
        self._mwb_zeilen: list[tuple[QCheckBox, QSpinBox, list[QLabel]]] = []
        for i, start in enumerate((1, 2, 4)):
            gb = QGroupBox(f"Anzeige {i + 1}")
            gl = QGridLayout(gb)
            chk = QCheckBox("Gruppe")
            chk.setChecked(i == 0)
            sp = QSpinBox()
            sp.setRange(0, 255)
            sp.setValue(start)
            gl.addWidget(chk, 0, 0)
            gl.addWidget(sp, 0, 1)
            felder = []
            for feld in range(4):
                lb = QLabel("—")
                lb.setFont(gross)
                lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lb.setMinimumWidth(170)
                lb.setMinimumHeight(48)
                lb.setFrameShape(QFrame.Shape.StyledPanel)
                gl.addWidget(lb, 1, feld)
                felder.append(lb)
            self._mwb_zeilen.append((chk, sp, felder))
            mv.addWidget(gb)
        steuer = QHBoxLayout()
        self.bt_mwb_start = QPushButton("Start")
        self.chk_csv = QCheckBox("in CSV-Datei aufzeichnen")
        self.lb_rate = QLabel("")
        steuer.addWidget(self.bt_mwb_start)
        steuer.addWidget(self.chk_csv)
        steuer.addStretch(1)
        steuer.addWidget(self.lb_rate)
        mv.addLayout(steuer)
        hinweis = QLabel("Rohwerte (Formeltyp, a, b) stehen im Tooltip jedes Feldes.")
        hinweis.setEnabled(False)
        mv.addWidget(hinweis)
        mv.addStretch(1)
        self.tabs.addTab(seite_mwb, "Messwertblöcke")

        teiler = QSplitter(Qt.Orientation.Horizontal)
        teiler.addWidget(links)
        teiler.addWidget(self.tabs)
        teiler.setStretchFactor(1, 1)
        self.setCentralWidget(teiler)

        # ---------------- Protokoll unten
        dock = QDockWidget("Protokoll", self)
        dock.setObjectName("protokoll")
        dw = QWidget()
        dl = QVBoxLayout(dw)
        self.tx_log = QPlainTextEdit()
        self.tx_log.setReadOnly(True)
        self.tx_log.setFont(mono)
        self.tx_log.setMaximumBlockCount(5000)
        lz = QHBoxLayout()
        self.chk_bloecke = QCheckBox("Blöcke anzeigen")
        self.chk_bytes = QCheckBox("Einzelbytes anzeigen")
        lb_datei = QLabel(f"Vollständiges Protokoll: {self.logdatei}")
        lb_datei.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lz.addWidget(self.chk_bloecke)
        lz.addWidget(self.chk_bytes)
        lz.addStretch(1)
        lz.addWidget(lb_datei)
        dl.addWidget(self.tx_log)
        dl.addLayout(lz)
        dock.setWidget(dw)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

        # ---------------- Signale
        self.cb_interface.currentIndexChanged.connect(self._interface_geaendert)
        self.bt_suchen.clicked.connect(self._kabel_suchen)
        self.bt_kabeltest.clicked.connect(self._kabeltest)
        self.lw_adressen.itemDoubleClicked.connect(self._eintrag_doppelklick)
        self.le_adresse.returnPressed.connect(self._verbinden)
        self.bt_verbinden.clicked.connect(self._verbinden)
        self.bt_trennen.clicked.connect(self._trennen)
        self.bt_fehler.clicked.connect(self._fehler_lesen)
        self.bt_loeschen.clicked.connect(self._fehler_loeschen)
        self.bt_mwb.clicked.connect(self._zeige_mwb)
        self.bt_mwb_start.clicked.connect(self._mwb_umschalten)
        self.chk_bloecke.toggled.connect(self._log_bloecke)
        self.chk_bytes.toggled.connect(self._log_bytes)

    # ============================================================ Hilfen
    def _sitzung(self) -> DiagSession:
        reizung = "bitbang" if self.cb_reizung.currentIndex() == 1 else "break"
        schluessel = (self.cb_interface.currentIndex(), self.le_url.text().strip(), reizung)
        if self.sitzung is not None and schluessel != self._sitzung_schluessel:
            self.sitzung.schliessen()
            self.sitzung = None
        if self.sitzung is None:
            if schluessel[0] == 1:
                fabrik = sim_port
            else:
                url = schluessel[1] or "ftdi:///1"

                def fabrik(url=url, reizung=reizung):
                    return FtdiPort(url, reizung)
            self.sitzung = DiagSession(
                fabrik, ereignis=self._ereignis_aus_thread).start()
            self._sitzung_schluessel = schluessel
        return self.sitzung

    def _ereignis_aus_thread(self, art: str, daten: object) -> None:
        try:
            self.bruecke.ereignis.emit(art, daten)
        except RuntimeError:
            pass

    def _auftrag(self, aufgabe: str, future, kontext=None, beschaeftigt: bool = True) -> None:
        if beschaeftigt:
            self._beschaeftigt = True
            self._aktualisiere_knoepfe()

        def fertig(f):
            if f.cancelled():
                return
            fehler = f.exception()
            ergebnis = None if fehler else f.result()
            try:
                self.bruecke.fertig.emit(aufgabe, kontext, ergebnis, fehler)
            except RuntimeError:
                pass

        future.add_done_callback(fertig)

    def _bereit(self) -> bool:
        return (self.sitzung is not None and self._verbindung is not None
                and not self._beschaeftigt and not self._mwb_laeuft)

    def _zeige_fehler_dialog(self, titel: str, fehler: BaseException) -> None:
        text = str(fehler) or fehler.__class__.__name__
        if isinstance(fehler, UnsupportedProtocol):
            text += f"\n\nBitte schick mir die Protokolldatei:\n{self.logdatei}"
        elif isinstance(fehler, PortError):
            text += "\n\nHinweise zur Einrichtung (udev-Regel) stehen in der README."
        elif not isinstance(fehler, DiagError):
            log.error("Unerwarteter Fehler: %r", fehler, exc_info=fehler)
            text = (f"Unerwarteter Fehler ({fehler.__class__.__name__}): {fehler}\n\n"
                    f"Protokolldatei: {self.logdatei}")
        QMessageBox.warning(self, titel, text)

    def _aktualisiere_knoepfe(self) -> None:
        verbunden = self._verbindung is not None
        frei = not self._beschaeftigt
        mwb = self._mwb_laeuft
        ftdi = self.cb_interface.currentIndex() == 0
        self.cb_interface.setEnabled(frei and not verbunden)
        self.le_url.setEnabled(frei and not verbunden and ftdi)
        self.cb_reizung.setEnabled(frei and not verbunden and ftdi)
        self.bt_suchen.setEnabled(not verbunden and ftdi)
        self.bt_kabeltest.setEnabled(frei and not mwb)
        self.lw_adressen.setEnabled(frei and not mwb)
        self.le_adresse.setEnabled(frei and not mwb)
        self.bt_verbinden.setEnabled(frei and not mwb)
        self.bt_trennen.setEnabled(frei and verbunden)
        self.bt_fehler.setEnabled(frei and verbunden and not mwb)
        self.bt_loeschen.setEnabled(frei and verbunden and not mwb)
        self.bt_mwb.setEnabled(verbunden)
        self.bt_mwb_start.setEnabled((frei and verbunden) or mwb)

    # ============================================================ Interface
    def _interface_geaendert(self, _index: int) -> None:
        self._aktualisiere_knoepfe()

    def _kabel_suchen(self) -> None:
        try:
            geraete = list_ftdi_devices()
        except PortError as exc:
            QMessageBox.warning(self, "Kabel suchen", str(exc))
            return
        if not geraete:
            QMessageBox.information(
                self, "Kabel suchen",
                "Kein FTDI-Kabel gefunden.\n\nSteckt es? Ist die udev-Regel "
                "eingerichtet (README)?")
            return
        self.le_url.setText(geraete[0][0])
        liste = "\n".join(f"{url}  {beschreibung}" for url, beschreibung in geraete)
        QMessageBox.information(self, "Kabel suchen",
                                f"Gefunden:\n{liste}\n\nDas erste Kabel ist eingetragen.")

    def _kabeltest(self) -> None:
        if self._beschaeftigt or self._mwb_laeuft:
            return
        self._auftrag("kabeltest", self._sitzung().kabeltest())

    def _fertig_kabeltest(self, _kontext, ergebnis, fehler) -> None:
        if fehler:
            self._zeige_fehler_dialog("Kabeltest", fehler)
            return
        QMessageBox.information(
            self, "Kabeltest",
            f"Interface: {ergebnis['geraet']}\n"
            f"Echo: {'ja' if ergebnis['echo'] else 'nein'}\n\n{ergebnis['hinweis']}")

    # ============================================================ Verbindung
    def _gewaehlte_adresse(self) -> int | None:
        text = self.le_adresse.text().strip()
        if text:
            try:
                wert = int(text, 16)
            except ValueError:
                wert = -1
            if not 0 <= wert <= 0x7F:
                QMessageBox.warning(self, "Adresse",
                                    "Bitte eine Adresse von 00 bis 7F eingeben (hex), z. B. 01 oder 17.")
                return None
            return wert
        eintrag = self.lw_adressen.currentItem()
        return eintrag.data(Qt.ItemDataRole.UserRole) if eintrag else None

    def _eintrag_doppelklick(self, _eintrag) -> None:
        self.le_adresse.clear()
        self._verbinden()

    def _verbinden(self) -> None:
        if self._beschaeftigt or self._mwb_laeuft:
            return
        adresse = self._gewaehlte_adresse()
        if adresse is None:
            return
        bauds = BAUD_AUSWAHL[self.cb_baud.currentIndex()][1]
        self.statusBar().showMessage(
            f"Verbinde mit {adressen.text(adresse)} … (die Reizung dauert gut 2 Sekunden)")
        self._auftrag("verbinden", self._sitzung().verbinden(adresse, bauds), adresse)

    def _fertig_verbinden(self, adresse, verbindung, fehler) -> None:
        if fehler:
            self._verbindung = None
            self.statusBar().showMessage(f"Keine Verbindung zu {adressen.text(adresse)}")
            self._zeige_fehler_dialog("Verbindung fehlgeschlagen", fehler)
            return
        self._verbindung = verbindung
        self._zeige_ident(verbindung)
        self.tb_fehler.setRowCount(0)
        self.lb_fehler.setText("Noch nicht gelesen.")
        for _, _, felder in self._mwb_zeilen:
            for lb in felder:
                lb.setText("—")
                lb.setToolTip("")
        self.tabs.setCurrentIndex(TAB_IDENT)
        self.statusBar().showMessage(
            f"Verbunden: {adressen.text(verbindung.adresse)} – {verbindung.protokoll}, "
            f"{verbindung.baud} Baud, Kabel-Echo {'ja' if verbindung.echo else 'nein'}")

    def _zeige_ident(self, v: Verbindung) -> None:
        zeilen = [
            f"Adresse:      {adressen.text(v.adresse)}",
            f"Protokoll:    {v.protokoll} (Keyword {v.keyword})",
            f"Baudrate:     {v.baud}",
            f"Kabel-Echo:   {'ja' if v.echo else 'nein'}",
            "",
            f"Teilenummer:  {v.teilenummer}",
            f"Bauteil:      {v.bauteil}",
        ]
        for z in v.zusatzdaten:
            zeilen.append(f"Zusatzdaten:  {z}   (Codierung/Werkstattcode – Auswertung folgt)")
        self.tx_ident.setPlainText("\n".join(zeilen))

    def _trennen(self) -> None:
        self._mwb_stopp()
        if self.sitzung is not None and not self._beschaeftigt:
            self._auftrag("trennen", self.sitzung.trennen())

    def _fertig_trennen(self, _kontext, _ergebnis, fehler) -> None:
        self._verbindung = None
        self.statusBar().showMessage("Verbindung geschlossen.")

    def _ereignis(self, art: str, daten: object) -> None:
        if art == "getrennt":
            war_verbunden = self._verbindung is not None
            self._verbindung = None
            self._mwb_stopp()
            if war_verbunden:
                self.statusBar().showMessage(f"Getrennt: {daten}")
            self._aktualisiere_knoepfe()

    # ============================================================ Fehlerspeicher
    def _fehler_lesen(self) -> None:
        if not self._bereit():
            return
        self.statusBar().showMessage("Lese Fehlerspeicher …")
        self._auftrag("fehler", self.sitzung.fehler_lesen())

    def _fertig_fehler(self, _kontext, liste, fehler) -> None:
        if fehler:
            self._zeige_fehler_dialog("Fehlerspeicher", fehler)
            return
        self._zeige_fehlerliste(liste)
        self.tabs.setCurrentIndex(TAB_FEHLER)
        self.statusBar().showMessage("Fehlerspeicher gelesen.")

    def _zeige_fehlerliste(self, liste) -> None:
        self.tb_fehler.setRowCount(len(liste))
        for zeile, f in enumerate(liste):
            werte = [f.code_text, f.p_code or "", f.beschreibung, f.fehlerart_text,
                     "ja" if f.sporadisch else ""]
            for spalte, wert in enumerate(werte):
                self.tb_fehler.setItem(zeile, spalte, QTableWidgetItem(wert))
        self.tb_fehler.resizeColumnToContents(0)
        self.tb_fehler.resizeColumnToContents(1)
        self.tb_fehler.resizeColumnToContents(3)
        anzahl = f"{len(liste)} Fehler gespeichert" if liste else "Kein Fehler gespeichert"
        self.lb_fehler.setText(f"{anzahl} (gelesen um {time.strftime('%H:%M:%S')})")

    def _fehler_loeschen(self) -> None:
        if not self._bereit():
            return
        antwort = QMessageBox.question(
            self, "Fehlerspeicher löschen",
            f"Fehlerspeicher von {adressen.text(self._verbindung.adresse)} wirklich löschen?\n\n"
            "Dabei werden auch die Readiness-Codes zurückgesetzt (wichtig vor einer AU).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if antwort != QMessageBox.StandardButton.Yes:
            return
        self.statusBar().showMessage("Lösche Fehlerspeicher …")
        self._auftrag("loeschen", self.sitzung.fehler_loeschen())

    def _fertig_loeschen(self, _kontext, _rest, fehler) -> None:
        if fehler:
            self._zeige_fehler_dialog("Fehlerspeicher löschen", fehler)
            return
        self.statusBar().showMessage("Fehlerspeicher gelöscht – lese neu …")
        self._fehler_lesen()

    # ============================================================ Messwertblöcke
    def _zeige_mwb(self) -> None:
        self.tabs.setCurrentIndex(TAB_MWB)

    def _mwb_umschalten(self) -> None:
        if self._mwb_laeuft:
            self._mwb_stopp()
        else:
            self._mwb_start()

    def _mwb_start(self) -> None:
        if not self._bereit():
            return
        if not any(chk.isChecked() for chk, _, _ in self._mwb_zeilen):
            QMessageBox.information(self, "Messwertblöcke",
                                    "Bitte mindestens eine Gruppe aktivieren.")
            return
        if self.chk_csv.isChecked() and not self._csv_oeffnen():
            self.chk_csv.setChecked(False)
        self._mwb_laeuft = True
        self._mwb_index = 0
        self._mwb_zaehler = 0
        self._mwb_zeit = time.monotonic()
        self.bt_mwb_start.setText("Stopp")
        self.lb_rate.setText("")
        self._aktualisiere_knoepfe()
        self._mwb_naechste()

    def _csv_oeffnen(self) -> bool:
        vorschlag = str(Path.home() / time.strftime("messwerte-%Y%m%d-%H%M%S.csv"))
        pfad, _ = QFileDialog.getSaveFileName(self, "Messwerte aufzeichnen", vorschlag,
                                              "CSV-Dateien (*.csv)")
        if not pfad:
            return False
        try:
            self._csv_datei = open(pfad, "w", newline="", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "CSV-Datei", f"Datei nicht anlegbar: {exc}")
            return False
        self._csv = csv.writer(self._csv_datei, delimiter=";")
        self._csv.writerow(["Zeit", "Gruppe", "Feld 1", "Feld 2", "Feld 3", "Feld 4"])
        log.info("Messwerte werden aufgezeichnet: %s", pfad)
        return True

    def _mwb_stopp(self) -> None:
        self._mwb_laeuft = False
        self.bt_mwb_start.setText("Start")
        if self._csv_datei is not None:
            self._csv_datei.close()
            self._csv_datei = None
            self._csv = None
            log.info("Aufzeichnung beendet")
        self._aktualisiere_knoepfe()

    def _mwb_naechste(self) -> None:
        if not self._mwb_laeuft or self._verbindung is None:
            self._mwb_stopp()
            return
        aktiv = [(i, sp.value()) for i, (chk, sp, _) in enumerate(self._mwb_zeilen)
                 if chk.isChecked()]
        if not aktiv:
            self._mwb_stopp()
            return
        zeile, gruppe = aktiv[self._mwb_index % len(aktiv)]
        self._mwb_index += 1
        self._auftrag("mwb", self.sitzung.gruppe_lesen(gruppe), (zeile, gruppe),
                      beschaeftigt=False)

    def _fertig_mwb(self, kontext, werte, fehler) -> None:
        zeile, gruppe = kontext
        chk, _, felder = self._mwb_zeilen[zeile]
        if fehler:
            if isinstance(fehler, (NotAvailable, Nak)):
                felder[0].setText("nicht belegt")
                felder[0].setToolTip(str(fehler))
                for lb in felder[1:]:
                    lb.setText("—")
                chk.setChecked(False)
            else:
                self._mwb_stopp()
                self._zeige_fehler_dialog("Messwertblöcke", fehler)
                return
        else:
            for i, lb in enumerate(felder):
                if i < len(werte):
                    lb.setText(werte[i].text)
                    lb.setToolTip(werte[i].roh)
                else:
                    lb.setText("")
                    lb.setToolTip("")
            if self._csv is not None:
                self._csv.writerow([f"{time.time():.3f}", f"{gruppe:03d}"]
                                   + [w.text for w in werte])
            self._mwb_zaehler += 1
            dauer = time.monotonic() - self._mwb_zeit
            if dauer >= 1.0:
                self.lb_rate.setText(f"{self._mwb_zaehler / dauer:.1f} Abfragen/s")
                self._mwb_zaehler = 0
                self._mwb_zeit = time.monotonic()
        if self._mwb_laeuft:
            QTimer.singleShot(0, self._mwb_naechste)

    # ============================================================ Ergebnisse
    def _fertig(self, aufgabe: str, kontext, ergebnis, fehler) -> None:
        if aufgabe != "mwb":
            self._beschaeftigt = False
        getattr(self, f"_fertig_{aufgabe}")(kontext, ergebnis, fehler)
        self._aktualisiere_knoepfe()

    # ============================================================ Protokoll
    def _logzeile(self, zeile: str) -> None:
        self.tx_log.appendPlainText(zeile)

    def _log_bloecke(self, an: bool) -> None:
        self._loghandler.bloecke = an

    def _log_bytes(self, an: bool) -> None:
        self._loghandler.einzelbytes = an

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt-Name)
        self._mwb_stopp()
        log.removeHandler(self._loghandler)
        if self.sitzung is not None:
            self.sitzung.schliessen()
        super().closeEvent(event)


def main() -> None:
    logdatei = protokolldatei.einrichten()
    app = QApplication(sys.argv)
    app.setApplicationName("vagdiag")
    fenster = Hauptfenster(logdatei)
    fenster.show()
    sys.exit(app.exec())

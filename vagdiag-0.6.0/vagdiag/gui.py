"""Grafische Oberfläche (PySide6), angelehnt an den Ablauf von VCDS:
Interface wählen → Steuergerät öffnen → Funktionen.

Alle Texte laufen durch t() (siehe sprache.py). Wird die Sprache in den
Einstellungen umgestellt, baut sich das Fenster nach Rückfrage neu auf.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDialog, QDialogButtonBox, QDockWidget,
                               QFileDialog, QFormLayout, QFrame, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPlainTextEdit,
                               QPushButton, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import (__version__, adressen, airbag, beschriftung, einstellungen, ident,
               protokolldatei, sprache)
from .aufzeichnung import CsvAufzeichnung
from .fahrtenschreiber import FahrtPlan, _gruppenliste
from .kilometerstand import km_text
from .kw1281 import (Abgebrochen, Anpassung, DiagError, Nak, NotAvailable,
                     UnsupportedProtocol, Verbindung, kwp_ohne_anpassung)
from .messwerte import MinMax
from .port import (PortError, einrichtungs_hinweis, kabel_oeffnen, list_ftdi_devices,
                   standard_url)
from .session import DiagSession
from .sim import sim_port
from .sprache import N_, t

log = logging.getLogger("vagdiag")

BAUD_AUSWAHL = [
    (N_("Automatisch (gemerkte zuerst)"), (10400, 9600)),
    ("10400", (10400,)),
    ("9600", (9600,)),
    ("4800", (4800,)),
    ("1200", (1200,)),
]

TAB_IDENT, TAB_FEHLER, TAB_MWB, TAB_ANP, TAB_FAHRT = 0, 1, 2, 3, 4
KABEL, SIM, SIM_KWP2000 = 0, 1, 2          # Einträge der Interface-Auswahl
# Live-Anzeige des Fahrtenschreibers – interne (deutsche) Feldnamen
LIVE_WERTE = ["Motordrehzahl", N_("Tempo"), "Kühlmitteltemperatur", "Bordspannung",
              "Ansauglufttemperatur", "Tankinhalt", "Saugrohrdruck", "Bremslichtschalter"]
KOMBI = 0x17


def ordner_oeffnen(pfad: Path) -> None:
    pfad.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(pfad)))


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


class EinstellungenDialog(QDialog):
    def __init__(self, eltern: QWidget):
        super().__init__(eltern)
        self.setWindowTitle(t("Einstellungen"))
        self.resize(660, 300)
        werte = einstellungen.laden()
        form = QFormLayout(self)

        # zweisprachig, damit man auch zurückfindet
        self.cb_sprache = QComboBox()
        for code, name in sprache.SPRACHEN.items():
            self.cb_sprache.addItem(name, code)
        codes = list(sprache.SPRACHEN)
        self.cb_sprache.setCurrentIndex(codes.index(werte["sprache"])
                                        if werte["sprache"] in codes else 0)
        form.addRow("Sprache / Language:", self.cb_sprache)

        self.le_log = QLineEdit(werte["log_ordner"])
        self.le_csv = QLineEdit(werte["csv_ordner"])
        form.addRow(t("Ordner für Protokolle:"), self._ordnerzeile(self.le_log))
        form.addRow(t("Ordner für Messwerte (CSV):"), self._ordnerzeile(self.le_csv))
        self.chk_log = QCheckBox(t("Protokolldatei schreiben (für die Fehlersuche)"))
        self.chk_log.setChecked(bool(werte["log_datei"]))
        self.chk_log.setToolTip(t("Aus: Das Protokoll bleibt nur im Speicher und lässt sich bei "
                                  "Bedarf über Datei → Protokoll speichern … sichern."))
        self.chk_csv = QCheckBox(t("Messwertblöcke automatisch als CSV aufzeichnen"))
        self.chk_csv.setChecked(bool(werte["csv_automatisch"]))
        self.chk_csv.setToolTip(t("Voreinstellung für „aufzeichnen (CSV)“ im Reiter "
                                  "Messwertblöcke. Der Fahrtenschreiber schreibt immer."))
        self.chk_neu = QCheckBox(t("Bei Verbindungsabbruch während der Messung neu verbinden"))
        self.chk_neu.setChecked(bool(werte["neu_verbinden"]))
        form.addRow(self.chk_log)
        form.addRow(self.chk_csv)
        form.addRow(self.chk_neu)
        knoepfe = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def sprache_code(self) -> str:
        return str(self.cb_sprache.currentData() or sprache.STANDARD)

    def _ordnerzeile(self, feld: QLineEdit) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(feld, 1)
        waehlen = QPushButton(t("Wählen …"))
        oeffnen = QPushButton(t("Öffnen"))
        h.addWidget(waehlen)
        h.addWidget(oeffnen)

        def wahl():
            pfad = QFileDialog.getExistingDirectory(self, t("Ordner wählen"), feld.text())
            if pfad:
                feld.setText(pfad)
        waehlen.clicked.connect(wahl)
        oeffnen.clicked.connect(lambda: ordner_oeffnen(Path(feld.text()).expanduser()))
        return w


class Hauptfenster(QMainWindow):
    def __init__(self, logdatei: Path | None = None):
        super().__init__()
        self.logdatei = logdatei
        self.neustart = False          # True: main() baut das Fenster neu auf (Sprache)
        self.resize(1180, 820)

        self.bruecke = Bruecke()
        self.bruecke.fertig.connect(self._fertig)
        self.bruecke.ereignis.connect(self._ereignis)
        self.bruecke.logzeile.connect(self._logzeile)
        self._loghandler = QtLogHandler(self.bruecke)
        log.addHandler(self._loghandler)

        self.sitzung: DiagSession | None = None
        self._sitzung_schluessel = None
        self._sitzung_sim = False
        self._verbindung: Verbindung | None = None
        self._adresse: int | None = None
        self._beschaeftigt = False
        self._mwb_laeuft = False
        self._mwb_index = 0
        self._mwb_zaehler = 0
        self._mwb_zeit = time.monotonic()
        self._csv: CsvAufzeichnung | None = None
        self._minmax = MinMax()
        self._suche_laeuft = False
        self._suche_ergebnis: list[str] = []
        self._anp_suche_laeuft = False
        self._anp_zeilen: dict[int, int] = {}
        self._fahrt_laeuft = False
        self._fahrt_endet = False

        self._baue_menue()
        self._baue_oberflaeche()
        self._interface_geaendert(0)
        self.statusBar().showMessage(
            t("Bereit – Zündung an, Kabel stecken, Steuergerät wählen."))

    # ================================================================ Aufbau
    def _baue_menue(self) -> None:
        menue = self.menuBar().addMenu(t("&Datei"))
        for text, funktion in (
                (N_("Einstellungen …"), self._einstellungen),
                (N_("Protokoll speichern …"), self._protokoll_speichern),
                (N_("Ordner der Protokolle öffnen"),
                 lambda: ordner_oeffnen(einstellungen.ordner("log_ordner"))),
                (N_("Ordner der Messwerte öffnen"),
                 lambda: ordner_oeffnen(einstellungen.ordner("csv_ordner"))),
                (None, None),
                (N_("Beenden"), self.close)):
            if text is None:
                menue.addSeparator()
                continue
            aktion = QAction(t(text), self)
            aktion.triggered.connect(funktion)
            menue.addAction(aktion)

    def _baue_oberflaeche(self) -> None:
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

        # ---------------- linke Spalte
        links = QWidget()
        lv = QVBoxLayout(links)

        self.lb_sim = QLabel(t("SIMULATOR – keine echten Fahrzeugdaten"))
        self.lb_sim.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lb_sim.setStyleSheet("background:#c62828; color:white; font-weight:bold; "
                                  "padding:6px; border-radius:4px;")
        lv.addWidget(self.lb_sim)

        gb_if = QGroupBox(t("Interface"))
        form = QFormLayout(gb_if)
        self.cb_interface = QComboBox()
        self.cb_interface.addItems([t("KKL-Kabel (FTDI)"), t("Simulator (ohne Auto)"),
                                    t("Simulator mit KWP2000-Motor (ohne Auto)")])
        self.le_url = QLineEdit(standard_url())
        self.le_url.setToolTip(t("Kabel-Adresse: ftdi:///1 (Linux) bzw. d2xx:0 (Windows) nimmt "
                                 "das erste angeschlossene FTDI-Kabel. „Kabel suchen“ trägt "
                                 "das gefundene ein."))
        self.cb_baud = QComboBox()
        for text, _ in BAUD_AUSWAHL:
            self.cb_baud.addItem(t(text))
        self.cb_reizung = QComboBox()
        self.cb_reizung.addItems([t("Break (Standard)"), t("Bitbang (für Klon-Chips)")])
        self.cb_reizung.setToolTip(t("Wie die 5-Baud-Reizung erzeugt wird. Bitbang nur "
                                     "probieren, wenn mit Break nichts antwortet."))
        self.chk_fast_init = QCheckBox(t("Motor: zuerst Fast-Init (KWP2000)"))
        self.chk_fast_init.setChecked(bool(einstellungen.laden()["fast_init"]))
        self.chk_fast_init.setToolTip(t(
            "Nur für Motorsteuergeräte mit KWP2000, die auf die normale 5-Baud-Reizung nicht "
            "antworten (z. B. manche späteren Dieselsteuergeräte). Kommt keine Antwort, folgt "
            "die normale Reizung. Bei älteren Motoren nicht nötig. Experimentell."))
        self.chk_fast_init.toggled.connect(lambda an: einstellungen.speichern(fast_init=an))
        knoepfe_if = QHBoxLayout()
        self.bt_suchen = QPushButton(t("Kabel suchen"))
        self.bt_kabeltest = QPushButton(t("Kabel testen"))
        knoepfe_if.addWidget(self.bt_suchen)
        knoepfe_if.addWidget(self.bt_kabeltest)
        form.addRow(t("Interface:"), self.cb_interface)
        form.addRow(t("Kabel-URL:"), self.le_url)
        form.addRow(t("Baudrate:"), self.cb_baud)
        form.addRow(t("Reizung:"), self.cb_reizung)
        form.addRow(self.chk_fast_init)
        form.addRow(knoepfe_if)
        lv.addWidget(gb_if)

        gb_sg = QGroupBox(t("Steuergerät"))
        sv = QVBoxLayout(gb_sg)
        self.lw_adressen = QListWidget()
        for adresse in adressen.ADRESSEN:
            eintrag = QListWidgetItem(f"{adresse:02X}   {adressen.name(adresse)}")
            eintrag.setData(Qt.ItemDataRole.UserRole, adresse)
            self.lw_adressen.addItem(eintrag)
        self.lw_adressen.setCurrentRow(0)
        zeile_adr = QHBoxLayout()
        zeile_adr.addWidget(QLabel(t("oder Adresse (hex):")))
        self.le_adresse = QLineEdit()
        self.le_adresse.setPlaceholderText(t("z. B. 01"))
        self.le_adresse.setMaxLength(2)
        zeile_adr.addWidget(self.le_adresse)
        zeile_kn = QHBoxLayout()
        self.bt_verbinden = QPushButton(t("Öffnen"))
        self.bt_trennen = QPushButton(t("Schließen"))
        zeile_kn.addWidget(self.bt_verbinden)
        zeile_kn.addWidget(self.bt_trennen)
        sv.addWidget(self.lw_adressen)
        sv.addLayout(zeile_adr)
        sv.addLayout(zeile_kn)
        lv.addWidget(gb_sg, 1)

        gb_fn = QGroupBox(t("Funktionen"))
        fv = QVBoxLayout(gb_fn)
        self.bt_fehler = QPushButton(t("Fehlerspeicher lesen"))
        self.bt_loeschen = QPushButton(t("Fehlerspeicher löschen …"))
        self.bt_mwb = QPushButton(t("Messwertblöcke"))
        self.bt_anp = QPushButton(t("Anpassung (nur lesen)"))
        self.bt_km = QPushButton(t("Kilometerstand (Kombi)"))
        self.bt_fahrtenschreiber = QPushButton(t("Fahrtenschreiber"))
        self.bt_km.setToolTip(t("Nur beim Kombiinstrument (Adresse 17): liest Messwertgruppe 002 "
                                "und, falls dort kein Wert steht, Anpassungskanal 09."))
        for knopf in (self.bt_fehler, self.bt_loeschen, self.bt_mwb, self.bt_anp, self.bt_km,
                      self.bt_fahrtenschreiber):
            fv.addWidget(knopf)
        lv.addWidget(gb_fn)

        # ---------------- Reiter rechts
        self.tabs = QTabWidget()

        self.tx_ident = QPlainTextEdit()
        self.tx_ident.setReadOnly(True)
        self.tx_ident.setFont(mono)
        self.tx_ident.setPlaceholderText(t("Noch kein Steuergerät geöffnet."))
        self.tabs.addTab(self.tx_ident, t("Identifikation"))

        seite_fehler = QWidget()
        fl = QVBoxLayout(seite_fehler)
        self.lb_fehler = QLabel(t("Noch nicht gelesen."))
        self.tb_fehler = QTableWidget(0, 5)
        self.tb_fehler.setHorizontalHeaderLabels(
            [t("Code"), t("P-Code"), t("Beschreibung"), t("Fehlerart"), t("Sporadisch")])
        self.tb_fehler.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tb_fehler.verticalHeader().setVisible(False)
        self.tb_fehler.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        fl.addWidget(self.lb_fehler)
        fl.addWidget(self.tb_fehler)
        self.tabs.addTab(seite_fehler, t("Fehlerspeicher"))

        self.tabs.addTab(self._baue_messwertseite(), t("Messwertblöcke"))
        self.tabs.addTab(self._baue_anpassungsseite(), t("Anpassung"))
        self.tabs.addTab(self._baue_fahrtseite(), t("Fahrtenschreiber"))

        teiler = QSplitter(Qt.Orientation.Horizontal)
        teiler.addWidget(links)
        teiler.addWidget(self.tabs)
        teiler.setStretchFactor(1, 1)
        self.setCentralWidget(teiler)

        # ---------------- Protokoll unten
        dock = QDockWidget(t("Protokoll"), self)
        dock.setObjectName("protokoll")
        dw = QWidget()
        dl = QVBoxLayout(dw)
        self.tx_log = QPlainTextEdit()
        self.tx_log.setReadOnly(True)
        self.tx_log.setFont(mono)
        self.tx_log.setMaximumBlockCount(5000)
        lz = QHBoxLayout()
        self.chk_bloecke = QCheckBox(t("Blöcke anzeigen"))
        self.chk_bytes = QCheckBox(t("Einzelbytes anzeigen"))
        self.lb_logdatei = QLabel()
        self.lb_logdatei.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.bt_log_speichern = QPushButton(t("Protokoll speichern …"))
        self._zeige_logdatei()
        lz.addWidget(self.chk_bloecke)
        lz.addWidget(self.chk_bytes)
        lz.addStretch(1)
        lz.addWidget(self.lb_logdatei)
        lz.addWidget(self.bt_log_speichern)
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
        self.bt_anp.clicked.connect(lambda: self.tabs.setCurrentIndex(TAB_ANP))
        self.bt_km.clicked.connect(self._km_lesen)
        self.bt_fahrtenschreiber.clicked.connect(lambda: self.tabs.setCurrentIndex(TAB_FAHRT))
        self.chk_bloecke.toggled.connect(self._log_bloecke)
        self.chk_bytes.toggled.connect(self._log_bytes)
        self.bt_log_speichern.clicked.connect(self._protokoll_speichern)

    def _baue_messwertseite(self) -> QWidget:
        seite = QWidget()
        mv = QVBoxLayout(seite)
        gross = self.font()
        gross.setPointSize(max(gross.pointSize(), 9) + 4)
        gross.setBold(True)
        self._mwb_zeilen: list[tuple[QCheckBox, QSpinBox, list[QLabel], list[QLabel]]] = []
        self._mwb_namen: list[list[QLabel]] = []
        for i, start in enumerate((4, 1, 2)):
            gb = QGroupBox(t("Anzeige {nummer}", nummer=i + 1))
            gl = QGridLayout(gb)
            chk = QCheckBox(t("Gruppe"))
            chk.setChecked(i == 0)
            sp = QSpinBox()
            sp.setRange(0, 255)
            sp.setValue(start)
            sp.valueChanged.connect(lambda _w, z=i: self._minmax_zeile_zuruecksetzen(z))
            gl.addWidget(chk, 0, 0)
            gl.addWidget(sp, 0, 1)
            felder, minmax, namen = [], [], []
            for feld in range(4):
                name = QLabel("")
                name.setAlignment(Qt.AlignmentFlag.AlignCenter)
                name.setEnabled(False)
                lb = QLabel("—")
                lb.setFont(gross)
                lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lb.setMinimumWidth(170)
                lb.setMinimumHeight(48)
                lb.setFrameShape(QFrame.Shape.StyledPanel)
                mm = QLabel("")
                mm.setAlignment(Qt.AlignmentFlag.AlignCenter)
                mm.setEnabled(False)
                gl.addWidget(name, 1, feld)
                gl.addWidget(lb, 2, feld)
                gl.addWidget(mm, 3, feld)
                felder.append(lb)
                minmax.append(mm)
                namen.append(name)
            self._mwb_zeilen.append((chk, sp, felder, minmax))
            self._mwb_namen.append(namen)
            mv.addWidget(gb)

        werte = einstellungen.laden()
        steuer = QHBoxLayout()
        self.bt_mwb_start = QPushButton(t("Start"))
        # Vorbelegung aus den Einstellungen; Änderungen hier gelten nur bis zum Schließen
        self.chk_csv = QCheckBox(t("aufzeichnen (CSV)"))
        self.chk_csv.setChecked(bool(werte["csv_automatisch"]))
        self.chk_csv.setToolTip(t("Gilt bis zum Schließen des Programms. Die Voreinstellung "
                                  "steht unter Datei → Einstellungen."))
        self.chk_neu = QCheckBox(t("bei Abbruch neu verbinden"))
        self.chk_neu.setChecked(bool(werte["neu_verbinden"]))
        self.bt_minmax = QPushButton(t("Min/Max zurücksetzen"))
        self.bt_suche = QPushButton(t("Gruppen durchsuchen …"))
        self.lb_rate = QLabel("")
        for w in (self.bt_mwb_start, self.chk_csv, self.chk_neu, self.bt_minmax, self.bt_suche):
            steuer.addWidget(w)
        steuer.addStretch(1)
        steuer.addWidget(self.lb_rate)
        mv.addLayout(steuer)

        datei = QHBoxLayout()
        self.lb_csv = QLabel("")
        self.lb_csv.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bt_csv_ordner = QPushButton(t("CSV-Ordner öffnen"))
        datei.addWidget(self.lb_csv, 1)
        datei.addWidget(bt_csv_ordner)
        mv.addLayout(datei)
        hinweis = QLabel(t("Für die Bordspannung beim Anlassen nur Gruppe 004 aktivieren – "
                           "dann wird am häufigsten abgefragt. Rohwerte im Tooltip jedes Feldes."))
        hinweis.setWordWrap(True)
        hinweis.setEnabled(False)
        mv.addWidget(hinweis)
        mv.addStretch(1)

        self.bt_mwb_start.clicked.connect(self._mwb_umschalten)
        self.bt_minmax.clicked.connect(self._minmax_zuruecksetzen)
        self.bt_suche.clicked.connect(self._suche_umschalten)
        self.chk_csv.toggled.connect(lambda _an: self._zeige_csv_ziel())
        bt_csv_ordner.clicked.connect(lambda: ordner_oeffnen(einstellungen.ordner("csv_ordner")))
        self._zeige_csv_ziel()
        return seite

    def _baue_anpassungsseite(self) -> QWidget:
        seite = QWidget()
        av = QVBoxLayout(seite)
        info = QLabel(t("Nur lesen: vagdiag schreibt keine Anpassungswerte. Kanal 00 wird nie "
                        "angesprochen – er steht bei vielen Steuergeräten für „alle "
                        "Anpassungswerte löschen“."))
        info.setWordWrap(True)
        av.addWidget(info)

        zeile = QHBoxLayout()
        zeile.addWidget(QLabel(t("Kanal:")))
        self.sp_kanal = QSpinBox()
        self.sp_kanal.setRange(1, 255)
        self.sp_kanal.setValue(9)
        self.bt_anp_lesen = QPushButton(t("Lesen"))
        zeile.addWidget(self.sp_kanal)
        zeile.addWidget(self.bt_anp_lesen)
        zeile.addSpacing(30)
        zeile.addWidget(QLabel(t("Kanäle")))
        self.sp_anp_von = QSpinBox()
        self.sp_anp_von.setRange(1, 255)
        self.sp_anp_von.setValue(1)
        self.sp_anp_bis = QSpinBox()
        self.sp_anp_bis.setRange(1, 255)
        self.sp_anp_bis.setValue(99)
        self.bt_anp_suche = QPushButton(t("durchsuchen"))
        zeile.addWidget(self.sp_anp_von)
        zeile.addWidget(QLabel(t("bis")))
        zeile.addWidget(self.sp_anp_bis)
        zeile.addWidget(self.bt_anp_suche)
        zeile.addStretch(1)
        av.addLayout(zeile)

        self.lb_anp_hinweis = QLabel("")
        self.lb_anp_hinweis.setWordWrap(True)
        av.addWidget(self.lb_anp_hinweis)

        self.tb_anp = QTableWidget(0, 5)
        self.tb_anp.setHorizontalHeaderLabels(
            [t("Kanal"), t("Wert"), t("Hex"), t("Hinweis"), t("Gelesen")])
        self.tb_anp.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tb_anp.verticalHeader().setVisible(False)
        self.tb_anp.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        av.addWidget(self.tb_anp, 1)
        unten = QHBoxLayout()
        bt_leeren = QPushButton(t("Liste leeren"))
        unten.addStretch(1)
        unten.addWidget(bt_leeren)
        av.addLayout(unten)

        self.bt_anp_lesen.clicked.connect(self._anp_lesen)
        self.bt_anp_suche.clicked.connect(self._anp_suche_umschalten)
        bt_leeren.clicked.connect(self._anp_leeren)
        return seite

    def _baue_fahrtseite(self) -> QWidget:
        seite = QWidget()
        fv = QVBoxLayout(seite)
        info = QLabel(t(
            "Zeichnet eine ganze Fahrt in einer Datei auf: das Motorsteuergerät durchgehend, "
            "Kombi und ABS in Abständen, am Anfang und am Ende die Fehlerspeicher aller "
            "Steuergeräte und den Tankinhalt im Stand. Vor dem Losfahren starten (Zündung an), "
            "nach dem Abstellen beenden und die Zündung anlassen, bis die Abschlussprüfung "
            "fertig ist. Während der Fahrt muss niemand den Laptop bedienen – und bitte den "
            "Laptop nicht vor einem Airbag halten."))
        info.setWordWrap(True)
        fv.addWidget(info)

        werte = einstellungen.laden()
        gb = QGroupBox(t("Einstellungen"))
        form = QFormLayout(gb)
        self.le_fahrt_gruppen = QLineEdit(str(werte["fahrt_motor_gruppen"]))
        self.le_fahrt_gruppen.setToolTip(t("Messwertgruppen des Motorsteuergeräts, z. B. "
                                           "1,2,3,4,5. Gruppen, die es nicht gibt, werden "
                                           "übersprungen."))
        self.sp_fahrt_kombi = QSpinBox()
        self.sp_fahrt_kombi.setRange(0, 3600)
        self.sp_fahrt_kombi.setValue(int(werte["fahrt_kombi_alle"]))
        self.sp_fahrt_abs = QSpinBox()
        self.sp_fahrt_abs.setRange(0, 3600)
        self.sp_fahrt_abs.setValue(int(werte["fahrt_abs_alle"]))
        self.sp_fahrt_besuch = QSpinBox()
        self.sp_fahrt_besuch.setRange(2, 60)
        self.sp_fahrt_besuch.setValue(int(werte["fahrt_besuch"]))
        self.chk_fahrt_pruefung = QCheckBox(
            t("Start- und Abschlussprüfung (Tankinhalt im Stand, alle Fehlerspeicher)"))
        self.chk_fahrt_pruefung.setChecked(bool(werte["fahrt_pruefung"]))
        # bewusst nicht gespeichert: bei jedem Programmstart wieder aus
        self.chk_fahrt_airbag = QCheckBox(t("Dabei auch den Airbag-Fehlerspeicher lesen "
                                            "(Adresse 15)"))
        self.chk_fahrt_airbag.setChecked(False)
        self.chk_fahrt_airbag.setToolTip(t("Standardmäßig aus. Beim Einschalten erscheint der "
                                           "Hinweis zum Airbag-Steuergerät."))
        form.addRow(t("Motor-Gruppen:"), self.le_fahrt_gruppen)
        form.addRow(t("Kombi alle … s (0 = nie):"), self.sp_fahrt_kombi)
        form.addRow(t("ABS alle … s (0 = nie):"), self.sp_fahrt_abs)
        form.addRow(t("Dauer je Besuch (s):"), self.sp_fahrt_besuch)
        form.addRow(self.chk_fahrt_pruefung)
        form.addRow(self.chk_fahrt_airbag)
        fv.addWidget(gb)

        knoepfe = QHBoxLayout()
        self.bt_fahrt = QPushButton(t("Fahrt starten"))
        self.bt_fahrt_ereignis = QPushButton(t("Ereignis markieren (F9)"))
        self.bt_fahrt_ereignis.setToolTip(
            t("Zum Beispiel wenn eine Warnlampe angeht: setzt eine Markierung und liest sofort "
              "die Fehlerspeicher von Motor und ABS."))
        self.bt_fahrt_abbrechen = QPushButton(t("Sofort abbrechen"))
        self.bt_fahrt_abbrechen.setToolTip(t("Beendet ohne Abschlussprüfung."))
        for knopf in (self.bt_fahrt, self.bt_fahrt_ereignis, self.bt_fahrt_abbrechen):
            knoepfe.addWidget(knopf)
        knoepfe.addStretch(1)
        fv.addLayout(knoepfe)

        fett = self.font()
        fett.setBold(True)
        self.lb_fahrt_phase = QLabel(t("Bereit."))
        self.lb_fahrt_phase.setFont(fett)
        self.lb_fahrt_datei = QLabel("")
        self.lb_fahrt_datei.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fv.addWidget(self.lb_fahrt_phase)
        fv.addWidget(self.lb_fahrt_datei)

        gross = self.font()
        gross.setPointSize(max(gross.pointSize(), 9) + 3)
        gross.setBold(True)
        gb_live = QGroupBox(t("Aktuelle Werte"))
        raster = QGridLayout(gb_live)
        self._fahrt_live: dict[str, QLabel] = {}
        for i, name in enumerate(LIVE_WERTE):
            titel = QLabel(beschriftung.anzeige(name))
            titel.setEnabled(False)
            wert = QLabel("—")
            wert.setFont(gross)
            raster.addWidget(titel, (i // 4) * 2, i % 4)
            raster.addWidget(wert, (i // 4) * 2 + 1, i % 4)
            self._fahrt_live[name] = wert
        fv.addWidget(gb_live)

        self.tx_fahrt = QPlainTextEdit()
        self.tx_fahrt.setReadOnly(True)
        self.tx_fahrt.setMaximumBlockCount(3000)
        self.tx_fahrt.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        fv.addWidget(self.tx_fahrt, 1)

        self.bt_fahrt.clicked.connect(self._fahrt_umschalten)
        self.chk_fahrt_airbag.clicked.connect(self._fahrt_airbag_gewaehlt)
        self.chk_fahrt_pruefung.toggled.connect(lambda _an: self._aktualisiere_knoepfe())
        self.bt_fahrt_ereignis.clicked.connect(self._fahrt_ereignis)
        self.bt_fahrt_abbrechen.clicked.connect(self._fahrt_abbrechen)
        kurz = QShortcut(QKeySequence("F9"), self)
        kurz.activated.connect(self._fahrt_ereignis)
        return seite

    # ============================================================ Hilfen
    def _ist_sim(self) -> bool:
        return self.cb_interface.currentIndex() in (SIM, SIM_KWP2000)

    def _sitzung(self) -> DiagSession:
        reizung = "bitbang" if self.cb_reizung.currentIndex() == 1 else "break"
        schluessel = (self.cb_interface.currentIndex(), self.le_url.text().strip(), reizung)
        if self.sitzung is not None and schluessel != self._sitzung_schluessel:
            self.sitzung.schliessen()
            self.sitzung = None
        if self.sitzung is None:
            if schluessel[0] == SIM:
                fabrik = sim_port
            elif schluessel[0] == SIM_KWP2000:
                def fabrik():
                    return sim_port(kwp2000_motor=True)
            else:
                url = schluessel[1] or standard_url()

                def fabrik(url=url, reizung=reizung):
                    return kabel_oeffnen(url, reizung)
            # Der Simulator nutzt und hinterlässt keine gemerkten Baudraten
            self._sitzung_sim = schluessel[0] in (SIM, SIM_KWP2000)
            gemerkt = ({} if self._sitzung_sim else
                       {int(k, 16): v for k, v in einstellungen.laden()["baudraten"].items()})
            self.sitzung = DiagSession(fabrik, ereignis=self._ereignis_aus_thread,
                                       baudraten=gemerkt).start()
            self._sitzung_schluessel = schluessel
        self.sitzung.fast_init = self.chk_fast_init.isChecked()
        return self.sitzung

    def _ereignis_aus_thread(self, art: str, daten: object) -> None:
        # CSV-Ereignisse sofort schreiben (der Zeitpunkt zählt), Rest an die GUI
        aufzeichnung = self._csv
        if aufzeichnung is not None:
            if art == "getrennt" and daten.get("neu_verbinden"):
                aufzeichnung.ereignis(t("Verbindung verloren: {grund}", grund=daten["grund"]))
            elif art == "verbunden":
                aufzeichnung.ereignis(t("wieder verbunden"))
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
                and not self._beschaeftigt and not self._mwb_laeuft
                and not self._suche_laeuft and not self._anp_suche_laeuft
                and not self._fahrt_laeuft)

    def _protokoll_hinweis(self) -> str:
        if self.logdatei is not None:
            return t("Protokolldatei: {pfad}", pfad=self.logdatei)
        return t("Das Protokoll lässt sich über Datei → Protokoll speichern … sichern.")

    def _zeige_fehler_dialog(self, titel: str, fehler: BaseException) -> None:
        text = str(fehler) or fehler.__class__.__name__
        if isinstance(fehler, UnsupportedProtocol):
            if self.logdatei is not None:
                text += "\n\n" + t(
                    "Für eine Fehlermeldung bitte diese Protokolldatei mitschicken:\n{pfad}",
                    pfad=self.logdatei)
            else:
                text += "\n\n" + t("Für eine Fehlermeldung bitte das Protokoll speichern (Datei "
                                   "→ Protokoll speichern …) und mitschicken.")
        elif isinstance(fehler, PortError):
            text += "\n\n" + t("Hinweise zur Einrichtung stehen in der README.")
        elif not isinstance(fehler, DiagError):
            log.error(t("Unerwarteter Fehler: %r"), fehler, exc_info=fehler)
            text = (t("Unerwarteter Fehler ({art}): {fehler}", art=fehler.__class__.__name__,
                      fehler=fehler) + "\n\n" + self._protokoll_hinweis())
        QMessageBox.warning(self, titel, text)

    def _aktualisiere_knoepfe(self) -> None:
        verbunden = self._verbindung is not None
        frei = not self._beschaeftigt
        aktiv = (self._mwb_laeuft or self._suche_laeuft or self._anp_suche_laeuft
                 or self._fahrt_laeuft)
        ftdi = not self._ist_sim()
        kombi = verbunden and self._verbindung.adresse == KOMBI
        kwp = verbunden and self._verbindung.protokoll == "KWP2000"
        self.cb_interface.setEnabled(frei and not verbunden and not aktiv)
        self.le_url.setEnabled(frei and not verbunden and ftdi and not aktiv)
        self.cb_reizung.setEnabled(frei and not verbunden and ftdi and not aktiv)
        self.chk_fast_init.setEnabled(frei and not verbunden and not aktiv)
        self.bt_suchen.setEnabled(not verbunden and ftdi and not aktiv)
        self.bt_kabeltest.setEnabled(frei and not aktiv)
        self.lw_adressen.setEnabled(frei and not aktiv)
        self.le_adresse.setEnabled(frei and not aktiv)
        self.bt_verbinden.setEnabled(frei and not aktiv)
        self.bt_trennen.setEnabled(frei and verbunden and not aktiv)
        self.bt_fehler.setEnabled(frei and verbunden and not aktiv)
        self.bt_loeschen.setEnabled(frei and verbunden and not aktiv)
        self.bt_mwb.setEnabled(verbunden or self._mwb_laeuft)
        self.bt_mwb_start.setEnabled((frei and verbunden and not self._suche_laeuft)
                                     or self._mwb_laeuft)
        self.bt_suche.setEnabled((frei and verbunden and not self._mwb_laeuft
                                  and not self._anp_suche_laeuft) or self._suche_laeuft)
        self.bt_anp.setEnabled(verbunden or self._anp_suche_laeuft)
        self.bt_km.setEnabled(frei and kombi and not aktiv)
        self.bt_anp_lesen.setEnabled(frei and verbunden and not aktiv and not kwp)
        self.bt_anp_suche.setEnabled((frei and verbunden and not kwp and not self._mwb_laeuft
                                      and not self._suche_laeuft and not self._fahrt_laeuft)
                                     or self._anp_suche_laeuft)
        fahrt = self._fahrt_laeuft
        self.bt_fahrt.setEnabled((frei and not aktiv) or (fahrt and not self._fahrt_endet))
        self.bt_fahrt_ereignis.setEnabled(fahrt and not self._fahrt_endet)
        self.bt_fahrt_abbrechen.setEnabled(fahrt)
        for feld in (self.le_fahrt_gruppen, self.sp_fahrt_kombi, self.sp_fahrt_abs,
                     self.sp_fahrt_besuch, self.chk_fahrt_pruefung):
            feld.setEnabled(not fahrt)
        self.chk_fahrt_airbag.setEnabled(not fahrt and self.chk_fahrt_pruefung.isChecked())

    def _zeige_logdatei(self) -> None:
        if self.logdatei is not None:
            self.lb_logdatei.setText(t("Protokoll: {pfad}", pfad=self.logdatei))
        else:
            self.lb_logdatei.setText(t("Protokolldatei: aus"))

    def _zeige_csv_ziel(self) -> None:
        if self._csv is not None:
            self.lb_csv.setText(t("Aufzeichnung läuft: {pfad}", pfad=self._csv.pfad))
        elif self.chk_csv.isChecked():
            self.lb_csv.setText(t("CSV-Ordner: {pfad}", pfad=einstellungen.laden()["csv_ordner"]))
        else:
            self.lb_csv.setText(t("Keine CSV-Aufzeichnung."))

    def _airbag_bestaetigt(self, frage: str) -> bool:
        """Rückfrage vor dem Airbag-Steuergerät (wie VCDS, Vorgabe: Nein)."""
        antwort = QMessageBox.question(
            self, t("Airbag-Steuergerät"), airbag.hinweis() + "\n\n" + frage,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return antwort == QMessageBox.StandardButton.Yes

    def _airbag_freigeben(self, frage: str) -> bool:
        if not self._airbag_bestaetigt(frage):
            return False
        self._sitzung().airbag_freigeben()
        return True

    def _fahrt_airbag_gewaehlt(self, an: bool) -> None:
        """Häkchen „Airbag-Fehlerspeicher lesen“: erst nach dem Hinweis."""
        if an and not self._airbag_bestaetigt(
                t("Den Airbag-Fehlerspeicher in der Start- und Abschlussprüfung lesen?")):
            self.chk_fahrt_airbag.setChecked(False)

    # ============================================================ Einstellungen
    def _einstellungen(self) -> None:
        dialog = EinstellungenDialog(self)
        if not dialog.exec():   # 0 = abgebrochen
            return
        alt = einstellungen.laden()
        neu = einstellungen.speichern(
            sprache=dialog.sprache_code(),
            log_ordner=dialog.le_log.text().strip() or alt["log_ordner"],
            csv_ordner=dialog.le_csv.text().strip() or alt["csv_ordner"],
            log_datei=dialog.chk_log.isChecked(),
            csv_automatisch=dialog.chk_csv.isChecked(),
            neu_verbinden=dialog.chk_neu.isChecked())
        # neue Voreinstellungen auch für diese Sitzung übernehmen
        if not self._mwb_laeuft:
            self.chk_csv.setChecked(bool(neu["csv_automatisch"]))
            self.chk_neu.setChecked(bool(neu["neu_verbinden"]))
        if neu["log_datei"] and protokolldatei.aktuelle_datei() is None:
            protokolldatei.datei_einschalten(ordner=Path(neu["log_ordner"]))
        elif not neu["log_datei"] and protokolldatei.aktuelle_datei() is not None:
            protokolldatei.datei_ausschalten()
        elif Path(neu["log_ordner"]).expanduser() != Path(alt["log_ordner"]).expanduser():
            protokolldatei.ordner_wechseln(Path(neu["log_ordner"]))
        self.logdatei = protokolldatei.aktuelle_datei()
        self._zeige_logdatei()
        self._zeige_csv_ziel()
        self.statusBar().showMessage(t("Einstellungen gespeichert."))
        if neu["sprache"] != alt["sprache"]:
            self._sprache_gewechselt()

    def _sprache_gewechselt(self) -> None:
        if self._laeuft_etwas():
            QMessageBox.information(
                self, "Sprache / Language",
                "Die neue Sprache gilt beim nächsten Start.\n\n"
                "The new language applies the next time vagdiag starts.")
            return
        antwort = QMessageBox.question(
            self, "Sprache / Language",
            "Die neue Sprache gilt nach einem Neustart des Fensters. Eine offene Verbindung "
            "wird dabei geschlossen. Jetzt neu starten?\n\n"
            "The new language applies after restarting the window. An open connection will "
            "be closed. Restart now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if antwort == QMessageBox.StandardButton.Yes:
            self.neustart = True
            self.close()

    def _protokoll_speichern(self) -> None:
        vorschlag = einstellungen.ordner("log_ordner") / time.strftime(
            "vagdiag-%Y%m%d-%H%M%S.log")
        pfad, _ = QFileDialog.getSaveFileName(self, t("Protokoll speichern"), str(vorschlag),
                                              t("Protokolle (*.log);;Alle Dateien (*)"))
        if not pfad:
            return
        try:
            ziel = protokolldatei.speichern(Path(pfad))
        except OSError as exc:
            QMessageBox.warning(self, t("Protokoll speichern"), str(exc))
            return
        self.statusBar().showMessage(t("Protokoll gespeichert: {pfad}", pfad=ziel))

    # ============================================================ Interface
    def _interface_geaendert(self, _index: int) -> None:
        sim = self._ist_sim()
        self.lb_sim.setVisible(sim)
        titel = t("VAG-Diagnose {version} – KW1281/KWP2000 über KKL-Kabel",
                  version=__version__)
        self.setWindowTitle(titel + ("  [" + t("SIMULATOR") + "]" if sim else ""))
        self._aktualisiere_knoepfe()

    def _kabel_suchen(self) -> None:
        try:
            geraete = list_ftdi_devices()
        except PortError as exc:
            QMessageBox.warning(self, t("Kabel suchen"), str(exc))
            return
        if not geraete:
            QMessageBox.information(
                self, t("Kabel suchen"),
                t("Kein FTDI-Kabel gefunden.\n\nSteckt es?") + " " + einrichtungs_hinweis())
            return
        self.le_url.setText(geraete[0][0])
        liste = "\n".join(f"{url}  {beschreibung}" for url, beschreibung in geraete)
        QMessageBox.information(self, t("Kabel suchen"),
                                t("Gefunden:\n{liste}\n\nDas erste Kabel ist eingetragen.",
                                  liste=liste))

    def _laeuft_etwas(self) -> bool:
        return (self._beschaeftigt or self._mwb_laeuft or self._suche_laeuft
                or self._anp_suche_laeuft or self._fahrt_laeuft)

    def _kabeltest(self) -> None:
        if self._laeuft_etwas():
            return
        self._auftrag("kabeltest", self._sitzung().kabeltest())

    def _fertig_kabeltest(self, _kontext, ergebnis, fehler) -> None:
        if fehler:
            self._zeige_fehler_dialog(t("Kabeltest"), fehler)
            return
        QMessageBox.information(
            self, t("Kabeltest"),
            t("Interface: {geraet}\nEcho: {echo}", geraet=ergebnis["geraet"],
              echo=sprache.ja_nein(ergebnis["echo"])) + "\n\n" + ergebnis["hinweis"])

    # ============================================================ Verbindung
    def _gewaehlte_adresse(self) -> int | None:
        text = self.le_adresse.text().strip()
        if text:
            try:
                wert = int(text, 16)
            except ValueError:
                wert = -1
            if not 0 <= wert <= 0x7F:
                QMessageBox.warning(self, t("Adresse"),
                                    t("Bitte eine Adresse von 00 bis 7F eingeben (hex), "
                                      "z. B. 01 oder 17."))
                return None
            return wert
        eintrag = self.lw_adressen.currentItem()
        return eintrag.data(Qt.ItemDataRole.UserRole) if eintrag else None

    def _eintrag_doppelklick(self, _eintrag) -> None:
        self.le_adresse.clear()
        self._verbinden()

    def _verbinden(self) -> None:
        if self._laeuft_etwas():
            return
        adresse = self._gewaehlte_adresse()
        if adresse is None:
            return
        if adresse == airbag.ADRESSE and not self._airbag_freigeben(
                t("Trotzdem mit dem Airbag-Steuergerät verbinden?")):
            self.statusBar().showMessage(t("Airbag-Steuergerät nicht geöffnet."))
            return
        bauds = BAUD_AUSWAHL[self.cb_baud.currentIndex()][1]
        self.statusBar().showMessage(
            t("Verbinde mit {steuergeraet} … (die Reizung dauert gut 2 Sekunden)",
              steuergeraet=adressen.text(adresse)))
        self._auftrag("verbinden", self._sitzung().verbinden(adresse, bauds), adresse)

    def _fertig_verbinden(self, adresse, verbindung, fehler) -> None:
        if fehler:
            self._verbindung = None
            self.statusBar().showMessage(t("Keine Verbindung zu {steuergeraet}",
                                           steuergeraet=adressen.text(adresse)))
            self.tx_ident.setPlainText(t("Keine Verbindung zu {steuergeraet}:",
                                         steuergeraet=adressen.text(adresse)) + f"\n{fehler}")
            self._zeige_fehler_dialog(t("Verbindung fehlgeschlagen"), fehler)
            return
        self._verbindung = verbindung
        self._adresse = verbindung.adresse
        self._zeige_ident(verbindung)
        self.tb_fehler.setRowCount(0)
        self.lb_fehler.setText(t("Noch nicht gelesen."))
        self._minmax.zuruecksetzen()
        for (_, _, felder, minmax), namen in zip(self._mwb_zeilen, self._mwb_namen):
            for lb in felder:
                lb.setText("—")
                lb.setToolTip("")
            for mm in minmax:
                mm.setText("")
            for name in namen:
                name.setText("")
        self._anp_leeren()
        if verbindung.protokoll == "KWP2000":
            self.lb_anp_hinweis.setText(kwp_ohne_anpassung())
        else:
            self.lb_anp_hinweis.setText(
                t("Kombi: Bei vielen VAG-Kombis ist Kanal 09 der Kilometerstand in "
                  "10-km-Schritten – nicht bei jedem, deshalb mit der Anzeige im Kombi "
                  "vergleichen.") if verbindung.adresse == KOMBI else "")
        self.tabs.setCurrentIndex(TAB_IDENT)
        self.statusBar().showMessage(
            t("Verbunden: {steuergeraet} – {protokoll}, {baud} Baud, Kabel-Echo {echo}",
              steuergeraet=adressen.text(verbindung.adresse), protokoll=verbindung.protokoll,
              baud=verbindung.baud, echo=sprache.ja_nein(verbindung.echo)))

    def _zeige_ident(self, v: Verbindung) -> None:
        self.tx_ident.setPlainText("\n".join(ident.zeilen(v, self._ist_sim())))

    def _trennen(self) -> None:
        self._mwb_stopp()
        if self.sitzung is not None and not self._beschaeftigt:
            self._auftrag("trennen", self.sitzung.trennen())

    def _fertig_trennen(self, _kontext, _ergebnis, fehler) -> None:
        self._verbindung = None
        self.statusBar().showMessage(t("Verbindung geschlossen."))

    def _ereignis(self, art: str, daten: object) -> None:
        if art == "getrennt":
            self._verbindung = None
            if daten.get("neu_verbinden") and self._mwb_laeuft:
                self.statusBar().showMessage(
                    t("Verbindung verloren ({grund}) – verbinde neu …", grund=daten["grund"]))
            else:
                if self._mwb_laeuft:
                    self._mwb_stopp()
                if not self._beschaeftigt and not self._fahrt_laeuft:
                    # beim Wechsel steht dort „Verbinde mit …“
                    self.statusBar().showMessage(t("Getrennt: {grund}", grund=daten["grund"]))
        elif art == "neu_verbinden":
            self.statusBar().showMessage(t("Verbinde neu … (Versuch {nummer})", nummer=daten))
        elif art == "verbunden":
            self._verbindung = daten
            if self._mwb_laeuft:
                self.statusBar().showMessage(
                    t("Wieder verbunden ({uhrzeit}) – Messung läuft weiter",
                      uhrzeit=time.strftime("%H:%M:%S")))
        elif art == "baud":
            if not self._sitzung_sim:   # Simulator-Baudraten nicht fürs Auto merken
                einstellungen.baud_merken(*daten)
        elif art == "suche":
            gruppe, werte = daten
            self.statusBar().showMessage(t("Durchsuche Gruppe {gruppe:03d} …", gruppe=gruppe))
            if werte is not None:
                namen = beschriftung.namen(self._verbindung, gruppe, werte)
                self._suche_ergebnis.append(
                    f"{gruppe:03d}: " + " | ".join(beschriftung.mit_namen(namen, werte))
                    + "      (" + "; ".join(w.roh for w in werte) + ")")
        elif art == "anpassung_suche":
            kanal, anpassung = daten
            self.statusBar().showMessage(t("Lese Anpassungskanal {kanal:02d} …", kanal=kanal))
            if anpassung is not None:
                self._anp_eintragen(anpassung)
        elif art == "fahrt":
            minuten = int(daten.get("dauer", 0) // 60)
            self.lb_fahrt_phase.setText(f"{daten['phase']}: {daten['text']}")
            self.lb_fahrt_datei.setText(
                f"{daten['datei']}  ·  "
                + t("{zeilen} Zeilen", zeilen=daten["zeilen"]) + f"  ·  {minuten} min")
            self.statusBar().showMessage(t("Fahrtenschreiber – {phase}: {text}",
                                           phase=daten["phase"], text=daten["text"]))
        elif art == "fahrt_notiz":
            self.tx_fahrt.appendPlainText(daten)
        elif art == "fahrt_werte":
            self._fahrt_live_zeigen(daten)
        self._aktualisiere_knoepfe()

    # ============================================================ Fehlerspeicher
    def _fehler_lesen(self) -> None:
        if not self._bereit():
            return
        self.statusBar().showMessage(t("Lese Fehlerspeicher …"))
        self._auftrag("fehler", self.sitzung.fehler_lesen())

    def _fertig_fehler(self, _kontext, liste, fehler) -> None:
        if fehler:
            self._zeige_fehler_dialog(t("Fehlerspeicher"), fehler)
            return
        self._zeige_fehlerliste(liste)
        self.tabs.setCurrentIndex(TAB_FEHLER)
        self.statusBar().showMessage(t("Fehlerspeicher gelesen."))

    def _zeige_fehlerliste(self, liste) -> None:
        self.tb_fehler.setRowCount(len(liste))
        for zeile, f in enumerate(liste):
            werte = [f.code_text, f.p_code or "", f.beschreibung, f.fehlerart_text,
                     t("ja") if f.sporadisch else ""]
            for spalte, wert in enumerate(werte):
                self.tb_fehler.setItem(zeile, spalte, QTableWidgetItem(wert))
        self.tb_fehler.resizeColumnToContents(0)
        self.tb_fehler.resizeColumnToContents(1)
        self.tb_fehler.resizeColumnToContents(3)
        anzahl = (t("{anzahl} Fehler gespeichert", anzahl=len(liste)) if liste
                  else t("Kein Fehler gespeichert"))
        self.lb_fehler.setText(anzahl + " " + t("(gelesen um {uhrzeit})",
                                                uhrzeit=time.strftime("%H:%M:%S")))

    def _fehler_loeschen(self) -> None:
        if not self._bereit():
            return
        text = t("Fehlerspeicher von {steuergeraet} wirklich löschen?\n\nDabei werden auch die "
                 "Readiness-Codes zurückgesetzt (wichtig vor einer AU).",
                 steuergeraet=adressen.text(self._verbindung.adresse))
        if self._verbindung.adresse == airbag.ADRESSE:
            text += "\n\n" + t("Ein Fehler, dessen Ursache noch besteht, kommt sofort wieder. "
                               "Crashdaten lassen sich nicht löschen.")
        antwort = QMessageBox.question(
            self, t("Fehlerspeicher löschen"), text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if antwort != QMessageBox.StandardButton.Yes:
            return
        self.statusBar().showMessage(t("Lösche Fehlerspeicher …"))
        self._auftrag("loeschen", self.sitzung.fehler_loeschen())

    def _fertig_loeschen(self, _kontext, _rest, fehler) -> None:
        if fehler:
            self._zeige_fehler_dialog(t("Fehlerspeicher löschen"), fehler)
            return
        self.statusBar().showMessage(t("Fehlerspeicher gelöscht – lese neu …"))
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
        if not any(chk.isChecked() for chk, _, _, _ in self._mwb_zeilen):
            QMessageBox.information(self, t("Messwertblöcke"),
                                    t("Bitte mindestens eine Gruppe aktivieren."))
            return
        if self.chk_csv.isChecked():
            try:
                self._csv = CsvAufzeichnung.neu(self._verbindung.adresse,
                                                sim=self._sitzung_sim)
            except OSError as exc:
                QMessageBox.warning(self, t("Aufzeichnung"),
                                    t("CSV-Datei konnte nicht angelegt werden: {fehler}",
                                      fehler=exc))
                self._csv = None
        self._minmax.zuruecksetzen()
        for _, _, _, minmax in self._mwb_zeilen:
            for mm in minmax:
                mm.setText("")
        self.sitzung.messung_starten()
        self._mwb_laeuft = True
        self._mwb_index = 0
        self._mwb_zaehler = 0
        self._mwb_zeit = time.monotonic()
        self.bt_mwb_start.setText(t("Stopp"))
        self.lb_rate.setText("")
        self._zeige_csv_ziel()
        self._aktualisiere_knoepfe()
        self._mwb_naechste()

    def _mwb_stopp(self) -> None:
        war_aktiv = self._mwb_laeuft
        self._mwb_laeuft = False
        self.bt_mwb_start.setText(t("Start"))
        if war_aktiv and self.sitzung is not None:
            self.sitzung.abbrechen()   # ein laufendes Neuverbinden beenden
        if self._csv is not None:
            pfad = self._csv.pfad
            self._csv.schliessen()
            self._csv = None
            self.statusBar().showMessage(t("Messwerte gespeichert: {pfad}", pfad=pfad))
        self._zeige_csv_ziel()
        self._aktualisiere_knoepfe()

    def _mwb_naechste(self) -> None:
        if not self._mwb_laeuft or self.sitzung is None:
            self._mwb_stopp()
            return
        aktiv = [(i, sp.value()) for i, (chk, sp, _, _) in enumerate(self._mwb_zeilen)
                 if chk.isChecked()]
        if not aktiv:
            self._mwb_stopp()
            return
        zeile, gruppe = aktiv[self._mwb_index % len(aktiv)]
        self._mwb_index += 1
        self._auftrag("mwb", self.sitzung.gruppe_lesen(gruppe, self.chk_neu.isChecked()),
                      (zeile, gruppe), beschaeftigt=False)

    def _fertig_mwb(self, kontext, werte, fehler) -> None:
        zeile, gruppe = kontext
        chk, _, felder, minmax = self._mwb_zeilen[zeile]
        namen_labels = self._mwb_namen[zeile]
        if fehler:
            if not self._mwb_laeuft or isinstance(fehler, Abgebrochen):
                return   # Messung wurde schon beendet
            if isinstance(fehler, (NotAvailable, Nak)):
                felder[0].setText(t("nicht belegt"))
                felder[0].setToolTip(str(fehler))
                for lb in felder[1:]:
                    lb.setText("—")
                for name in namen_labels:
                    name.setText("")
                chk.setChecked(False)
            else:
                self._mwb_stopp()
                self._zeige_fehler_dialog(t("Messwertblöcke"), fehler)
                return
        else:
            # Namen nur mit bestehender Verbindung bestimmen (beim Neuverbinden bleiben sie)
            namen = (beschriftung.namen(self._verbindung, gruppe, werte)
                     if self._verbindung is not None else None)
            for i, lb in enumerate(felder):
                if i < len(werte):
                    lb.setText(werte[i].text)
                    tipp = werte[i].roh
                    erklaerung = beschriftung.bitfeld_erklaerung(
                        self._verbindung, gruppe, i + 1, werte[i].wert_text)
                    if erklaerung:
                        tipp += "\n" + erklaerung
                    lb.setToolTip(tipp)
                    self._minmax.erfassen((zeile, i), werte[i])
                    minmax[i].setText(self._minmax.text((zeile, i)))
                else:
                    lb.setText("")
                    lb.setToolTip("")
                    minmax[i].setText("")
                if namen is not None:
                    namen_labels[i].setText(beschriftung.anzeige(namen[i]) if i < len(namen)
                                            else "")
            if self._csv is not None and self._mwb_laeuft:
                self._csv.messwerte(gruppe, werte, namen)
            self._mwb_zaehler += 1
            dauer = time.monotonic() - self._mwb_zeit
            if dauer >= 1.0:
                self.lb_rate.setText(t("{rate} Abfragen/s",
                                       rate=sprache.zahl(self._mwb_zaehler / dauer, 1)))
                self._mwb_zaehler = 0
                self._mwb_zeit = time.monotonic()
        if self._mwb_laeuft:
            QTimer.singleShot(0, self._mwb_naechste)

    def _minmax_zuruecksetzen(self) -> None:
        self._minmax.zuruecksetzen()
        for _, _, _, minmax in self._mwb_zeilen:
            for mm in minmax:
                mm.setText("")

    def _minmax_zeile_zuruecksetzen(self, zeile: int) -> None:
        for feld in range(4):
            self._minmax.zuruecksetzen((zeile, feld))
            self._mwb_zeilen[zeile][3][feld].setText("")
            self._mwb_namen[zeile][feld].setText("")

    # ============================================================ Gruppensuche
    def _suche_umschalten(self) -> None:
        if self._suche_laeuft:
            if self.sitzung is not None:
                self.sitzung.abbrechen()
            return
        if not self._bereit():
            return
        self._suche_laeuft = True
        self._suche_ergebnis = []
        self.bt_suche.setText(t("Suche abbrechen"))
        self.statusBar().showMessage(t("Durchsuche Messwertgruppen 001–255 …"))
        self._auftrag("suche", self.sitzung.gruppen_suchen(1, 255), beschaeftigt=False)
        self._aktualisiere_knoepfe()

    def _fertig_suche(self, _kontext, gefunden, fehler) -> None:
        self._suche_laeuft = False
        self.bt_suche.setText(t("Gruppen durchsuchen …"))
        if fehler:
            self._zeige_fehler_dialog(t("Gruppensuche"), fehler)
            return
        self.statusBar().showMessage(t("Gruppensuche fertig: {anzahl} belegte Gruppen",
                                       anzahl=len(gefunden)))
        dialog = QDialog(self)
        dialog.setWindowTitle(t("Belegte Messwertgruppen – {steuergeraet}",
                                steuergeraet=adressen.text(self._adresse or 0)))
        dialog.resize(900, 500)
        lay = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        text.setPlainText("\n".join(self._suche_ergebnis)
                          or t("Keine belegten Gruppen gefunden."))
        lay.addWidget(text)
        knopf = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        knopf.rejected.connect(dialog.reject)
        lay.addWidget(knopf)
        dialog.exec()

    # ============================================================ Anpassung (nur lesen)
    def _anp_leeren(self) -> None:
        self.tb_anp.setRowCount(0)
        self._anp_zeilen = {}

    def _anp_zeile(self, kanal: int, werte: tuple[str, str, str]) -> None:
        zeile = self._anp_zeilen.get(kanal)
        if zeile is None:
            zeile = self.tb_anp.rowCount()
            self.tb_anp.insertRow(zeile)
            self._anp_zeilen[kanal] = zeile
        for spalte, text in enumerate((f"{kanal:02d}",) + werte + (time.strftime("%H:%M:%S"),)):
            self.tb_anp.setItem(zeile, spalte, QTableWidgetItem(text))

    def _anp_eintragen(self, anpassung: Anpassung) -> None:
        hinweis = ""
        if (self._verbindung is not None and self._verbindung.adresse == KOMBI
                and anpassung.kanal == 9 and anpassung.wert != 0xFFFF):
            hinweis = t("Kilometerstand? {km} (unbestätigt)", km=km_text(anpassung.wert * 10))
        self._anp_zeile(anpassung.kanal, (str(anpassung.wert), anpassung.hex, hinweis))

    def _anp_lesen(self) -> None:
        if not self._bereit():
            return
        kanal = self.sp_kanal.value()
        self.statusBar().showMessage(t("Lese Anpassungskanal {kanal:02d} …", kanal=kanal))
        self._auftrag("anpassung", self.sitzung.anpassung_lesen(kanal), kanal)

    def _fertig_anpassung(self, kanal, anpassung, fehler) -> None:
        if fehler:
            if isinstance(fehler, (Nak, NotAvailable)):
                self._anp_zeile(kanal, ("—", "", str(fehler)))
                self.statusBar().showMessage(str(fehler))
                return
            self._zeige_fehler_dialog(t("Anpassung lesen"), fehler)
            return
        self._anp_eintragen(anpassung)
        self.statusBar().showMessage(anpassung.text)

    def _anp_suche_umschalten(self) -> None:
        if self._anp_suche_laeuft:
            if self.sitzung is not None:
                self.sitzung.abbrechen()
            return
        if not self._bereit():
            return
        von, bis = sorted((self.sp_anp_von.value(), self.sp_anp_bis.value()))
        self._anp_suche_laeuft = True
        self.bt_anp_suche.setText(t("abbrechen"))
        self.statusBar().showMessage(t("Lese Anpassungskanäle {von:02d}–{bis:02d} (nur lesen) …",
                                       von=von, bis=bis))
        self._auftrag("anpsuche", self.sitzung.anpassungen_suchen(von, bis), beschaeftigt=False)
        self._aktualisiere_knoepfe()

    def _fertig_anpsuche(self, _kontext, gefunden, fehler) -> None:
        self._anp_suche_laeuft = False
        self.bt_anp_suche.setText(t("durchsuchen"))
        if fehler:
            self._zeige_fehler_dialog(t("Kanalsuche"), fehler)
            return
        self.statusBar().showMessage(t("Kanalsuche fertig: {anzahl} lesbare Kanäle",
                                       anzahl=len(gefunden)))

    def _km_lesen(self) -> None:
        if not self._bereit():
            return
        self.statusBar().showMessage(t("Lese Kilometerstand …"))
        self._auftrag("km", self.sitzung.kilometerstand())

    def _fertig_km(self, _kontext, ergebnis, fehler) -> None:
        if fehler:
            self._zeige_fehler_dialog(t("Kilometerstand"), fehler)
            return
        text = "\n".join(ergebnis.zeilen)
        if ergebnis.km is None:
            text += "\n\n" + t("Im Reiter „Anpassung“ lassen sich alle lesbaren Kanäle "
                               "durchsuchen (nur lesen).")
        if self._sitzung_sim:
            text += "\n\n" + t("(Simulator – keine echten Fahrzeugdaten)")
        self.statusBar().showMessage(ergebnis.zeilen[0])
        QMessageBox.information(self, t("Kilometerstand"), text)

    # ============================================================ Fahrtenschreiber
    def _fahrt_umschalten(self) -> None:
        if self._fahrt_laeuft:
            if not self._fahrt_endet and self.sitzung is not None:
                self._fahrt_endet = True
                self.sitzung.fahrt_beenden()
                self.bt_fahrt.setText(t("Abschlussprüfung läuft …"))
                self.tx_fahrt.appendPlainText(f"{time.strftime('%H:%M:%S')}  "
                                              + t("Fahrt wird beendet – Zündung noch an lassen"))
                self._aktualisiere_knoepfe()
            return
        if self._laeuft_etwas():
            return
        gruppen = _gruppenliste(self.le_fahrt_gruppen.text())
        if not gruppen:
            QMessageBox.warning(self, t("Fahrtenschreiber"),
                                t("Bitte mindestens eine Motor-Gruppe angeben, z. B. 1,2,3,4,5."))
            return
        einstellungen.speichern(
            fahrt_motor_gruppen=",".join(str(g) for g in gruppen),
            fahrt_kombi_alle=self.sp_fahrt_kombi.value(),
            fahrt_abs_alle=self.sp_fahrt_abs.value(),
            fahrt_besuch=self.sp_fahrt_besuch.value(),
            fahrt_pruefung=self.chk_fahrt_pruefung.isChecked())
        plan = FahrtPlan.aus_einstellungen()
        plan.mit_airbag = plan.pruefung and self.chk_fahrt_airbag.isChecked()
        sitzung = self._sitzung()
        if plan.mit_airbag:
            sitzung.airbag_freigeben()      # beim Setzen des Häkchens bestätigt
        self._fahrt_laeuft = True
        self._fahrt_endet = False
        self.tx_fahrt.clear()
        for wert in self._fahrt_live.values():
            wert.setText("—")
        self.bt_fahrt.setText(t("Fahrt beenden"))
        self.tabs.setCurrentIndex(TAB_FAHRT)
        self._auftrag("fahrt", sitzung.fahrt_starten(plan, None, sim=self._sitzung_sim),
                      beschaeftigt=False)
        self._aktualisiere_knoepfe()

    def _fahrt_ereignis(self) -> None:
        if not self._fahrt_laeuft or self._fahrt_endet or self.sitzung is None:
            return
        self.sitzung.fahrt_ereignis(t("Knopf"))
        self.tx_fahrt.appendPlainText(f"{time.strftime('%H:%M:%S')}  "
                                      + t("Ereignis markiert – lese Fehlerspeicher von Motor "
                                          "und ABS …"))

    def _fahrt_abbrechen(self) -> None:
        if self._fahrt_laeuft and self.sitzung is not None:
            self.sitzung.abbrechen()

    def _fahrt_live_zeigen(self, daten: dict) -> None:
        adresse = daten["adresse"]
        for name, m in zip(daten["namen"], daten["werte"]):
            ziel = name
            if name in ("Fahrgeschwindigkeit", "Geschwindigkeit"):
                ziel = "Tempo"
            elif name == "Rad vorn links":
                ziel = "Tempo"
            elif name in ("Motordrehzahl", "Kühlmitteltemperatur") and adresse != 0x01:
                continue      # Kombi zeigt eigene Werte – im Feld steht das Motorsteuergerät
            label = self._fahrt_live.get(ziel)
            if label is not None:
                label.setText(m.text)

    def _fertig_fahrt(self, _kontext, ergebnis, fehler) -> None:
        self._fahrt_laeuft = False
        self._fahrt_endet = False
        self._verbindung = None
        self.bt_fahrt.setText(t("Fahrt starten"))
        if fehler:
            self.lb_fahrt_phase.setText(t("Fahrtenschreiber mit Fehler beendet."))
            self._zeige_fehler_dialog(t("Fahrtenschreiber"), fehler)
            return
        self.lb_fahrt_phase.setText(t("Fertig – Zusammenfassung gespeichert.")
                                    if ergebnis.txt_datei else t("Fertig."))
        self.statusBar().showMessage(t("Fahrt gespeichert: {pfad}", pfad=ergebnis.csv_datei))
        dialog = QDialog(self)
        dialog.setWindowTitle(t("Fahrtenschreiber – Zusammenfassung"))
        dialog.resize(900, 560)
        lay = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(ergebnis.zeilen))
        lay.addWidget(text)
        unten = QHBoxLayout()
        bt_ordner = QPushButton(t("Ordner öffnen"))
        bt_ordner.clicked.connect(lambda: ordner_oeffnen(ergebnis.csv_datei.parent))
        unten.addWidget(bt_ordner)
        unten.addStretch(1)
        knopf = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        knopf.rejected.connect(dialog.reject)
        unten.addWidget(knopf)
        lay.addLayout(unten)
        dialog.exec()

    # ============================================================ Ergebnisse
    def _fertig(self, aufgabe: str, kontext, ergebnis, fehler) -> None:
        if aufgabe not in ("mwb", "suche", "anpsuche", "fahrt"):
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


def _unerwarteter_fehler(art, wert, verlauf) -> None:
    """Unbehandelte Fehler ins Protokoll und als Meldung – unter Windows läuft die
    Oberfläche ohne Konsole, dort sähe man sie sonst nie."""
    if issubclass(art, KeyboardInterrupt):
        sys.__excepthook__(art, wert, verlauf)
        return
    log.error(t("Unerwarteter Fehler: %r"), wert, exc_info=(art, wert, verlauf))
    try:
        QMessageBox.critical(None, "vagdiag",
                             t("Unerwarteter Fehler ({art}): {fehler}", art=art.__name__,
                               fehler=wert) + "\n\n"
                             + t("Das Protokoll lässt sich über Datei → Protokoll speichern "
                                 "… sichern."))
    except Exception:
        pass


def main() -> None:
    sprache.setzen(einstellungen.laden()["sprache"])
    logdatei = protokolldatei.einrichten()
    app = QApplication(sys.argv)
    sys.excepthook = _unerwarteter_fehler
    app.setApplicationName("vagdiag")
    while True:
        fenster = Hauptfenster(logdatei)
        fenster.show()
        code = app.exec()
        if not fenster.neustart:
            break
        # Sprache gewechselt: Fenster mit den neuen Texten neu aufbauen
        sprache.setzen(einstellungen.laden()["sprache"])
        logdatei = protokolldatei.aktuelle_datei()
    sys.exit(code)

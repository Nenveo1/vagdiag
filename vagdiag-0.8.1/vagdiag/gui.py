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
                               QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import (__version__, adressen, airbag, berichte, beschriftung, einstellungen, ident,
               protokolldatei, scan, sprache, stellglied)
from .experte import (DROSSELKLAPPE_GRUPPEN, SCHRITT_MAX, adp_status, feldnamen_060,
                      kennung_text, verfuegbarkeit)
from .aufzeichnung import CsvAufzeichnung
from .fahrtenschreiber import FahrtPlan, _gruppenliste
from .kilometerstand import km_text
from .kw1281 import (Abgebrochen, Anpassung, DiagError, Nak, NotAvailable,
                     UnsupportedProtocol, Verbindung)
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

TAB_IDENT, TAB_FEHLER, TAB_MWB, TAB_ANP, TAB_FAHRT, TAB_SCAN, TAB_EXPERTE = range(7)
# Reiter, die zum geöffneten Steuergerät gehören – der zuletzt benutzte davon erscheint
# wieder, wenn ein Steuergerät geöffnet wird (Fahrtenschreiber und Scan gehören nicht dazu)
STEUERGERAETE_REITER = (TAB_IDENT, TAB_FEHLER, TAB_MWB, TAB_ANP, TAB_EXPERTE)
MOTOR = 0x01
KABEL, SIM, SIM_KWP2000 = 0, 1, 2          # Einträge der Interface-Auswahl
# Live-Anzeige des Fahrtenschreibers – interne (deutsche) Feldnamen
LIVE_WERTE = ["Motordrehzahl", N_("Tempo"), "Kühlmitteltemperatur", "Bordspannung",
              "Ansauglufttemperatur", "Tankinhalt", "Saugrohrdruck", "Bremslichtschalter"]
KOMBI = 0x17

EXPERTE_HINWEIS = N_(
    "Im Expertenmodus kann vagdiag Werte in Steuergeräten ändern und Stellglieder "
    "ansteuern:\n"
    "• Grundeinstellung starten (Drosselklappe anlernen)\n"
    "• Anpassungswerte speichern (Service-Intervall zurücksetzen)\n"
    "• Stellglieddiagnose (Zeiger, Lampen, Relais und Ventile nacheinander ansteuern)\n\n"
    "Nur am stehenden Auto mit eingeschalteter Zündung benutzen. Eine falsche Einstellung "
    "kann zu Fehlfunktionen führen. vagdiag prüft vorher die Bedingungen, sichert alte Werte "
    "und schreibt jeden Schritt ins Protokoll – die Benutzung bleibt trotzdem auf eigene "
    "Gefahr.\n\n"
    "Auch im Expertenmodus gesperrt: Kanal 00 (alle Anpassungen löschen), der "
    "Kilometerstand, Codierung, Login sowie Grundeinstellung und Anpassung bei Airbag, "
    "Bremsen, Wegfahrsperre, Lenkung und Niveauregulierung. Deren Stellglieddiagnose startet "
    "erst nach einer Warnung, die die möglichen Schäden nennt.\n\n"
    "Der Expertenmodus gilt nur bis zum Beenden des Programms.\n\n"
    "Expertenmodus einschalten?")


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
        self._scan_laeuft = False
        self._scan_eintraege: dict[int, scan.ScanEintrag] = {}
        self._scan_zeilen: dict[int, int] = {}
        self._scan_sim = False
        self._scan_abgebrochen = False
        self._scan_alle = False
        # Expertenmodus: bei jedem Programmstart aus, wird nicht gespeichert
        self._experte = False
        self._grundeinstellung_laeuft = False
        self._stellglied_laeuft = False
        self._stg_wartet = False        # Schritt läuft – „Weiter“ erst nach der Antwort
        self._stg_liste_kennung: tuple = ()      # für welches Gerät die Liste gerade steht
        self._stg_codes: list[int] = []          # Codes der angezeigten Liste
        self._stg_pos: int | None = None         # gerade angesteuert (Zeile der Liste)
        self._stg_anzeige: list[str] = []        # Zeilen der Liste, wie angezeigt
        self._stg_lauf_kennung: tuple = ()       # Gerät des laufenden Durchlaufs
        # was die Reiter zeigen – zum Speichern als Textdatei
        self._ident_stand: tuple[Verbindung, bool] | None = None
        self._fehler_stand: tuple[tuple, list, str, bool] | None = None
        self._anp_daten: dict[int, berichte.AnpassungsZeile] = {}
        self._anp_kennung: tuple = ()
        self._anp_sim = False

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
        menue_experte = self.menuBar().addMenu(t("E&xperte"))
        self.akt_experte = QAction(t("Expertenmodus …"), self)
        self.akt_experte.setCheckable(True)
        self.akt_experte.setChecked(False)
        self.akt_experte.triggered.connect(self._experte_umschalten)
        menue_experte.addAction(self.akt_experte)

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
                                    t("Simulator mit KWP2000 bei Motor und Kombi (ohne Auto)")])
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
        self.bt_scan = QPushButton(t("Scan (alle Steuergeräte)"))
        self.bt_km.setToolTip(t("Nur beim Kombiinstrument (Adresse 17): liest Messwertgruppe 002 "
                                "und, falls dort kein Wert steht, Anpassungskanal 09."))
        for knopf in (self.bt_fehler, self.bt_loeschen, self.bt_mwb, self.bt_anp, self.bt_km,
                      self.bt_fahrtenschreiber, self.bt_scan):
            fv.addWidget(knopf)
        lv.addWidget(gb_fn)

        # ---------------- Reiter rechts
        self.tabs = QTabWidget()

        seite_ident = QWidget()
        il = QVBoxLayout(seite_ident)
        self.tx_ident = QPlainTextEdit()
        self.tx_ident.setReadOnly(True)
        self.tx_ident.setFont(mono)
        self.tx_ident.setPlaceholderText(t("Noch kein Steuergerät geöffnet."))
        il.addWidget(self.tx_ident, 1)
        self.bt_ident_speichern = self._speichern_knopf(
            t("Die angezeigte Identifikation als Textdatei speichern."))
        il.addLayout(self._knopfzeile(self.bt_ident_speichern))
        self.tabs.addTab(seite_ident, t("Identifikation"))

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
        fl.addWidget(self.tb_fehler, 1)
        self.bt_fehler_speichern = self._speichern_knopf(
            t("Alle gelesenen Fehler dieses Steuergeräts als Textdatei speichern."))
        fl.addLayout(self._knopfzeile(self.bt_fehler_speichern))
        self.tabs.addTab(seite_fehler, t("Fehlerspeicher"))

        self.tabs.addTab(self._baue_messwertseite(), t("Messwertblöcke"))
        self.tabs.addTab(self._baue_anpassungsseite(), t("Anpassung"))
        self.tabs.addTab(self._baue_fahrtseite(), t("Fahrtenschreiber"))
        self.tabs.addTab(self._baue_scanseite(), t("Scan"))
        self.tabs.addTab(self._baue_expertenseite(), t("Experte"))

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
        self._steuergeraete_reiter = TAB_IDENT        # gilt bis zum Beenden des Programms
        self.tabs.currentChanged.connect(self._reiter_gewechselt)
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
        self.bt_scan.clicked.connect(lambda: self.tabs.setCurrentIndex(TAB_SCAN))
        self.chk_bloecke.toggled.connect(self._log_bloecke)
        self.chk_bytes.toggled.connect(self._log_bytes)
        self.bt_log_speichern.clicked.connect(self._protokoll_speichern)
        self.bt_ident_speichern.clicked.connect(self._ident_speichern)
        self.bt_fehler_speichern.clicked.connect(self._fehler_speichern)

    def _speichern_knopf(self, tipp: str) -> QPushButton:
        """„Speichern …“ – speichert, was der Reiter zeigt (nur Text, nichts wird gesendet)."""
        knopf = QPushButton(t("Speichern …"))
        knopf.setToolTip(tipp)
        knopf.setEnabled(False)
        return knopf

    @staticmethod
    def _knopfzeile(*knoepfe: QWidget) -> QHBoxLayout:
        zeile = QHBoxLayout()
        zeile.addStretch(1)
        for knopf in knoepfe:
            zeile.addWidget(knopf)
        return zeile

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
        info = QLabel(t("Nur lesen: Hier schreibt vagdiag keine Anpassungswerte (Service-Reset: "
                        "Reiter Experte). Kanal 00 wird nie angesprochen – er steht bei vielen "
                        "Steuergeräten für „alle Anpassungswerte löschen“."))
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
        bt_leeren = QPushButton(t("Liste leeren"))
        self.bt_anp_speichern = self._speichern_knopf(
            t("Alle Kanäle in der Liste als Textdatei speichern."))
        av.addLayout(self._knopfzeile(bt_leeren, self.bt_anp_speichern))

        self.bt_anp_lesen.clicked.connect(self._anp_lesen)
        self.bt_anp_suche.clicked.connect(self._anp_suche_umschalten)
        bt_leeren.clicked.connect(self._anp_leeren)
        self.bt_anp_speichern.clicked.connect(self._anp_speichern)
        return seite

    def _baue_fahrtseite(self) -> QWidget:
        seite = QWidget()
        fv = QVBoxLayout(seite)
        info = QLabel(t(
            "Zeichnet eine ganze Fahrt in einer Datei auf: das Motorsteuergerät durchgehend, "
            "das Kombi in Abständen, das ABS in Abständen nur im Stand, am Anfang und am Ende "
            "die Fehlerspeicher aller Steuergeräte und den Tankinhalt im Stand. Vor dem "
            "Losfahren starten (Zündung an, Motor aus) und den Motor erst anlassen, wenn "
            "„jetzt Motor starten“ erscheint – dann ist das Anlassen mit aufgezeichnet. Am Ziel "
            "bei eingeschalteter Zündung beenden und warten, bis die Abschlussprüfung fertig "
            "ist. Während der Fahrt muss niemand den Laptop bedienen – und bitte den Laptop "
            "nicht vor einem Airbag halten."))
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
        self.sp_fahrt_abs.setToolTip(t("Das ABS wird nur im Stand besucht (z. B. an der Ampel) – "
                                       "viele ABS-Steuergeräte nehmen während der Fahrt keine "
                                       "Verbindung an."))
        form.addRow(t("ABS alle … s, nur im Stand (0 = nie):"), self.sp_fahrt_abs)
        form.addRow(t("Dauer je Besuch (s):"), self.sp_fahrt_besuch)
        form.addRow(self.chk_fahrt_pruefung)
        form.addRow(self.chk_fahrt_airbag)
        fv.addWidget(gb)

        knoepfe = QHBoxLayout()
        self.bt_fahrt = QPushButton(t("Fahrt starten"))
        self.bt_fahrt_ereignis = QPushButton(t("Ereignis markieren (F9)"))
        self.bt_fahrt_ereignis.setToolTip(
            t("Zum Beispiel wenn eine Warnlampe angeht: setzt eine Markierung und liest sofort "
              "den Fehlerspeicher des Motors, den des ABS beim nächsten Halt."))
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

    def _baue_scanseite(self) -> QWidget:
        seite = QWidget()
        sv = QVBoxLayout(seite)
        info = QLabel(t("Fragt die Steuergeräte nacheinander ab – nur lesen: Kennung und "
                        "Fehlerspeicher. „Übliche Adressen“ nimmt die 15 häufigsten, „Alle "
                        "Adressen“ jede von 01 bis 7F (außer 33 = OBD-II und 7C = Werksmodus des "
                        "Radios) und zeigt nur die, die antworten. Jede nicht verbaute Adresse "
                        "kostet einige Sekunden. Doppelklick auf eine gefundene Zeile öffnet das "
                        "Steuergerät."))
        info.setWordWrap(True)
        sv.addWidget(info)
        zeile = QHBoxLayout()
        self.bt_scan_start = QPushButton(t("Scan starten"))
        self.cb_scan_umfang = QComboBox()
        self.cb_scan_umfang.addItems([
            t("Übliche Adressen ({anzahl}, etwa 1 Minute)", anzahl=len(adressen.ADRESSEN)),
            t("Alle Adressen 01–7F (etwa 8 Minuten)")])
        self.chk_scan_fehler = QCheckBox(t("Fehlerspeicher mitlesen"))
        self.chk_scan_fehler.setChecked(True)
        # bewusst nicht gespeichert: bei jedem Programmstart wieder aus
        self.chk_scan_airbag = QCheckBox(t("Airbag (15) einschließen"))
        self.chk_scan_airbag.setChecked(False)
        self.chk_scan_airbag.setToolTip(t("Standardmäßig aus. Beim Einschalten erscheint der "
                                          "Hinweis zum Airbag-Steuergerät."))
        self.bt_scan_bericht = self._speichern_knopf(
            t("Den Scan als Textdatei speichern: alle gefundenen Steuergeräte mit Kennung und "
              "Fehlern."))
        for w in (self.bt_scan_start, self.cb_scan_umfang, self.chk_scan_fehler,
                  self.chk_scan_airbag):
            zeile.addWidget(w)
        zeile.addStretch(1)
        zeile.addWidget(self.bt_scan_bericht)
        sv.addLayout(zeile)
        self.lb_scan = QLabel(t("Noch kein Scan."))
        sv.addWidget(self.lb_scan)
        self.tb_scan = QTableWidget(0, 7)
        self.tb_scan.setHorizontalHeaderLabels(
            [t("Adresse"), t("Steuergerät"), t("Teilenummer"), t("Bauteil"), t("Protokoll"),
             t("Fehler"), t("Status")])
        self.tb_scan.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tb_scan.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tb_scan.verticalHeader().setVisible(False)
        self.tb_scan.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tx_scan = QPlainTextEdit()
        self.tx_scan.setReadOnly(True)
        self.tx_scan.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.tx_scan.setPlaceholderText(t("Zeile anklicken: Kennung und Fehler des Steuergeräts."))
        teiler = QSplitter(Qt.Orientation.Vertical)
        teiler.addWidget(self.tb_scan)
        teiler.addWidget(self.tx_scan)
        teiler.setStretchFactor(0, 2)
        teiler.setStretchFactor(1, 1)
        sv.addWidget(teiler, 1)

        self.bt_scan_start.clicked.connect(self._scan_umschalten)
        self.chk_scan_airbag.clicked.connect(self._scan_airbag_gewaehlt)
        self.bt_scan_bericht.clicked.connect(self._scan_bericht_speichern)
        self.tb_scan.currentCellChanged.connect(lambda zeile, *_: self._scan_detail(zeile))
        self.tb_scan.cellDoubleClicked.connect(lambda zeile, _spalte: self._scan_oeffnen(zeile))
        return seite

    def _baue_expertenseite(self) -> QWidget:
        seite = QWidget()
        ev = QVBoxLayout(seite)
        self.lb_experte = QLabel()
        self.lb_experte.setWordWrap(True)
        ev.addWidget(self.lb_experte)

        gb_dk = QGroupBox(t("Drosselklappe anlernen (Motor 01, Grundeinstellung)"))
        dl = QVBoxLayout(gb_dk)
        hinweis = QLabel(t("Zündung an, Motor aus, Gaspedal nicht berühren. vagdiag prüft vorher: "
                           "Drehzahl 0, Bordspannung mindestens 11,5 V, Kühlmittel 5–95 °C, kein "
                           "Fehler im Motor-Fehlerspeicher. Die Grundeinstellung läuft etwa 30 "
                           "Sekunden, danach liest vagdiag den Fehlerspeicher."))
        hinweis.setWordWrap(True)
        dl.addWidget(hinweis)
        dl.addWidget(self._notiz(t("Dafür erst links {steuergeraet} öffnen.",
                                   steuergeraet=adressen.text(MOTOR))))
        self.lb_dk_grund = self._grund_label()
        dl.addWidget(self.lb_dk_grund)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel(t("Gruppe:")))
        self.cb_dk_gruppe = QComboBox()
        for name in DROSSELKLAPPE_GRUPPEN.values():
            self.cb_dk_gruppe.addItem(t(name))
        self.bt_dk_start = QPushButton(t("Prüfen und anlernen …"))
        self.bt_dk_abbrechen = QPushButton(t("Abbrechen"))
        for w in (self.cb_dk_gruppe, self.bt_dk_start, self.bt_dk_abbrechen):
            zeile.addWidget(w)
        zeile.addStretch(1)
        dl.addLayout(zeile)
        raster = QGridLayout()
        gross = self.font()
        gross.setPointSize(max(gross.pointSize(), 9) + 3)
        gross.setBold(True)
        self._dk_titel: list[QLabel] = []
        self._dk_werte: list[QLabel] = []
        for i in range(4):
            titel = QLabel(t("Feld {nummer}", nummer=i + 1))
            titel.setEnabled(False)
            wert = QLabel("—")
            wert.setFont(gross)
            raster.addWidget(titel, 0, i)
            raster.addWidget(wert, 1, i)
            self._dk_titel.append(titel)
            self._dk_werte.append(wert)
        dl.addLayout(raster)
        self.lb_dk = QLabel(t("Bereit."))
        dl.addWidget(self.lb_dk)
        ev.addWidget(gb_dk)

        gb_sv = QGroupBox(t("Service-Intervall zurücksetzen (Kombi 17, Kanal 02)"))
        sl = QVBoxLayout(gb_sv)
        hinweis = QLabel(t("Für Kombis mit Service-Anzeige ab etwa 1998: Anpassungskanal 02 auf 0. "
                           "vagdiag liest den Kanal vorher, sichert den alten Wert und liest danach "
                           "zurück. Ohne Kanal 02 geht es nur am Kombi selbst."))
        hinweis.setWordWrap(True)
        sl.addWidget(hinweis)
        sl.addWidget(self._notiz(t("Dafür erst links {steuergeraet} öffnen.",
                                   steuergeraet=adressen.text(KOMBI))))
        self.lb_sv_grund = self._grund_label()
        sl.addWidget(self.lb_sv_grund)
        zeile = QHBoxLayout()
        self.bt_service = QPushButton(t("Lesen und zurücksetzen …"))
        zeile.addWidget(self.bt_service)
        zeile.addStretch(1)
        sl.addLayout(zeile)
        ev.addWidget(gb_sv)

        gb_stg = QGroupBox(t("Stellglieddiagnose (geöffnetes Steuergerät)"))
        gl = QVBoxLayout(gb_stg)
        hinweis = QLabel(t(
            "Steuert die Stellglieder des geöffneten Steuergeräts nacheinander an – im Kombi "
            "z. B. Zeiger, Lampen und Gong, im Motor Relais und Ventile. Zündung an, Motor aus, "
            "Auto steht. „Weiter“ schaltet zum nächsten Stellglied, „Stopp“ hört auf; danach "
            "verbindet vagdiag neu. Bei Bremsen (03, 23, 53), Airbag (15), Wegfahrsperre (25), "
            "Niveauregulierung (34) und Lenkung (44) nennt vagdiag vorher die möglichen Schäden "
            "und fragt nach. Bei KWP2000 experimentell."))
        hinweis.setWordWrap(True)
        gl.addWidget(hinweis)
        gl.addWidget(self._notiz(t("Gilt für das Steuergerät, das links geöffnet ist – erst "
                                   "dort öffnen, dann hier starten.")))
        self.lb_stg_grund = self._grund_label()
        gl.addWidget(self.lb_stg_grund)
        zeile = QHBoxLayout()
        self.bt_stg_start = QPushButton(t("Starten …"))
        self.bt_stg_weiter = QPushButton(t("Weiter"))
        self.bt_stg_ende = QPushButton(t("Stopp"))
        for w in (self.bt_stg_start, self.bt_stg_weiter, self.bt_stg_ende):
            zeile.addWidget(w)
        zeile.addStretch(1)
        gl.addLayout(zeile)
        self.lb_stg_aktuell = QLabel("—")
        self.lb_stg_aktuell.setFont(gross)
        gl.addWidget(self.lb_stg_aktuell)
        self.lb_stg = QLabel(t("Bereit."))
        self.lb_stg.setWordWrap(True)
        gl.addWidget(self.lb_stg)
        # Liste der Stellglieder – nur Übersicht, gemerkt aus dem letzten Durchlauf
        self.lb_stg_liste = QLabel()
        self.lb_stg_liste.setWordWrap(True)
        gl.addWidget(self.lb_stg_liste)
        self.lw_stg = QListWidget()
        self.lw_stg.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.lw_stg.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lw_stg.setMaximumHeight(130)
        self.lw_stg.setToolTip(t("Nur Übersicht: Die Reihenfolge gibt das Steuergerät vor, "
                                 "weiter geht es mit „Weiter“."))
        gl.addWidget(self.lw_stg)
        ev.addWidget(gb_stg)

        self.chk_sim_motor_aus = QCheckBox(t("Simulator: Motor aus (Zündung an)"))
        self.chk_sim_motor_aus.setToolTip(t("Nur im Simulator: hält den Motor an, damit sich "
                                            "Grundeinstellung und Stellglieddiagnose des Motors "
                                            "ausprobieren lassen."))
        ev.addWidget(self.chk_sim_motor_aus)
        self.tx_experte = QPlainTextEdit()
        self.tx_experte.setReadOnly(True)
        self.tx_experte.setMaximumBlockCount(2000)
        ev.addWidget(self.tx_experte, 1)

        self.bt_dk_start.clicked.connect(self._dk_start)
        self.bt_dk_abbrechen.clicked.connect(self._dk_abbrechen)
        self.bt_service.clicked.connect(self._service_start)
        self.bt_stg_start.clicked.connect(self._stg_start)
        self.bt_stg_weiter.clicked.connect(self._stg_weiter)
        self.bt_stg_ende.clicked.connect(self._stg_ende)
        self.chk_sim_motor_aus.toggled.connect(self._sim_motor_aus)
        self._zeige_expertenstatus()
        self._stg_liste_zeigen()
        # Hinweise, Gründe und Liste brauchen Platz – auf kleinen Bildschirmen rollen
        rahmen = QScrollArea()
        rahmen.setWidgetResizable(True)
        rahmen.setFrameShape(QFrame.Shape.NoFrame)
        rahmen.setWidget(seite)
        return rahmen

    @staticmethod
    def _notiz(text: str) -> QLabel:
        """Fester Hinweis im Reiter Experte (z. B. welches Steuergerät links offen sein muss)."""
        notiz = QLabel(text)
        notiz.setWordWrap(True)
        notiz.setStyleSheet("font-style:italic;")
        return notiz

    @staticmethod
    def _grund_label() -> QLabel:
        """Darunter: ob die Funktion gerade geht – und wenn nicht, warum."""
        grund = QLabel()
        grund.setWordWrap(True)
        return grund

    # ============================================================ Hilfen
    def _ist_sim(self) -> bool:
        return self.cb_interface.currentIndex() in (SIM, SIM_KWP2000)

    def _ziel_zeilen(self, kennung: tuple) -> str:
        """Für jede Rückfrage, die etwas am Steuergerät ändert: welches Gerät genau, und ob
        Simulator oder Auto – damit niemand „im Simulator übt“, während das Kabel steckt."""
        port = getattr(self.sitzung, "_port", None)
        sim = port.simulator if port is not None else self._ist_sim()
        ziel = (t("Ziel: Simulator – kein Auto") if sim else
                t("Ziel: ECHTES FAHRZEUG über das Kabel"))
        return t("Steuergerät: {kennung}", kennung=kennung_text(kennung)) + "\n" + ziel

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
                    return sim_port(kwp2000_motor=True, kwp2000_kombi=True)
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
        self.sitzung.experte = self._experte
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
                and not self._beschaeftigt and not self._laeuft_etwas())

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
                 or self._fahrt_laeuft or self._scan_laeuft or self._grundeinstellung_laeuft
                 or self._stellglied_laeuft)
        ftdi = not self._ist_sim()
        kombi = verbunden and self._verbindung.adresse == KOMBI
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
        # Während etwas anderes läuft (Scan, Expertenfunktion …), startet keine Messung
        self.bt_mwb_start.setEnabled((frei and verbunden and not aktiv) or self._mwb_laeuft)
        self.bt_suche.setEnabled((frei and verbunden and not aktiv) or self._suche_laeuft)
        self.bt_anp.setEnabled(verbunden or self._anp_suche_laeuft)
        self.bt_km.setEnabled(frei and kombi and not aktiv)
        self.bt_anp_lesen.setEnabled(frei and verbunden and not aktiv)
        self.bt_anp_suche.setEnabled((frei and verbunden and not aktiv) or self._anp_suche_laeuft)
        fahrt = self._fahrt_laeuft
        self.bt_fahrt.setEnabled((frei and not aktiv) or (fahrt and not self._fahrt_endet))
        self.bt_fahrt_ereignis.setEnabled(fahrt and not self._fahrt_endet)
        self.bt_fahrt_abbrechen.setEnabled(fahrt)
        for feld in (self.le_fahrt_gruppen, self.sp_fahrt_kombi, self.sp_fahrt_abs,
                     self.sp_fahrt_besuch, self.chk_fahrt_pruefung):
            feld.setEnabled(not fahrt)
        self.chk_fahrt_airbag.setEnabled(not fahrt and self.chk_fahrt_pruefung.isChecked())
        laeuft_scan = self._scan_laeuft
        self.bt_scan.setEnabled(not fahrt)
        self.bt_scan_start.setEnabled((frei and not aktiv) or laeuft_scan)
        self.cb_scan_umfang.setEnabled(not laeuft_scan)
        self.chk_scan_fehler.setEnabled(not laeuft_scan)
        self.chk_scan_airbag.setEnabled(not laeuft_scan)
        self.bt_scan_bericht.setEnabled(not laeuft_scan and bool(self._scan_eintraege))
        self.bt_ident_speichern.setEnabled(self._ident_stand is not None)
        self.bt_fehler_speichern.setEnabled(self._fehler_stand is not None)
        self.bt_anp_speichern.setEnabled(bool(self._anp_daten) and not self._anp_suche_laeuft)
        ex = self._experte
        ge = self._grundeinstellung_laeuft
        sg = self._stellglied_laeuft
        self.akt_experte.setEnabled(frei and not aktiv)
        self.cb_dk_gruppe.setEnabled(ex and not ge)
        # Ob eine Expertenfunktion gerade geht und warum nicht – eine Quelle für Knopf und Text
        verfuegbar = verfuegbarkeit(ex, self._verbindung, self._beschaeftigt, self._was_laeuft())
        for name, knopf, grund, selbst in (
                ("drosselklappe", self.bt_dk_start, self.lb_dk_grund, ge),
                ("service", self.bt_service, self.lb_sv_grund, False),
                ("stellglied", self.bt_stg_start, self.lb_stg_grund, sg)):
            v = verfuegbar[name]
            knopf.setEnabled(v.ok)
            knopf.setToolTip("" if v.ok else v.text)
            self._grund_zeigen(grund, v, selbst)
        self.bt_dk_abbrechen.setEnabled(ge)
        self.bt_stg_weiter.setEnabled(sg and not self._stg_wartet)
        self.bt_stg_ende.setEnabled(sg)
        self.chk_sim_motor_aus.setVisible(not ftdi)
        self.chk_sim_motor_aus.setEnabled(not ftdi and frei and not aktiv)

    def _was_laeuft(self) -> str | None:
        """Was gerade läuft – für die Gründe im Reiter Experte (sonst None)."""
        for an, name in ((self._mwb_laeuft, N_("Messwertblöcke")),
                         (self._suche_laeuft, N_("Gruppensuche")),
                         (self._anp_suche_laeuft, N_("Kanalsuche")),
                         (self._fahrt_laeuft, N_("Fahrtenschreiber")),
                         (self._scan_laeuft, N_("Scan")),
                         (self._grundeinstellung_laeuft, N_("Grundeinstellung")),
                         (self._stellglied_laeuft, N_("Stellglieddiagnose"))):
            if an:
                return t(name)
        return None

    @staticmethod
    def _grund_zeigen(label: QLabel, v, selbst: bool) -> None:
        """✓ bereit, ⚠ bereit mit Warnung, ✗ geht nicht – mit Grund. Läuft die Funktion
        selbst gerade, steht ihr Stand darunter, nicht hier."""
        label.setVisible(not selbst)
        if selbst:
            return
        zeichen = "✗" if not v.ok else "⚠" if v.warnung else "✓"
        label.setText(f"{zeichen} {v.text}")

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
        if self.chk_sim_motor_aus.isChecked():
            self.chk_sim_motor_aus.setChecked(False)   # neuer Simulator: Motor läuft wieder
        self._titel_setzen()
        self._aktualisiere_knoepfe()

    def _titel_setzen(self) -> None:
        titel = t("VAG-Diagnose {version} – KW1281/KWP2000 über KKL-Kabel",
                  version=__version__)
        if self._ist_sim():
            titel += "  [" + t("SIMULATOR") + "]"
        if self._experte:
            titel += "  [" + t("EXPERTENMODUS") + "]"
        self.setWindowTitle(titel)

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
                or self._anp_suche_laeuft or self._fahrt_laeuft or self._scan_laeuft
                or self._grundeinstellung_laeuft or self._stellglied_laeuft)

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

    def _reiter_gewechselt(self, index: int) -> None:
        if index in STEUERGERAETE_REITER:
            self._steuergeraete_reiter = index

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
            self._ident_stand = None
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
        self._fehler_stand = None
        self.lb_fehler.setText(t("Noch nicht gelesen."))
        self._stg_liste_zeigen()
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
        hinweise = []
        if verbindung.protokoll == "KWP2000":
            hinweise.append(t("KWP2000: vagdiag liest die Kanäle über die VAG-Anpassungsroutine "
                              "– an echten Steuergeräten bisher wenig geprüft. Manche verlangen "
                              "dafür eine Anmeldung; vagdiag meldet sich nicht an."))
        if verbindung.adresse == KOMBI:
            hinweise.append(t("Kombi: Bei vielen VAG-Kombis ist Kanal 09 der Kilometerstand in "
                              "10-km-Schritten – nicht bei jedem, deshalb mit der Anzeige im "
                              "Kombi vergleichen."))
        self.lb_anp_hinweis.setText(" ".join(hinweise))
        # der zuletzt benutzte Reiter eines Steuergeräts (z. B. Experte) – gesendet wird
        # dadurch nichts, Fehler und Messwerte liest erst der Knopf
        self.tabs.setCurrentIndex(self._steuergeraete_reiter)
        self.statusBar().showMessage(
            t("Verbunden: {steuergeraet} – {protokoll}, {baud} Baud, Kabel-Echo {echo}",
              steuergeraet=adressen.text(verbindung.adresse), protokoll=verbindung.protokoll,
              baud=verbindung.baud, echo=sprache.ja_nein(verbindung.echo)))

    def _zeige_ident(self, v: Verbindung) -> None:
        sim = self._ist_sim()
        self.tx_ident.setPlainText("\n".join(ident.zeilen(v, sim)))
        self._ident_stand = (v, sim)

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
            if daten.kennung != self._stg_liste_kennung and not self._stellglied_laeuft:
                self._stg_liste_zeigen()
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
        elif art == "scan":
            self._scan_ereignis(daten)
        elif art == "stellglied":
            self._stg_wartet = False
            self._stg_zeigen(daten)
        elif art == "grundeinstellung":
            self._dk_zeigen(daten["werte"])
            status = adp_status(daten["werte"])
            self.lb_dk.setText(t("Grundeinstellung läuft: {sekunden:.0f} von {dauer:.0f} s",
                                 sekunden=daten["sekunden"], dauer=daten["dauer"])
                               + (f" – {self._adp_text(status)}" if status else ""))
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
        kennung = self._verbindung.kennung if self._verbindung is not None else ()
        self._fehler_stand = (kennung, list(liste), time.strftime("%H:%M:%S"), self._sitzung_sim)
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
                                                uhrzeit=self._fehler_stand[2]))

    def _fehler_loeschen(self) -> None:
        if not self._bereit():
            return
        kennung = self._verbindung.kennung
        text = t("Fehlerspeicher von {steuergeraet} wirklich löschen?\n\nDabei werden auch die "
                 "Readiness-Codes zurückgesetzt (wichtig vor einer AU).",
                 steuergeraet=adressen.text(self._verbindung.adresse))
        text += "\n\n" + self._ziel_zeilen(kennung)
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
        self._auftrag("loeschen", self.sitzung.fehler_loeschen(kennung))

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
        self._anp_daten = {}
        self._aktualisiere_knoepfe()

    def _anp_zeile(self, kanal: int, werte: tuple[str, str, str]) -> None:
        if not self._anp_daten:
            # die Liste gehört zu dem Steuergerät, das beim ersten Eintrag geöffnet war
            # (beim Öffnen eines anderen wird sie geleert)
            self._anp_kennung = self._verbindung.kennung if self._verbindung is not None else ()
            self._anp_sim = self._sitzung_sim
        zeile = self._anp_zeilen.get(kanal)
        if zeile is None:
            zeile = self.tb_anp.rowCount()
            self.tb_anp.insertRow(zeile)
            self._anp_zeilen[kanal] = zeile
        gelesen = time.strftime("%H:%M:%S")
        for spalte, text in enumerate((f"{kanal:02d}",) + werte + (gelesen,)):
            self.tb_anp.setItem(zeile, spalte, QTableWidgetItem(text))
        self._anp_daten[kanal] = berichte.AnpassungsZeile(kanal, werte[0], werte[1], werte[2],
                                                          gelesen)

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
                                              + t("Fahrt wird beendet – Zündung an lassen, bis "
                                                  "„Fahrtenschreiber beendet“ erscheint"))
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
                                      + t("Ereignis markiert – lese den Fehlerspeicher des "
                                          "Motors, den des ABS beim nächsten Halt …"))

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

    # ============================================================ Scan
    def _scan_airbag_gewaehlt(self, an: bool) -> None:
        if an and not self._airbag_bestaetigt(t("Den Airbag beim Scan mit abfragen?")):
            self.chk_scan_airbag.setChecked(False)

    def _scan_umschalten(self) -> None:
        if self._scan_laeuft:
            if self.sitzung is not None:
                self.sitzung.abbrechen()
                self._scan_abgebrochen = True
                self.bt_scan_start.setText(t("Wird abgebrochen …"))
            return
        if self._laeuft_etwas():
            return
        sitzung = self._sitzung()
        if self.chk_scan_airbag.isChecked():
            sitzung.airbag_freigeben()        # beim Setzen des Häkchens bestätigt
        self._scan_alle = self.cb_scan_umfang.currentIndex() == 1
        liste = adressen.alle() if self._scan_alle else list(adressen.ADRESSEN)
        self._scan_eintraege = {}
        # alle Adressen: Zeilen nur für Adressen, die antworten (kommen während des Scans dazu)
        self._scan_zeilen = ({} if self._scan_alle
                             else {adresse: i for i, adresse in enumerate(liste)})
        self._scan_sim = self._sitzung_sim
        self._scan_abgebrochen = False
        self.tb_scan.setRowCount(len(self._scan_zeilen))
        for adresse, zeile in self._scan_zeilen.items():
            self._scan_zeile(zeile, [f"{adresse:02X}", adressen.name(adresse), "", "", "", "",
                                     "…"])
        self.tx_scan.clear()
        self._scan_laeuft = True
        self.bt_scan_start.setText(t("Abbrechen"))
        self.tabs.setCurrentIndex(TAB_SCAN)
        self.statusBar().showMessage(t("Scan läuft …"))
        bauds = BAUD_AUSWAHL[self.cb_baud.currentIndex()][1]    # z. B. 4800 für alte Autos
        self._auftrag("scan", sitzung.scannen(liste, self.chk_scan_fehler.isChecked(),
                                              self.chk_scan_airbag.isChecked(), bauds),
                      beschaeftigt=False)
        self._aktualisiere_knoepfe()

    def _scan_zeile(self, zeile: int, werte: list[str]) -> None:
        for spalte, wert in enumerate(werte):
            self.tb_scan.setItem(zeile, spalte, QTableWidgetItem(wert))

    def _scan_ereignis(self, daten: dict) -> None:
        adresse, eintrag = daten["adresse"], daten["eintrag"]
        zeile = self._scan_zeilen.get(adresse)
        if eintrag is None:
            self.lb_scan.setText(t("Frage {steuergeraet} ab … ({nummer} von {anzahl})",
                                   steuergeraet=adressen.text(adresse),
                                   nummer=daten["index"] + 1, anzahl=daten["anzahl"]))
            if zeile is not None:
                self.tb_scan.setItem(zeile, 6, QTableWidgetItem(t("frage ab …")))
            return
        self._scan_eintraege[adresse] = eintrag
        if zeile is None:
            if eintrag.status == "keine_antwort":
                return
            zeile = len(self._scan_zeilen)
            self._scan_zeilen[adresse] = zeile
            self.tb_scan.setRowCount(zeile + 1)
        v = eintrag.verbindung
        self._scan_zeile(zeile, [
            f"{adresse:02X}", adressen.name(adresse), v.teilenummer if v else "",
            v.bauteil if v else "", f"{v.protokoll}, {v.baud}" if v else "",
            eintrag.fehler_text, eintrag.status_text])

    def _fertig_scan(self, _kontext, eintraege, fehler) -> None:
        self._scan_laeuft = False
        self._verbindung = None
        self.bt_scan_start.setText(t("Scan starten"))
        if fehler:
            self.lb_scan.setText(t("Scan mit Fehler beendet."))
            self._zeige_fehler_dialog(t("Scan"), fehler)
            return
        for e in eintraege:
            self._scan_eintraege[e.adresse] = e
        for adresse, zeile in self._scan_zeilen.items():
            if adresse not in self._scan_eintraege:
                self.tb_scan.setItem(zeile, 6, QTableWidgetItem(t("nicht abgefragt")))
        if self._scan_alle and not self._scan_zeilen:
            self.tx_scan.setPlainText(t("Keine Adresse hat geantwortet."))
        gefunden = sum(1 for e in eintraege if e.status == "gefunden")
        text = t("Scan fertig: {gefunden} von {anzahl} Adressen antworten",
                 gefunden=gefunden, anzahl=len(eintraege))
        if self._scan_abgebrochen:
            text += " – " + t("abgebrochen")
        self.lb_scan.setText(text)
        self.statusBar().showMessage(text)

    def _scan_detail(self, zeile: int) -> None:
        adresse = next((a for a, z in self._scan_zeilen.items() if z == zeile), None)
        eintrag = self._scan_eintraege.get(adresse) if adresse is not None else None
        if eintrag is None:
            self.tx_scan.clear()
            return
        zeilen = [f"{adressen.text(adresse)}: {eintrag.status_text}"]
        if eintrag.verbindung is not None:
            zeilen += [""] + ident.zeilen(eintrag.verbindung, self._scan_sim)
        if eintrag.fehler is not None:
            zeilen.append("")
            zeilen += ([t("{anzahl} Fehler gespeichert:", anzahl=len(eintrag.fehler))]
                       + ["  " + f.zeile() for f in eintrag.fehler]
                       if eintrag.fehler else [t("Kein Fehler gespeichert")])
        if eintrag.meldung:
            zeilen += ["", eintrag.meldung]
        self.tx_scan.setPlainText("\n".join(zeilen))

    def _scan_oeffnen(self, zeile: int) -> None:
        adresse = next((a for a, z in self._scan_zeilen.items() if z == zeile), None)
        eintrag = self._scan_eintraege.get(adresse) if adresse is not None else None
        if eintrag is None or eintrag.status != "gefunden" or self._laeuft_etwas():
            return
        self.le_adresse.setText(f"{adresse:02X}")
        self._verbinden()

    def _scan_bericht_speichern(self) -> None:
        if not self._scan_eintraege:
            return
        eintraege = [self._scan_eintraege[a] for a in sorted(self._scan_eintraege)]
        self._text_speichern(t("Scan speichern"), berichte.dateiname("scan", None, self._scan_sim),
                             scan.bericht(eintraege, self._scan_sim, self._scan_abgebrochen,
                                          self._scan_alle))

    def _text_speichern(self, titel: str, name: str, zeilen: list[str]) -> None:
        """Was ein Reiter zeigt, als Textdatei – Vorschlag im Ordner der Messwerte."""
        vorschlag = einstellungen.ordner("csv_ordner") / name
        pfad, _ = QFileDialog.getSaveFileName(self, titel, str(vorschlag),
                                              t("Textdateien (*.txt)"))
        if not pfad:
            return
        try:
            Path(pfad).write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, titel, str(exc))
            return
        self.statusBar().showMessage(t("Gespeichert: {pfad}", pfad=pfad))

    def _ident_speichern(self) -> None:
        if self._ident_stand is None:
            return
        v, sim = self._ident_stand
        self._text_speichern(t("Identifikation speichern"),
                             berichte.dateiname("ident", v.adresse, sim),
                             berichte.identifikation(v, sim))

    def _fehler_speichern(self) -> None:
        if self._fehler_stand is None:
            return
        kennung, liste, gelesen, sim = self._fehler_stand
        self._text_speichern(t("Fehlerspeicher speichern"),
                             berichte.dateiname("fehler", kennung[0] if kennung else None, sim),
                             berichte.fehlerspeicher(kennung, liste, gelesen, sim))

    def _anp_speichern(self) -> None:
        if not self._anp_daten:
            return
        kennung = self._anp_kennung
        self._text_speichern(t("Anpassungskanäle speichern"),
                             berichte.dateiname("anpassung", kennung[0] if kennung else None,
                                                self._anp_sim),
                             berichte.anpassung(kennung, list(self._anp_daten.values()),
                                                self._anp_sim))

    # ============================================================ Expertenmodus
    def _experte_umschalten(self, an: bool) -> None:
        if an and not self._experte:
            antwort = QMessageBox.question(
                self, t("Expertenmodus"), t(EXPERTE_HINWEIS),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if antwort != QMessageBox.StandardButton.Yes:
                self.akt_experte.setChecked(False)
                return
        self._experte = bool(an)
        self.akt_experte.setChecked(self._experte)
        if self.sitzung is not None:
            self.sitzung.experte = self._experte
        self._titel_setzen()
        self._zeige_expertenstatus()
        self.statusBar().showMessage(t("Expertenmodus an – Änderungen am Steuergerät möglich.")
                                     if self._experte else t("Expertenmodus aus."))
        if self._experte:
            self.tabs.setCurrentIndex(TAB_EXPERTE)
        self._aktualisiere_knoepfe()

    def _zeige_expertenstatus(self) -> None:
        if self._experte:
            self.lb_experte.setText(t("EXPERTENMODUS AN – Änderungen werden im Steuergerät "
                                      "gespeichert. Alte Werte sichert vagdiag vorher, jeder "
                                      "Schreibblock steht im Protokoll."))
            self.lb_experte.setStyleSheet("background:#ef6c00; color:white; font-weight:bold; "
                                          "padding:6px; border-radius:4px;")
        else:
            self.lb_experte.setText(t("Expertenmodus aus. Die Funktionen auf dieser Seite ändern "
                                      "Werte im Steuergerät – einschalten über das Menü Experte "
                                      "→ Expertenmodus."))
            self.lb_experte.setStyleSheet("")

    def _sim_motor_aus(self, an: bool) -> None:
        if self._ist_sim():
            self._auftrag("sim_motor", self._sitzung().sim_motor_aus(an), beschaeftigt=False)

    def _fertig_sim_motor(self, _kontext, _ergebnis, fehler) -> None:
        if fehler:
            self._zeige_fehler_dialog(t("Simulator"), fehler)

    def _dk_gruppe(self) -> int:
        return list(DROSSELKLAPPE_GRUPPEN)[max(0, self.cb_dk_gruppe.currentIndex())]

    def _dk_zeigen(self, werte) -> None:
        namen = feldnamen_060(werte)
        for i in range(4):
            self._dk_titel[i].setText(namen[i] if i < len(namen) else
                                      t("Feld {nummer}", nummer=i + 1))
            self._dk_werte[i].setText(werte[i].text if i < len(werte) else "—")

    @staticmethod
    def _adp_text(status: str | None) -> str:
        return {"ok": t("ADP i.O."), "fehler": t("ADP ERROR"), "laeuft": t("ADP läuft")}.get(
            status, t("Status unbekannt"))

    def _experte_notiz(self, text: str) -> None:
        self.tx_experte.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")

    def _dk_start(self) -> None:
        if not self._experte or not self._bereit():
            return
        gruppe = self._dk_gruppe()
        self.lb_dk.setText(t("Prüfe die Bedingungen …"))
        self._auftrag("dk_pruefung", self.sitzung.drosselklappe_pruefen(gruppe), gruppe)

    def _fertig_dk_pruefung(self, gruppe, pruefung, fehler) -> None:
        if fehler:
            self.lb_dk.setText(t("Nicht gestartet."))
            self._zeige_fehler_dialog(t("Drosselklappe anlernen"), fehler)
            return
        self._dk_zeigen(pruefung.vorher)
        zeichen = {True: "✓", False: "✗", None: "?"}
        liste = "\n".join(f"{zeichen[b.ok]}  {t(b.name)}: {b.wert}" for b in pruefung.bedingungen)
        self._experte_notiz(t("Prüfung Gruppe {gruppe:03d}:", gruppe=gruppe) + "\n" + liste)
        if pruefung.verletzt:
            self.lb_dk.setText(t("Nicht gestartet – Bedingung nicht erfüllt."))
            text = (t("Nicht erfüllt – vagdiag startet die Grundeinstellung nicht:")
                    + "\n\n" + liste)
            if pruefung.fehler:
                text += "\n\n" + t("Fehler erst beheben oder löschen, danach die Zündung aus- und "
                                    "wieder einschalten.")
            QMessageBox.warning(self, t("Drosselklappe anlernen"), text)
            return
        text = (t("Grundeinstellung Gruppe {gruppe:03d} jetzt starten?", gruppe=gruppe)
                + "\n\n" + self._ziel_zeilen(pruefung.kennung)
                + "\n\n" + liste + "\n\n"
                + t("Während der nächsten 30 Sekunden: Gaspedal nicht berühren, Motor nicht "
                    "starten."))
        if pruefung.ungeprueft:
            text += "\n\n" + t("Nicht prüfbar – bitte selbst sicherstellen: {liste}", liste=", ".join(
                t(b.name) for b in pruefung.ungeprueft))
        antwort = QMessageBox.question(
            self, t("Drosselklappe anlernen"), text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if antwort != QMessageBox.StandardButton.Yes:
            self.lb_dk.setText(t("Nicht gestartet."))
            return
        self._grundeinstellung_laeuft = True
        self.lb_dk.setText(t("Grundeinstellung startet …"))
        self._experte_notiz(t("Grundeinstellung Gruppe {gruppe:03d} gestartet", gruppe=gruppe))
        self._auftrag("grundeinstellung", self.sitzung.drosselklappe_anlernen(
            gruppe, ohne_pruefung_ok=bool(pruefung.ungeprueft), kennung=pruefung.kennung),
            gruppe, beschaeftigt=False)
        self._aktualisiere_knoepfe()

    def _dk_abbrechen(self) -> None:
        if self._grundeinstellung_laeuft and self.sitzung is not None:
            self.sitzung.abbrechen()
            self.lb_dk.setText(t("Wird abgebrochen – zurück zu den Messwerten …"))

    def _fertig_grundeinstellung(self, gruppe, ergebnis, fehler) -> None:
        self._grundeinstellung_laeuft = False
        if fehler:
            self.lb_dk.setText(t("Mit Fehler beendet."))
            self._experte_notiz(t("Grundeinstellung mit Fehler beendet: {fehler}", fehler=fehler))
            self._zeige_fehler_dialog(t("Drosselklappe anlernen"), fehler)
            return
        self._dk_zeigen(ergebnis.nachher)
        feld4 = ergebnis.nachher[3].text if len(ergebnis.nachher) >= 4 else "–"
        if ergebnis.status == "ok":
            urteil = t("Laut Steuergerät erfolgreich ({text}).", text=feld4)
        elif ergebnis.status == "fehler":
            urteil = t("Das Steuergerät meldet einen Fehler ({text}). Bedingungen prüfen und "
                       "noch einmal versuchen.", text=feld4)
        elif ergebnis.status == "laeuft":
            urteil = t("Die Anpassung lief am Ende noch ({text}).", text=feld4)
        else:
            urteil = t("Ergebnis unklar – vagdiag kennt den Statustext in Feld 4 noch nicht "
                       "({text}). Bitte das Protokoll schicken.", text=feld4)
        if ergebnis.abgebrochen:
            urteil = t("Abgebrochen nach {sekunden:.0f} s.", sekunden=ergebnis.dauer) + " " + urteil
        if ergebnis.fehler_nachher is None:
            fehlertext = t("Fehlerspeicher danach nicht lesbar.")
        elif ergebnis.fehler_nachher:
            fehlertext = (t("{anzahl} Fehler gespeichert:", anzahl=len(ergebnis.fehler_nachher))
                          + "\n" + "\n".join("  " + f.zeile() for f in ergebnis.fehler_nachher))
        else:
            fehlertext = t("Kein Fehler gespeichert")
        self.lb_dk.setText(urteil)
        self._experte_notiz(urteil + "\n" + fehlertext)
        self.statusBar().showMessage(t("Grundeinstellung beendet."))
        QMessageBox.information(self, t("Drosselklappe anlernen"), urteil + "\n\n" + fehlertext)

    def _service_start(self) -> None:
        if not self._experte or not self._bereit():
            return
        self._auftrag("service_lesen", self.sitzung.service_lesen())

    def _fertig_service_lesen(self, _kontext, anpassung, fehler) -> None:
        if fehler:
            self._zeige_fehler_dialog(t("Service-Intervall zurücksetzen"), fehler)
            return
        self._experte_notiz(anpassung.text)
        kennung = self._verbindung.kennung if self._verbindung is not None else ()
        antwort = QMessageBox.question(
            self, t("Service-Intervall zurücksetzen"),
            t("{kanal}\n\nAuf 0 zurücksetzen? Der alte Wert wird vorher gesichert.",
              kanal=anpassung.text) + "\n\n" + self._ziel_zeilen(kennung),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if antwort != QMessageBox.StandardButton.Yes:
            return
        self._auftrag("service", self.sitzung.service_zuruecksetzen(anpassung.wert,
                                                                    kennung=kennung),
                      anpassung.wert)

    def _fertig_service(self, _alt, ergebnis, fehler) -> None:
        if fehler:
            self._experte_notiz(t("Service-Intervall nicht zurückgesetzt: {fehler}",
                                  fehler=fehler))
            self._zeige_fehler_dialog(t("Service-Intervall zurücksetzen"), fehler)
            return
        text = t("Kanal 02: vorher {alt}, jetzt {neu}. Sicherung: {pfad}", alt=ergebnis.alt,
                 neu=ergebnis.neu, pfad=ergebnis.sicherung)
        self._experte_notiz(text)
        self.statusBar().showMessage(t("Service-Intervall zurückgesetzt."))
        QMessageBox.information(self, t("Service-Intervall zurücksetzen"), text)

    def _stg_start(self) -> None:
        if not self._experte or not self._bereit():
            return
        self.lb_stg.setText(t("Prüfe …"))
        self._auftrag("stg_pruefung", self.sitzung.stellglied_pruefen())

    def _fertig_stg_pruefung(self, _kontext, pruefung, fehler) -> None:
        if fehler:
            self.lb_stg.setText(t("Nicht gestartet."))
            self._zeige_fehler_dialog(t("Stellglieddiagnose"), fehler)
            return
        zeichen = {True: "✓", False: "✗", None: "?"}
        liste = "\n".join(f"{zeichen[b.ok]}  {t(b.name)}: {b.wert}" for b in pruefung.bedingungen)
        steuergeraet = adressen.text(pruefung.adresse)
        if liste:
            self._experte_notiz(t("Prüfung Stellglieddiagnose {steuergeraet}:",
                                  steuergeraet=steuergeraet) + "\n" + liste)
        if pruefung.verletzt:
            log.info(t("EXPERTE: Stellglieddiagnose %02X nicht gestartet – Bedingung nicht "
                       "erfüllt: %s"), pruefung.adresse,
                     ", ".join(f"{t(b.name)} ({b.wert})" for b in pruefung.verletzt))
            self.lb_stg.setText(t("Nicht gestartet – Bedingung nicht erfüllt."))
            QMessageBox.warning(self, t("Stellglieddiagnose"),
                                t("Nicht erfüllt – vagdiag startet die Stellglieddiagnose nicht:")
                                + "\n\n" + liste)
            return
        gefahr = pruefung.gefahr
        if gefahr is not None and not self._stg_warnung_bestaetigt(pruefung, steuergeraet):
            self.lb_stg.setText(t("Nicht gestartet – Warnung nicht bestätigt."))
            self._experte_notiz(t("Warnung ({art}) nicht bestätigt – nicht gestartet.",
                                  art=gefahr.name))
            return
        text = t("Stellglieddiagnose an {steuergeraet} starten?", steuergeraet=steuergeraet)
        text += "\n\n" + self._ziel_zeilen(pruefung.kennung)
        if liste:
            text += "\n\n" + liste
        text += "\n\n" + t("Zündung an, Motor aus, Auto steht. Das Steuergerät steuert seine "
                            "Stellglieder nacheinander an: Zeiger bewegen sich, Relais und Ventile "
                            "schalten, Lüfter können anlaufen. Nicht in Lüfter oder Gestänge "
                            "greifen.")
        hinweis = stellglied.hinweis(pruefung.adresse)
        if hinweis:
            text += "\n\n" + t("Bei diesem Steuergerät: {hinweis}", hinweis=hinweis)
        if gefahr is not None:
            text += "\n\n" + t("Denk an die Vorbereitung aus der Warnung ({art}).",
                                art=gefahr.name)
        text += "\n\n" + t("Kommt {sekunden:.0f} Sekunden lang kein „Weiter“, beendet vagdiag "
                            "die Stellglieddiagnose von selbst.", sekunden=self._schritt_max())
        if pruefung.kwp2000:
            text += "\n\n" + t("KWP2000: experimentell – der Ablauf stammt aus einem Mitschnitt "
                                "an einem Diesel-Steuergerät (EDC16). Dort steuert der erste "
                                "Schritt das angezeigte Stellglied an, der zweite schaltet weiter.")
        if pruefung.ungeprueft:
            text += "\n\n" + t("Nicht prüfbar – bitte selbst sicherstellen: {liste}",
                                liste=", ".join(t(b.name) for b in pruefung.ungeprueft))
        antwort = QMessageBox.question(
            self, t("Stellglieddiagnose"), text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if antwort != QMessageBox.StandardButton.Yes:
            log.info(t("EXPERTE: Stellglieddiagnose %02X – Rückfrage mit Nein beantwortet, "
                       "nicht gestartet"), pruefung.adresse)
            self.lb_stg.setText(t("Nicht gestartet."))
            return
        self._stellglied_laeuft = True
        self._stg_wartet = True
        self.lb_stg_aktuell.setText("—")
        self.lb_stg.setText(t("Stellglieddiagnose startet …"))
        self._experte_notiz(t("Stellglieddiagnose an {steuergeraet} gestartet",
                              steuergeraet=steuergeraet))
        self._stg_lauf_kennung = tuple(pruefung.kennung)
        if self._stg_liste_kennung != self._stg_lauf_kennung:
            self._stg_liste_zeigen(self._stg_lauf_kennung)
        self._stg_pos = None
        self._auftrag("stellglied", self.sitzung.stellglieddiagnose(
            ohne_pruefung_ok=bool(pruefung.ungeprueft), kennung=pruefung.kennung,
            gefahr_bestaetigt=gefahr.art if gefahr is not None else None),
            pruefung.adresse, beschaeftigt=False)
        self._aktualisiere_knoepfe()

    def _stg_warnung_bestaetigt(self, pruefung, steuergeraet: str) -> bool:
        """Bremsen, Airbag, Wegfahrsperre, Lenkung, Niveauregulierung: Warnung mit den
        möglichen Schäden für genau dieses Steuergerät (Vorgabe: Nein)."""
        gefahr = pruefung.gefahr
        text = (t("Achtung: {steuergeraet} gehört zu „{art}“. Eine Stellglieddiagnose kann "
                  "hier Schaden anrichten.", steuergeraet=steuergeraet, art=gefahr.name)
                + "\n\n" + self._ziel_zeilen(pruefung.kennung)
                + "\n\n" + t("Mögliche Schäden:") + "\n" + gefahr.schaeden
                + "\n\n" + t("vagdiag kennt die Stellglieder dieses Steuergeräts nicht im "
                              "Einzelnen. Nur weitermachen, wenn du weißt, was dabei angesteuert "
                              "wird, und die Vorbereitung erledigt ist.")
                + "\n\n" + t("Warnung gelesen – weiter zur Rückfrage?"))
        antwort = QMessageBox.warning(
            self, t("Warnung: {art}", art=gefahr.name), text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if antwort != QMessageBox.StandardButton.Yes:
            log.info(t("EXPERTE: Warnung (%s) für %s nicht bestätigt – nicht gestartet"),
                     gefahr.name, kennung_text(pruefung.kennung))
            return False
        log.warning(t("EXPERTE: Warnung (%s) für %s bestätigt"), gefahr.name,
                    kennung_text(pruefung.kennung))
        self._experte_notiz(t("Warnung ({art}) bestätigt.", art=gefahr.name))
        return True

    def _schritt_max(self) -> float:
        """So lange bleibt ein Stellglied höchstens ohne „Weiter“ angesteuert."""
        return getattr(self.sitzung, "stellglied_schritt_max", SCHRITT_MAX)

    def _stg_zeigen(self, daten: dict) -> None:
        aktuell = daten["stellglied"]
        nummer = daten["schritt"]
        self.lb_stg_aktuell.setText(aktuell.text)
        self._stg_markieren(aktuell.code)
        if not daten["kwp2000"]:
            zustand = t("Schritt {nummer}: wird angesteuert – „Weiter“ schaltet zum nächsten "
                        "Stellglied.", nummer=nummer)
        elif daten["gleich"]:
            zustand = t("Schritt {nummer}: angesteuert – „Weiter“ schaltet zum nächsten "
                        "Stellglied.", nummer=nummer)
        else:
            zustand = t("Schritt {nummer}: angezeigt – beim EDC16 steuert „Weiter“ es jetzt an.",
                        nummer=nummer)
        self.lb_stg.setText(zustand)
        self._experte_notiz(t("Stellglied {nummer}: {text}", nummer=nummer, text=aktuell.text))

    def _stg_liste_zeigen(self, kennung: tuple | None = None) -> None:
        """Gemerkte Stellglieder des geöffneten (oder des genannten) Steuergeräts – nur aus der
        Datei gelesen, ohne etwas an das Steuergerät zu senden."""
        if kennung is None and self._verbindung is not None:
            kennung = self._verbindung.kennung
        kennung = tuple(kennung or ())
        self._stg_liste_kennung = kennung
        self._stg_codes, self._stg_pos = [], None
        if len(kennung) != 3:
            kopf = t("Liste der Stellglieder: erst links ein Steuergerät öffnen.")
        else:
            adresse, teilenummer, bauteil = kennung
            gemerkt = stellglied.liste_laden(teilenummer, bauteil, sim=self._sitzung_sim)
            if gemerkt is None:
                kopf = t("Für {steuergeraet} hat vagdiag noch keine Liste der Stellglieder. Sie "
                         "entsteht beim ersten Durchlauf – vorher lesen lässt sie sich nicht: "
                         "Das Steuergerät nennt das nächste Stellglied erst, wenn es es "
                         "ansteuert.", steuergeraet=adressen.text(adresse))
            else:
                self._stg_codes = list(gemerkt.codes)
                umfang = (t("bis zum Ende") if gemerkt.vollstaendig else
                          t("vorzeitig beendet – danach können weitere kommen"))
                kopf = t("Stellglieder von {steuergeraet} laut Durchlauf vom {stand} "
                         "({anzahl}, {umfang}). Nur Übersicht – die Reihenfolge gibt das "
                         "Steuergerät vor:", steuergeraet=adressen.text(adresse),
                         stand=gemerkt.stand, anzahl=len(gemerkt.codes), umfang=umfang)
        self.lb_stg_liste.setText(kopf)
        self._stg_liste_fuellen()

    def _stg_markieren(self, code: int) -> None:
        """Das gerade angesteuerte Stellglied hervorheben – fehlt es in der Liste (erster
        Durchlauf, andere Reihenfolge), kommt es dazu."""
        if self._stg_lauf_kennung and self._stg_liste_kennung != self._stg_lauf_kennung:
            self._stg_liste_zeigen(self._stg_lauf_kennung)
        start = self._stg_pos or 0
        pos = next((i for i in range(start, len(self._stg_codes)) if self._stg_codes[i] == code),
                   None)
        if pos is None:
            pos = next((i for i, c in enumerate(self._stg_codes) if c == code), None)
        if pos is None:
            self._stg_codes.append(code)
            pos = len(self._stg_codes) - 1
        self._stg_pos = pos
        self._stg_liste_fuellen()

    def _stg_liste_fuellen(self) -> None:
        self.lw_stg.clear()
        self._stg_anzeige = []
        markiert = None
        for i, code in enumerate(self._stg_codes):
            zeile = ("▶ " if i == self._stg_pos else "    ") + stellglied.Stellglied(code).text
            eintrag = QListWidgetItem(zeile)
            if i == self._stg_pos:
                schrift = eintrag.font()
                schrift.setBold(True)
                eintrag.setFont(schrift)
                markiert = eintrag
            self.lw_stg.addItem(eintrag)
            self._stg_anzeige.append(zeile)
        self.lw_stg.setVisible(bool(self._stg_codes))
        if markiert is not None:
            self.lw_stg.scrollToItem(markiert)

    def _stg_weiter(self) -> None:
        if self._stellglied_laeuft and not self._stg_wartet and self.sitzung is not None:
            self._stg_wartet = True
            self.sitzung.stellglied_weiter()
            self.lb_stg.setText(t("Schalte weiter …"))
            self._aktualisiere_knoepfe()

    def _stg_ende(self) -> None:
        if self._stellglied_laeuft and self.sitzung is not None:
            self._stg_wartet = True
            self.sitzung.stellglied_beenden()
            self.lb_stg.setText(t("Wird beendet – danach verbindet vagdiag neu …"))
            self._aktualisiere_knoepfe()

    def _fertig_stellglied(self, _adresse, ergebnis, fehler) -> None:
        self._stellglied_laeuft = False
        self._stg_wartet = False
        self.lb_stg_aktuell.setText("—")
        if self._stg_lauf_kennung:
            self._stg_liste_zeigen(self._stg_lauf_kennung)
        if fehler:
            self.lb_stg.setText(t("Mit Fehler beendet."))
            self._experte_notiz(t("Stellglieddiagnose mit Fehler beendet: {fehler}",
                                  fehler=fehler))
            self._zeige_fehler_dialog(t("Stellglieddiagnose"), fehler)
            return
        verschiedene = list(dict.fromkeys(s.code for s in ergebnis.schritte))
        texte = {s.code: s.text for s in ergebnis.schritte}
        grund = {
            "ende": t("Das Steuergerät meldet das Ende der Liste."),
            "durch": t("Alle Stellglieder einmal durch – wieder beim ersten."),
            "kein_status": t("Das Steuergerät meldet kein weiteres Stellglied."),
            "max": t("Nach {anzahl} Schritten beendet.", anzahl=len(ergebnis.schritte)),
            "zeit": t("Nach {sekunden:.0f} Sekunden ohne „Weiter“ von selbst beendet.",
                      sekunden=self._schritt_max()),
            "beendet": t("Von dir beendet."),
            "abgebrochen": t("Abgebrochen."),
        }.get(ergebnis.grund, ergebnis.grund)
        kopf = t("Stellglieddiagnose beendet: {anzahl} Stellglieder in {sekunden:.0f} s.",
                 anzahl=len(verschiedene), sekunden=ergebnis.dauer) + " " + grund
        text = kopf
        if verschiedene:
            text += "\n\n" + "\n".join(f"  {texte[c]}" for c in verschiedene)
        text += "\n\n" + (t("Die Verbindung wurde beendet und neu aufgebaut.")
                           if ergebnis.wieder_verbunden else
                           t("Die Verbindung wurde beendet – bitte das Steuergerät neu öffnen."))
        self.lb_stg.setText(kopf)
        self._experte_notiz(text)
        self.statusBar().showMessage(t("Stellglieddiagnose beendet."))
        QMessageBox.information(self, t("Stellglieddiagnose"), text)

    # ============================================================ Ergebnisse
    def _fertig(self, aufgabe: str, kontext, ergebnis, fehler) -> None:
        if aufgabe not in ("mwb", "suche", "anpsuche", "fahrt", "scan", "grundeinstellung",
                           "sim_motor", "stellglied"):
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

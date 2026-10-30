# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""VAG-Diagnose über ein KKL-Kabel (FTDI FT232R) – Protokolle KW1281 und KWP2000.

Verbindungsaufbau mit automatischer Baudrate und Protokollerkennung (KWP2000
auch per Fast-Init zum Motor), Identifikation, Fehlerspeicher lesen/löschen,
Messwertblöcke mit Feldnamen, Anpassungskanäle lesen (nur lesen, KW1281 und
KWP2000), Kilometerstand aus dem Kombi, Fahrtenschreiber, Scan der üblichen oder
aller Adressen, OBD-II-Test mit Readiness (nur lesen) und ein Expertenmodus
(Drosselklappe anlernen, Service-Intervall zurücksetzen, Stellglieddiagnose).
Linux (pyftdi) und Windows (FTDI-Treiber/D2XX), Oberfläche und Ausgaben auf
Deutsch oder Englisch.
"""

__version__ = "0.9.1"

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""VAG-Diagnose über ein KKL-Kabel (FTDI FT232R) – Protokolle KW1281 und KWP2000.

Verbindungsaufbau mit automatischer Baudrate und Protokollerkennung (KWP2000
auch per Fast-Init zum Motor), Identifikation, Fehlerspeicher lesen/löschen,
Messwertblöcke mit Feldnamen und abschaltbarer Verlaufskurve, Anpassungskanäle
lesen (nur lesen, KW1281 und KWP2000), Kilometerstand aus dem Kombi,
Fahrtenschreiber (auch passiv wie eine Dashcam, fortgesetzt nach dem Neustart), Scan
der üblichen oder aller Adressen, OBD-II-Test mit Readiness (nur lesen) und ein
Expertenmodus (Drosselklappe anlernen, Service-Intervall zurücksetzen,
Stellglieddiagnose – in der Oberfläche und auf der Kommandozeile).
Linux (pyftdi) und Windows (FTDI-Treiber/D2XX), Oberfläche und Ausgaben auf
Deutsch oder Englisch; Installer je System im Ordner installation, Autostart beim
Anmelden auf Wunsch.
"""

__version__ = "1.0.3"

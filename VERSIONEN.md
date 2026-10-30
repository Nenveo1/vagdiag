# vagdiag – Versionen

Was sich von Version zu Version geändert hat, die neueste zuerst.

## 1.0.3 (30.10.2026)
- Der passive Fahrtenschreiber läuft nach einem Neustart weiter: Lief er beim Schließen
  von vagdiag (oder beim Ausschalten des Rechners), startet er beim nächsten Öffnen von
  selbst. „Fahrt beenden“ oder „Sofort abbrechen“ schalten das ab.
- Autostart beim Anmelden: Der Installer fragt danach (Vorauswahl Nein), im Programm
  geht es über *Datei → Beim Anmelden starten*.
- Kabel nach Ruhezustand oder kurzem Abziehen: vagdiag öffnet es beim nächsten Versuch
  neu, statt bis zum Programmende mit USB-Fehlern hängen zu bleiben. Fehlt das Kabel,
  wartet der passive Fahrtenschreiber still darauf (eine Notiz statt einer alle paar
  Sekunden).
- USB-Fehler nennen den echten Grund statt „UsbError: {exc}“ (Fehler in pyftdi).
- Texte der Oberfläche gekürzt, README neu gegliedert, diese Versionsdatei.

## 1.0.2 (29.10.2026)
- Installer und Startdateien funktionieren auch in der fish-Shell (Standard unter
  CachyOS), auch mit `.` oder `source` gestartet.

## 1.0.1 (29.10.2026)
- Verlaufskurve abschaltbar und standardmäßig aus – auf langsamen Rechnern (TV-Box mit
  RK3318) kostete das Zeichnen zu viel Zeit.
- Der Reiter Messwertblöcke scrollt als Ganzes; das Mausrad verstellt Zahlen und Listen
  nur, wenn das Feld angeklickt ist.
- Ordner `installation` mit einem Installer je System (Windows 10/11, CachyOS/Arch,
  Debian/Ubuntu/Mint/Armbian, Alpine); PySide6 aus der Distribution, wo es sie gibt;
  unter Windows 10 PySide6 bis 6.12.
- `vagdiag-cli` findet das Programm auch aus einem anderen Ordner (Dienst, Aufgabe).

## 1.0.0 (28.10.2026)
- Passiver Fahrtenschreiber wie eine Dashcam: Ringspeicher mit den letzten 5 min bis
  5 h Fahrzeit, über Fahrten und Neustarts hinweg; F9 sichert die Zeitspanne; auch auf
  der Kommandozeile (`fahrt --passiv`, `fahrt-export`).
- Verlaufskurve der Messwertblöcke mit wählbarer Zeitachse.
- Gruppe 000 am ME7.5 mit vier benannten, umgerechneten Feldern; Gruppensuche ab 000.
- Alle Formeltypen aus KLineKWP1281Lib, Gruppen im Kopf-Rumpf-Format, unbenutzte
  Schalterstellen als „·“, richtige Nachkommastellen bei 16-Bit-Werten.
- Drosselklappe anlernen auch bei KWP2000 (experimentell); Expertenfunktionen auch auf
  der Kommandozeile.
- Adresszeile und Liste zeigen immer dasselbe Steuergerät.

## 0.9.1 (28.10.2026)
- Freie Software unter GPL-3.0-or-later, *Hilfe → Über vagdiag*, `NOTICE.txt`.
- Hinweis an Steuergeräten, an denen vagdiag nicht geprüft ist.
- Fehlertexte und Klartexte aus KLineKWP1281Lib (rund 9.700 Codes, auch C-, B- und
  U-Codes).
- Felder mit eigener Länge (Typen 5F, 76, 3F, A0) richtig ausgewertet; Einheit mg/Hub.
- Drosselklappe nur, wenn die Gruppe wie die Anpassung aufgebaut ist.
- Feldnamen lassen sich an eine Teilenummer binden.

## 0.9.0 (23.10.2026)
- OBD-II-Test: Readiness, Motorkontrollleuchte, OBD-Norm, Fahrgestellnummer – nur lesen.
- Gruppe 000 mit zehn Rohwerten.
- Marker während der Messung (F9).

## 0.8.1 (22.10.2026)
- Fahrtenschreiber: Startprüfung erst Wegfahrsperre, zuletzt der Motor; die
  Aufforderung zum Anlassen kommt mit den ersten Motorwerten; Fehlerspeicher nach
  Adressen sortiert.
- Eigene Fehlertexte für 193 VAG-Codes und 316 P-Codes (deutsch und englisch).
- Beim Öffnen eines Steuergeräts erscheint der zuletzt benutzte Reiter.
- Protokoll vermerkt Warnungen, Rückfragen und Abbrüche der Stellglieddiagnose.

## 0.8.0 (22.10.2026)
- „Speichern …“ in Identifikation, Fehlerspeicher, Anpassung und Scan (Textdateien).
- Stellglieddiagnose an allen Steuergeräten; bei Bremsen, Airbag, Wegfahrsperre, Lenkung
  und Niveauregulierung erst nach einer Warnung mit den möglichen Schäden.
- Im Reiter Experte steht unter jedem Knopf, warum er gerade nicht geht; die Liste der
  Stellglieder wird je Steuergerät gemerkt.
- Fahrtenschreiber: Stillstand erst nach zwei Werten 0 km/h; Zündung aus zählt nicht als
  Störung; jede Notiz auch im Protokoll.

## 0.7.2 (22.10.2026)
- Zeitwächter: Hängt der Rechner beim Senden, bricht vagdiag den Block ab, statt ein
  verspätetes Byte zu schicken. Protokolldatei in einem eigenen Thread.
- Nach einer abgebrochenen Verbindung eine Pause, bevor ein anderes Steuergerät gereizt
  wird.
- Rückfragen nennen genau das Steuergerät und ob Simulator oder Auto; meldet sich
  irgendwo ein Airbag, trennt vagdiag sofort.

## 0.7.1 (21.10.2026)
- Sicherheitskorrektur: Bei falschem Komplement sendet vagdiag den Block nicht zu Ende
  (0.2.0 bis 0.7.0 sendeten weiter). Schreibvorgänge werden nie wiederholt.
- Scan aller Adressen 01–7F, Stellglieddiagnose, Anpassungskanäle auch bei KWP2000.

## 0.7.0 (21.10.2026)
- Scan der üblichen Steuergeräte mit Bericht.
- Expertenmodus: Drosselklappe anlernen, Service-Intervall zurücksetzen.

## 0.6.1 (20.10.2026)
- Fahrtenschreiber besucht das ABS nur im Stand; mehr in der Zusammenfassung.
- Die letzten 256.000 Protokollzeilen bleiben im Speicher.

## 0.6.0 (20.10.2026)
- KWP2000 (Identifikation, Fehlerspeicher, Messwertblöcke), beim Motor auch per
  Fast-Init; Simulator mit KWP2000.

## 0.5.0 (20.10.2026)
- Windows 10/11 über den FTDI-Treiber (D2XX), Installer für Windows.

## 0.4.0 (19.10.2026)
- Fahrtenschreiber für eine ganze Fahrt mit Zusammenfassung.
- Oberfläche auf Englisch.
- Standardmäßig keine Dateien; Rückfrage vor dem Airbag.
- Gestörte Antworten werden erkannt und neu angefragt.

## 0.3.0 (19.10.2026)
- Feldnamen, Klartexte, Anpassungskanäle lesen, Kilometerstand aus dem Kombi, eigene
  Texte.

## 0.2.0 (19.10.2026)
- Codierung, Werkstattcode und Zusatzkennung; Min/Max, Gruppensuche, Neuverbinden bei
  Abbruch, wählbare Ordner.

## 0.1.0 (19.10.2026)
- Erste Fassung: Verbindung per 5-Baud-Reizung (KW1281), Identifikation,
  Fehlerspeicher lesen und löschen, Messwertblöcke mit CSV, Simulator.

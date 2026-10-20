# VAG-Diagnose über KKL-Kabel – Version 0.3

Linux-Programm für VW/Audi/Seat/Škoda mit K-Leitung (Protokoll KW1281), für ein
KKL-Kabel mit FT232RL. Gebaut für den Polo 6KV (ANW). Im Auto getestet mit
Motor (6K0 906 032 M, ME7.5.10), ABS, Kombi, Wegfahrsperre und Airbag.

**Kann diese Version:**

- Verbindung mit 5-Baud-Reizung, automatischer Baudrate (die funktionierende
  wird je Steuergerät gemerkt) und Protokollerkennung
- Identifikation mit Teilenummer, Bauteil, **Codierung, Werkstattcode** und
  **Zusatzkennung** (bei der Wegfahrsperre: Fahrgestellnummer und Immo-ID)
- Fehlerspeicher lesen (mit P-Code, Klartext soweit hinterlegt, Fehlerart) und löschen
- Messwertblöcke: bis zu 3 Gruppen live, **Feldnamen** für die Gruppen deiner
  Steuergeräte, **Min/Max je Feld**, **automatische CSV-Aufzeichnung**,
  **automatisches Neuverbinden** bei Abbruch (z. B. beim Anlassen)
- **Klartexte** statt Textnummern (z. B. „Öldruck 2 i. O.“ im Kombi)
- **Gruppensuche**: findet alle belegten Messwertgruppen eines Steuergeräts
- **Anpassungskanäle lesen** – nur lesen, einzeln oder als Suche
- **Kilometerstand** aus dem Kombi (Gruppe 002, sonst Anpassungskanal 09)
- Einstellbare Ordner für Protokolle und Messwerte
- Simulator mit Aufbau und Zeitverhalten deines Polos

Schreibende Funktionen (Codierung, Anpassung speichern, Grundeinstellung) sind
bewusst nicht drin. Anpassungskanäle werden ausschließlich gelesen.

---

## 1. Einrichtung (CachyOS)

```bash
sudo pacman -S --needed python libusb
cd vagdiag
./installieren.sh
```

Das Skript legt eine virtuelle Umgebung `.venv` an (pyftdi + PySide6) und
installiert die udev-Regel `70-kkl-ftdi.rules`. Danach das Kabel einmal ab- und
wieder anstecken.

**Update von 0.1/0.2:** Die ZIP-Datei im selben Ordner entpacken, in dem der
Ordner `vagdiag` liegt, und vorhandene Dateien überschreiben:
```bash
unzip -o vagdiag-0.3.0.zip
```
`.venv`, Einstellungen und Messdaten bleiben erhalten. `./installieren.sh` ist
für 0.3 nicht nötig (keine neuen Pakete).

Falls PySide6 per pip nicht klappt:
```bash
sudo pacman -S pyside6
rm -rf .venv && python -m venv --system-site-packages .venv
.venv/bin/pip install pyftdi
```

**Wichtig:** Das Programm spricht den FTDI-Chip direkt per USB an (pyftdi).
Solange es läuft, verschwindet `/dev/ttyUSB0` – das ist normal.

## 2. Wo die Dateien landen

| Was | Standard-Ordner |
|---|---|
| Protokolle (jedes Byte, für die Fehlersuche) | `~/vagdiag-daten/logs` |
| Messwerte (CSV) | `~/vagdiag-daten/messwerte` |
| Einstellungen | `~/.config/vagdiag/einstellungen.json` |

Ändern: in der Oberfläche über **Datei → Einstellungen**, dort gibt es auch
„Öffnen“-Knöpfe für beide Ordner. Auf der Kommandozeile:
```bash
.venv/bin/python -m vagdiag.cli einstellungen --log-ordner-setzen ~/Diagnose/logs \
                                              --csv-ordner-setzen ~/Diagnose/messwerte
```

Die CSV-Dateien heißen `messwerte-<Adresse>-<Datum>-<Uhrzeit>.csv` (Semikolon,
Dezimalkomma – öffnet direkt in LibreOffice). Aufnahmen aus dem Simulator
heißen `sim-messwerte-…` und beginnen mit der Zeile „Simulator – keine echten
Fahrzeugdaten“. In der Spalte „Ereignis“ stehen beim ersten Auftreten einer
Gruppe ihre Feldnamen sowie Verbindungsabbrüche, damit Lücken erkennbar sind.

## 3. Oberfläche

```bash
./vagdiag.sh
```

Links: Interface, Steuergerät, Funktionen. Rechts: Identifikation,
Fehlerspeicher, Messwertblöcke, Anpassung. Unten: Protokoll.

- Über jedem Messwert steht der Feldname, sofern die Gruppe bekannt ist (siehe
  Abschnitt 9). Den Rohwert zeigt der Tooltip.
- Ist der **Simulator** gewählt, steht oben ein roter Hinweis und im
  Fenstertitel „[SIMULATOR]“. Der Simulator merkt sich keine Baudraten, damit
  beim Auto nichts Falsches zuerst probiert wird.

## 4. Bordspannung beim Anlassen messen

1. Zündung an, Motorelektronik (01) öffnen, Reiter **Messwertblöcke**.
2. **Nur Gruppe 004** aktivieren (Feld 2 ist die Bordspannung). Mit drei
   aktiven Gruppen kommt jede nur etwa alle 0,9 s dran, mit einer etwa
   3,5-mal pro Sekunde.
3. **Start**, dann den Motor anlassen, laufen lassen, **Stopp**.
4. Unter jedem Feld steht Min/Max; die CSV-Datei liegt im Messwert-Ordner.

Was du wissen solltest:
- Das Motorsteuergerät braucht rund 10 ms pro Byte, schneller geht es über
  die K-Leitung nicht. Den allerersten, sehr kurzen Einbruch beim Einspuren
  des Anlassers kann man damit verpassen, und das Steuergerät glättet seine
  Messung. Für den exakten Tiefstwert ist eine direkte Messung an der Batterie
  besser (Multimeter mit MIN/MAX).
- Deine Messung vom 19.10. (Version 0.2): Ruhe 11,9–12,0 V, beim Anlassen
  10,43 V (200 /min), danach 13,4–14,1 V – ohne Verbindungsabbruch.

Auf der Kommandozeile (bis Strg+C, mit CSV und Min/Max am Ende):
```bash
.venv/bin/python -m vagdiag.cli --adresse 01 gruppe 4 --dauer
```

## 5. Kilometerstand

Dein Kombi (TRW, 6K9 920 806) schickt im Kilometerstand-Feld (Gruppe 002,
Feld 1) den Wert FF FF – „kein Wert“. Deshalb liest vagdiag jetzt zusätzlich
**Anpassungskanal 09**: Bei vielen VAG-Kombis dieser Zeit steht dort der
Kilometerstand in 10-km-Schritten.

1. Zündung an, **17 Schalttafeleinsatz (Kombi)** öffnen.
2. Knopf **Kilometerstand (Kombi)** – oder auf der Kommandozeile:
   ```bash
   .venv/bin/python -m vagdiag.cli kilometerstand
   ```
3. **Mit der Anzeige im Kombi vergleichen.** Ob dein TRW-Kombi Kanal 09 so
   belegt, ist nicht bestätigt; das Ergebnis ist deshalb als „unbestätigt“
   markiert. Stimmt der Wert (auf 10 km genau), gib mir Bescheid – dann
   markiere ich ihn für dein Kombi als bestätigt.

Lehnt das Kombi Kanal 09 ab, findet die Kanalsuche alle lesbaren Kanäle
(Reiter **Anpassung → durchsuchen**, oder `--adresse 17 anpassungssuche`).
Schick mir dann das Protokoll.

vagdiag liest den Kilometerstand nur. Verändern lässt er sich damit nicht
(und das wäre nach § 22b StVG verboten).

## 6. Anpassungskanäle lesen

Reiter **Anpassung**: Kanal wählen, **Lesen** – oder einen Bereich
durchsuchen (Standard 1–99). Angezeigt werden Wert und Hex-Wert, so wie VCDS
sie unter „Anpassung“ zeigt. Kanal 00 wird nie angesprochen: Er steht bei
vielen Steuergeräten für „alle Anpassungswerte löschen“. „Abgelehnt“ heißt:
Den Kanal gibt es nicht, oder er ist nur nach einer Anmeldung (Login) lesbar.

## 7. Kommandozeile

```bash
.venv/bin/python -m vagdiag.cli geraete                    # Kabel finden
.venv/bin/python -m vagdiag.cli kabeltest
.venv/bin/python -m vagdiag.cli --adresse 01 ident
.venv/bin/python -m vagdiag.cli --adresse 01 fehler
.venv/bin/python -m vagdiag.cli --adresse 01 loeschen
.venv/bin/python -m vagdiag.cli --adresse 01 gruppe 1 2 4 --wiederholen 10
.venv/bin/python -m vagdiag.cli --adresse 17 gruppensuche
.venv/bin/python -m vagdiag.cli kilometerstand             # Kombi (Adresse 17)
.venv/bin/python -m vagdiag.cli --adresse 17 anpassung 9   # nur lesen
.venv/bin/python -m vagdiag.cli --adresse 17 anpassungssuche --von 1 --bis 99
.venv/bin/python -m vagdiag.cli scan                       # alle üblichen Steuergeräte
.venv/bin/python -m vagdiag.cli --sim --adresse 01 gruppe 4 --dauer
```
`-v` zeigt den Ablauf, `--bytes` zusätzlich jedes Byte, `--ohne-csv` schaltet
die Aufzeichnung für einen Lauf ab.

## 8. Wenn etwas nicht klappt

| Ausgabe | Bedeutung |
|---|---|
| „Keine Antwort von Adresse …“ | Zündung? Kabel? Steuergerät vorhanden? Wenn alles stimmt: `--reizung bitbang` probieren (manche Klon-Chips setzen das Break-Signal nicht sauber um). |
| „spricht KWP2000“ | Neueres Protokoll, noch nicht eingebaut – Protokolldatei schicken. |
| „Verbindung verloren …“ | Nur bei einer bestehenden Verbindung. Bei laufender Messung wird automatisch neu verbunden, sonst Protokolldatei schicken. |
| „Anpassungskanal … abgelehnt“ | Kanal nicht vorhanden oder nur mit Login lesbar – nichts kaputt, die Verbindung bleibt bestehen. |

**WLAN fällt beim Auslesen aus:** Laut deinem journalctl begannen die
Aussetzer, bevor vagdiag das Kabel geöffnet hat – vermutlich schwacher Empfang
im Auto (Blechkarosserie). Gegentest: Handy-Hotspot im Auto, Tür offen, oder
Laptop ohne Kabel im Auto.
```bash
journalctl -b -k --since "-10min" | grep -i -E "wlan|wifi|wlp|mt79|ath1|iwl|rtw|rfkill|usb|ftdi"
rfkill list
```

## 9. Eigene Texte und Feldnamen

Alle drei Dateien sind optional und liegen in `~/.config/vagdiag/`.
Eigene Einträge haben Vorrang vor den eingebauten.

`fehlertexte.json` – Fehlercodes:
```json
{ "16486": "Luftmassenmesser: Signal zu klein", "P0171": "Gemisch zu mager" }
```

`texte.json` – Klartexte für Textnummern („Text Nr. …“), dezimal oder hex:
```json
{ "31": "Öldruck 2 i. O.", "0x0105": "Klima ein" }
```

`beschriftungen.json` – Feldnamen je Adresse (hex) und Gruppe, `null` = kein Name:
```json
{ "25": { "2": ["Start erlaubt", "Motor-SG antwortet", "Schlüssel lesbar", "angelernte Schlüssel"] },
  "01": { "3": ["Motordrehzahl", "Saugrohrdruck", "Drosselklappe", "Zündwinkel"] } }
```
Eingebaut sind die Feldnamen der Gruppen, die an deinem Polo gelesen wurden:
Motor (ME7.5) 001, 002, 004, Kombi 001–003 und ABS 001. Sie erscheinen nur,
wenn die Einheiten der gelesenen Werte passen, damit bei einem anderen
Steuergerät nichts Falsches dransteht. Eigene Feldnamen werden nicht geprüft.

## 10. Tischaufbau mit ausgebautem Steuergerät (6K0 906 032 M)

Nur diese Pins anschließen, alles andere frei lassen:

| Steuergerät | Anschluss |
|---|---|
| Pin 3 | +12 V (Netzteil) |
| Pin 21 | +12 V über Schalter („Zündung“) |
| Pin 1 und Pin 2 | Masse |
| Pin 43 | OBD-Buchse Pin 7 (K-Leitung) |
| OBD-Buchse Pin 16 | +12 V (versorgt das KKL-Kabel) |
| OBD-Buchse Pin 4 und 5 | Masse |

Netzteil 12–13,5 V, Strombegrenzung ca. 1 A, 2-A-Sicherung in der Plusleitung.

## 11. Grenzen dieser Version

- Die Klartext-Tabelle enthält nur die Nummern, die bei deinem Polo vorkommen
  oder bei Motorsteuergeräten dieser Zeit üblich sind. Andere erscheinen als
  „Text Nr. …“ (eigene Ergänzungen: Abschnitt 9).
- Feldnamen gibt es nur für die oben genannten Gruppen.
- ABS Gruppe 002 zeigt im Stand 255 km/h: Das Rohbyte ist FF, ein Platzhalter.
  Was die Gruppe genau zeigt, ist noch offen.
- Anpassungskanäle werden nur gelesen; Login, Codierung und Grundeinstellung
  fehlen bewusst.
- KWP2000 wird erkannt, aber nicht gesprochen (für deinen Polo nicht nötig).

## 12. Aufbau

```
vagdiag/port.py            FTDI-Zugriff, 5-Baud-Reizung (Break oder Bitbang)
vagdiag/kline.py           Byte-Ebene, Echo-Erkennung des Kabels
vagdiag/kw1281.py          Protokoll: Handshake, Blöcke, Kennung, Funktionen
vagdiag/messwerte.py       Umrechnungsformeln, Min/Max
vagdiag/texte.py           Klartexte für Textnummern
vagdiag/beschriftung.py    Feldnamen der Messwertgruppen
vagdiag/kilometerstand.py  Kilometerstand aus dem Kombi (nur lesen)
vagdiag/fehler.py          Fehlercodes, P-Codes, Fehlerarten
vagdiag/session.py         Diagnose-Thread mit Keep-Alive und Neuverbinden
vagdiag/aufzeichnung.py    CSV-Aufzeichnung
vagdiag/einstellungen.py   Ordner und Optionen
vagdiag/sim.py             simulierte Steuergeräte auf Byte-Ebene
vagdiag/gui.py             Oberfläche (PySide6)
vagdiag/cli.py             Kommandozeile
tests/                     python -m unittest -v
```

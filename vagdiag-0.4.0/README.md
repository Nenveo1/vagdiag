# VAG-Diagnose über KKL-Kabel – Version 0.4

Linux-Programm für VW/Audi/Seat/Škoda mit K-Leitung (Protokoll KW1281), für ein
KKL-Kabel mit FT232RL. Gebaut für den Polo 6KV (ANW). Im Auto getestet mit
Motor (6K0 906 032 M, ME7.5.10), ABS, Kombi, Wegfahrsperre und Airbag.

**Kann diese Version:**

- Verbindung mit 5-Baud-Reizung, automatischer Baudrate (die funktionierende
  wird je Steuergerät gemerkt) und Protokollerkennung
- Identifikation mit Teilenummer, Bauteil, Codierung, Werkstattcode und
  Zusatzkennung (bei der Wegfahrsperre: Fahrgestellnummer und Immo-ID)
- Fehlerspeicher lesen (mit P-Code, Klartext soweit hinterlegt, Fehlerart) und löschen
- Messwertblöcke: bis zu 3 Gruppen live, Feldnamen, Min/Max je Feld,
  CSV-Aufzeichnung auf Wunsch, automatisches Neuverbinden bei Abbruch
- Gruppensuche, Anpassungskanäle lesen (nur lesen), Kilometerstand aus dem Kombi
- **Neu: Fahrtenschreiber** – eine ganze Fahrt in einer Datei: Motor
  durchgehend, Kombi und ABS in Abständen, Fehlerspeicher am Anfang und am
  Ende, Ereignis-Taste für den Moment, in dem eine Warnlampe angeht, und eine
  Zusammenfassung am Schluss (Abschnitt 4)
- **Neu: Englisch** – Sprache in den Einstellungen umstellbar (Abschnitt 3)
- **Neu: Standardmäßig keine Dateien** – Protokoll und CSV nur, wenn du sie
  einschaltest; das Protokoll lässt sich trotzdem jederzeit nachträglich
  speichern (Abschnitt 2)
- **Neu: Vorsicht beim Airbag** – Rückfrage vor Adresse 15, sofortiges
  Trennen bei Steuergeräten mit bekanntem Firmwarefehler (Abschnitt 6)
- **Robuster**: gestörte Antworten (Müll-Block, falscher Blockzähler,
  verlorenes Echo beim Anlassen) werden erkannt und neu angefragt, statt eine
  Gruppe abzuschalten oder Werte der falschen Gruppe zuzuordnen – gefunden in
  deinen Fahrdaten vom 19.10.
- Simulator mit Aufbau, Zeitverhalten und einer simulierten Fahrt deines Polos

Schreibende Funktionen (Codierung, Anpassung speichern, Grundeinstellung,
Stellglieddiagnose) sind bewusst nicht drin. Anpassungskanäle werden
ausschließlich gelesen.

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

**Update von 0.1–0.3:** Die ZIP-Datei im selben Ordner entpacken, in dem der
Ordner `vagdiag` liegt, und vorhandene Dateien überschreiben:
```bash
unzip -o vagdiag-0.4.0.zip
```
`.venv`, Einstellungen und Messdaten bleiben erhalten. `./installieren.sh` ist
nicht nötig (keine neuen Pakete). Beim ersten Start von 0.4 ist die
automatische CSV-Aufzeichnung aus, auch wenn sie vorher an war.

Falls PySide6 per pip nicht klappt:
```bash
sudo pacman -S pyside6
rm -rf .venv && python -m venv --system-site-packages .venv
.venv/bin/pip install pyftdi
```

**Wichtig:** Das Programm spricht den FTDI-Chip direkt per USB an (pyftdi).
Solange es läuft, verschwindet `/dev/ttyUSB0` – das ist normal.

## 2. Dateien: was wann geschrieben wird

Standardmäßig schreibt vagdiag **keine Protokoll- und keine CSV-Dateien**.

| Was | Wann | Standard-Ordner |
|---|---|---|
| Protokoll (jedes Byte, für die Fehlersuche) | nur wenn eingeschaltet oder gespeichert | `~/vagdiag-daten/logs` |
| Messwerte (CSV) | Häkchen „aufzeichnen (CSV)“ im Reiter Messwertblöcke | `~/vagdiag-daten/messwerte` |
| Fahrtenschreiber (CSV + Zusammenfassung) | immer – dafür startet man ihn | `~/vagdiag-daten/messwerte` |
| Einstellungen | beim Ändern | `~/.config/vagdiag/einstellungen.json` |

**Protokoll ohne Datei:** Die letzten rund 100 000 Zeilen (mit allen Bytes)
bleiben im Speicher. Geht etwas schief, über **Datei → Protokoll speichern …**
(oder den Knopf unten rechts) sichern und mir schicken.

**Einschalten auf Dauer:** **Datei → Einstellungen** – „Protokolldatei
schreiben“ und „Messwertblöcke automatisch als CSV aufzeichnen“. Das Häkchen
„aufzeichnen (CSV)“ im Reiter Messwertblöcke gilt nur bis zum Schließen des
Programms. Auf der Kommandozeile:
```bash
.venv/bin/python -m vagdiag.cli einstellungen --log-datei ja --csv-automatisch ja
.venv/bin/python -m vagdiag.cli einstellungen --log-ordner-setzen ~/Diagnose/logs \
                                              --csv-ordner-setzen ~/Diagnose/messwerte
```
Für einen einzelnen Lauf: `--log` (Protokolldatei) bzw. `gruppe … --csv`.

Die CSV-Dateien heißen `messwerte-<Adresse>-<Datum>-<Uhrzeit>.csv`, auf Deutsch
mit Semikolon und Dezimalkomma (öffnet direkt in LibreOffice), auf Englisch mit
Komma und Dezimalpunkt. Aufnahmen aus dem Simulator heißen `sim-…` und
beginnen mit der Zeile „Simulator – keine echten Fahrzeugdaten“. In der Spalte
„Ereignis“ stehen die Feldnamen einer Gruppe und Verbindungsabbrüche.

## 3. Oberfläche und Sprache

```bash
./vagdiag.sh
```

Links: Interface, Steuergerät, Funktionen. Rechts: Identifikation,
Fehlerspeicher, Messwertblöcke, Anpassung, Fahrtenschreiber. Unten: Protokoll.

- Über jedem Messwert steht der Feldname, sofern die Gruppe bekannt ist. Den
  Rohwert zeigt der Tooltip, beim Bitfeld in Gruppe 001 auch die Bedeutung
  der bekannten Stellen.
- Ist der **Simulator** gewählt, steht oben ein roter Hinweis und im
  Fenstertitel „[SIMULATOR]“.

**Sprache / Language:** **Datei → Einstellungen → Sprache / Language**
(Deutsch oder English). Das Fenster baut sich danach nach Rückfrage neu auf;
eine offene Verbindung wird dabei geschlossen. Übersetzt sind die ganze
Oberfläche, Meldungen, Fehlertexte, Feldnamen, Zusammenfassungen und die
Spaltenköpfe der CSV-Dateien. Zahlen folgen der Sprache (13,86 V bzw. 13.86 V).
Eigene Texte und Feldnamen (Abschnitt 10) bleiben, wie du sie geschrieben hast.
Auf der Kommandozeile: `--sprache en` für einen Lauf oder
`einstellungen --sprache-setzen en` auf Dauer.

## 4. Fahrtenschreiber

Über die K-Leitung kann das Programm immer nur mit einem Steuergerät
sprechen. Der Fahrtenschreiber wechselt deshalb selbst und schreibt alles in
**eine** Datei:

| Phase | Was passiert |
|---|---|
| Startprüfung | Tankinhalt im Stand (Kombi, 10 s), Fehlerspeicher aller Steuergeräte |
| Fahrt | Motorsteuergerät durchgehend (Gruppen 001–005). Solange der Motor steht, nur Gruppe 004 – so wird die Bordspannung beim Anlassen möglichst oft gelesen. Kurze Besuche beim Kombi (alle 3 min: Tempo, Tank, Kühlmittel) und beim ABS (alle 5 min: Raddrehzahlen, Bremslichtschalter) |
| Ereignis | Taste **F9** (Kommandozeile: Enter): Markierung und sofort die Fehlerspeicher von Motor und ABS – für den Moment, in dem MKL und ABS-Lampe angehen |
| Abschlussprüfung | Tankinhalt im Stand, Fehlerspeicher aller Steuergeräte |

So geht's:
1. Laptop sicher ablegen (nicht auf den Schoß des Beifahrers, nicht vor einen
   Airbag), Kabel so verlegen, dass es nicht an die Pedale kommt.
2. Zündung an, Reiter **Fahrtenschreiber**, **Fahrt starten**. Nach der
   Startprüfung Motor starten und losfahren. Während der Fahrt muss niemand
   den Laptop bedienen.
3. Nach dem Abstellen **Fahrt beenden** und die Zündung anlassen, bis die
   Abschlussprüfung fertig ist (etwa eine halbe Minute). **Sofort abbrechen**
   endet ohne Abschlussprüfung.

Am Ende erscheint eine Zusammenfassung (auch als `…-zusammenfassung.txt` neben
der CSV): Fehlerspeicher am Anfang, am Ende und bei jedem Ereignis,
Kühlmittel mit Thermostat-Hinweis, Bordspannung (Motor aus / beim Anlassen /
laufend), Drehzahl, Lambdaregelung, Höchsttempo je Quelle, Tankanzeige im Stand
und während der Fahrt (für die schwankende Tankanzeige), Bremslichtschalter
und welche Steuergeräte wann nicht erreichbar waren.

Kommandozeile (Enter = Ereignis, Strg+C = beenden mit Abschlussprüfung,
nochmal Strg+C = sofort abbrechen):
```bash
.venv/bin/python -m vagdiag.cli fahrt
.venv/bin/python -m vagdiag.cli fahrt --kombi-alle 120 --abs-alle 0 --motor-gruppen 1,2,4
```

## 5. Bordspannung beim Anlassen messen

1. Zündung an, Motorelektronik (01) öffnen, Reiter **Messwertblöcke**.
2. **Nur Gruppe 004** aktivieren (Feld 2 ist die Bordspannung).
3. **Start**, dann den Motor anlassen, laufen lassen, **Stopp**.
4. Unter jedem Feld steht Min/Max.

Das Motorsteuergerät braucht rund 10 ms pro Byte; den allerersten, sehr kurzen
Einbruch beim Einspuren kann man damit verpassen. Für den exakten Tiefstwert
ist ein Multimeter mit MIN/MAX an der Batterie besser. Der Fahrtenschreiber
erfasst das Anlassen automatisch.

## 6. Airbag (Adresse 15) – warum vagdiag nachfragt

VCDS warnt vor dem Öffnen des Airbag-Steuergeräts. Hintergrund laut Ross-Tech:
Airbag-Steuergeräte **6Q0 909 605 A** (Golf/Jetta/Beetle 2000–2001 und
ähnliche SEAT/Škoda) haben einen Firmwarefehler. Bei Störungen in der
Kommunikation können sie den Fehler 65535 speichern, der sich nicht löschen
lässt – die Airbaglampe bleibt an, das Steuergerät muss getauscht werden. Mit
einfachen KKL-Kabeln ist das wahrscheinlicher. Andere Teilenummern gelten als
unbedenklich; dein Polo hat ein 1J0 909 609.

Deshalb:
- Vor dem Öffnen von Adresse 15 fragt vagdiag nach (Vorgabe: Nein). Der
  Fahrtenschreiber fragt beim Start, ob er den Airbag-Fehlerspeicher mitlesen
  soll.
- Meldet sich ein 6Q0 909 605 A, beendet vagdiag die Verbindung sofort sauber
  und liest es nicht.
- Kommandozeile: Adresse 15 nur nach Rückfrage oder mit `--mit-airbag`; `scan`
  und `fahrt` lassen den Airbag ohne `--mit-airbag` aus.
- Beim Airbag liest vagdiag nur Kennung und Fehlerspeicher. Während der
  Verbindung kann die Airbaglampe leuchten; nach dem Trennen geht sie wieder
  aus.

Unabhängig von der Software: Nie bei eingeschalteter Zündung an der
Airbaganlage arbeiten (Stecker unter dem Sitz, Lenkrad, Gurtstraffer).
Fehlerspeicher löschen beseitigt keine Ursache – ein noch bestehender Fehler
kommt sofort wieder, und Crashdaten lassen sich nicht löschen.

Quelle: [Ross-Tech: VCDS – VW Issues](https://www.ross-tech.com/vag-com/vw_issues.php)

## 7. Kilometerstand

Dein Kombi (TRW, 6K9 920 806) schickt im Kilometerstand-Feld (Gruppe 002,
Feld 1) FF FF – „kein Wert“. vagdiag liest dann **Anpassungskanal 09**. Bei
deinem Kombi steht dort ebenfalls FF FF; das Kombi beschreibt den Kanal selbst
als „Kilometerstand in 10 km alte“ – vermutlich der übernommene Stand eines
früheren Kombis. Ein leerer Kanal ist kein Hinweis auf Manipulation.

1. Zündung an, **17 Schalttafeleinsatz (Kombi)** öffnen.
2. Knopf **Kilometerstand (Kombi)** – oder `vagdiag.cli kilometerstand`.

vagdiag liest den Kilometerstand nur. Verändern lässt er sich damit nicht
(und das wäre nach § 22b StVG verboten).

## 8. Anpassungskanäle lesen

Reiter **Anpassung**: Kanal wählen, **Lesen** – oder einen Bereich
durchsuchen (Standard 1–99). Kanal 00 wird nie angesprochen: Er steht bei
vielen Steuergeräten für „alle Anpassungswerte löschen“. „Abgelehnt“ heißt:
Den Kanal gibt es nicht, oder er ist nur nach einer Anmeldung (Login) lesbar.

## 9. Kommandozeile

```bash
.venv/bin/python -m vagdiag.cli geraete                    # Kabel finden
.venv/bin/python -m vagdiag.cli kabeltest
.venv/bin/python -m vagdiag.cli --adresse 01 ident
.venv/bin/python -m vagdiag.cli --adresse 01 fehler
.venv/bin/python -m vagdiag.cli --adresse 01 loeschen
.venv/bin/python -m vagdiag.cli --adresse 01 gruppe 1 2 4 --wiederholen 10
.venv/bin/python -m vagdiag.cli --adresse 01 gruppe 4 --dauer --csv
.venv/bin/python -m vagdiag.cli --adresse 17 gruppensuche
.venv/bin/python -m vagdiag.cli kilometerstand             # Kombi (Adresse 17)
.venv/bin/python -m vagdiag.cli --adresse 17 anpassung 9   # nur lesen
.venv/bin/python -m vagdiag.cli --adresse 17 anpassungssuche --von 1 --bis 99
.venv/bin/python -m vagdiag.cli fahrt                      # Fahrtenschreiber
.venv/bin/python -m vagdiag.cli scan                       # alle üblichen Steuergeräte
.venv/bin/python -m vagdiag.cli einstellungen              # anzeigen/ändern
.venv/bin/python -m vagdiag.cli --sim --adresse 01 gruppe 4 --dauer
```
`-v` zeigt den Ablauf, `--bytes` zusätzlich jedes Byte, `--log` schreibt eine
Protokolldatei. Jeder Befehl und jede Option hat auch einen englischen Namen
(`fehler` = `faults`, `--adresse` = `--address`, `--mit-airbag` =
`--with-airbag` …), siehe `--help`.

## 10. Wenn etwas nicht klappt

| Ausgabe | Bedeutung |
|---|---|
| „Keine Antwort von Adresse …“ | Zündung? Kabel? Steuergerät vorhanden? Wenn alles stimmt: `--reizung bitbang` probieren (manche Klon-Chips setzen das Break-Signal nicht sauber um). |
| „spricht KWP2000“ | Neueres Protokoll, noch nicht eingebaut – Protokoll speichern und schicken. |
| „Verbindung verloren …“ | Nur bei einer bestehenden Verbindung. Bei laufender Messung und im Fahrtenschreiber wird automatisch neu verbunden. |
| „… verworfen“ / „frage erneut“ im Protokoll | Eine gestörte Antwort wurde erkannt und neu angefragt – kein Fehler. |
| „Anpassungskanal … abgelehnt“ | Kanal nicht vorhanden oder nur mit Login lesbar – nichts kaputt. |
| „Airbag-Steuergerät … nicht freigegeben“ | Rückfrage verneint bzw. Kommandozeile ohne `--mit-airbag` (Abschnitt 6). |

Für die Fehlersuche: **Datei → Protokoll speichern …** direkt nach dem
Problem, oder auf der Kommandozeile den Lauf mit `--log` wiederholen.

## 11. Eigene Texte und Feldnamen

Alle drei Dateien sind optional und liegen in `~/.config/vagdiag/`.
Eigene Einträge haben Vorrang vor den eingebauten (in beiden Sprachen).

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
Motor (ME7.5) 001–004 (005 vorläufig), Kombi 001–003, ABS 001 und 003. Sie
erscheinen nur, wenn die Einheiten der gelesenen Werte passen, damit bei einem
anderen Steuergerät nichts Falsches dransteht.

## 12. Tischaufbau mit ausgebautem Steuergerät (6K0 906 032 M)

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

## 13. Grenzen dieser Version

- Die Klartext-Tabelle enthält nur die Nummern, die bei deinem Polo vorkommen
  oder bei Motorsteuergeräten dieser Zeit üblich sind (eigene Ergänzungen:
  Abschnitt 11). Die Fehlertext-Liste ist bewusst klein.
- Feldnamen gibt es nur für die oben genannten Gruppen. Gruppe 005 des Motors
  ist an deinem Auto noch nicht gelesen.
- ABS Gruppe 002 zeigt im Stand 255 km/h: Das Rohbyte ist FF, ein Platzhalter.
- Anpassungskanäle werden nur gelesen; Login, Codierung, Grundeinstellung und
  Stellglieddiagnose fehlen bewusst.
- KWP2000 wird erkannt, aber nicht gesprochen (für deinen Polo nicht nötig).

## 14. Aufbau

```
vagdiag/port.py              FTDI-Zugriff, 5-Baud-Reizung (Break oder Bitbang)
vagdiag/kline.py             Byte-Ebene, Echo-Erkennung des Kabels
vagdiag/kw1281.py            Protokoll: Handshake, Blöcke, Kennung, Funktionen
vagdiag/messwerte.py         Umrechnungsformeln, Min/Max
vagdiag/texte.py             Klartexte für Textnummern
vagdiag/beschriftung.py      Feldnamen der Messwertgruppen
vagdiag/kilometerstand.py    Kilometerstand aus dem Kombi (nur lesen)
vagdiag/fehler.py            Fehlercodes, P-Codes, Fehlerarten
vagdiag/airbag.py            Vorsicht bei Adresse 15
vagdiag/session.py           Diagnose-Thread mit Keep-Alive und Neuverbinden
vagdiag/fahrtenschreiber.py  Fahrtenschreiber mit Zusammenfassung
vagdiag/aufzeichnung.py      CSV-Aufzeichnung
vagdiag/protokolldatei.py    Protokoll im Speicher, auf Wunsch als Datei
vagdiag/einstellungen.py     Sprache, Ordner und Optionen
vagdiag/sprache.py           Übersetzung (Texte in sprache_en.py)
vagdiag/ident.py             Identifikation als Text
vagdiag/sim.py               simulierte Steuergeräte und simulierte Fahrt
vagdiag/gui.py               Oberfläche (PySide6)
vagdiag/cli.py               Kommandozeile
tests/                       python -m unittest -v
```

---

## English quick start

vagdiag is a Linux diagnostic tool for older VW/Audi/SEAT/Škoda cars with a
K-line (KW1281 protocol) and an FT232RL-based KKL cable. It reads
identification, fault codes, measuring blocks and adaptation channels (read
only), clears fault codes, and records whole drives (drive logger).

- **Install (Arch/CachyOS):** `sudo pacman -S --needed python libusb`, then
  `./installieren.sh` in the `vagdiag` folder. Start the window with
  `./vagdiag.sh`.
- **English:** File → Settings → Sprache / Language → English. The window
  restarts after asking. Command line: `--language en` for one run, or
  `settings --set-language en` permanently.
- **Files:** by default vagdiag writes no log and no CSV files. Turn them on in
  File → Settings, tick “record (CSV)” on the Measuring blocks tab, or use
  `--log` / `group … --csv` on the command line. File → Save log … saves the
  in-memory log at any time. The drive logger always writes its CSV file and
  a summary. English CSV files use a comma separator and a decimal point.
- **Airbag (address 15):** some airbag modules (6Q0 909 605 A) have a firmware
  bug that can store a fault 65535 that cannot be cleared. vagdiag therefore
  asks before connecting to address 15 (command line: `--with-airbag`) and
  disconnects immediately if such a module answers.
- **Command line:** `python -m vagdiag.cli --help` – every command has an
  English name: `devices`, `cable-test`, `ident`, `faults`, `clear`, `group`,
  `group-scan`, `adaptation`, `adaptation-scan`, `odometer`, `drive`, `scan`,
  `settings`.
- Nothing is ever written to a control module except “clear fault codes”
  (after confirmation): no coding, no adaptation, no basic settings, no output
  tests.

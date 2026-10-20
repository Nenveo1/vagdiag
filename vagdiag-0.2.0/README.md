# VAG-Diagnose über KKL-Kabel – Version 0.2

Linux-Programm für VW/Audi/Seat/Škoda mit K-Leitung (Protokoll KW1281), für ein
KKL-Kabel mit FT232RL. Gebaut für den Polo 6KV (ANW). Im Auto getestet mit
Motor (6K0 906 032 M, ME7.5.10), ABS, Kombi, Wegfahrsperre und Airbag.

**Kann diese Version:**

- Verbindung mit 5-Baud-Reizung, automatischer Baudrate (die funktionierende
  wird je Steuergerät gemerkt) und Protokollerkennung
- Identifikation mit Teilenummer, Bauteil, **Codierung, Werkstattcode** und
  **Zusatzkennung** (bei der Wegfahrsperre: Fahrgestellnummer und Immo-ID)
- Fehlerspeicher lesen (mit P-Code, Klartext soweit hinterlegt, Fehlerart) und löschen
- Messwertblöcke: bis zu 3 Gruppen live, **Min/Max je Feld**, **automatische
  CSV-Aufzeichnung**, **automatisches Neuverbinden** bei Abbruch (z. B. beim Anlassen)
- **Gruppensuche**: findet alle belegten Messwertgruppen eines Steuergeräts
- Einstellbare Ordner für Protokolle und Messwerte
- Simulator mit dem Zeitverhalten deines Polos

Schreibende Funktionen (Codierung, Anpassung, Grundeinstellung) sind bewusst
noch nicht drin.

---

## 1. Einrichtung (CachyOS)

```bash
sudo pacman -S --needed python libusb
cd vagdiag
./installieren.sh
```

Das Skript legt eine virtuelle Umgebung `.venv` an (pyftdi + PySide6) und
installiert die udev-Regel `70-kkl-ftdi.rules`. Danach das Kabel einmal ab- und
wieder anstecken. Bei einem Update von Version 0.1 einfach den neuen Ordner
entpacken und `./installieren.sh` erneut ausführen.

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
Protokolle aus Version 0.1 liegen noch in `~/.local/share/vagdiag/logs`.

Die CSV-Dateien heißen `messwerte-<Adresse>-<Datum>-<Uhrzeit>.csv` (Semikolon,
Dezimalkomma – öffnet direkt in LibreOffice). Verbindungsabbrüche stehen als
eigene Zeile darin, damit Lücken erkennbar sind.

## 3. Oberfläche

```bash
./vagdiag.sh
```

Links: Interface, Steuergerät, Funktionen. Rechts: Identifikation,
Fehlerspeicher, Messwertblöcke. Unten: Protokoll. Ist der **Simulator**
gewählt, steht oben ein roter Hinweis und im Fenstertitel „[SIMULATOR]“ – die
Werte sind dann nicht aus dem Auto.

## 4. Bordspannung beim Anlassen messen

1. Zündung an, Motorelektronik (01) öffnen, Reiter **Messwertblöcke**.
2. Nur **Gruppe 004** aktivieren (Feld 2 ist die Bordspannung) – je weniger
   Gruppen, desto häufiger wird abgefragt.
3. **Start**, dann den Motor anlassen, laufen lassen, **Stopp**.
4. Unter jedem Feld steht Min/Max; die CSV-Datei liegt im Messwert-Ordner.

Was du wissen solltest:
- Das Motorsteuergerät liefert etwa **3 Werte pro Sekunde** (es braucht rund
  10 ms pro Byte). Den allerersten, sehr kurzen Einbruch beim Einspuren des
  Anlassers kann man damit verpassen. Für den exakten Tiefstwert ist eine
  direkte Messung an der Batterie besser (Multimeter mit MIN/MAX oder ein eigener ADC).
- In deinem Test kam beim Anlassen noch ein Wert durch (160 /min, 9,87 V),
  dann hat das Steuergerät die Verbindung gestört. Jetzt toleriert das
  Programm einzelne gestörte Bytes und verbindet sonst automatisch neu – die
  Lücke dauert dann etwa 3–4 Sekunden.

Auf der Kommandozeile (bis Strg+C, mit CSV und Min/Max am Ende):
```bash
.venv/bin/python -m vagdiag.cli --adresse 01 gruppe 4 --dauer
```

## 5. Kilometerstand

Dein Kombi (TRW, 6K9 920 806) schickt im Kilometerstand-Feld (Gruppe 002,
Feld 1) den Wert FF FF – das heißt „kein Wert“. Früher zeigte das Programm
daraus 655350 km, jetzt „kein Wert (FF FF)“. Ob das Kombi den Stand in einer
anderen Gruppe liefert, zeigt die Gruppensuche (Knopf **Gruppen durchsuchen**,
oder `--adresse 17 gruppensuche`). Schick mir das Ergebnis.

## 6. Kommandozeile

```bash
.venv/bin/python -m vagdiag.cli geraete                    # Kabel finden
.venv/bin/python -m vagdiag.cli kabeltest
.venv/bin/python -m vagdiag.cli --adresse 01 ident
.venv/bin/python -m vagdiag.cli --adresse 01 fehler
.venv/bin/python -m vagdiag.cli --adresse 01 loeschen
.venv/bin/python -m vagdiag.cli --adresse 01 gruppe 1 2 4 --wiederholen 10
.venv/bin/python -m vagdiag.cli --adresse 17 gruppensuche
.venv/bin/python -m vagdiag.cli scan                       # alle üblichen Steuergeräte
.venv/bin/python -m vagdiag.cli --sim --adresse 01 gruppe 4 --dauer
```
`-v` zeigt den Ablauf, `--bytes` zusätzlich jedes Byte, `--ohne-csv` schaltet
die Aufzeichnung für einen Lauf ab.

## 7. Wenn etwas nicht klappt

| Ausgabe | Bedeutung |
|---|---|
| „Keine Antwort von Adresse …“ | Zündung? Kabel? Steuergerät vorhanden? Wenn alles stimmt: `--reizung bitbang` probieren (manche Klon-Chips setzen das Break-Signal nicht sauber um). |
| „spricht KWP2000“ | Neueres Protokoll, noch nicht eingebaut – Protokolldatei schicken. |
| „Verbindung verloren …“ | Bei laufender Messung wird automatisch neu verbunden. Sonst Protokolldatei schicken. |

**WLAN fällt beim Auslesen aus:** Das Programm selbst fasst das WLAN nicht an.
Um die Ursache zu finden, direkt nach dem Ausfall ausführen und mir die Ausgabe schicken:
```bash
journalctl -b -k --since "-10min" | grep -i -E "wlan|wifi|wlp|mt79|ath1|iwl|rtw|rfkill|usb|ftdi"
rfkill list
```
Gegentest: Passiert es auch im Simulator-Modus, oder wenn das Kabel nur am
Laptop steckt (nicht im Auto)?

## 8. Tischaufbau mit ausgebautem Steuergerät (6K0 906 032 M)

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

## 9. Eigene Fehlertexte

Eigene Texte kommen in `~/.config/vagdiag/fehlertexte.json`:
```json
{ "16486": "Luftmassenmesser: Signal zu klein", "P0171": "Gemisch zu mager" }
```

## 10. Grenzen dieser Version

- Messwerte vom Formeltyp „Text aus Tabelle“ (z. B. beim Airbag) erscheinen
  als „Text Nr. …“ – die Texttabelle fehlt noch.
- Klartext-Beschriftungen der Messwertfelder gibt es noch nicht.
- KWP2000 wird erkannt, aber nicht gesprochen (für deinen Polo nicht nötig).

## 11. Aufbau

```
vagdiag/port.py           FTDI-Zugriff, 5-Baud-Reizung (Break oder Bitbang)
vagdiag/kline.py          Byte-Ebene, Echo-Erkennung des Kabels
vagdiag/kw1281.py         Protokoll: Handshake, Blöcke, Kennung, Funktionen
vagdiag/messwerte.py      Umrechnungsformeln, Min/Max
vagdiag/fehler.py         Fehlercodes, P-Codes, Fehlerarten
vagdiag/session.py        Diagnose-Thread mit Keep-Alive und Neuverbinden
vagdiag/aufzeichnung.py   CSV-Aufzeichnung
vagdiag/einstellungen.py  Ordner und Optionen
vagdiag/sim.py            simulierte Steuergeräte auf Byte-Ebene
vagdiag/gui.py            Oberfläche (PySide6)
vagdiag/cli.py            Kommandozeile
tests/                    python -m unittest -v
```

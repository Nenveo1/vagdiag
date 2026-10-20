# VAG-Diagnose über KKL-Kabel – Stufe 1

Linux-Programm für VW/Audi/Seat/Škoda mit K-Leitung (Protokoll KW1281), für ein
KKL-Kabel mit FT232RL. Gebaut für den Polo 6KV (ANW, Motorsteuergerät 6K0 906 032 M).

**Kann diese Version:**

- Verbindung aufbauen mit 5-Baud-Reizung, automatischer Baudrate (10400/9600)
  und Protokollerkennung (KW1281; KWP2000 wird erkannt und gemeldet)
- Identifikation (Teilenummer, Bauteil, Codierungsblock roh)
- Fehlerspeicher lesen – mit P-Code, Klartext (soweit hinterlegt), Fehlerart, sporadisch
- Fehlerspeicher löschen (mit Rückfrage)
- Messwertblöcke: bis zu 3 Gruppen live, Aufzeichnung als CSV, Rohwerte im Tooltip
- Protokolldatei mit jedem einzelnen Byte (für die Fehlersuche)
- Simulator: Motor (01), Kombi (17, mit Kilometerstand) und ein KWP2000-Gerät (15)

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
installiert die udev-Regel `70-kkl-ftdi.rules`, damit das Kabel ohne root
nutzbar ist. Danach das Kabel einmal ab- und wieder anstecken.

Falls PySide6 per pip nicht klappt:
```bash
sudo pacman -S pyside6
rm -rf .venv && python -m venv --system-site-packages .venv
.venv/bin/pip install pyftdi
```

**Wichtig:** Das Programm spricht den FTDI-Chip direkt per USB an (pyftdi).
Nur so lässt sich die 5-Baud-Reizung unter Linux exakt erzeugen. Solange das
Programm läuft, verschwindet deshalb `/dev/ttyUSB0` – das ist normal.

## 2. Erst ohne Auto: Simulator

```bash
./vagdiag.sh
```
Interface **„Simulator (ohne Auto)“** wählen, **01** doppelklicken, Fehlerspeicher
lesen, Messwertblöcke starten. Adresse **17** zeigt den Kilometerstand in
Gruppe 002, Adresse **15** zeigt, was bei einem KWP2000-Steuergerät passiert.

Oder auf der Kommandozeile:
```bash
.venv/bin/python -m vagdiag.cli --sim --adresse 01 fehler
.venv/bin/python -m vagdiag.cli --sim --adresse 17 gruppe 1 2
```

## 3. Erster Test im Auto

Zündung an (Motor aus), Kabel in die OBD-Buchse, USB an den Laptop.

```bash
# Ist das Kabel da?
.venv/bin/python -m vagdiag.cli geraete
.venv/bin/python -m vagdiag.cli kabeltest

# Motorsteuergerät identifizieren, dann Fehlerspeicher
.venv/bin/python -m vagdiag.cli --adresse 01 ident
.venv/bin/python -m vagdiag.cli --adresse 01 fehler

# Bordspannung & Co.: Gruppen 1–4 je 5-mal, am Ende die Rohwerte
.venv/bin/python -m vagdiag.cli --adresse 01 gruppe 1 2 3 4 --wiederholen 5

# Kombiinstrument (Kilometerstand liegt meist in Gruppe 1 oder 2)
.venv/bin/python -m vagdiag.cli --adresse 17 ident
.venv/bin/python -m vagdiag.cli --adresse 17 gruppe 1 2 3
```

`-v` zeigt den Ablauf, `--bytes` zusätzlich jedes Byte. Jeder Aufruf schreibt
eine Protokolldatei nach `~/.local/share/vagdiag/logs/` – der Pfad steht in der
ersten Ausgabezeile.

**Mögliche Ergebnisse von `ident`:**

| Ausgabe | Bedeutung |
|---|---|
| Teilenummer + Bauteil | Alles gut, KW1281 läuft. |
| „spricht KWP2000“ | Das Steuergerät nutzt das neuere Protokoll. Das baue ich als Nächstes ein – schick mir die Protokolldatei. |
| „Keine Antwort von Adresse 01“ | Zündung? Kabel? K-Leitung (OBD-Pin 7)? Wenn alles stimmt: mit `--reizung bitbang` noch einmal versuchen (manche Klon-Chips setzen das Break-Signal nicht sauber um). |
| „bei keiner der Baudraten lesbar“ | Steuergerät antwortet, aber anders als erwartet – Protokolldatei schicken. |
| „Verbindungsaufbau abgebrochen“ | Handshake gestört (Timing/Kabel) – Protokolldatei schicken. |

## 4. Oberfläche

Links: Interface, Steuergerät (Liste oder Adresse in hex), Funktionen.
Rechts: Identifikation, Fehlerspeicher, Messwertblöcke. Unten: Protokoll
(„Blöcke anzeigen“ / „Einzelbytes anzeigen“ für Details).

- Doppelklick auf ein Steuergerät öffnet es; die Reizung dauert gut 2 Sekunden.
- Messwertblöcke: Gruppe ankreuzen, Nummer wählen, **Start**. Nicht belegte
  Gruppen werden automatisch abgewählt. Mauszeiger auf einen Wert zeigt
  Formeltyp und Rohbytes.
- Die Verbindung wird im Hintergrund gehalten (Keep-Alive). Bricht sie ab,
  zeigt die Statuszeile das an.

## 5. Tischaufbau mit ausgebautem Steuergerät (6K0 906 032 M)

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
Ohne Sensoren füllt sich der Fehlerspeicher mit Unterbrechungs-Fehlern – ideal
zum Testen von Lesen und Löschen. Die Bordspannung im Messwertblock lässt sich
am Netzteil verstellen und so prüfen.

## 6. Eigene Fehlertexte

Die eingebaute Textliste ist klein und enthält nur sichere Einträge. Eigene
Texte kommen in `~/.config/vagdiag/fehlertexte.json`:
```json
{ "16486": "Luftmassenmesser: Signal zu klein", "P0171": "Gemisch zu mager" }
```
Schlüssel sind der 5-stellige VAG-Code oder der P-Code.

## 7. Grenzen dieser Version

- KWP2000 wird erkannt, aber noch nicht gesprochen.
- Codierung/Werkstattcode werden nur roh angezeigt (Auswertung folgt, sobald
  echte Daten deines Steuergeräts vorliegen).
- Messwert-Formeln: die gängigen Typen sind drin; unbekannte Typen erscheinen
  als „Typ X: a/b“. Zu jedem Wert ist der Rohwert sichtbar.
- Klartexte für Messwertfelder („Feld 2 = Bordspannung“) gibt es noch nicht –
  die kommen pro Steuergerät, wenn wir sie für deinen Polo zusammentragen.

## 8. Aufbau

```
vagdiag/port.py         FTDI-Zugriff, 5-Baud-Reizung per Break
vagdiag/kline.py        Byte-Ebene, Echo-Erkennung des Kabels
vagdiag/kw1281.py       Protokoll: Handshake, Blöcke, Funktionen
vagdiag/messwerte.py    Umrechnungsformeln der Messwertblöcke
vagdiag/fehler.py       Fehlercodes, P-Codes, Fehlerarten
vagdiag/session.py      Diagnose-Thread mit Keep-Alive
vagdiag/sim.py          simulierte Steuergeräte auf Byte-Ebene
vagdiag/gui.py          Oberfläche (PySide6)
vagdiag/cli.py          Kommandozeile
tests/                  python -m unittest -v
```


# vagdiag 0.6.1 – VAG-Diagnose über KKL-Kabel

Diagnoseprogramm für Linux und Windows für VW, Audi, SEAT und Škoda mit
K-Leitung (Protokolle KW1281 und KWP2000, etwa Baujahre 1995–2006). Es braucht
ein KKL-Kabel mit FTDI-Chip (FT232R/FT232RL). Getestet wurde es an einem VW
Polo 6KV mit Motor (ME7.5), ABS, Kombi, Wegfahrsperre und Airbag (alle KW1281).
KWP2000 ist neu und bisher nur gegen den Simulator geprüft.

**Funktionen**
- Identifikation: Teilenummer, Codierung, Werkstattcode, Zusatzkennung
- Fehlerspeicher lesen (mit Fehlerart und P-Code) und löschen
- Messwertblöcke: 3 Gruppen live, Feldnamen, Min/Max, CSV auf Wunsch,
  Gruppensuche
- Anpassungskanäle lesen und Kilometerstand aus dem Kombi – **nur lesen**
- Fahrtenschreiber: eine ganze Fahrt mit mehreren Steuergeräten in einer
  Datei, mit Zusammenfassung
- KW1281 oder KWP2000 erkennt vagdiag selbst; Motoren mit KWP2000 auch per
  Fast-Init
- Simulator zum Ausprobieren ohne Auto (auch mit KWP2000-Motor)
- Oberfläche und Kommandozeile auf Deutsch oder Englisch

Geschrieben wird nur beim Fehlerspeicher-Löschen, und nur nach Rückfrage.
Codierung, Anpassung, Grundeinstellung und Stellglieddiagnose gibt es (noch) nicht.

## Installation

### CachyOS / Arch Linux

```bash
sudo pacman -S --needed python libusb
cd vagdiag
./installieren.sh
```
Danach das Kabel einmal ab- und wieder anstecken (die udev-Regel greift erst
dann).

- Oberfläche starten: `./vagdiag.sh`
- Kommandozeile: `./vagdiag-cli.sh --help`

Lässt sich PySide6 per pip nicht installieren:
```bash
sudo pacman -S pyside6
rm -rf .venv && python -m venv --system-site-packages .venv && .venv/bin/pip install pyftdi
```
Während vagdiag läuft, verschwindet `/dev/ttyUSB0`. Das ist normal: Das
Programm spricht den Chip direkt an, damit die 5-Baud-Reizung genau stimmt.

### Windows 10/11

1. **Python 3.11 oder neuer** von [python.org](https://www.python.org/downloads/)
   installieren und dabei den Haken bei „Add python.exe to PATH“ setzen.
2. Die ZIP-Datei entpacken, z. B. nach `Dokumente\vagdiag`.
3. Im Ordner `vagdiag` **installieren.bat** doppelklicken. Bei einer
   SmartScreen-Warnung „Weitere Informationen → Trotzdem ausführen“ wählen.
4. Das Kabel einstecken. Windows installiert den FTDI-Treiber selbst. Falls
   nicht: den „VCP Driver“ (Setup-Programm) von
   [ftdichip.com](https://ftdichip.com/drivers/vcp-drivers/) installieren –
   er enthält auch den D2XX-Teil, den vagdiag benutzt.
5. Oberfläche starten: **vagdiag.bat**. Kommandozeile: `vagdiag-cli.bat --help`

Das Kabel darf nicht gleichzeitig in einem anderen Programm (z. B. VCDS-Lite)
geöffnet sein. Kabel mit nachgemachtem FTDI-Chip arbeiten mit dem
Windows-Treiber nicht immer zuverlässig; unter Linux gibt es das Problem nicht.

### Update

Die neue ZIP-Datei über den alten Ordner entpacken und Dateien ersetzen.
Einstellungen und Messdaten bleiben erhalten. Neue Pakete kommen mit dem
erneuten Ausführen von `installieren.sh` bzw. `installieren.bat` dazu.

## Bedienung

Links das Interface (KKL-Kabel oder Simulator) und das Steuergerät wählen
(Doppelklick öffnet). Rechts stehen die Reiter Identifikation, Fehlerspeicher,
Messwertblöcke, Anpassung und Fahrtenschreiber. Unten läuft das Protokoll.

- **Sprache:** *Datei → Einstellungen → Sprache / Language* (Deutsch oder
  English). Das Fenster startet danach neu.
- **Dateien:** Standardmäßig schreibt vagdiag weder ein Protokoll noch
  CSV-Dateien. Einschalten lässt sich beides unter *Datei → Einstellungen*,
  die CSV-Aufzeichnung auch mit dem Häkchen „aufzeichnen (CSV)“ im Reiter
  Messwertblöcke. Die letzten 256.000 Zeilen des Protokolls (beim
  Fahrtenschreiber gut eine halbe Stunde) bleiben im Speicher und lassen sich
  nach einem Problem mit *Datei → Protokoll speichern …* sichern.
- **Ablage:** Daten liegen in `~/vagdiag-daten` (Windows:
  `%USERPROFILE%\vagdiag-daten`), Einstellungen in `~/.config/vagdiag`
  (Windows: `%APPDATA%\vagdiag`). Deutsche CSV-Dateien nutzen Semikolon und
  Dezimalkomma, englische Komma und Dezimalpunkt. Beide öffnen direkt in
  Excel und LibreOffice.
- **Bordspannung beim Anlassen:** Im Reiter Messwertblöcke nur die Gruppe mit
  der Spannung aktivieren (bei ME7 Gruppe 004). Dann wird sie am häufigsten
  gelesen. Min/Max steht unter dem Feld.

## Fahrtenschreiber

Über die K-Leitung spricht man immer nur mit einem Steuergerät. Der
Fahrtenschreiber wechselt deshalb selbst:
- Das Motorsteuergerät liest er durchgehend.
- Kombi und ABS besucht er in einstellbaren Abständen, das ABS aber nur im
  Stand (z. B. an der Ampel): Manche ABS-Steuergeräte nehmen während der
  Fahrt keine Verbindung an. Das Tempo dafür kommt aus einer Motor-Gruppe
  (bei ME7 Gruppe 005) – die sollte deshalb mitgelesen werden.
- Am Anfang und am Ende liest er die Fehlerspeicher und den Tankinhalt im
  Stand.

1. Laptop sicher ablegen, nicht vor einem Airbag. Das Kabel so verlegen, dass
   es nicht an die Pedale kommt.
2. Zündung an, Reiter Fahrtenschreiber → **Fahrt starten**. Nach der
   Startprüfung den Motor starten und losfahren.
3. Geht unterwegs eine Warnlampe an: **F9** drücken. Das setzt eine Markierung
   und liest sofort den Fehlerspeicher des Motors, den des ABS beim nächsten
   Halt.
4. Am Ziel **Fahrt beenden**, solange die Zündung noch an ist (der Motor darf
   aus sein), und warten, bis „Fahrtenschreiber beendet“ erscheint. Ist die
   Zündung schon aus, wartet vagdiag bis zu 60 Sekunden, ob sie wieder
   eingeschaltet wird.

Ergebnis ist eine CSV-Datei und eine Zusammenfassung mit diesen Punkten:
- Fehlerspeicher
- Kühlmittel
- Bordspannung (Motor aus, beim Anlassen, im Lauf – die ersten Sekunden nach
  dem Anspringen zählen noch zum Anlassen)
- Drehzahl, Lambdaregelung (nur mit warmem Motor) und Tempo
- Tankanzeige im Stand und während der Fahrt
- Bremslichtschalter
- Steuergeräte, die nicht erreichbar waren

Der Fahrtenschreiber schreibt seine Datei immer, auch wenn die
CSV-Aufzeichnung sonst aus ist.

## KWP2000

Viele VAG-Steuergeräte von etwa 2002 bis 2006 sprechen über die K-Leitung
KWP2000 statt KW1281. vagdiag erkennt das an der Antwort auf die Reizung und
liest dann Identifikation, Fehlerspeicher und Messwertblöcke wie gewohnt –
auch im Fahrtenschreiber. Anpassungskanäle gibt es bei KWP2000 noch nicht.

- **Fast-Init:** Manche spätere Motorsteuergeräte (vor allem Diesel)
  antworten nicht auf die 5-Baud-Reizung, sondern nur auf den schnelleren
  Fast-Init. Dafür links das Häkchen „Motor: zuerst Fast-Init (KWP2000)“
  setzen (Kommandozeile: `--fast-init`). Gilt nur für Adresse 01; ohne
  Antwort folgt die normale Reizung. Bei älteren Motoren nicht nötig.
- **Noch ungeprüft:** KWP2000 ist bisher nur gegen den Simulator getestet.
  Vor Versuchen an einem unbekannten Auto unter *Datei → Einstellungen* die
  Protokolldatei einschalten – jede KWP2000-Nachricht steht dann darin. Wie
  das Statusbyte eines Fehlers zu lesen ist (Fehlerart, sporadisch), ist bei
  KWP2000 noch nicht an echten Geräten bestätigt.
- **CAN:** Ab etwa Modelljahr 2005 (z. B. Golf V) läuft die Diagnose über
  CAN (OBD-Pins 6 und 14). Das kann ein KKL-Kabel grundsätzlich nicht.

## Airbag (Adresse 15)

Laut Ross-Tech (VCDS) haben Airbag-Steuergeräte **6Q0 909 605 A** einen
Firmwarefehler. Verbaut sind sie in Golf/Jetta/Beetle 2000–2001 und ähnlichen
SEAT/Škoda. Bei Störungen in der Kommunikation können sie einen nicht
löschbaren Fehler (65535) speichern. Die Airbaglampe bleibt dann an, und das
Steuergerät muss getauscht werden. Deshalb:
- vagdiag fragt vor dem Öffnen von Adresse 15 nach (Vorgabe: Nein).
- Meldet sich ein betroffenes Gerät, trennt vagdiag sofort.
- Im Fahrtenschreiber ist der Airbag standardmäßig nicht dabei. Das Häkchen
  „Airbag-Fehlerspeicher lesen“ zeigt beim Setzen denselben Hinweis.
- Auf der Kommandozeile geht es nur mit `--mit-airbag`.

Unabhängig von jeder Software gilt: Nie bei eingeschalteter Zündung an der
Airbaganlage arbeiten. Fehlerspeicher löschen beseitigt keine Ursache.

## Kommandozeile

```bash
./vagdiag-cli.sh geraete                       # Kabel finden
./vagdiag-cli.sh --adresse 01 fehler           # Fehlerspeicher Motor
./vagdiag-cli.sh --adresse 01 gruppe 4 --dauer --csv
./vagdiag-cli.sh --adresse 17 kilometerstand
./vagdiag-cli.sh fahrt                         # Enter = Ereignis, Strg+C = beenden
./vagdiag-cli.sh einstellungen --sprache-setzen en --log-datei ja
./vagdiag-cli.sh --log scan                    # alle üblichen Steuergeräte, mit Protokoll
./vagdiag-cli.sh --fast-init --adresse 01 ident   # KWP2000-Motor per Fast-Init
./vagdiag-cli.sh --sim --adresse 01 ident      # Simulator
./vagdiag-cli.sh --sim-kwp2000 --adresse 01 fehler   # Simulator mit KWP2000-Motor
```
Unter Windows heißt das Skript `vagdiag-cli.bat`. Jeder Befehl und jede Option
hat auch einen englischen Namen (`fehler` = `faults`, `--adresse` =
`--address` …), siehe `--help`. `--log` schreibt für diesen Lauf eine
Protokolldatei.

## Wenn etwas nicht klappt

| Meldung | Was tun |
|---|---|
| „Kein FTDI-Kabel gefunden“ | Linux: `installieren.sh` erneut ausführen, Kabel neu stecken. Windows: FTDI-Treiber installieren. |
| „Keine Antwort von Adresse …“ | Zündung an? Steuergerät vorhanden? Sonst Reizung „Bitbang“ probieren (für Klon-Chips). |
| „spricht KWP2000 …, antwortet aber auf keine Anfrage“ | Beim Motor Fast-Init probieren. Sonst Protokoll speichern und mitschicken. |
| „Anpassungskanal … abgelehnt“ | Kanal gibt es nicht oder er braucht eine Anmeldung – nichts kaputt. |
| „… verworfen“ im Protokoll | Gestörte Antwort erkannt und neu angefragt – kein Fehler. |

Für eine Fehlermeldung direkt nach dem Problem *Datei → Protokoll speichern …*
wählen und die Datei mitschicken.

## Eigene Texte und Feldnamen

Im Einstellungsordner lassen sich drei Dateien anlegen: `fehlertexte.json`,
`texte.json` und `beschriftungen.json`. Damit ergänzt man Fehlertexte,
Klartexte und Feldnamen für weitere Steuergeräte. Eigene Einträge gelten in
beiden Sprachen. Beispiel für Feldnamen (Adresse hex → Gruppe → Namen):
```json
{ "25": { "2": ["Start erlaubt", "Motor-SG antwortet", "Schlüssel lesbar", "angelernte Schlüssel"] } }
```

## Grenzen

- Eingebaut sind Feldnamen und Klartexte nur für die geprüften Steuergeräte
  (ME7.5, TRW-Kombi, ABS Mark 20). Andere zeigen Rohwerte und „Text Nr. …“.
- KWP2000: nur Identifikation, Fehlerspeicher und Messwertblöcke, noch nicht
  am Auto geprüft. CAN-Diagnose geht mit einem KKL-Kabel nicht.
- „Automatisch“ probiert 10400 und 9600 Baud. Manche alten Steuergeräte
  brauchen 4800 oder 1200 – dann die Baudrate von Hand wählen.
- Beim A4 B6 mit Xenon und beim A6 C5 (2002–2004) hängen einige Steuergeräte
  an einer zweiten K-Leitung. Ein normales KKL-Kabel erreicht sie nicht.
- Autos vor etwa 1996 haben teils eine 2×2-Diagnosebuchse statt OBD – dafür
  braucht es einen Adapter.
- Der Kilometerstand aus Anpassungskanal 09 ist nicht bei jedem Kombi
  bestätigt. Deshalb immer mit der Anzeige vergleichen.

---

## English

vagdiag reads identification, fault codes, measuring blocks and adaptation
channels (read only) from older VW/Audi/SEAT/Škoda cars (K-line, KW1281 and
KWP2000) via an FTDI KKL cable. It also records whole drives with the drive
logger (it visits the ABS only at standstill). KWP2000 is new and so far only tested against the simulator; for
engines that ignore the 5-baud init, tick “Engine: fast init first” (command
line: `--fast-init`). CAN diagnostics are not possible with a KKL cable.

- **Install:** Linux: `./installieren.sh`, then `./vagdiag.sh`. Windows 10/11:
  install Python 3.11+ (python.org, tick “Add python.exe to PATH”), run
  `installieren.bat`, then `vagdiag.bat`.
- **Language:** File → Settings → Sprache / Language → English. On the command
  line, use `--language en`.
- **Files:** no log or CSV files by default. Turn them on under File →
  Settings, or save the in-memory log via File → Save log ….
- **Airbag (15):** asks before connecting. It is never read by the drive
  logger unless you tick the checkbox.
- **Command line:** `vagdiag-cli --help`. All commands have English names
  (`faults`, `group`, `odometer`, `drive`, `settings` …).

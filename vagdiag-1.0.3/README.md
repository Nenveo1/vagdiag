# vagdiag 1.0.3 – VAG-Diagnose über KKL-Kabel

Diagnose für VW, Audi, SEAT und Škoda mit K-Leitung (KW1281 und KWP2000, etwa
Baujahre 1995–2006) unter Linux und Windows, mit einem KKL-Kabel mit FTDI-Chip
(FT232R/FT232RL). Geprüft an einem VW Polo 6KV (Motor ME7.5, ABS, Kombi,
Wegfahrsperre, Airbag – alle KW1281); KWP2000 bisher nur am Simulator. Freie
Software unter der GNU GPL Version 3 oder später, ohne Gewährleistung.

Was sich in welcher Version geändert hat, steht in `VERSIONEN.md`.

## Kurzanleitung

1. vagdiag installieren (siehe „Installation“). Das Kabel in die OBD-Buchse
   stecken, Zündung an.
2. vagdiag starten: `vagdiag.sh` (Linux) bzw. `vagdiag.bat` (Windows) im Ordner
   `vagdiag`.
3. Links unter **Interface** „KKL-Kabel (FTDI)“ wählen – zum Ausprobieren ohne
   Auto „Simulator (ohne Auto)“.
4. Ein **Steuergerät** in der Liste wählen (oder die Adresse eintippen, z. B.
   `01` für den Motor) und **Öffnen** – oder doppelklicken.
5. Rechts in den Reitern lesen:
   - **Identifikation:** Teilenummer und Codierung, gleich nach dem Öffnen.
   - **Fehlerspeicher:** **Fehlerspeicher lesen**; **Fehlerspeicher löschen …**
     fragt vorher nach.
   - **Messwertblöcke:** bis zu drei Gruppen anhaken, **Start**.
   - **Anpassung:** Kanäle lesen (nur lesen).
6. Eine Fahrt aufzeichnen: Reiter **Fahrtenschreiber** → **Fahrt starten**
   (Zündung an). Den Motor erst anlassen, wenn „jetzt Motor starten“ erscheint.
   Am Ziel **Fahrt beenden** und die Zündung an lassen, bis „Fahrtenschreiber
   beendet“ erscheint. Mit „passiv wie eine Dashcam“ hält ein Ringspeicher
   immer die letzten Minuten bis Stunden Fahrzeit und läuft nach einem Neustart
   von selbst weiter.
7. Überblick: Reiter **Scan** liest alle Steuergeräte mit ihren Fehlern, Reiter
   **OBD-II** die Readiness (z. B. vor der AU).
8. Bei Problemen: *Datei → Protokoll speichern …* und die Datei mitschicken.

vagdiag liest nur. Ohne Expertenmodus schreibt es einzig beim Löschen des
Fehlerspeichers, nach Rückfrage. Das Airbag-Steuergerät (15) öffnet es nur nach
einer eigenen Rückfrage.

## Quick guide (English)

1. Install vagdiag (see “Installation (English)”). Plug the cable into the OBD
   port, ignition on.
2. Start `vagdiag.sh` (Linux) or `vagdiag.bat` (Windows) in the folder
   `vagdiag`. For English menus: *Datei → Einstellungen … → Sprache / Language
   → English*; the window restarts.
3. Under **Interface** on the left choose “KKL cable (FTDI)” – or “Simulator (no
   car)” to try it without a car.
4. Select a **control module** in the list (or type its address, e.g. `01` for
   the engine) and click **Open** – or double-click it.
5. Read in the tabs on the right:
   - **Identification:** part number and coding, right after opening.
   - **Fault codes:** **Read fault codes**; **Clear fault codes …** asks first.
   - **Measuring blocks:** tick up to three groups, **Start**.
   - **Adaptation:** read channels (read only).
6. Record a drive: **Drive logger** tab → **Start drive** (ignition on). Crank
   the engine only when “start the engine now” appears. At your destination
   click **Finish drive** and keep the ignition on until “Drive logger
   finished” appears. With “passive like a dashcam” a ring buffer always keeps
   the last minutes to hours of driving time and resumes by itself after a
   restart.
7. Overview: the **Scan** tab reads all control modules with their faults, the
   **OBD-II** tab reads the readiness (e.g. before an emissions test).
8. If something goes wrong: *File → Save log …* and send the file.

vagdiag only reads. Without expert mode its only write is clearing fault codes,
after a confirmation. It opens the airbag module (15) only after a separate
confirmation. The detailed description further down is in German only.

## Installation

Die ZIP-Datei entpacken – es entsteht der Ordner `vagdiag`. Im Unterordner
`installation` liegt ein Installer je System:

| System | Installer |
|---|---|
| Windows 10 und 11 | `installieren-windows-10-11.bat` |
| CachyOS, Arch Linux, Arch Linux ARM | `installieren-cachyos-archlinux-archlinuxarm.sh` |
| Debian, Ubuntu, Linux Mint, Armbian | `installieren-debian-ubuntu-linuxmint-armbian.sh` |
| Alpine Linux (auch auf ARM) | `installieren-alpine.sh` |

**Linux:** Im Ordner `vagdiag` den passenden Installer als normaler Benutzer
starten; für die Pakete fragt er nach dem Passwort (sudo, unter Alpine auch
doas):
```bash
cd vagdiag
sh installation/installieren-debian-ubuntu-linuxmint-armbian.sh
```
Danach das Kabel einmal ab- und wieder anstecken. Start: `./vagdiag.sh`,
Kommandozeile: `./vagdiag-cli.sh --help`.

**Windows:**
1. Python 3.11 oder neuer von [python.org](https://www.python.org/downloads/)
   installieren, dabei „Add python.exe to PATH“ anhaken.
2. `installation\installieren-windows-10-11.bat` doppelklicken (bei einer
   SmartScreen-Warnung „Weitere Informationen → Trotzdem ausführen“).
3. Das Kabel einstecken. Den FTDI-Treiber installiert Windows meist selbst,
   sonst den „VCP Driver“ (Setup-Programm) von
   [ftdichip.com](https://ftdichip.com/drivers/vcp-drivers/) installieren.
4. Start: `vagdiag.bat`, Kommandozeile: `vagdiag-cli.bat --help`.

Zum Schluss fragt der Installer, ob vagdiag beim Anmelden von selbst starten
soll (Vorauswahl Nein). Ändern lässt sich das jederzeit im Programm: *Datei →
Beim Anmelden starten*.

**Update:** vagdiag schließen, die neue ZIP-Datei über den alten Ordner
entpacken (Dateien ersetzen) und den Installer noch einmal starten.
Einstellungen und Messdaten bleiben erhalten.

## Installation (English)

Unzip the file – this creates the folder `vagdiag`. Its subfolder
`installation` holds one installer per system (see the table above).

- **Linux:** in the folder `vagdiag`, run the installer for your system as a
  normal user, e.g. `sh installation/installieren-debian-ubuntu-linuxmint-armbian.sh`;
  it asks for your password for the packages (sudo, on Alpine also doas). Then
  unplug and replug the cable. Start: `./vagdiag.sh`, command line:
  `./vagdiag-cli.sh --help`.
- **Windows:** install Python 3.11 or newer from python.org and tick “Add
  python.exe to PATH”. Double-click `installation\installieren-windows-10-11.bat`
  (SmartScreen: “More info → Run anyway”). Windows usually installs the FTDI
  driver by itself; otherwise install the “VCP Driver” from ftdichip.com.
  Start: `vagdiag.bat`, command line: `vagdiag-cli.bat --help`.
- At the end the installer asks in German whether vagdiag should start at
  login: “vagdiag beim Anmelden automatisch starten? [j/N]” – `j` = yes, Enter
  = no. You can change this at any time in the program: *File → Start at
  login*.
- **Update:** close vagdiag, unzip the new version over the old folder (replace
  the files) and run the installer again. Settings and data are kept.

## Bedienung im Einzelnen

Links wählt man Interface und Steuergerät, rechts stehen die Reiter, unten läuft
das Protokoll. Im Simulator steht links oben ein roter Balken „SIMULATOR“. Ein
gelber Hinweis über den Reitern zeigt, dass das geöffnete Steuergerät nicht zu
den geprüften gehört (siehe „Geprüfte Steuergeräte“) – gesperrt wird dadurch
nichts.

### Interface

- **Interface:** KKL-Kabel (FTDI), Simulator (ohne Auto) oder Simulator mit
  KWP2000 bei Motor und Kombi.
- **Kabel-URL:** `ftdi:///1` (Linux) bzw. `d2xx:0` (Windows) nimmt das erste
  FTDI-Kabel. **Kabel suchen** trägt das gefundene ein.
- **Baudrate:** „Automatisch“ probiert 10400 und 9600 Baud, die zuletzt an
  dieser Adresse erfolgreiche zuerst. Sehr alte Steuergeräte brauchen 4800 oder
  1200 – dann von Hand wählen.
- **Reizung:** Break (Standard). Bitbang nur probieren, wenn mit Break nichts
  antwortet – manche Klon-Chips setzen den Break nicht sauber um.
- **Motor: zuerst Fast-Init (KWP2000):** für spätere Motorsteuergeräte (vor
  allem Diesel), die auf die normale 5-Baud-Reizung nicht antworten. Gilt nur
  für Adresse 01; antwortet niemand, folgt die normale Reizung.
- **Kabel testen:** öffnet das Kabel und sendet ein einzelnes Byte. Im Auto mit
  Zündung an kommt es als Echo zurück; ohne Strom an OBD-Pin 16 (Kabel nicht
  im Auto) ist kein Echo normal. Steuergeräte reagieren darauf nicht.

Unter Linux verschwindet `/dev/ttyUSB0`, solange vagdiag das Kabel benutzt – das
Programm spricht den Chip direkt an, damit die 5-Baud-Reizung genau stimmt.
Nach dem Ruhezustand des Rechners oder kurzem Abziehen öffnet vagdiag das Kabel
beim nächsten Versuch von selbst neu.

### Steuergerät und Funktionen

Die Liste enthält die 15 üblichen Adressen (01 Motor, 03 ABS, 15 Airbag,
17 Kombi, 25 Wegfahrsperre …). Ein Klick schreibt die Adresse in die Zeile
„oder Adresse (hex)“, eine getippte Adresse (00–7F) markiert den passenden
Eintrag. **Öffnen**, Enter oder ein Doppelklick öffnet, was in der Zeile steht;
**Schließen** beendet die Verbindung. Nach dem Öffnen erscheint der zuletzt
benutzte Reiter – gesendet wird dadurch nichts.

Die Knöpfe unter **Funktionen** lesen oder löschen (mit Rückfrage) den
Fehlerspeicher und führen zu den übrigen Reitern. **Kilometerstand (Kombi)**
liest am Kombi (17) Gruppe 002, sonst Anpassungskanal 09 – nur lesen, nicht bei
jedem Kombi bestätigt, deshalb mit der Anzeige vergleichen.

### Identifikation und Fehlerspeicher

**Identifikation** zeigt Teilenummer, Bauteil, Codierung, Werkstattcode und
Zusatzkennung. **Speichern …** schreibt das als Textdatei – so auch in
Fehlerspeicher, Anpassung, Scan und OBD-II; gesendet wird dabei nichts.

**Fehlerspeicher** zeigt jeden Fehler mit Code, OBD-Code (P, C, B oder U),
Beschreibung, Fehlerart und „sporadisch“. Die Texte kommen zuerst aus eigenen
Texten (siehe „Eigene Texte und Feldnamen“), dann aus den eingebauten (193
VAG-Codes und 316 P-Codes, deutsch und englisch, gegen KLineKWP1281Lib bzw. die
Norm geprüft), dann aus den Tabellen von KLineKWP1281Lib (rund 9.700 Codes,
83 Fehlerarten). Fehlt ein Text, steht „(kein Klartext hinterlegt)“.
Fehlerart 34 heißt bei vagdiag „keine Grundeinstellung“, in der Bibliothek
„keine Fehlerart erkannt“ – welcher Text stimmt, ist offen.

**Fehlerspeicher löschen …** fragt vorher nach und nennt dabei Teilenummer,
Bauteil und ob es der Simulator oder das Auto ist. Löschen beseitigt keine
Ursache.

### Messwertblöcke

- **Anzeige 1–3:** je ein Häkchen **Gruppe** und die Gruppennummer. Jedes Feld
  zeigt Wert und Namen, darunter Min/Max; den Rohwert zeigt der Tooltip.
- **Start** liest die angehakten Gruppen reihum. Je weniger Gruppen, desto
  öfter wird jede gelesen – für die Bordspannung beim Anlassen nur die Gruppe
  mit der Spannung anhaken (ME7: 004).
- **aufzeichnen (CSV):** schreibt die Werte in eine CSV-Datei; **CSV-Ordner
  öffnen** zeigt sie. Deutsche CSV-Dateien nutzen Semikolon und Dezimalkomma,
  englische Komma und Dezimalpunkt – beide öffnen direkt in Excel und
  LibreOffice.
- **bei Abbruch neu verbinden:** bricht die Verbindung ab (etwa beim
  Spannungseinbruch), verbindet vagdiag von selbst neu.
- **Min/Max zurücksetzen**, **Gruppen durchsuchen …** (findet alle belegten
  Gruppen ab 000) und **Marker setzen (F9)** – ein nummerierter Marker in CSV
  und Protokoll, z. B. wenn eine Warnlampe angeht.
- **Gruppe 000** liefert zehn Rohwerte (0–255), nur bei KW1281. Beim
  6K0 906 032 M sind vier davon benannt und umgerechnet: 1 Kühlmittel
  (Rohwert − 100 = °C), 2 Motorlast (× 100/133 = %), 3 Drehzahl (× 40 = /min),
  8 Lambdaregelung ((Rohwert − 128) × 100/128 = %).
- **Verlaufskurve** (standardmäßig aus): jedes Zahlenfeld als eigener Streifen
  über eine gemeinsame **Zeitachse** von 30 Sekunden bis 60 Minuten. Der
  Mauszeiger zeigt alle Werte zu einem Zeitpunkt, **Kurve leeren** beginnt neu.
  Das Zeichnen kostet Rechenzeit – auf langsamen Rechnern (TV-Box, Raspberry
  Pi) bricht die Verbindung damit öfter ab.

vagdiag rechnet nach allen Formeltypen von KLineKWP1281Lib, auch bei Gruppen im
Kopf-Rumpf-Format und Feldern mit eigener Länge (Texte). Unbenutzte Stellen
eines Schalterfelds stehen als „·“; ab einem unbekannten Format zeigt vagdiag
die Gruppe roh („roh: …“).

### Anpassung

Nur lesen: **Lesen** liest einen Kanal, **durchsuchen** alle Kanäle eines
Bereichs (z. B. 1 bis 99). Kanal 00 (bei vielen Steuergeräten „alle Anpassungen
löschen“) spricht vagdiag nie an. Lehnt ein Steuergerät einen Kanal ab, gibt es
ihn nicht oder er verlangt eine Anmeldung – vagdiag meldet sich nie an.

### Fahrtenschreiber

Über die K-Leitung spricht man immer nur mit einem Steuergerät, der
Fahrtenschreiber wechselt deshalb selbst: Den Motor liest er durchgehend, Kombi
und ABS besucht er in Abständen – das ABS nur im Stand (zweimal 0 km/h im
Abstand einer Sekunde), denn viele ABS-Steuergeräte antworten während der Fahrt
nicht. Das Tempo kommt aus einer Motor-Gruppe (ME7: 005), die deshalb
mitgelesen werden sollte.

Einstellungen:
- **Aufzeichnung:** „ganze Fahrt“ (eine Datei je Fahrt) oder „passiv wie eine
  Dashcam“ (Ringspeicher, siehe unten) mit der **Zeitspanne** 5 min, 20 min,
  1 h oder 5 h Fahrzeit.
- **Motor-Gruppen** (Standard 1,2,3,4,5 – fehlende werden übersprungen),
  **Kombi alle … s**, **ABS alle … s** (0 = nie) und **Dauer je Besuch**.
- **Start- und Abschlussprüfung:** liest am Anfang und am Ende alle
  Fehlerspeicher und den Tankinhalt im Stand; der Start wartet dafür bis zu
  60 Sekunden auf die Zündung. Die Prüfung beginnt an der Wegfahrsperre und
  endet am Motor, mit dem vagdiag dann verbunden bleibt.
- **Auch den Airbag-Fehlerspeicher lesen (15):** erst nach dem Hinweis zum
  Airbag; bei jedem Programmstart wieder aus.

Ablauf:
1. Laptop sicher ablegen, nicht vor einem Airbag; das Kabel von den Pedalen
   fernhalten.
2. Zündung an, Motor aus, **Fahrt starten**. Erst bei „Aufzeichnung läuft –
   jetzt Motor starten und losfahren“ anlassen – dann ist das Anlassen mit
   aufgezeichnet.
3. Geht eine Warnlampe an: **F9** (**Ereignis markieren**). Das markiert die
   Stelle und liest sofort den Fehlerspeicher des Motors, den des ABS beim
   nächsten Halt.
4. Am Ziel **Fahrt beenden**, solange die Zündung an ist (der Motor darf aus
   sein), und warten, bis „Fahrtenschreiber beendet“ erscheint. Ist die Zündung
   schon aus, wartet vagdiag bis zu 60 Sekunden auf sie. **Sofort abbrechen**
   endet ohne Abschlussprüfung.

**Aktuelle Werte** zeigt Drehzahl, Tempo, Kühlmittel, Bordspannung, Ansaugluft,
Tank, Saugrohrdruck und Bremslichtschalter. Ergebnis ist eine CSV-Datei (auch
wenn die CSV-Aufzeichnung sonst aus ist) mit einer Zusammenfassung:
Fehlerspeicher nach Adressen, Kühlmittel, Bordspannung (Motor aus, Anlassen,
Lauf), Drehzahl, Lambdaregelung, Tempo, Tank, Bremslichtschalter, nicht
erreichbare Steuergeräte, Zündung zwischendurch aus und Zeiten ohne Kabel. Jede
Notiz steht auch im Protokoll. Fehlt unterwegs das Kabel (abgezogen,
Ruhezustand), notiert vagdiag das einmal, wartet und macht weiter, sobald es
wieder da ist.

### Passiv wie eine Dashcam

Der passive Fahrtenschreiber arbeitet wie oben, schreibt aber in einen
Ringspeicher (Ordner `passiv` unter dem CSV-Ordner, im Simulator `passiv-sim`):
- Gespeichert wird in Stücken von etwa einer Minute Fahrzeit; ist mehr als die
  Zeitspanne beisammen, fällt das älteste Stück weg. Als Fahrzeit zählt nur
  Zeit mit Zündung an – bei ausgeschalteter Zündung wird nichts überschrieben,
  auch wenn vagdiag weiterläuft.
- Die Stücke bleiben über Fahrten und Neustarts hinweg erhalten.
- Am Ende jedes Laufs setzt vagdiag daraus `fahrt-passiv.csv` mit genau der
  Zeitspanne zusammen, mit Zusammenfassung (zuerst Fehlerspeicher und
  Ereignisse im Zeitraum, dann die Werte). Diese Datei wird jedes Mal neu
  geschrieben.
- **F9** markiert ein Ereignis und sichert die Zeitspanne bis jetzt zusätzlich
  in `fahrt-passiv-gesichert-<Datum>-<Uhrzeit>.csv` – solche Dateien
  überschreibt vagdiag nie. **Zeitspanne sichern …** tut dasselbe ohne laufende
  Aufzeichnung.
- **Weiterlaufen nach einem Neustart:** Lief der passive Fahrtenschreiber, als
  vagdiag geschlossen oder der Rechner ausgeschaltet wurde, startet er beim
  nächsten Öffnen von selbst wieder, mit demselben Kabel. **Fahrt beenden** oder
  **Sofort abbrechen** schalten das ab. Steckt das Kabel nicht, wartet er still
  darauf („Warte auf das Kabel …“).
- In einen Ringspeicher schreibt immer nur ein vagdiag. Läuft schon einer,
  meldet ein zweiter das, statt mitzuschreiben; sichern geht trotzdem.

**Im Auto von selbst:** *Datei → Beim Anmelden starten* startet vagdiag nach
jeder Anmeldung. Unter Linux legt es dafür `~/.config/autostart/vagdiag.desktop`
an (GNOME, KDE, Xfce, Cinnamon, MATE, LXQt und andere lesen diesen Ordner),
unter Windows den Eintrag „vagdiag“ unter
`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` (sichtbar im
Task-Manager unter „Autostart“). Geht das nicht, zeigt vagdiag den Befehl zum
Eintragen von Hand. Zusammen mit dem Weiterlaufen zeichnet ein passiver
Fahrtenschreiber so nach jedem Start des Rechners weiter auf. Für den
Dauerbetrieb die Start- und Abschlussprüfung abschalten.

**Ohne Fenster** (etwa auf einem Rechner ohne Bildschirm) läuft er über die
Kommandozeile:
```bash
./vagdiag-cli.sh fahrt --passiv 1h --ohne-pruefung
```
Linux, als systemd-Benutzerdienst – Datei
`~/.config/systemd/user/vagdiag-fahrt.service`, Pfad an den eigenen Ordner
anpassen:
```ini
[Unit]
Description=vagdiag – passiver Fahrtenschreiber

[Service]
ExecStart=%h/vagdiag/vagdiag-cli.sh fahrt --passiv 1h --ohne-pruefung
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```
Einschalten mit `systemctl --user enable --now vagdiag-fahrt.service`; soll er
schon vor der Anmeldung laufen, einmal `loginctl enable-linger $USER`. Beim
Herunterfahren beendet vagdiag die Aufzeichnung sofort und schreibt noch
`fahrt-passiv.csv`. Der Dienst belegt das Kabel – für die Oberfläche oder ein
Update vorher `systemctl --user stop vagdiag-fahrt.service`.

Windows: in der **Aufgabenplanung** eine Aufgabe mit dem Trigger „Bei
Anmeldung“ und der Aktion „Programm starten“ anlegen: `vagdiag-cli.bat` aus dem
vagdiag-Ordner mit den Argumenten `fahrt --passiv 1h --ohne-pruefung`. Beim
Herunterfahren beendet Windows das Programm ohne Rückmeldung; der Ringspeicher
bleibt trotzdem erhalten – die Zeitspanne dann mit **Zeitspanne sichern …**
oder `vagdiag-cli.bat fahrt-export` holen.

### Scan

**Scan starten** fragt die Steuergeräte nacheinander ab – nur lesen: Kennung
und, mit **Fehlerspeicher mitlesen**, die Fehler.
- **Übliche Adressen:** die 15 aus der Liste, etwa eine Minute.
- **Alle Adressen 01–7F:** etwa acht Minuten; die Tabelle zeigt nur, wer
  antwortet. Nie gereizt werden 33 (die allgemeine OBD-II-Adresse – dafür gibt
  es den OBD-II-Test) und 7C (Werksmodus des Radios).

Die Tabelle zeigt Teilenummer, Bauteil, Protokoll, Fehlerzahl und Status. Ein
Klick zeigt Kennung und Fehler, ein Doppelklick öffnet das Steuergerät. Den
Airbag fragt der Scan nur mit **Airbag (15) einschließen** ab. Die Baudrate
links gilt auch hier: Steuergeräte mit 4800 Baud findet der Scan nur, wenn dort
4800 gewählt ist.

### OBD-II

**OBD-II-Test starten** prüft wie der Kompatibilitätstest von VCDS-Lite, ob das
Auto die allgemeine Abgasdiagnose OBD-II/EOBD über die K-Leitung spricht
(ISO 9141-2 oder ISO 14230-4), und zeigt:
- die **Readiness** je Abgasprüfung (abgeschlossen, nicht abgeschlossen, nicht
  vorhanden). Nach dem Fehlerlöschen sind die Prüfungen wieder offen, bis das
  Auto sie bei einer Fahrt erledigt hat – vor der AU wichtig;
- Motorkontrollleuchte, Zahl der gespeicherten Abgasfehler, OBD-Norm,
  Fahrgestellnummer und welche Werte das Auto über OBD-II liefert.

Gesendet werden nur Anfragen aus Mode 01 und Mode 09 – nie Mode 04
(Abgasfehler löschen, setzt auch die Readiness zurück). Eine offene Verbindung
beendet vagdiag vorher und wartet danach bis zu 5 Sekunden, bevor es wieder ein
Steuergerät öffnet. Antwortet niemand, spricht das Auto kein OBD-II über die
K-Leitung (oder die Zündung ist aus). Pflicht ist EOBD bei Benzinern ab etwa
2001, bei Dieseln ab etwa 2004.

### Experte

*Experte → Expertenmodus …* schaltet den Expertenmodus nach einem Hinweis ein,
bis zum Programmende. Unter jedem Knopf steht, ob die Funktion gerade geht und,
wenn nicht, warum. Jede Funktion fragt vorher nach und nennt das Ziel.
**Simulator: Motor aus (Zündung an)** erlaubt, alles im Simulator
auszuprobieren. Benutzung auf eigene Gefahr.

- **Drosselklappe anlernen** (Motor 01; Gruppe 060 bei E-Gas wie ME7, 098 bei
  Seilzug). vagdiag prüft vorher: Motor aus, Bordspannung mindestens 11,5 V,
  Kühlmittel 5–95 °C, kein Fehler im Motor – und dass die Gruppe wie die
  Anpassung aufgebaut ist, denn sonst könnte das Steuergerät mit derselben
  Gruppe etwas anderes anlernen. Die Grundeinstellung dauert etwa 30 Sekunden;
  Gaspedal nicht berühren. Weicht eine Antwort ab, hört vagdiag sofort auf.
  Feld 4 zeigt das Ergebnis („ADP. läuft“, „ADP. i.O.“). Bei KWP2000
  experimentell (Ablauf nach einem Mitschnitt an einem EDC16, an keinem
  Benziner geprüft).
- **Service-Intervall zurücksetzen** (Kombi 17, Anpassungskanal 02 auf 0 –
  Kombis ab etwa 1998). Den alten Wert sichert vagdiag vorher als JSON-Datei in
  `~/vagdiag-daten/sicherungen` und liest danach zurück.
- **Stellglieddiagnose** am geöffneten Steuergerät: Es steuert seine
  Stellglieder nacheinander an – im Kombi Zeiger, Lampen und Gong, im Motor
  Relais und Ventile. Zündung an, Motor aus, Auto steht (beim Motor prüft
  vagdiag die Drehzahl 0, beim ABS 0 km/h). **Weiter** schaltet weiter,
  **Stopp** hört auf, ohne **Weiter** endet sie nach 60 Sekunden; danach
  verbindet vagdiag neu. Bei Bremsen (03, 23, 53), Airbag (15), Wegfahrsperre
  (25), Niveauregulierung (34) und Lenkung (44) kommt vorher eine Warnung mit
  den möglichen Schäden (Vorgabe: Nein); passt die Kennung nicht zur Adresse,
  bleibt sie gesperrt. Die Reihenfolge merkt sich vagdiag je
  Steuergerät in `~/vagdiag-daten/stellglieder.json` und zeigt sie beim
  nächsten Mal als Übersicht – vorher lesen lässt sie sich nicht. Bei KWP2000
  experimentell.

Auch im Expertenmodus gesperrt: Kanal 00, Kilometerstand, Codierung, Login sowie
Grundeinstellung und Anpassung bei Airbag, Bremsen, Wegfahrsperre, Lenkung und
Niveauregulierung. Jeder Schreibblock steht im Protokoll („SCHREIBEN: …“ bzw.
„STELLGLIED: …“). Schlüssel anlernen gibt es nicht – das ginge nur mit Anmeldung
und PIN, die vagdiag nie sendet.

### Menüs, Protokoll und Einstellungen

- *Datei → Einstellungen …:* **Sprache / Language** (das Fenster startet danach
  neu), die Ordner für Protokolle und Messwerte, **Protokolldatei schreiben**,
  **Messwertblöcke automatisch als CSV aufzeichnen** und **Bei Abbruch während
  der Messung neu verbinden** (Voreinstellungen der beiden Häkchen im Reiter
  Messwertblöcke).
- *Datei → Beim Anmelden starten:* Autostart an oder aus (siehe „Passiv wie
  eine Dashcam“).
- *Datei → Protokoll speichern …:* Die letzten 256.000 Zeilen des Protokolls
  (beim Fahrtenschreiber gut eine halbe Stunde) bleiben im Speicher und lassen
  sich nach einem Problem sichern – auch ohne Protokolldatei.
- *Datei → Ordner der Protokolle öffnen / Ordner der Messwerte öffnen.*
- *Hilfe:* Über vagdiag, Lizenztext und Hinweise zu fremden Bestandteilen.
- **Protokoll** unten: **Blöcke anzeigen** und **Einzelbytes anzeigen** zeigen
  den Datenverkehr genauer.

Standardmäßig schreibt vagdiag weder Protokoll- noch CSV-Dateien. Daten liegen
in `~/vagdiag-daten` (Windows: `%USERPROFILE%\vagdiag-daten`), Einstellungen in
`~/.config/vagdiag` (Windows: `%APPDATA%\vagdiag`).

## Sicherheit

- Ohne Expertenmodus sendet vagdiag nur lesende Anfragen; einzige Ausnahme ist
  das Löschen des Fehlerspeichers nach Rückfrage. Rückfragen nennen
  Teilenummer, Bauteil und ob Simulator oder Auto. Ausgeführt wird nur, solange
  genau dieses Gerät verbunden ist.
- Bei KW1281 schickt das Steuergerät jedes empfangene Byte invertiert zurück.
  Stimmt diese Bestätigung nicht, sendet vagdiag den Block nicht zu Ende und
  beendet die Verbindung – aus einer gestörten Anfrage wird so nie ein anderer
  Befehl. Schreibvorgänge und Schritte der Stellglieddiagnose wiederholt vagdiag
  nie von selbst.
- Nach seiner Bestätigung wartet ein Steuergerät nur kurz auf das nächste Byte
  (ein ME7.5 etwa 45 ms). Ginge ein Byte später als 15 ms nach der Bestätigung
  hinaus (KWP2000: 18 ms nach dem vorigen), weil der Rechner hängt, bricht
  vagdiag den Block ab und verbindet neu.
- Nach einem Verbindungsabbruch reizt vagdiag ein anderes Steuergerät erst nach
  2,5 s (KWP2000: 5,5 s) – vorher könnte das alte noch zuhören.
- Meldet sich ein Gerät als Airbag, Bremse, Wegfahrsperre oder Lenkung, bekommt
  es keine Grundeinstellung und keine Anpassung – auch unter einer fremden
  Adresse, falls eine Störung die Reizung verfälscht hat.

### Airbag (Adresse 15)

Airbag-Steuergeräte **6Q0 909 605 A** (Golf/Jetta/Beetle 2000–2001 und ähnliche
SEAT/Škoda) haben laut Ross-Tech einen Firmwarefehler: Bei Störungen in der
Kommunikation können sie einen nicht löschbaren Fehler (65535) speichern; die
Airbaglampe bleibt dann an, und das Steuergerät muss getauscht werden. Deshalb:
- vagdiag fragt vor dem Öffnen von Adresse 15 nach (Vorgabe: Nein) und trennt
  ein betroffenes Gerät sofort.
- Meldet sich unter einer anderen Adresse ein Airbag, trennt vagdiag sofort
  nach der Kennung.
- Fahrtenschreiber und Scan lesen den Airbag nur mit eigenem Häkchen, die
  Kommandozeile nur mit `--mit-airbag`.

Unabhängig von jeder Software: Nie bei eingeschalteter Zündung an der
Airbaganlage arbeiten.

## Geprüfte Steuergeräte

vagdiag funktioniert auch an anderen Autos. Geprüft ist es an diesen
Steuergeräten (nach Teilenummer):

| Teilenummer | Steuergerät |
|---|---|
| 6K0 906 032 M | Motor ME7.5.10 |
| 6K9 920 806 | Kombiinstrument TRW |
| 6X0 907 379 B | ABS |
| 6X0 953 257 | Wegfahrsperre |
| 1J0 909 609 Q | Airbag |
| 6N0 909 901 | Gateway K<->CAN |

An jedem anderen Steuergerät (auch mit anderem Index) steht ein Hinweis – über
den Reitern, in Identifikation und Berichten, im Scan und in jeder Rückfrage.
Gesperrt wird dadurch nichts. Feldnamen stehen dort mit „(nicht geprüft)“; die
Erklärung des Bitfelds in Gruppe 001 und die Merker der Fahrt-Zusammenfassung
gelten nur am 6K0 906 032 M, die Namen der Diesel-Stellglieder nur an
Steuergeräten mit „EDC“ in der Kennung.

## KWP2000

Viele VAG-Steuergeräte von etwa 2002 bis 2006 sprechen über die K-Leitung
KWP2000. vagdiag erkennt das an der Antwort auf die Reizung und liest
Identifikation, Fehlerspeicher, Messwertblöcke und Anpassungskanäle wie gewohnt,
auch im Fahrtenschreiber. KWP2000 ist bisher nur gegen den Simulator geprüft –
vor Versuchen an einem unbekannten Auto die Protokolldatei einschalten. Wie das
Statusbyte eines Fehlers (Fehlerart, sporadisch) zu lesen ist, ist an echten
Geräten noch nicht bestätigt. Ab etwa Modelljahr 2005 (z. B. Golf V) läuft die
Diagnose über CAN – das kann ein KKL-Kabel nicht.

## Kommandozeile

```bash
./vagdiag-cli.sh geraete                       # Kabel finden
./vagdiag-cli.sh --adresse 01 ident            # Identifikation Motor
./vagdiag-cli.sh --adresse 01 fehler           # Fehlerspeicher Motor
./vagdiag-cli.sh --adresse 01 gruppe 4 --dauer --csv   # Enter = Marker, Strg+C = Ende
./vagdiag-cli.sh --adresse 17 kilometerstand
./vagdiag-cli.sh scan --alle                   # alle Adressen 01–7F (etwa 8 Minuten)
./vagdiag-cli.sh obd2                          # OBD-II-Test (nur lesen)
./vagdiag-cli.sh fahrt                         # Enter = Ereignis, Strg+C = beenden
./vagdiag-cli.sh fahrt --passiv 20min          # passiv: 5min, 20min, 1h oder 5h
./vagdiag-cli.sh fahrt-export --zeitspanne 1h  # Zeitspanne aus dem Ringspeicher sichern
./vagdiag-cli.sh --experte drosselklappe       # Gruppe 060; --gruppe 98 bei Seilzug
./vagdiag-cli.sh --experte service-reset       # Kombi 17, Kanal 02 → 0
./vagdiag-cli.sh --experte --adresse 17 stellglieder   # Enter = weiter, q = beenden
./vagdiag-cli.sh einstellungen --sprache-setzen en --log-datei ja
./vagdiag-cli.sh --sim --adresse 01 ident      # Simulator
./vagdiag-cli.sh --version                     # Version, Urheber, Lizenz
```
Unter Windows heißt das Skript `vagdiag-cli.bat`. Jeder Befehl und jede Option
hat auch einen englischen Namen (`fehler` = `faults`, `--adresse` =
`--address` …), siehe `--help`. `--log` schreibt für diesen Lauf eine
Protokolldatei, `--baud 4800` legt die Baudrate fest. Expertenfunktionen
schaltet `--experte` nur nach dem Hinweis und dem eingetippten Wort „ja“ frei,
nur an einer Konsole – ohne Konsole (Skript, Dienst) startet keine.

## Installation im Einzelnen

Der Linux-Installer
- installiert Python ab 3.11, libusb und PySide6 (für die Oberfläche) über die
  Paketverwaltung. Fehlt dort ein passendes PySide6 (etwa Debian 12, Ubuntu
  22.04), kommt es per pip; ist das Python des Systems älter als 3.11 (Ubuntu
  22.04, Linux Mint 21), holt er Python 3.11 dazu. Gibt es PySide6 gar nicht
  (etwa Raspberry Pi OS mit 32 Bit), richtet er nur die Kommandozeile ein.
- installiert pyftdi in die Python-Umgebung `.venv` im Ordner `vagdiag`.
- richtet die udev-Regel ein, damit das Kabel ohne root-Rechte geht, und nimmt
  den Benutzer in die Gruppe `uucp` auf – so geht das Kabel auch über SSH und
  für den automatisch gestarteten Fahrtenschreiber (ab der nächsten Anmeldung).
- legt die Startdateien `vagdiag.sh` und `vagdiag-cli.sh` in den Ordner
  `vagdiag` (Windows: `vagdiag.bat` und `vagdiag-cli.bat`) und fragt zuletzt
  nach dem Autostart.

Die Installer und Startdateien laufen auch aus der fish-Shell (Standard unter
CachyOS); `installation/teile` enthält nur ihre Bestandteile. Unter Alpine
steht PySide6 im Paketquellen-Verzeichnis „community“ (in
`/etc/apk/repositories` freischalten); ohne udev (mdev) darf nur root aufs
Kabel – dann `setup-devd udev` ausführen und den Installer noch einmal starten.
Unter Windows 10 bleibt PySide6 bei Version 6.12, laut Qt der letzten für
Windows 10. Das Kabel darf nicht gleichzeitig in einem anderen Programm (z. B.
VCDS-Lite) geöffnet sein; Kabel mit nachgemachtem FTDI-Chip arbeiten mit dem
Windows-Treiber nicht immer zuverlässig.

Die Installer sind im Trockenlauf geprüft (Paketverwaltung nachgebildet), noch
nicht auf jedem dieser Systeme selbst.

## Eigene Texte und Feldnamen

Im Einstellungsordner lassen sich `fehlertexte.json` (Fehlertexte und Namen der
Stellglieder, z. B. `{"01247": "Magnetventil Aktivkohlebehälter"}`),
`texte.json` (Klartexte) und `beschriftungen.json` (Feldnamen) anlegen. Eigene
Einträge haben Vorrang und gelten in beiden Sprachen. Feldnamen: Adresse (hex)
→ Gruppe → Namen; `"01:036906034AM"` statt `"01"` gilt nur für diese
Teilenummer.
```json
{ "25": { "2": ["Start erlaubt", "Motor-SG antwortet", "Schlüssel lesbar", "angelernte Schlüssel"] } }
```

## Wenn etwas nicht klappt

| Meldung | Was tun |
|---|---|
| „Kein FTDI-Kabel gefunden“ | Linux: den Installer noch einmal ausführen, Kabel neu stecken. Windows: FTDI-Treiber installieren. |
| „KKL-Kabel konnte nicht geöffnet werden … busy“ | Ein anderes Programm hat das Kabel, etwa ein zweites vagdiag oder der Dienst: `systemctl --user stop vagdiag-fahrt.service`, unter Windows die Aufgabe beenden. |
| „Lesen vom Kabel fehlgeschlagen …“ oder ein anderer USB-Fehler | Kabel abgezogen oder Rechner im Ruhezustand gewesen. Kabel stecken und noch einmal versuchen – vagdiag öffnet es neu. |
| „Kabel nicht erreichbar – vagdiag wartet darauf“ | Der Fahrtenschreiber wartet auf das Kabel und macht weiter, sobald es steckt. |
| „Keine Antwort von Adresse …“ | Zündung an? Steuergerät verbaut? Sonst Reizung „Bitbang“ probieren (Klon-Chips). |
| „spricht KWP2000 …, antwortet aber auf keine Anfrage“ | Beim Motor Fast-Init probieren, sonst Protokoll speichern und mitschicken. |
| „Anpassungskanal … abgelehnt“ / „Stellglieddiagnose abgelehnt“ | Gibt es nicht, braucht eine Anmeldung oder eine Bedingung fehlt – nichts kaputt. |
| „… passt nicht zu dieser Adresse“ | Ein anderes Gerät hat sich gemeldet (meist nach einer Störung bei der Reizung). Neu öffnen; bleibt es so, Protokoll mitschicken. |
| „… verworfen“ im Protokoll | Gestörte Antwort erkannt und neu angefragt – kein Fehler. |
| „Falsches Komplement … Block abgebrochen“ | Störung auf der K-Leitung (Wackelkontakt, Spannungseinbruch beim Anlassen) – neu verbinden. |
| „Byte … zu spät … Block abgebrochen“ | Der Rechner hat kurz gehangen; vagdiag verbindet neu – nichts kaputt. Kommt das oft: andere Programme schließen, Verlaufskurve aus, Protokoll mitschicken. |
| „Gruppe 060 ist … anders aufgebaut als die Drosselklappen-Anpassung“ | Die Gruppe ist bei diesem Motor etwas anderes – vagdiag hat nichts gesendet. Anlernen nach Reparaturleitfaden. |
| „An diesem Steuergerät ist vagdiag nicht geprüft“ | Nur ein Hinweis. Feldnamen und Erklärungen mit dem Reparaturleitfaden vergleichen. |
| „In den Ringspeicher … schreibt gerade ein anderes vagdiag“ | Der passive Fahrtenschreiber läuft schon (etwa als Dienst). Ihn beenden – oder nur **Zeitspanne sichern …**, das geht nebenher. |

Für eine Fehlermeldung gleich nach dem Problem *Datei → Protokoll speichern …*
wählen und die Datei mitschicken.

## Grenzen

- Eingebaute Feldnamen gibt es nur für Gruppen der geprüften Steuergeräte;
  Wegfahrsperre und Gateway haben keine (eigene über `beschriftungen.json`).
  Die vier Felder der Airbag-Gruppe 001 sind nach dem Reparaturleitfaden des
  Polo 6N benannt (Zündpillen N95, N131, N153, N154), die Reihenfolge ist am
  Auto nicht nachgeprüft.
- Der Fahrtenschreiber kennt die Motorgruppen nur vom ME7.5 (z. B. das Tempo
  in Gruppe 005); bei anderen Motoren bleibt die Zusammenfassung lückenhaft.
- OBD-II nur über die K-Leitung: Readiness, OBD-Norm, unterstützte Werte und
  Fahrgestellnummer – keine Live-Werte und keine OBD-II-Fehlercodes.
- Stellgliednamen gibt es nur für Kombi-Anzeigen und einige
  Diesel-Stellglieder; sonst zeigt vagdiag den Fehlertext zur Nummer oder die
  Nummer.
- Beim A4 B6 mit Xenon und beim A6 C5 (2002–2004) hängen einige Steuergeräte an
  einer zweiten K-Leitung, die ein normales KKL-Kabel nicht erreicht. Autos vor
  etwa 1996 haben teils eine 2×2-Diagnosebuchse – dafür braucht es einen
  Adapter.

## Lizenz

Copyright (C) 2026 Nenveo

vagdiag ist freie Software: Du kannst es unter den Bedingungen der GNU General
Public License, wie von der Free Software Foundation veröffentlicht,
weitergeben und/oder verändern – entweder nach Version 3 der Lizenz oder (nach
deiner Wahl) jeder späteren Version (SPDX: GPL-3.0-or-later). vagdiag wird in
der Hoffnung verbreitet, dass es nützlich ist, aber **ohne jede
Gewährleistung** – sogar ohne die implizite Gewährleistung der Marktreife oder
der Verwendbarkeit für einen bestimmten Zweck. Den Lizenztext enthält die
Datei `LICENSE`.

- **FTDI-Treiber:** Unter Windows nutzt vagdiag die D2XX-Bibliothek des
  FTDI-Treibers, die keine freie Software ist. Eine zusätzliche Erlaubnis nach
  Abschnitt 7 der GPL erlaubt, vagdiag mit ihr verbunden weiterzugeben –
  Wortlaut in `NOTICE.txt`.
- **Fremde Bestandteile:** die Texttabellen aus KLineKWP1281Lib (domnulvlad,
  GPL-3.0) in `vagdiag/daten/klinekwp1281lib`; die Rechnung der Messwerte folgt
  dieser Bibliothek. Protokollbeschreibungen und Stellgliednamen nach
  kw1281test (Greg Menounos, MIT-Lizenz). Einzelheiten in `NOTICE.txt`.
- In der Oberfläche: *Hilfe → Über vagdiag …*; auf der Kommandozeile:
  `--version` und `lizenz`.

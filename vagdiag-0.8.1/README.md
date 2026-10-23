# vagdiag 0.8.1 – VAG-Diagnose über KKL-Kabel

Diagnoseprogramm für Linux und Windows für VW, Audi, SEAT und Škoda mit
K-Leitung (Protokolle KW1281 und KWP2000, etwa Baujahre 1995–2006). Es braucht
ein KKL-Kabel mit FTDI-Chip (FT232R/FT232RL). Getestet wurde es an einem VW
Polo 6KV mit Motor (ME7.5), ABS, Kombi, Wegfahrsperre und Airbag (alle KW1281).
KWP2000 ist neu und bisher nur gegen den Simulator geprüft.

**Funktionen**
- Identifikation: Teilenummer, Codierung, Werkstattcode, Zusatzkennung
- Fehlerspeicher lesen (mit Fehlerart, P-Code und Klartext für gut 500 Codes)
  und löschen
- Messwertblöcke: 3 Gruppen live, Feldnamen, Min/Max, CSV auf Wunsch,
  Gruppensuche
- Anpassungskanäle lesen (KW1281 und KWP2000) und Kilometerstand aus dem
  Kombi – **nur lesen**
- Fahrtenschreiber: eine ganze Fahrt mit mehreren Steuergeräten in einer
  Datei, mit Zusammenfassung
- Scan: die üblichen Steuergeräte oder alle Adressen 01–7F auf einen Blick, mit
  Fehlern und Bericht
- Identifikation, Fehlerspeicher, Anpassungskanäle und Scan lassen sich als
  Textdatei speichern
- Expertenmodus (standardmäßig aus): Drosselklappe anlernen,
  Service-Intervall zurücksetzen und Stellglieddiagnose – bei Bremsen, Airbag,
  Wegfahrsperre, Lenkung und Niveauregulierung erst nach einer Warnung, die die
  möglichen Schäden nennt
- KW1281 oder KWP2000 erkennt vagdiag selbst; Motoren mit KWP2000 auch per
  Fast-Init
- Simulator zum Ausprobieren ohne Auto (auch mit KWP2000 bei Motor und Kombi)
- Oberfläche und Kommandozeile auf Deutsch oder Englisch

Ohne Expertenmodus schreibt vagdiag nur beim Fehlerspeicher-Löschen, und nur
nach Rückfrage. Im Expertenmodus kommen genau drei Funktionen dazu (siehe
unten). Codierung und Login gibt es nicht.

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
Messwertblöcke, Anpassung, Fahrtenschreiber, Scan und Experte. Unten läuft das
Protokoll.

Nach dem Öffnen eines Steuergeräts erscheint wieder der Reiter, der zuletzt
für ein Steuergerät benutzt wurde – Identifikation, Fehlerspeicher,
Messwertblöcke, Anpassung oder Experte (seit 0.8.1; vorher immer
Identifikation). Das gilt bis zum Beenden des Programms. Gesendet wird dadurch
nichts: Fehler und Messwerte liest erst der jeweilige Knopf.

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
- **Speichern (seit 0.8.0):** In den Reitern Identifikation, Fehlerspeicher,
  Anpassung und Scan speichert **Speichern …**, was der Reiter gerade zeigt,
  als Textdatei – beim Fehlerspeicher alle gelesenen Fehler, bei der Anpassung
  alle Kanäle der Liste, beim Scan alle gefundenen Steuergeräte. Der Vorschlag
  liegt im Ordner der Messwerte, im Simulator mit „sim-“ davor. Dabei wird
  nichts an das Steuergerät gesendet.
- **Bordspannung beim Anlassen:** Im Reiter Messwertblöcke nur die Gruppe mit
  der Spannung aktivieren (bei ME7 Gruppe 004). Dann wird sie am häufigsten
  gelesen. Min/Max steht unter dem Feld. Bricht die Verbindung beim
  Spannungseinbruch ab, verbindet vagdiag mit dem Häkchen „bei Abbruch neu
  verbinden“ von selbst neu.

## Fahrtenschreiber

Über die K-Leitung spricht man immer nur mit einem Steuergerät. Der
Fahrtenschreiber wechselt deshalb selbst:
- Das Motorsteuergerät liest er durchgehend.
- Kombi und ABS besucht er in einstellbaren Abständen, das ABS aber nur im
  Stand (z. B. an der Ampel): Manche ABS-Steuergeräte nehmen während der
  Fahrt keine Verbindung an. Das Tempo dafür kommt aus einer Motor-Gruppe
  (bei ME7 Gruppe 005) – die sollte deshalb mitgelesen werden. Als Stand
  zählt seit 0.8.0 erst, wenn mindestens zwei Werte mit einer Sekunde Abstand
  0 km/h zeigen (vorher reichte ein einziger Wert, auch kurz vor dem Anhalten).
- Am Anfang und am Ende liest er die Fehlerspeicher und den Tankinhalt im
  Stand.
- Startprüfung (seit 0.8.1): zuerst die Wegfahrsperre, zuletzt der Motor. Mit
  dem Motor bleibt vagdiag danach verbunden, und die Aufforderung zum Anlassen
  kommt erst, wenn die ersten Motorwerte da sind. Bis 0.8.0 kam sie schon nach
  der Startprüfung, einige Sekunden bevor der Motor gelesen wurde – wer gleich
  startete, verpasste das Anlassen. Läuft der Motor schon beim ersten
  Messwert, steht das als Notiz und in der Zusammenfassung („Anlassen nicht
  aufgezeichnet“).

1. Laptop sicher ablegen, nicht vor einem Airbag. Das Kabel so verlegen, dass
   es nicht an die Pedale kommt.
2. Zündung an, Motor aus, Reiter Fahrtenschreiber → **Fahrt starten**. Erst
   wenn „Aufzeichnung läuft – jetzt Motor starten und losfahren“ erscheint,
   den Motor anlassen und losfahren. Dann ist das Anlassen mit aufgezeichnet.
3. Geht unterwegs eine Warnlampe an: **F9** drücken. Das setzt eine Markierung
   und liest sofort den Fehlerspeicher des Motors, den des ABS beim nächsten
   Halt.
4. Am Ziel **Fahrt beenden**, solange die Zündung noch an ist (der Motor darf
   aus sein), und warten, bis „Fahrtenschreiber beendet“ erscheint. Ist die
   Zündung schon aus, wartet vagdiag bis zu 60 Sekunden, ob sie wieder
   eingeschaltet wird.

Ergebnis ist eine CSV-Datei und eine Zusammenfassung mit diesen Punkten:
- Fehlerspeicher (seit 0.8.1 nach Adressen sortiert)
- Kühlmittel
- Bordspannung (Motor aus, beim Anlassen, im Lauf – die ersten Sekunden nach
  dem Anspringen zählen noch zum Anlassen)
- Drehzahl, Lambdaregelung (nur mit warmem Motor) und Tempo
- Tankanzeige im Stand und während der Fahrt
- Bremslichtschalter
- Steuergeräte, die nicht erreichbar waren
- Zündung zwischendurch aus (seit 0.8.0): Antwortet der Motor nach einem
  Verbindungsverlust gar nicht mehr und später wieder, steht das mit Uhrzeit
  in der Zusammenfassung und zählt nicht als Störung. Als Störung zählen
  gestörte Verbindungsaufbauten und Verbindungsverluste mit sofortiger
  Antwort danach.

Der Fahrtenschreiber schreibt seine Datei immer, auch wenn die
CSV-Aufzeichnung sonst aus ist. Jede Notiz der Fahrt (Verbindungsverlust,
Zündung aus, F9 …) steht seit 0.8.0 auch im Protokoll – Protokoll und CSV
lassen sich so nebeneinanderlegen.

## Scan

Reiter **Scan** → **Scan starten** fragt die Steuergeräte nacheinander ab
(nur lesen): Kennung und, wenn angehakt, den Fehlerspeicher. Zwei Umfänge:
- **Übliche Adressen:** die 15 häufigsten (Liste links), etwa eine Minute. Die
  Tabelle zeigt jede davon.
- **Alle Adressen 01–7F:** jede Adresse, etwa acht Minuten. Die Tabelle zeigt
  nur die, die antworten. Nie gereizt werden 33 (die allgemeine OBD-II-Adresse,
  kein eigenes Steuergerät) und 7C (Werksmodus des Radios).

Die Tabelle zeigt Teilenummer, Bauteil, Protokoll, Fehlerzahl und Status. Ein
Klick auf eine Zeile zeigt Kennung und Fehler, ein Doppelklick öffnet das
Steuergerät. **Speichern …** schreibt alles als Textdatei. Jede nicht
verbaute Adresse kostet einige Sekunden. Der Airbag (15) ist nur mit dem
Häkchen „Airbag (15) einschließen“ dabei. Die Baudrate links gilt auch für den
Scan: „Automatisch“ probiert 10400 und 9600; sehr alte Steuergeräte mit 4800
Baud findet der Scan nur, wenn dort 4800 gewählt ist. In der Kommandozeile:
`./vagdiag-cli.sh scan`, alle Adressen mit `./vagdiag-cli.sh scan --alle`, mit
fester Baudrate `./vagdiag-cli.sh --baud 4800 scan`.

## Expertenmodus

Menü **Experte → Expertenmodus …** schaltet ihn nach einem Hinweis ein. Er
gilt nur bis zum Beenden des Programms. Erst dann werden die Knöpfe im Reiter
**Experte** aktiv. Unter jedem Knopf steht, ob die Funktion gerade geht und,
wenn nicht, warum – etwa „Verbunden ist 17 … – dafür links mit 01 …
verbinden“ (seit 0.8.0). Drosselklappe und Service-Reset gehören zu einem
bestimmten Steuergerät, die Stellglieddiagnose zum gerade geöffneten: Das
Steuergerät muss links geöffnet sein.

- **Drosselklappe anlernen** (Motor 01, Grundeinstellung Gruppe 060 bei E-Gas
  wie ME7, Gruppe 098 bei Seilzug). vagdiag prüft vorher über die Messwerte:
  Motor aus, Bordspannung mindestens 11,5 V, Kühlmittel 5–95 °C, kein Fehler
  im Motor-Fehlerspeicher (Bedingungen wie bei Ross-Tech). Dann läuft die
  Grundeinstellung etwa 30 Sekunden. Gaspedal dabei nicht berühren. Danach
  liest vagdiag die Gruppe normal (das beendet die Grundeinstellung) und den
  Fehlerspeicher. Feld 4 zeigt das Ergebnis. Den Statustext („ADP i.O.“)
  kennt vagdiag bei echten Steuergeräten noch nicht; dann steht dort
  „Text Nr. …“ – bitte das Protokoll schicken.
- **Service-Intervall zurücksetzen** (Kombi 17, Anpassungskanal 02 auf 0 –
  so bei Kombis ab etwa 1998). vagdiag liest den Kanal, sichert den alten
  Wert als JSON-Datei in `~/vagdiag-daten/sicherungen`, testet und speichert
  den Wert 0 und liest danach zurück. Gibt es Kanal 02 nicht, geht der Reset
  nur am Kombi selbst. Geht bei KW1281 und KWP2000.
- **Stellglieddiagnose** (das geöffnete Steuergerät). Das Steuergerät steuert
  seine Stellglieder nacheinander an – im Kombi z. B. Zeiger, Warnlampen und
  Gong, im Motor Relais und Ventile. Zündung an, Motor aus, Auto steht; beim
  Motor prüft vagdiag vorher, dass die Drehzahl 0 ist. **Weiter** schaltet zum
  nächsten Stellglied, **Stopp** hört auf; kommt 60 Sekunden lang kein
  **Weiter**, hört vagdiag von selbst auf. Danach beendet vagdiag die
  Verbindung – dann hört jedes Steuergerät sicher auf, etwas anzusteuern – und
  verbindet neu. Angezeigt wird die Nummer des Stellglieds (wie ein
  Fehlercode) und, wenn bekannt, sein Name. Fehlende Namen lassen sich in
  `fehlertexte.json` eintragen (siehe unten). Bei KWP2000 ist sie
  **experimentell**: Der Ablauf stammt aus einem Mitschnitt an einem
  Diesel-Steuergerät (EDC16). Dort steuert der erste Schritt das angezeigte
  Stellglied an, der zweite schaltet weiter.

**Stellglieddiagnose an allen Steuergeräten (seit 0.8.0).** Bis 0.7.2 waren
Bremsen, Airbag, Wegfahrsperre und Lenkung gesperrt. Jetzt gilt:
- Bei Bremsen (03 ABS, 23 Bremskraftverstärker, 53 Parkbremse), Airbag (15),
  Wegfahrsperre (25), Niveauregulierung (34) und Lenkung (44) erscheint vor
  der Rückfrage eine **Warnung** mit den möglichen Schäden für genau dieses
  Steuergerät und der nötigen Vorbereitung (Vorgabe: Nein). Beim ABS etwa:
  Luft aus der Hydraulikeinheit kann in die Bremsleitungen kommen, ein Rad
  kann ungebremst sein; vorher das Auto gegen Wegrollen sichern, danach die
  Bremse prüfen. Die Bestätigung reicht bis in die Schreibsperre des
  Protokolls: Ohne sie geht kein Stellglied-Block hinaus.
- Beim ABS prüft vagdiag vorher, dass alle Räder stehen (0 km/h in Gruppe
  001), beim Motor wie bisher die Drehzahl 0.
- Bei den übrigen Steuergeräten nennt die Rückfrage, was sich bewegen kann
  (z. B. beim Motor der Kühlerlüfter, bei Zentralverriegelung und Komfort die
  Fenster).
- Meldet sich unter einer Adresse ein Gerät, das nach Teilenummer oder Name zu
  einer anderen Art gehört (etwa ein ABS unter 17, wenn eine Störung die
  Reizung verfälscht hat), bleibt die Stellglieddiagnose gesperrt.
- Airbag-Steuergeräte und Wegfahrsperren haben meist keine Stellglieddiagnose
  und lehnen ab. Schlüssel anlernen gehört nicht dazu – das ginge nur mit
  Anmeldung und PIN, die vagdiag nie sendet. Das Airbag-Steuergerät öffnet
  vagdiag wie bisher nur nach der eigenen Rückfrage.

**Protokoll (seit 0.8.1).** Bei der Stellglieddiagnose steht jetzt auch im
Protokoll, ob die Warnung bestätigt oder abgelehnt wurde (mit Teilenummer), ob
die Rückfrage mit Nein beantwortet wurde und welche Bedingung nicht erfüllt
war. Die Startzeile nennt die bestätigte Warnung. Lehnt das Steuergerät die
Stellglieddiagnose ab oder bricht sie mit einem Fehler ab, steht das mit der
Zahl der Schritte im Protokoll; ebenso eine Grundeinstellung oder ein
Service-Reset, die mit einem Fehler enden. Nach einem Fehler sendet vagdiag
nichts erneut.

**Liste der Stellglieder (seit 0.8.0).** Lesen lässt sich die Liste vorher
nicht: Das Steuergerät nennt das nächste Stellglied erst, wenn es es
ansteuert. Deshalb merkt sich vagdiag nach jedem Durchlauf die Reihenfolge je
Steuergerät (Teilenummer und Bauteil) in `~/vagdiag-daten/stellglieder.json`
und zeigt sie beim nächsten Öffnen im Reiter Experte an; während eines
Durchlaufs ist das gerade angesteuerte markiert. Die Liste ist eine Übersicht
– welches Stellglied als nächstes kommt, bestimmt das Steuergerät, weiter geht
es nur mit **Weiter**. Ein abgebrochener Durchlauf ersetzt keine längere
Liste, die genauso beginnt.

Auch im Expertenmodus gesperrt: Kanal 00 (alle Anpassungen löschen), der
Kilometerstand, Codierung, Login sowie Grundeinstellung und Anpassung bei
Airbag, Bremsen, Wegfahrsperre, Lenkung und Niveauregulierung. Jeder Schreibblock
steht im Protokoll („SCHREIBEN: …“ bzw. „STELLGLIED: …“). Die Drosselklappe
gibt es bisher nur bei KW1281; alle Expertenfunktionen gibt es nur in der
Oberfläche. Im Simulator lässt sich mit dem Häkchen „Simulator: Motor aus“
alles ausprobieren. Benutzung auf eigene Gefahr.

**Störungen auf der Leitung.** Bei KW1281 bestätigt das Steuergerät jedes
Byte, indem es das Byte invertiert zurückschickt. Stimmt diese Bestätigung
nicht, hat das Steuergerät ein anderes Byte bekommen. vagdiag sendet den Block
dann nicht zu Ende, sendet eine halbe Sekunde lang nichts und beendet die
Verbindung – so wird aus einer gestörten Anfrage nie ein anderer Befehl (z. B.
„Fehler löschen“ statt „Fehler lesen“). Die Versionen 0.2.0 bis 0.7.0 haben in
diesem Fall einmal pro Block weitergesendet; bitte nicht mehr verwenden.
Außerdem gilt seit 0.7.1:
- Nach Testen und Speichern muss das Steuergerät genau den Kanal und Wert
  zurückmelden, sonst speichert vagdiag nicht bzw. beendet die Verbindung.
- Testen, Speichern und die Schritte der Stellglieddiagnose wiederholt
  vagdiag nie von selbst – bei KWP2000 auch dann nicht, wenn das Steuergerät
  „beschäftigt“ meldet. Die Antwort muss zur gesendeten Routine passen.
- Lässt sich eine KWP2000-Anpassung nach einem Schreibversuch nicht beenden,
  beendet vagdiag die Verbindung, damit kein Testwert aktiv bleibt.
- Eine Freigabe gilt nur für das gerade geöffnete Steuergerät und endet mit
  jedem neuen Verbindungsaufbau. Kanal 00 wird auch nicht gelesen.

**Pausen des Rechners (seit 0.7.2).** Nach seiner Bestätigung wartet das
Steuergerät nur kurz auf das nächste Byte – ein ME7.5 im Auto etwa 45 ms.
Kommt es später, verwirft das Steuergerät den halben Block und hält das späte
Byte für den Anfang eines neuen. Die Bestätigungen stimmen dann trotzdem, und
aus dem Rest kann ein anderer Befehl werden: Im Simulator nachgestellt, wurde
so aus „Gruppe 005 lesen“ ein „Fehlerspeicher löschen“ (ob echte Steuergeräte
das am Blockzähler erkennen, ist unbekannt). Bei zwei Fahrten mit 0.6.1 hing
vagdiag mit eingeschalteter Protokolldatei alle 30,72 Sekunden bis zu 47 ms,
weil es auf das Dateisystem wartete; bis 0.7.1 ist das gleich. Ältere
Versionen deshalb nicht mehr mit Protokolldatei benutzen. Seit 0.7.2:
- Protokolldatei und Konsolenausgabe (`-v`, `--bytes`) schreibt ein eigener
  Thread; Speichern geht in Stücken.
- Zeitwächter: Geht ein Byte nicht innerhalb von 15 ms nach der Bestätigung
  hinaus (im Zweifel ab dem früher möglichen Zeitpunkt gerechnet), bricht
  vagdiag den Block ab, ohne weiterzusenden, und verbindet neu. Bei KWP2000
  muss jedes eigene Byte innerhalb von 18 ms nach dem vorigen hinaus (Norm:
  20 ms), sonst ebenso. Während eines Blocks
  pausiert die Speicherbereinigung von Python. Auf vier echten Protokollen
  eines Polo (über 80.000 eigene Bytes) nachgespielt, hätte der Wächter genau
  an den 11 Hängern abgebrochen und sonst nie.
- Bricht eine Verbindung ohne Endeblock ab, reizt vagdiag ein anderes
  Steuergerät erst nach 2,5 s (KWP2000: 5,5 s). Vorher könnte das alte noch
  zuhören und Blöcke für das neue als seine eigenen nehmen – KW1281-Blöcke
  tragen keine Adresse. Auch der Fahrtenschreiber wartet jetzt so lange.

**Rückfragen gelten für genau ein Steuergerät (seit 0.7.2).** Jede Rückfrage,
die etwas am Steuergerät ändert (Fehler löschen, Expertenfunktionen), nennt
Teilenummer und Bauteil und ob das Ziel der Simulator oder das echte Auto ist.
Ausgeführt wird nur, wenn noch genau dieses Gerät verbunden ist. Meldet sich
ein Gerät als Airbag, Bremse, Wegfahrsperre oder Lenkung (Teilenummer oder
Name), bekommt es keine Grundeinstellung und keine Anpassung – auch unter einer
anderen Adresse, falls etwa eine Störung die Reizung verfälscht hat. Für
„Motor steht“ zählt die höchste Drehzahl aus allen gelesenen Gruppen.

## KWP2000

Viele VAG-Steuergeräte von etwa 2002 bis 2006 sprechen über die K-Leitung
KWP2000 statt KW1281. vagdiag erkennt das an der Antwort auf die Reizung und
liest dann Identifikation, Fehlerspeicher, Messwertblöcke und
Anpassungskanäle wie gewohnt – auch im Fahrtenschreiber.

- **Anpassung:** Bei KWP2000 liest vagdiag die Kanäle über die
  VAG-Anpassungsroutine (beginnen, Kanal wählen, Wert lesen, beenden). So
  beschreiben es zwei freie Programme (kw1281test für ein EDC16, bri3d/kwp2000
  für einen Service-Reset am Kombi). Manche Steuergeräte verlangen dafür eine
  Anmeldung – vagdiag meldet sich nicht an und zeigt dann „nur nach
  Anmeldung“.

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
- Meldet sich unter einer anderen Adresse ein Airbag (etwa weil eine Störung
  die Reizung verfälscht hat), trennt vagdiag ebenfalls sofort nach der
  Kennung – auch ohne Freigabe (seit 0.7.2).
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
./vagdiag-cli.sh scan --alle                   # alle Adressen 01–7F (etwa 8 Minuten)
./vagdiag-cli.sh --fast-init --adresse 01 ident   # KWP2000-Motor per Fast-Init
./vagdiag-cli.sh --sim --adresse 01 ident      # Simulator
./vagdiag-cli.sh --sim-kwp2000 --adresse 01 fehler   # Simulator, Motor und Kombi mit KWP2000
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
| „Stellglieddiagnose abgelehnt“ | Das Steuergerät kennt keine, oder eine Bedingung fehlt (z. B. läuft der Motor) – nichts kaputt. |
| „… passt nicht zu dieser Adresse“ | Unter der Adresse hat sich ein anderes Gerät gemeldet (meist nach einer Störung bei der Reizung). Neu öffnen; bleibt es so, Protokoll mitschicken. |
| „… verworfen“ im Protokoll | Gestörte Antwort erkannt und neu angefragt – kein Fehler. |
| „Falsches Komplement … Block abgebrochen“ | Störung auf der K-Leitung (Wackelkontakt, Spannungseinbruch beim Anlassen). vagdiag hat den Block nicht zu Ende gesendet – neu verbinden. |
| „Byte … zu spät … Block abgebrochen“ | Der Rechner hat kurz gehangen. vagdiag hat den Block nicht zu Ende gesendet und verbindet neu – nichts kaputt. Kommt das oft: andere Programme schließen, Protokoll mitschicken. |

Für eine Fehlermeldung direkt nach dem Problem *Datei → Protokoll speichern …*
wählen und die Datei mitschicken.

## Fehlertexte (seit 0.8.1)

Eingebaut sind 193 fünfstellige VAG-Fehlercodes (Motor, Getriebe, ABS,
Airbag, Kombi, Wegfahrsperre, Klima, Komfort, Radio, Datenbus) und 316 P-Codes
(SAE P0xxx und VAG P1xxx), jeweils auf Deutsch und Englisch – bis 0.8.0 waren
es 15 VAG-Codes und 72 P-Codes. Die Bedeutung jedes Codes wurde gegen die
Tabellen des freien Projekts KLineKWP1281Lib geprüft, bei P0-Codes gegen die
Norm; die Texte sind selbst formuliert. Beispiel aus dem Polo: 18058 = P1650
„Datenbus Antrieb: Botschaft vom Kombiinstrument fehlt“. Wo VAG einen P0-Code
anders belegt als die Norm (etwa P0700), fehlt er bewusst. Ohne Eintrag zeigt
vagdiag „(kein Klartext hinterlegt)“; eigene Texte gehen über
`fehlertexte.json` (siehe unten) und haben Vorrang.

## Eigene Texte und Feldnamen

Im Einstellungsordner lassen sich drei Dateien anlegen: `fehlertexte.json`,
`texte.json` und `beschriftungen.json`. Damit ergänzt man Fehlertexte,
Klartexte und Feldnamen für weitere Steuergeräte. Die Namen der Stellglieder
kommen aus `fehlertexte.json` – die Nummern stammen aus derselben Liste, z. B.
`{"01247": "Magnetventil Aktivkohlebehälter"}`. Eigene Einträge gelten in
beiden Sprachen. Beispiel für Feldnamen (Adresse hex → Gruppe → Namen):
```json
{ "25": { "2": ["Start erlaubt", "Motor-SG antwortet", "Schlüssel lesbar", "angelernte Schlüssel"] } }
```

## Grenzen

- Eingebaut sind Feldnamen und Klartexte der Messwerte nur für die geprüften
  Steuergeräte (ME7.5, TRW-Kombi, ABS Mark 20). Andere zeigen Rohwerte und
  „Text Nr. …“. Auch die Fehlertexte decken nicht jeden Code ab.
- Der Fahrtenschreiber kennt die Motorgruppen nur vom ME7.5 (z. B. das Tempo
  in Gruppe 005). Bei anderen Motoren, etwa Dieseln, bleibt die
  Zusammenfassung lückenhaft.
- KWP2000: Identifikation, Fehlerspeicher, Messwertblöcke und Anpassung, noch
  nicht am Auto geprüft; die Stellglieddiagnose dort experimentell.
  CAN-Diagnose geht mit einem KKL-Kabel nicht.
- Eingebaute Namen der Stellglieder gibt es nur für Kombi-Anzeigen und einige
  Diesel-Stellglieder; sonst zeigt vagdiag nur die Nummer. Die Liste der
  Stellglieder entsteht erst beim ersten Durchlauf.
- Welche Stellglieder ABS, Airbag, Wegfahrsperre, Lenkung und
  Niveauregulierung haben, kennt vagdiag nicht im Einzelnen; die Warnungen
  beschreiben, was dort typischerweise angesteuert wird.
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
channels (read only, KW1281 and KWP2000) from older VW/Audi/SEAT/Škoda cars
(K-line) via an FTDI KKL cable. It also records whole drives with the drive
logger (it visits the ABS only at standstill). KWP2000 is new and so far only
tested against the simulator; for engines that ignore the 5-baud init, tick
“Engine: fast init first” (command line: `--fast-init`). CAN diagnostics are not
possible with a KKL cable.

- **Install:** Linux: `./installieren.sh`, then `./vagdiag.sh`. Windows 10/11:
  install Python 3.11+ (python.org, tick “Add python.exe to PATH”), run
  `installieren.bat`, then `vagdiag.bat`.
- **Language:** File → Settings → Sprache / Language → English. On the command
  line, use `--language en`.
- **Files:** no log or CSV files by default. Turn them on under File →
  Settings, or save the in-memory log via File → Save log ….
- **Airbag (15):** asks before connecting. It is never read by the drive
  logger unless you tick the checkbox. If an airbag module answers at any other
  address (e.g. after a disturbed wake-up), vagdiag disconnects right after its
  identification.
- **Save (0.8.0):** the Identification, Fault codes, Adaptation and Scan tabs
  have a **Save …** button that writes what the tab shows as a text file
  (nothing is sent to the module).
- **Drive logger (0.8.0):** the ABS is visited only after two readings at least
  one second apart show 0 km/h; ignition off during the drive is noted with
  its time and no longer counted as a disturbance; every note also goes to the
  log.
- **Drive logger start (0.8.1):** the start check reads the immobilizer first
  and the engine last and stays connected to the engine. Crank the engine only
  when “Recording – start the engine now and drive off” appears – it now comes
  after the first engine readings, so cranking is recorded. If the engine was
  already running, the summary says “cranking not recorded”. Fault codes in
  the summary are sorted by address.
- **Fault texts (0.8.1):** 193 VAG five-digit codes and 316 P-codes (SAE P0xxx,
  VAG P1xxx) in German and English (0.8.0: 15 and 72). Each meaning was checked
  against the tables of the free KLineKWP1281Lib project, P0 codes against the
  standard; the wording is our own. Example: 18058 = P1650 “Powertrain Data
  Bus: Missing Message from Instrument Cluster”.
- **Tabs (0.8.1):** opening a control module shows the module tab used last
  (Identification, Fault codes, Measuring blocks, Adaptation or Expert)
  instead of always Identification; nothing is sent because of it.
- **Scan:** the Scan tab queries the 15 usual addresses (about 1 minute) or
  every address 01–7F (about 8 minutes, only answering ones are listed; 33 =
  OBD-II and 7C = radio factory mode are never woken) – read only – and shows
  part numbers, protocol and fault counts; the report can be saved as text.
  The baud rate selected on the left also applies to the scan (Automatic =
  10400 and 9600; choose 4800 for very old control units). Command line:
  `scan --all`.
- **Expert mode** (menu Expert, off at every start, with a warning): throttle
  body alignment (basic setting 060/098, KW1281, conditions checked first),
  service interval reset (cluster channel 02 → 0, old value backed up, KW1281
  and KWP2000) and output tests (“Next”/“Stop”; the connection is ended and
  re-established afterwards, and after 60 s without “Next” vagdiag stops by
  itself; experimental with KWP2000). Below each button the Expert tab shows
  whether the function is available and, if not, why (0.8.0). Since 0.8.0
  output tests work on every module: on brakes (03, 23, 53), airbag (15),
  immobilizer (25), level control (34) and steering (44) a warning first lists
  the possible damage for that module (default No) – without that confirmation
  the protocol's write lock lets no output-test block out; the ABS also needs
  all wheels at 0 km/h; if a module's identification does not match its
  address, output tests stay locked. After each run vagdiag remembers the
  order of the actuators per module and shows it as an overview next time
  (the module names the next actuator only when it drives it, so the list
  cannot be read beforehand). Everything else that writes stays blocked,
  including channel 00, the odometer, and basic settings and adaptation on
  airbag, brakes, immobilizer, steering and level control. Since 0.8.1 the log
  also records confirmed and declined warnings, a “No” to the confirmation,
  unmet conditions, and output tests, basic settings or service resets that a
  module refused or that ended with an error.
- **Line disturbances:** with KW1281 the control module confirms every byte
  with its inverse. If that confirmation is wrong, the module received a
  different byte – vagdiag stops the block, stays silent for half a second and
  ends the connection, so a disturbed request never turns into a different
  command. Versions 0.2.0 to 0.7.0 carried on once per block; please update.
  Test/save/output-test steps are never repeated automatically (with KWP2000
  not even after “busy”), and after test/save the module must report exactly
  the channel and value.
- **Computer stalls (0.7.2):** after its confirmation the module waits only
  briefly for the next byte (an ME7.5 in the car about 45 ms); a later byte
  starts a new block, which could turn into a different command. vagdiag now
  writes the log file and console output from their own thread (up to 0.7.1
  it stalled up to 47 ms every 30.72 s with the log file on – don't use older
  versions with the log file) and aborts a block if a byte would leave more
  than 15 ms after the confirmation (with KWP2000: more than 18 ms after the
  previous byte; message “Byte … too late”; it reconnects, nothing is
  harmed).
  After a connection breaks off, another module is only woken after 2.5 s
  (KWP2000: 5.5 s). Confirmations name the exact module and whether it is the
  simulator or the real car, and only apply to that module; modules that
  identify as airbag, brakes, immobilizer or steering never get basic settings
  or adaptation, whatever their address.
- **Command line:** `vagdiag-cli --help`. All commands have English names
  (`faults`, `group`, `odometer`, `drive`, `settings` …).

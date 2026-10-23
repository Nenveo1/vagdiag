"""Englische Texte: deutscher Originaltext → englische Fassung (siehe sprache.py).

Die Tests (tests/test_sprache.py) prüfen, dass jeder Text aus dem Programm
hier steht, dass die Platzhalter übereinstimmen und dass nichts übrig ist.
"""

EN: dict[str, str] = {
    # ------------------------------------------------------------ __main__.py
    "PySide6 fehlt. Installation siehe README, z. B.:\n  .venv/bin/pip install -r "
    "requirements.txt\nOhne Oberfläche geht es mit:  python -m vagdiag.cli --help":
        "PySide6 is missing. See the README for installation, e.g.:\n  .venv/bin/pip install "
        "-r requirements.txt\nWithout the window, use:  python -m vagdiag.cli --help",

    # ------------------------------------------------------------ adressen.py
    "Motorelektronik": "Engine electronics",
    "Getriebeelektronik": "Transmission electronics",
    "Bremsenelektronik (ABS)": "Brake electronics (ABS)",
    "Klima-/Heizungselektronik": "A/C and heating electronics",
    "Airbag": "Airbag",
    "Lenkradelektronik": "Steering wheel electronics",
    "Schalttafeleinsatz (Kombi)": "Instrument cluster",
    "Wegfahrsperre": "Immobilizer",
    "Zentralverriegelung": "Central locking",
    "Innenraumüberwachung": "Interior monitoring",
    "Komfortsystem": "Comfort system",
    "Leuchtweitenregulierung": "Headlight range control",
    "Radio": "Radio",
    "unbekanntes Steuergerät": "unknown control module",
    "Zentralelektrik": "Central electrics",
    "Diagnose-Interface Datenbus (Gateway)": "Data bus diagnostic interface (gateway)",
    "Zugang/Startberechtigung": "Access/Start Authorization",
    "Sitzverstellung Beifahrerseite": "Seat Adjustment, Passenger Side",
    "Bedieneinheit vorn": "Control Head",
    "Mediaplayer 1": "Media Player 1",
    "Digitalradio": "Digital Radio",
    "Motorelektronik 2": "Engine 2",
    "Abstandsregelung": "Auto Distance Regulation",
    "Zusatzheizung": "Auxiliary Heater",
    "Mediaplayer 2": "Media Player 2",
    "Allradelektronik": "All Wheel Drive",
    "Bremskraftverstärker": "Brake Booster",
    "Klimaanlage hinten": "HVAC, Rear",
    "Licht links": "Left Light",
    "OBD-II (allgemein)": "OBD-II (generic)",
    "Niveauregulierung": "Level Control",
    "Sitzverstellung Fahrerseite": "Driver's Seat",
    "Navigation": "Navigation",
    "Licht rechts": "Right Light",
    "Sonderfunktion": "Special Function",
    "Türelektronik Fahrerseite": "Door Electronics, Driver",
    "Lenkhilfe": "Steering Assist",
    "Soundsystem": "Sound System",
    "Zentralelektrik 2": "Central Electronics 2",
    "Türelektronik Beifahrerseite": "Door Electronics, Passenger",
    "Parkbremse": "Parking Brake",
    "TV-Tuner": "TV Tuner",
    "Informationselektronik": "Information Electronics",
    "Batterieregelung": "Battery Regulation",
    "Tür hinten links": "Door, Rear Left",
    "Reifendruckkontrolle": "Tire Pressure Monitor",
    "Sprachbedienung": "Voice Control",
    "Wischer": "Wipers",
    "Anhängerfunktion": "Trailer Function",
    "Bedieneinheit Dach": "Control Head, Roof",
    "Tür hinten rechts": "Door, Rear Right",
    "Telematik": "Telematics",
    "Einparkhilfe": "Park Assist",
    "Telefon": "Telephone",
    "Radio (Werksmodus)": "Radio (factory mode)",
    "OBD-II-Adresse (allgemeine Abgasdiagnose, kein eigenes Steuergerät)":
        "OBD-II address (generic emissions diagnostics, not a control module of its own)",
    "Werksmodus des Radios": "factory mode of the radio",

    # ------------------------------------------------------------ airbag.py
    "bekannter Firmwarefehler: kann bei Störungen in der Kommunikation den nicht löschbaren "
    "Fehler 65535 speichern – die Airbaglampe bleibt dann an und das Steuergerät muss "
    "getauscht werden":
        "known firmware bug: communication problems can make it store the fault 65535, which "
        "cannot be cleared – the airbag light then stays on and the module must be replaced",
    "Bestimmte Airbag-Steuergeräte (6Q0 909 605 A, Golf/Jetta/Beetle 2000–2001 und ähnliche "
    "SEAT/Škoda) haben einen Firmwarefehler: Bei Störungen in der Kommunikation können sie einen "
    "Fehler speichern, der sich nicht löschen lässt. Die Airbaglampe bleibt dann an, das "
    "Steuergerät muss getauscht werden. Mit einfachen KKL-Kabeln ist das wahrscheinlicher.\n\n"
    "vagdiag liest beim Airbag nur Kennung und Fehlerspeicher und beendet die Verbindung "
    "sofort, wenn sich ein betroffenes Gerät meldet. Andere Teilenummern gelten als "
    "unbedenklich.\n\nWährend der Verbindung kann die Airbaglampe leuchten – nach dem Trennen "
    "geht sie wieder aus.":
        "Certain airbag control modules (6Q0 909 605 A, Golf/Jetta/Beetle 2000–2001 and similar "
        "SEAT/Škoda) have a firmware bug: communication problems can make them store a fault "
        "that cannot be cleared. The airbag light then stays on and the module must be "
        "replaced. This is more likely with simple KKL cables.\n\n"
        "With the airbag, vagdiag only reads the identification and the fault codes, and it "
        "disconnects immediately if an affected module answers. Other part numbers are "
        "considered safe.\n\nThe airbag light may come on while connected – it goes out again "
        "after disconnecting.",
    "Airbag-Steuergerät (Adresse 15) nicht freigegeben – vorher bestätigen (Oberfläche: "
    "Rückfrage, Kommandozeile: --mit-airbag).":
        "Airbag control module (address 15) not enabled – confirm first (window: confirmation "
        "dialog, command line: --with-airbag).",
    "Airbag-Steuergerät {teilenummer}: {grund}. vagdiag hat die Verbindung sofort beendet und "
    "liest dieses Gerät nicht.":
        "Airbag control module {teilenummer}: {grund}. vagdiag disconnected immediately and "
        "does not read this module.",
    "Unter Adresse {adresse:02X} hat sich ein Airbag-Steuergerät gemeldet ({kennung}) – "
    "vermutlich hat eine Störung die Reizung verfälscht. vagdiag hat die Verbindung sofort "
    "beendet; den Airbag liest es nur unter Adresse 15 nach Rückfrage.":
        "An airbag control module answered at address {adresse:02X} ({kennung}) – probably "
        "a disturbance corrupted the wake-up. vagdiag ended the connection immediately; it "
        "only reads the airbag at address 15 after asking.",

    # ------------------------------------------------------------ aufzeichnung.py
    "Zeit": "Time",
    "Sekunden": "Seconds",
    "Gruppe": "Group",
    "Feld 1": "Field 1",
    "Einheit 1": "Unit 1",
    "Feld 2": "Field 2",
    "Einheit 2": "Unit 2",
    "Feld 3": "Field 3",
    "Einheit 3": "Unit 3",
    "Feld 4": "Field 4",
    "Einheit 4": "Unit 4",
    "Ereignis": "Event",
    "Messwerte werden aufgezeichnet: %s": "Recording measured values: %s",
    "Simulator – keine echten Fahrzeugdaten": "Simulator – no real vehicle data",
    "Gruppe {gruppe:03d}:": "Group {gruppe:03d}:",
    "Feld {nummer}": "Field {nummer}",
    "Aufzeichnung beendet (%d Zeilen): %s": "Recording finished (%d lines): %s",

    # ------------------------------------------------------------ berichte.py
    "vagdiag {version} – {titel} vom {datum}": "vagdiag {version} – {titel}, {datum}",
    "gelesen um {uhrzeit}": "read at {uhrzeit}",
    "Anpassungskanäle": "Adaptation channels",
    "Nur gelesen – vagdiag hat dabei nichts geändert.":
        "Read only – vagdiag changed nothing while reading.",
    "Keine Kanäle gelesen.": "No channels read.",

    # ------------------------------------------------------------ beschriftung.py
    "Motordrehzahl": "Engine speed",
    "Kühlmitteltemperatur": "Coolant temperature",
    "Lambdaregelung": "Lambda control",
    "Grundeinstellungsbedingungen": "Basic setting conditions",
    "Motorlast": "Engine load",
    "Einspritzzeit": "Injection time",
    "Saugrohrdruck": "Intake manifold pressure",
    "Drosselklappenwinkel": "Throttle angle",
    "Zündwinkel": "Ignition timing",
    "Bordspannung": "Supply voltage",
    "Ansauglufttemperatur": "Intake air temperature",
    "Fahrgeschwindigkeit": "Vehicle speed",
    "Lastzustand": "Load state",
    "Geschwindigkeit": "Speed",
    "Öldruckschalter": "Oil pressure switch",
    "Uhrzeit": "Clock",
    "Kilometerstand": "Odometer",
    "Tankinhalt": "Fuel level",
    "Tankgeber": "Fuel level sender",
    "Rad vorn links": "Front left wheel",
    "Rad vorn rechts": "Front right wheel",
    "Rad hinten links": "Rear left wheel",
    "Rad hinten rechts": "Rear right wheel",
    "Bremslichtschalter": "Brake light switch",
    "Kühlmittel über 80 °C": "Coolant above 80 °C",
    "Drehzahl unter 2000/min": "Engine speed below 2000/min",
    "Lambdaregelung aktiv": "Lambda control active",
    "ja": "yes",
    "nein": "no",
    "{stelle}. Stelle von rechts: {text}": "Digit {stelle} from the right: {text}",
    "Eigene Feldbezeichnungen geladen: %s": "Own field labels loaded: %s",
    "Eigene Feldbezeichnungen nicht lesbar (%s): %s": "Own field labels not readable (%s): %s",

    # ------------------------------------------------------------ cli.py
    "ja oder nein": "yes or no",
    "Kein Fehler gespeichert.": "No fault codes stored.",
    "{anzahl} Fehler gespeichert:": "{anzahl} fault code(s) stored:",
    "wieder verbunden ({uhrzeit})": "reconnected ({uhrzeit})",
    "wieder verbunden": "reconnected",
    "Verbindung verloren ({grund}) – verbinde neu": "Connection lost ({grund}) – reconnecting",
    "Verbindung verloren: {grund}": "Connection lost: {grund}",
    "Neuverbindung, Versuch {nummer}": "Reconnecting, attempt {nummer}",
    "Kanal {kanal:02d}": "Channel {kanal:02d}",
    "Einstellungsdatei:": "Settings file:",
    "Sprache:": "Language:",
    "Protokolldatei:": "Log file:",
    "Log-Ordner:": "Log folder:",
    "CSV automatisch:": "CSV automatically:",
    "CSV-Ordner:": "CSV folder:",
    "Neu verbinden:": "Reconnect:",
    "Gemerkte Baudraten:": "Remembered baud rates:",
    "Sprache für diesen Lauf (Standard: Einstellung)":
        "language for this run (default: settings)",
    "Simulator statt Kabel": "simulator instead of the cable",
    "Kabel-Adresse, z. B. ftdi:///1 (Linux) oder d2xx:0 (Windows)":
        "cable address, e.g. ftdi:///1 (Linux) or d2xx:0 (Windows)",
    "Art der 5-Baud-Reizung; bitbang als Ausweichweg für Klon-Chips":
        "how the 5-baud init is generated; bitbang as a fallback for clone chips",
    "Steuergeräte-Adresse hexadezimal (01 Motor, 17 Kombi); Standard 01, bei „kilometerstand“ "
    "17":
        "control module address in hex (01 engine, 17 instrument cluster); default 01, 17 for "
        "“odometer”",
    "Airbag-Steuergerät (15) ohne Rückfrage einbeziehen (siehe README)":
        "include the airbag control module (15) without asking (see README)",
    "DATEI": "FILE",
    "Protokolldatei schreiben – ohne DATEI eine neue im Log-Ordner":
        "write a log file – without FILE a new one in the log folder",
    "Protokolldatei in diesen Ordner schreiben (nur dieser Lauf)":
        "write the log file to this folder (this run only)",
    "CSV-Ordner nur für diesen Lauf": "CSV folder for this run only",
    "Protokollablauf anzeigen": "show the protocol flow",
    "auch jedes Byte anzeigen": "also show every byte",
    "angeschlossene FTDI-Kabel auflisten": "list connected FTDI cables",
    "Kabel öffnen und Echo prüfen": "open the cable and check the echo",
    "Steuergerät identifizieren": "identify the control module",
    "Fehlerspeicher lesen": "Read fault codes",
    "Fehlerspeicher löschen": "Clear fault codes",
    "ohne Rückfrage": "without asking",
    "Messwertgruppen lesen (mit Min/Max, auf Wunsch CSV)":
        "read measuring blocks (with min/max, optionally CSV)",
    "GRUPPE": "GROUP",
    "BEFEHL": "COMMAND",
    "ADRESSE": "ADDRESS",
    "bis Strg+C": "until Ctrl+C",
    "als CSV aufzeichnen": "record as CSV",
    "nicht aufzeichnen": "do not record",
    "bei Verbindungsabbruch aufhören statt neu zu verbinden":
        "stop on a lost connection instead of reconnecting",
    "alle belegten Messwertgruppen finden": "find all measuring blocks in use",
    "Anpassungskanäle lesen (nur lesen, nie Kanal 00)":
        "read adaptation channels (read only, never channel 00)",
    "KANAL": "CHANNEL",
    "alle lesbaren Anpassungskanäle finden (nur lesen)":
        "find all readable adaptation channels (read only)",
    "Kilometerstand aus dem Kombi (Gruppe 002, sonst Anpassungskanal 09)":
        "odometer from the instrument cluster (group 002, otherwise adaptation channel 09)",
    "Fahrtenschreiber: ganze Fahrt aufzeichnen (Enter = Ereignis markieren, Strg+C = beenden)":
        "drive logger: record a whole drive (Enter = mark an event, Ctrl+C = finish)",
    "LISTE": "LIST",
    "z. B. 1,2,3,4,5": "e.g. 1,2,3,4,5",
    "Sekunden zwischen zwei Besuchen beim Kombi (0 = nie)":
        "seconds between two visits to the instrument cluster (0 = never)",
    "Sekunden je Besuch": "seconds per visit",
    "ohne Start- und Abschlussprüfung": "without start and final check",
    "Ordner und Optionen anzeigen/ändern": "show/change folders and options",
    "ORDNER": "FOLDER",
    "ja|nein": "yes|no",
    "Protokolldatei immer schreiben": "always write a log file",
    "Messwertgruppen immer als CSV aufzeichnen": "always record measuring blocks as CSV",
    "Ohne Rückfragemöglichkeit nur mit --mit-airbag.":
        "Without a way to ask, only with --with-airbag.",
    "Trotzdem mit dem Airbag-Steuergerät verbinden? [j/N] ":
        "Connect to the airbag control module anyway? [y/N] ",
    "Protokoll: {pfad}": "Log: {pfad}",
    "Protokolldatei für die Fehlersuche: {pfad}": "Log file for troubleshooting: {pfad}",
    "Für die Fehlersuche mit --log wiederholen – dann entsteht eine Protokolldatei.":
        "For troubleshooting, repeat with --log – that writes a log file.",
    "Fehler: {fehler}": "Error: {fehler}",
    "Kein FTDI-Kabel gefunden.": "No FTDI cable found.",
    "Kabel: {geraet}\nEcho: {echo}": "Cable: {geraet}\nEcho: {echo}",
    "übersprungen – mit --mit-airbag einschließen (Hinweis in der README)":
        "skipped – include it with --with-airbag (see the note in the README)",
    "keine Antwort": "no response",
    "Abgebrochen.": "Cancelled.",
    "Fehlerspeicher löschen? Readiness wird dabei zurückgesetzt. [j/N] ":
        "Clear the fault codes? This also resets the readiness codes. [y/N] ",
    "Gelöscht.": "Cleared.",
    "Sofort wieder gesetzt:": "Set again right away:",
    "Fehlerspeicher jetzt:": "Fault codes now:",
    "Suche Messwertgruppen {von:03d}–{bis:03d} (Strg+C bricht ab) …":
        "Searching measuring blocks {von:03d}–{bis:03d} (Ctrl+C cancels) …",
    "{anzahl} belegte Gruppen:": "{anzahl} groups in use:",
    "Kanal {kanal:02d}:": "Channel {kanal:02d}:",
    "Lese Anpassungskanäle {von:02d}–{bis:02d} (nur lesen, Strg+C bricht ab) …":
        "Reading adaptation channels {von:02d}–{bis:02d} (read only, Ctrl+C cancels) …",
    "{anzahl} lesbare Kanäle:": "{anzahl} readable channels:",
    "Hinweis: Der Kilometerstand steht normalerweise im Kombi (Adresse 17).":
        "Note: the odometer is normally in the instrument cluster (address 17).",
    "Für eine Fehlermeldung bitte diese Protokolldatei mitschicken: {pfad}":
        "When reporting a problem, please include this log file: {pfad}",
    "Für eine Fehlermeldung bitte mit --log wiederholen und die Protokolldatei mitschicken.":
        "When reporting a problem, please repeat with --log and include the log file.",
    "Der Airbag-Fehlerspeicher wird nicht gelesen (mit --mit-airbag einschließen).":
        "The airbag fault codes are not read (include them with --with-airbag).",
    "Enter": "Enter",
    "Ereignis markiert, lese Fehlerspeicher …": "Event marked, reading fault codes …",
    "Fahrt wird beendet – Abschlussprüfung läuft, Zündung noch an lassen. Nochmal Strg+C bricht "
    "sofort ab.":
        "Finishing the drive – final check running, keep the ignition on. Press Ctrl+C again "
        "to cancel immediately.",
    "Abbruch …": "Cancelling …",
    "Zusammenfassung gespeichert: {pfad}": "Summary saved: {pfad}",
    "Aufzeichnung: {pfad}": "Recording: {pfad}",
    "Messung läuft – Strg+C beendet sie.": "Measuring – Ctrl+C stops.",
    "Messung beendet.": "Measurement stopped.",
    "Min/Max:": "Min/max:",
    "Gruppe {gruppe:03d} Feld {feld}": "Group {gruppe:03d} field {feld}",
    "CSV-Datei: {pfad}": "CSV file: {pfad}",
    "Fast-Init beim Motor:": "Fast init for the engine:",
    "VAG-Diagnose über KKL-Kabel (KW1281/KWP2000)":
        "VAG diagnostics via KKL cable (KW1281/KWP2000)",
    "Motor (01): zuerst den KWP2000-Fast-Init probieren (Standard: Einstellung)":
        "engine (01): try the KWP2000 fast init first (default: setting)",
    "beim Motor immer zuerst den Fast-Init probieren":
        "always try the fast init first for the engine",
    "Sekunden zwischen zwei Besuchen beim ABS, nur im Stand (0 = nie)":
        "seconds between two visits to the ABS, only at standstill (0 = never)",
    "Fahrtenschreiber. Enter markiert ein Ereignis (z. B. Warnlampe an) und liest\n"
    "sofort den Fehlerspeicher des Motors, den des ABS beim nächsten Halt. Strg+C\n"
    "beendet die Fahrt – danach läuft noch die Abschlussprüfung, Zündung so lange\n"
    "an lassen. Das ABS wird nur im Stand besucht.":
        "Drive logger. Enter marks an event (e.g. a warning light came on) and\n"
        "immediately reads the engine fault codes, those of the ABS at the next stop.\n"
        "Ctrl+C ends the drive – the final check runs afterwards, keep the ignition\n"
        "on until it is done. The ABS is only visited at standstill.",
    "Simulator, dessen Motor und Kombi KWP2000 sprechen":
        "simulator whose engine and instrument cluster speak KWP2000",
    "übliche Steuergeräte abfragen (mit --alle: alle Adressen 01–7F)":
        "query the usual control modules (with --all: every address 01–7F)",
    "alle Adressen 01–7F abfragen (etwa 8 Minuten)": "query every address 01–7F (about 8 minutes)",
    "Frage alle Adressen 01–7F ab – etwa 8 Minuten, Strg+C bricht ab. Gezeigt werden nur die "
    "Adressen, die antworten.":
        "Querying every address 01–7F – about 8 minutes, Ctrl+C cancels. Only addresses that "
        "answer are shown.",
    "… Adressen {von:02X}–{bis:02X}": "… addresses {von:02X}–{bis:02X}",
    "übersprungen – {grund}": "skipped – {grund}",
    "Keine Antwort ({anzahl}): {liste}": "No answer ({anzahl}): {liste}",

    # ------------------------------------------------------------ einstellungen.py
    "kein JSON-Objekt": "not a JSON object",
    "Einstellungen nicht lesbar (%s) – nehme Standardwerte":
        "Settings not readable (%s) – using defaults",
    "Einstellungen konnten nicht gespeichert werden: %s": "Settings could not be saved: %s",

    # ------------------------------------------------------------ experte.py
    "060 – E-Gas (z. B. ME7)": "060 – drive-by-wire (e.g. ME7)",
    "098 – Drosselklappe mit Seilzug": "098 – cable-operated throttle",
    "Drosselklappe Poti 1": "Throttle pot 1",
    "Drosselklappe Poti 2": "Throttle pot 2",
    "Lernschritt": "Learning step",
    "Anpassungsstatus": "Adaptation status",
    "Erst mit {steuergeraet} verbinden": "Connect to {steuergeraet} first",
    "Expertenfunktionen gibt es bisher nur bei KW1281 – dieses Steuergerät spricht KWP2000.":
        "Expert functions are so far only available with KW1281 – this control module speaks "
        "KWP2000.",
    "Motor aus (Drehzahl 0)": "Engine off (speed 0)",
    "Bordspannung mindestens 11,5 V": "Supply voltage at least 11.5 V",
    "Kühlmittel zwischen 5 und 95 °C": "Coolant between 5 and 95 °C",
    "Kein Fehler im Motor-Fehlerspeicher": "No fault code in the engine",
    "{anzahl} Fehler": "{anzahl} fault(s)",
    "Drosselklappe anlernen nur mit Gruppe 060 oder 098":
        "Throttle body alignment only with group 060 or 098",
    "Gruppe {gruppe:03d} gibt es in diesem Motorsteuergerät nicht ({fehler}) – die "
    "Drosselklappe wird hier anders angelernt.":
        "This engine ECU has no group {gruppe:03d} ({fehler}) – its throttle body is aligned "
        "differently.",
    "EXPERTE: Prüfung Grundeinstellung %03d – %s": "EXPERT: check for basic setting %03d – %s",
    "Nicht gestartet – Bedingung nicht erfüllt: {liste}":
        "Not started – condition not met: {liste}",
    "Nicht gestartet – nicht prüfbar: {liste}": "Not started – cannot be checked: {liste}",
    "EXPERTE: Grundeinstellung %03d startet (%s, %s)":
        "EXPERT: basic setting %03d starting (%s, %s)",
    "EXPERTE: Grundeinstellung abgebrochen": "EXPERT: basic setting cancelled",
    "EXPERTE: Rückkehr zu den Messwerten: %s": "EXPERT: returning to measuring blocks: %s",
    "EXPERTE: Fehlerspeicher danach nicht lesbar: %s":
        "EXPERT: fault codes not readable afterwards: %s",
    "EXPERTE: Grundeinstellung %03d beendet nach %.0f s – Feld 4: %s":
        "EXPERT: basic setting %03d finished after %.0f s – field 4: %s",
    "Kanal 02 gibt es bei diesem Kombi nicht ({fehler}). Dann hat es keine Service-Anzeige, "
    "oder sie wird nur am Kombi selbst zurückgesetzt (Knopf).":
        "This cluster has no channel 02 ({fehler}). Then it either has no service reminder, or "
        "the reminder can only be reset on the cluster itself (button).",
    "EXPERTE: alter Wert gesichert in %s": "EXPERT: old value saved to %s",
    "Kanal 02 steht jetzt auf {jetzt} statt {vorher} – nichts geschrieben, bitte neu lesen.":
        "Channel 02 is now {jetzt} instead of {vorher} – nothing written, please read it again.",
    "EXPERTE: Service-Intervall zurückgesetzt – Kanal 02 vorher %d, jetzt %d":
        "EXPERT: service interval reset – channel 02 was %d, now %d",
    "Erst ein Steuergerät öffnen": "Open a control module first",
    "Diese Expertenfunktion gibt es bisher nur bei KW1281 – dieses Steuergerät spricht KWP2000.":
        "This expert function is only available for KW1281 so far – this control module "
        "speaks KWP2000.",
    "EXPERTE: Prüfung Stellglieddiagnose %02X – %s": "EXPERT: check for output test %02X – %s",
    "EXPERTE: Stellglieddiagnose %02X startet (%s, %s)%s":
        "EXPERT: output test %02X starting (%s, %s)%s",
    "KWP2000, experimentell": "KWP2000, experimental",
    "EXPERTE: Stellglieddiagnose beenden: %s": "EXPERT: ending the output test: %s",
    "EXPERTE: nach der Stellglieddiagnose nicht wieder verbunden: %s":
        "EXPERT: not reconnected after the output test: %s",
    "EXPERTE: Stellglieddiagnose %02X beendet nach %.0f s – %d Schritte (%s)":
        "EXPERT: output test %02X ended after %.0f s – %d steps (%s)",
    "EXPERTE: %.0f s ohne „Weiter“ – Stellglieddiagnose wird beendet":
        "EXPERT: %.0f s without “Next” – ending the output test",
    "Inzwischen ist ein anderes Steuergerät verbunden ({jetzt} statt {vorher}) – nichts "
    "gesendet.":
        "A different control module is connected by now ({jetzt} instead of {vorher}) – "
        "nothing sent.",
    "Alle Räder stehen (0 km/h)": "All wheels stationary (0 km/h)",
    "Nicht gestartet – die Warnung vor möglichen Schäden ({art}) ist nicht bestätigt.":
        "Not started – the warning about possible damage ({art}) has not been confirmed.",
    "Expertenmodus ist aus – einschalten über Menü Experte → Expertenmodus …":
        "Expert mode is off – switch it on via menu Expert → Expert mode …",
    "Gerade läuft: {was} – erst beenden.": "Currently running: {was} – stop it first.",
    "vagdiag arbeitet gerade – bitte kurz warten.": "vagdiag is busy – please wait a moment.",
    "Erst links mit {steuergeraet} verbinden (Adresse {adresse:02X}, „Öffnen“).":
        "Connect to {steuergeraet} on the left first (address {adresse:02X}, “Open”).",
    "Verbunden ist {jetzt} – dafür links mit {soll} verbinden.":
        "Connected to {jetzt} – for this, connect to {soll} on the left.",
    "Gibt es bisher nur bei KW1281 – dieses Steuergerät spricht KWP2000.":
        "So far only available with KW1281 – this control module uses KWP2000.",
    "Bereit – {steuergeraet}.": "Ready – {steuergeraet}.",
    "Erst links ein Steuergerät öffnen – die Stellglieddiagnose gilt dem geöffneten Steuergerät.":
        "Open a control module on the left first – the output tests apply to the open control "
        "module.",
    "Achtung, {art}: Vor dem Start nennt vagdiag die möglichen Schäden und fragt nach.":
        "Caution, {art}: before starting, vagdiag lists the possible damage and asks for "
        "confirmation.",
    "EXPERTE: Grundeinstellung %03d nach %.0f s mit Fehler beendet: %s":
        "EXPERT: basic setting %03d ended with an error after %.0f s: %s",
    "EXPERTE: Service-Intervall nicht zurückgesetzt: %s": "EXPERT: service interval not reset: %s",
    "Warnung ({art}) bestätigt": "warning ({art}) confirmed",
    "EXPERTE: Stellglieddiagnose %02X nach %d Schritten nicht fortgesetzt: %s":
        "EXPERT: output test %02X not continued after %d steps: %s",

    # ------------------------------------------------------------ fahrtenschreiber.py
    "Start": "Start",
    "Fahrt": "Drive",
    "Ende": "End",
    "Abschluss": "Finish",
    "Fertig": "Done",
    "Steuergerät": "Control module",
    "Phase": "Phase",
    "kein Fehler": "no fault",
    "{anzahl} Fehler:": "{anzahl} fault(s):",
    "Fahrtenschreiber – %s: %s": "Drive logger – %s: %s",
    "Abgebrochen": "Cancelled",
    "Tempo zuletzt {tempo:.0f} km/h": "last speed {tempo:.0f} km/h",
    "{steuergeraet} nicht erreichbar ({fehler})": "{steuergeraet} not reachable ({fehler})",
    "Trennen: %s": "Disconnect: %s",
    "{adresse:02X}/{gruppe:03d} gibt es nicht – wird übersprungen":
        "{adresse:02X}/{gruppe:03d} does not exist – skipped",
    "nicht lesbar ({fehler})": "not readable ({fehler})",
    "Fehlerspeicher {steuergeraet}: {ergebnis}": "Fault codes {steuergeraet}: {ergebnis}",
    "nicht gelesen (Airbag nicht freigegeben)": "not read (airbag not enabled)",
    "verbinde mit {steuergeraet} …": "connecting to {steuergeraet} …",
    "nicht erreichbar": "not reachable",
    "Tankinhalt im Stand ({dauer:.0f} s) …": "Fuel level at standstill ({dauer:.0f} s) …",
    "Aufzeichnung läuft": "Recording",
    "Fahrt beginnt": "Drive starts",
    "Verbindung zum Motor verloren: {fehler}": "Connection to the engine lost: {fehler}",
    "Motor läuft": "Engine running",
    "Motor steht": "Engine stopped",
    "kurzer Besuch bei {steuergeraet} …": "short visit to {steuergeraet} …",
    "Störung bei {adresse:02X}: {fehler}": "Disturbance at {adresse:02X}: {fehler}",
    "{text} – lese Fehlerspeicher …": "{text} – reading fault codes …",
    "EREIGNIS ({text}) um {uhrzeit}": "EVENT ({text}) at {uhrzeit}",
    "Fahrtenschreiber gestartet": "Drive logger started",
    "(Simulator – keine echten Fahrzeugdaten)": "(simulator – no real vehicle data)",
    "Startprüfung: Tankinhalt im Stand, Fehlerspeicher":
        "Start check: fuel level at standstill, fault codes",
    "Abschlussprüfung – Zündung noch an lassen": "Final check – keep the ignition on",
    "Fahrtenschreiber abgebrochen": "Drive logger cancelled",
    "Fahrtenschreiber beendet": "Drive logger finished",
    "-zusammenfassung": "-summary",
    "Zusammenfassung nicht gespeichert: %s": "Summary not saved: %s",
    "Fahrt vom {datum} – Dauer {minuten:.0f} min": "Drive on {datum} – duration {minuten:.0f} min",
    "SIMULATOR, keine echten Fahrzeugdaten": "SIMULATOR, no real vehicle data",
    "abgebrochen": "cancelled",
    "Datei: {pfad}": "File: {pfad}",
    "Fehlerspeicher": "Fault codes",
    "Ereignis {uhrzeit} ({text}):": "Event {uhrzeit} ({text}):",
    "nicht gelesen": "not read",
    "Kühlmittel (Motor): Anfang {anfang} °C, höchstens {hoechstens} °C":
        "Coolant (engine): start {anfang} °C, maximum {hoechstens} °C",
    "nach dem Warmlaufen {von}–{bis} °C (Median {median} °C)":
        "after warm-up {von}–{bis} °C (median {median} °C)",
    "Merker „Kühlmittel über 80 °C“ (Gruppe 001): {anteil:.0f} % der Zeit":
        "Flag “coolant above 80 °C” (group 001): {anteil:.0f} % of the time",
    "Hinweis: Nach über 15 Minuten nie 85 °C erreicht – Thermostat beobachten.":
        "Note: never reached 85 °C after more than 15 minutes – keep an eye on the thermostat.",
    "Kühlmittel (Kombi, während der Fahrt): {von}–{bis} °C":
        "Coolant (cluster, while driving): {von}–{bis} °C",
    "Motor aus {spannung} V": "engine off {spannung} V",
    "beim Anlassen min. {spannung} V": "cranking min. {spannung} V",
    "bei laufendem Motor Median {median} V ({von}–{bis} V)":
        "engine running median {median} V ({von}–{bis} V)",
    "Bordspannung:": "Supply voltage:",
    "Ansauglufttemperatur: {von}–{bis} °C": "Intake air temperature: {von}–{bis} °C",
    "Drehzahl: höchstens {hoechstens}/min, Median {median}/min":
        "Engine speed: maximum {hoechstens}/min, median {median}/min",
    "Motorsteuergerät": "Engine ECU",
    "Kombi": "Cluster",
    "ABS": "ABS",
    "Tempo höchstens:": "Top speed:",
    "Stand am Anfang": "level at the start",
    "während der Fahrt": "while driving",
    "Stand am Ende": "level at the end",
    "Median aus {anzahl} Werten": "median of {anzahl} values",
    "Tankanzeige:": "Fuel gauge:",
    "Nicht erreicht:": "Not reached:",
    "bei etwa {tempo:.0f} km/h": "at about {tempo:.0f} km/h",
    "bei der Abschlussprüfung gelesen": "read during the final check",
    "im Stand gelesen um {uhrzeit}": "read at standstill at {uhrzeit}",
    "Halt – lese den Fehlerspeicher von {steuergeraet} nach …":
        "Stopped – catching up on the fault codes of {steuergeraet} …",
    "Zündung ist wieder an – die Prüfung läuft": "Ignition is on again – the check is running",
    "Keine Antwort – ist die Zündung aus? Bitte einschalten (Motor nicht starten). "
    "vagdiag wartet bis zu {sekunden:.0f} s.":
        "No answer – is the ignition off? Please switch it on (do not start the engine). "
        "vagdiag waits up to {sekunden:.0f} s.",
    "Zündung aus? Bitte einschalten – warte noch {rest:.0f} s …":
        "Ignition off? Please switch it on – waiting another {rest:.0f} s …",
    "Zündung aus – {phase} nicht möglich": "Ignition off – {phase} not possible",
    "nicht geprüft (Zündung aus)": "not checked (ignition off)",
    "{steuergeraet} wird nur im Stand besucht – das Tempo ist aber unbekannt (eine "
    "Motor-Gruppe mit dem Tempo mitlesen, bei ME7 die 005)":
        "{steuergeraet} is only visited at standstill – but the speed is unknown (log an "
        "engine group that contains the speed, on the ME7 group 005)",
    "wird beim nächsten Halt gelesen": "will be read at the next stop",
    "{steuergeraet}: Fehlerspeicher wird beim nächsten Halt gelesen (antwortet nur im Stand)":
        "{steuergeraet}: fault codes will be read at the next stop (only answers at "
        "standstill)",
    "nicht gelesen (kein Halt mehr)": "not read (no further stop)",
    "(nur im Stand)": "(only at standstill)",
    "Motordaten: {anteil:.0f} % der Fahrzeit · Besuche: {besuche} · Störungen: {stoerungen}":
        "Engine data: {anteil:.0f} % of the drive · visits: {besuche} · disturbances: "
        "{stoerungen}",
    "nicht geprüft – die Zündung war aus": "not checked – the ignition was off",
    "Lambdaregelung (warmer Motor): Mittel {mittel} %, meist {p5} bis {p95} %, äußerste "
    "Werte {von} bis {bis} %":
        "Lambda control (warm engine): mean {mittel} %, mostly {p5} to {p95} %, extremes "
        "{von} to {bis} %",
    "Stand am Ende nicht gemessen (Zündung aus)": "level at the end not measured (ignition off)",
    "Bremslichtschalter (ABS-Besuche): {anzahl} Werte, bei {betaetigt} von {besuche} Besuchen "
    "betätigt":
        "Brake light switch (ABS visits): {anzahl} values, pressed during {betaetigt} of "
        "{besuche} visits",
    "Fahrtenschreiber – Notiz: %s": "Drive logger – note: %s",
    "Motor antwortet nicht ({fehler}) – Zündung aus?":
        "Engine does not answer ({fehler}) – ignition off?",
    "Verbindungsaufbau zum Motor gestört: {fehler}":
        "Connecting to the engine disturbed: {fehler}",
    "Motor antwortet wieder – die Zündung war vermutlich von {von} bis {bis} aus":
        "Engine answers again – the ignition was probably off from {von} to {bis}",
    "Zündung zwischendurch aus (keine Störung): {zeiten}":
        "Ignition off in between (not a disturbance): {zeiten}",
    "Der Motor lief schon beim ersten Messwert – das Anlassen ist nicht aufgezeichnet":
        "The engine was already running at the first reading – cranking was not recorded",
    "Aufzeichnung läuft – jetzt Motor starten und losfahren":
        "Recording – start the engine now and drive off",
    "Startprüfung fertig": "Start check done",
    "Anlassen nicht aufgezeichnet (Motor lief schon beim ersten Messwert)":
        "cranking not recorded (engine already running at the first reading)",

    # ------------------------------------------------------------ fehler.py
    "%d eigene Fehlertexte geladen": "%d own fault texts loaded",
    "Eigene Fehlertexte nicht lesbar (%s): %s": "Own fault texts not readable (%s): %s",
    "(kein Klartext hinterlegt)": "(no description available)",
    "sporadisch": "intermittent",

    # ------------------------------------------------------------ gui.py
    "Automatisch (gemerkte zuerst)": "Automatic (remembered first)",
    "Kabel-Adresse: ftdi:///1 (Linux) bzw. d2xx:0 (Windows) nimmt das erste angeschlossene "
    "FTDI-Kabel. „Kabel suchen“ trägt das gefundene ein.":
        "Cable address: ftdi:///1 (Linux) or d2xx:0 (Windows) takes the first connected FTDI "
        "cable. “Find cable” enters the one it finds.",
    "Dabei auch den Airbag-Fehlerspeicher lesen (Adresse 15)":
        "Also read the airbag fault codes (address 15)",
    "Standardmäßig aus. Beim Einschalten erscheint der Hinweis zum Airbag-Steuergerät.":
        "Off by default. Switching it on shows the note about the airbag control module.",
    "Hinweise zur Einrichtung stehen in der README.": "Setup notes are in the README.",
    "Den Airbag-Fehlerspeicher in der Start- und Abschlussprüfung lesen?":
        "Read the airbag fault codes in the start and final check?",
    "Kein FTDI-Kabel gefunden.\n\nSteckt es?": "No FTDI cable found.\n\nIs it plugged in?",
    "Tempo": "Speed",
    "Einstellungen": "Settings",
    "Ordner für Protokolle:": "Folder for logs:",
    "Ordner für Messwerte (CSV):": "Folder for measured values (CSV):",
    "Protokolldatei schreiben (für die Fehlersuche)": "Write a log file (for troubleshooting)",
    "Aus: Das Protokoll bleibt nur im Speicher und lässt sich bei Bedarf über Datei → "
    "Protokoll speichern … sichern.":
        "Off: the log stays in memory only and can be saved when needed via File → Save log …",
    "Messwertblöcke automatisch als CSV aufzeichnen":
        "Record measuring blocks as CSV automatically",
    "Voreinstellung für „aufzeichnen (CSV)“ im Reiter Messwertblöcke. Der Fahrtenschreiber "
    "schreibt immer.":
        "Default for “record (CSV)” on the Measuring blocks tab. The drive logger always "
        "writes its file.",
    "Bei Verbindungsabbruch während der Messung neu verbinden":
        "Reconnect when the connection is lost during a measurement",
    "Wählen …": "Choose …",
    "Öffnen": "Open",
    "Ordner wählen": "Choose folder",
    "Bereit – Zündung an, Kabel stecken, Steuergerät wählen.":
        "Ready – ignition on, plug in the cable, choose a control module.",
    "&Datei": "&File",
    "Einstellungen …": "Settings …",
    "Protokoll speichern …": "Save log …",
    "Ordner der Protokolle öffnen": "Open the log folder",
    "Ordner der Messwerte öffnen": "Open the measured values folder",
    "Beenden": "Quit",
    "SIMULATOR – keine echten Fahrzeugdaten": "SIMULATOR – no real vehicle data",
    "Interface": "Interface",
    "KKL-Kabel (FTDI)": "KKL cable (FTDI)",
    "Simulator (ohne Auto)": "Simulator (no car)",
    "Break (Standard)": "Break (default)",
    "Bitbang (für Klon-Chips)": "Bitbang (for clone chips)",
    "Wie die 5-Baud-Reizung erzeugt wird. Bitbang nur probieren, wenn mit Break nichts "
    "antwortet.":
        "How the 5-baud init is generated. Only try bitbang if nothing answers with break.",
    "Kabel suchen": "Find cable",
    "Kabel testen": "Test cable",
    "Interface:": "Interface:",
    "Kabel-URL:": "Cable URL:",
    "Baudrate:": "Baud rate:",
    "Reizung:": "Init:",
    "oder Adresse (hex):": "or address (hex):",
    "z. B. 01": "e.g. 01",
    "Schließen": "Close",
    "Funktionen": "Functions",
    "Fehlerspeicher löschen …": "Clear fault codes …",
    "Messwertblöcke": "Measuring blocks",
    "Anpassung (nur lesen)": "Adaptation (read only)",
    "Kilometerstand (Kombi)": "Odometer (cluster)",
    "Fahrtenschreiber": "Drive logger",
    "Nur beim Kombiinstrument (Adresse 17): liest Messwertgruppe 002 und, falls dort kein Wert "
    "steht, Anpassungskanal 09.":
        "Instrument cluster only (address 17): reads measuring block 002 and, if it holds no "
        "value, adaptation channel 09.",
    "Noch kein Steuergerät geöffnet.": "No control module opened yet.",
    "Identifikation": "Identification",
    "Noch nicht gelesen.": "Not read yet.",
    "Code": "Code",
    "P-Code": "P-code",
    "Beschreibung": "Description",
    "Fehlerart": "Fault type",
    "Sporadisch": "Intermittent",
    "Anpassung": "Adaptation",
    "Protokoll": "Log",
    "Blöcke anzeigen": "Show blocks",
    "Einzelbytes anzeigen": "Show single bytes",
    "Anzeige {nummer}": "Display {nummer}",
    "aufzeichnen (CSV)": "record (CSV)",
    "Gilt bis zum Schließen des Programms. Die Voreinstellung steht unter Datei → "
    "Einstellungen.":
        "Applies until the program is closed. The default is under File → Settings.",
    "bei Abbruch neu verbinden": "reconnect when lost",
    "Min/Max zurücksetzen": "Reset min/max",
    "Gruppen durchsuchen …": "Search groups …",
    "CSV-Ordner öffnen": "Open CSV folder",
    "Für die Bordspannung beim Anlassen nur Gruppe 004 aktivieren – dann wird am häufigsten "
    "abgefragt. Rohwerte im Tooltip jedes Feldes.":
        "For the supply voltage while cranking, enable only group 004 – it is then read most "
        "often. Raw values are in each field's tooltip.",
    "Kanal:": "Channel:",
    "Lesen": "Read",
    "Kanäle": "Channels",
    "durchsuchen": "search",
    "bis": "to",
    "Kanal": "Channel",
    "Wert": "Value",
    "Hex": "Hex",
    "Hinweis": "Note",
    "Gelesen": "Read at",
    "Liste leeren": "Clear list",
    "Messwertgruppen des Motorsteuergeräts, z. B. 1,2,3,4,5. Gruppen, die es nicht gibt, "
    "werden übersprungen.":
        "Measuring blocks of the engine ECU, e.g. 1,2,3,4,5. Groups that do not exist are "
        "skipped.",
    "Start- und Abschlussprüfung (Tankinhalt im Stand, alle Fehlerspeicher)":
        "Start and final check (fuel level at standstill, all fault codes)",
    "Motor-Gruppen:": "Engine groups:",
    "Kombi alle … s (0 = nie):": "Cluster every … s (0 = never):",
    "Dauer je Besuch (s):": "Duration per visit (s):",
    "Fahrt starten": "Start drive",
    "Ereignis markieren (F9)": "Mark event (F9)",
    "Sofort abbrechen": "Cancel now",
    "Beendet ohne Abschlussprüfung.": "Ends without the final check.",
    "Bereit.": "Ready.",
    "Aktuelle Werte": "Current values",
    "Protokolldatei: {pfad}": "Log file: {pfad}",
    "Das Protokoll lässt sich über Datei → Protokoll speichern … sichern.":
        "The log can be saved via File → Save log …",
    "Für eine Fehlermeldung bitte diese Protokolldatei mitschicken:\n{pfad}":
        "When reporting a problem, please include this log file:\n{pfad}",
    "Für eine Fehlermeldung bitte das Protokoll speichern (Datei → Protokoll speichern …) und "
    "mitschicken.":
        "When reporting a problem, please save the log (File → Save log …) and include it.",
    "Unerwarteter Fehler: %r": "Unexpected error: %r",
    "Unerwarteter Fehler ({art}): {fehler}": "Unexpected error ({art}): {fehler}",
    "Protokolldatei: aus": "Log file: off",
    "Aufzeichnung läuft: {pfad}": "Recording: {pfad}",
    "CSV-Ordner: {pfad}": "CSV folder: {pfad}",
    "Keine CSV-Aufzeichnung.": "No CSV recording.",
    "Airbag-Steuergerät": "Airbag control module",
    "Einstellungen gespeichert.": "Settings saved.",
    "Protokoll speichern": "Save log",
    "Protokolle (*.log);;Alle Dateien (*)": "Logs (*.log);;All files (*)",
    "Protokoll gespeichert: {pfad}": "Log saved: {pfad}",
    "SIMULATOR": "SIMULATOR",
    "Gefunden:\n{liste}\n\nDas erste Kabel ist eingetragen.":
        "Found:\n{liste}\n\nThe first cable has been entered.",
    "Kabeltest": "Cable test",
    "Interface: {geraet}\nEcho: {echo}": "Interface: {geraet}\nEcho: {echo}",
    "Adresse": "Address",
    "Bitte eine Adresse von 00 bis 7F eingeben (hex), z. B. 01 oder 17.":
        "Please enter an address from 00 to 7F (hex), e.g. 01 or 17.",
    "Trotzdem mit dem Airbag-Steuergerät verbinden?":
        "Connect to the airbag control module anyway?",
    "Airbag-Steuergerät nicht geöffnet.": "Airbag control module not opened.",
    "Verbinde mit {steuergeraet} … (die Reizung dauert gut 2 Sekunden)":
        "Connecting to {steuergeraet} … (the init takes just over 2 seconds)",
    "Keine Verbindung zu {steuergeraet}": "No connection to {steuergeraet}",
    "Keine Verbindung zu {steuergeraet}:": "No connection to {steuergeraet}:",
    "Verbindung fehlgeschlagen": "Connection failed",
    "Kombi: Bei vielen VAG-Kombis ist Kanal 09 der Kilometerstand in 10-km-Schritten – nicht bei "
    "jedem, deshalb mit der Anzeige im Kombi vergleichen.":
        "Cluster: on many VAG clusters, channel 09 is the odometer in 10 km steps – not on all "
        "of them, so compare with the cluster display.",
    "Verbunden: {steuergeraet} – {protokoll}, {baud} Baud, Kabel-Echo {echo}":
        "Connected: {steuergeraet} – {protokoll}, {baud} baud, cable echo {echo}",
    "Verbindung geschlossen.": "Connection closed.",
    "Verbindung verloren ({grund}) – verbinde neu …": "Connection lost ({grund}) – reconnecting …",
    "Getrennt: {grund}": "Disconnected: {grund}",
    "Verbinde neu … (Versuch {nummer})": "Reconnecting … (attempt {nummer})",
    "Wieder verbunden ({uhrzeit}) – Messung läuft weiter":
        "Reconnected ({uhrzeit}) – measurement continues",
    "Durchsuche Gruppe {gruppe:03d} …": "Searching group {gruppe:03d} …",
    "{zeilen} Zeilen": "{zeilen} lines",
    "Fahrtenschreiber – {phase}: {text}": "Drive logger – {phase}: {text}",
    "Lese Fehlerspeicher …": "Reading fault codes …",
    "Fehlerspeicher gelesen.": "Fault codes read.",
    "{anzahl} Fehler gespeichert": "{anzahl} fault code(s) stored",
    "Kein Fehler gespeichert": "No fault codes stored",
    "(gelesen um {uhrzeit})": "(read at {uhrzeit})",
    "Fehlerspeicher von {steuergeraet} wirklich löschen?\n\nDabei werden auch die "
    "Readiness-Codes zurückgesetzt (wichtig vor einer AU).":
        "Really clear the fault codes of {steuergeraet}?\n\nThis also resets the readiness "
        "codes (matters before an emissions test).",
    "Ein Fehler, dessen Ursache noch besteht, kommt sofort wieder. Crashdaten lassen sich nicht "
    "löschen.":
        "A fault whose cause still exists comes back right away. Crash data cannot be "
        "cleared.",
    "Lösche Fehlerspeicher …": "Clearing fault codes …",
    "Fehlerspeicher gelöscht – lese neu …": "Fault codes cleared – reading again …",
    "Bitte mindestens eine Gruppe aktivieren.": "Please enable at least one group.",
    "Aufzeichnung": "Recording",
    "CSV-Datei konnte nicht angelegt werden: {fehler}": "CSV file could not be created: {fehler}",
    "Stopp": "Stop",
    "Messwerte gespeichert: {pfad}": "Measured values saved: {pfad}",
    "nicht belegt": "not in use",
    "{rate} Abfragen/s": "{rate} requests/s",
    "Suche abbrechen": "Cancel search",
    "Durchsuche Messwertgruppen 001–255 …": "Searching measuring blocks 001–255 …",
    "Gruppensuche": "Group search",
    "Gruppensuche fertig: {anzahl} belegte Gruppen": "Group search done: {anzahl} groups in use",
    "Belegte Messwertgruppen – {steuergeraet}": "Measuring blocks in use – {steuergeraet}",
    "Keine belegten Gruppen gefunden.": "No groups in use found.",
    "Kilometerstand? {km} (unbestätigt)": "Odometer? {km} (unconfirmed)",
    "Lese Anpassungskanal {kanal:02d} …": "Reading adaptation channel {kanal:02d} …",
    "abbrechen": "cancel",
    "Lese Anpassungskanäle {von:02d}–{bis:02d} (nur lesen) …":
        "Reading adaptation channels {von:02d}–{bis:02d} (read only) …",
    "Kanalsuche": "Channel search",
    "Kanalsuche fertig: {anzahl} lesbare Kanäle": "Channel search done: {anzahl} readable channels",
    "Lese Kilometerstand …": "Reading odometer …",
    "Im Reiter „Anpassung“ lassen sich alle lesbaren Kanäle durchsuchen (nur lesen).":
        "The “Adaptation” tab can search all readable channels (read only).",
    "Abschlussprüfung läuft …": "Final check running …",
    "Bitte mindestens eine Motor-Gruppe angeben, z. B. 1,2,3,4,5.":
        "Please enter at least one engine group, e.g. 1,2,3,4,5.",
    "Fahrt beenden": "Finish drive",
    "Knopf": "Button",
    "Fahrtenschreiber mit Fehler beendet.": "Drive logger stopped with an error.",
    "Fertig – Zusammenfassung gespeichert.": "Done – summary saved.",
    "Fertig.": "Done.",
    "Fahrt gespeichert: {pfad}": "Drive saved: {pfad}",
    "Fahrtenschreiber – Zusammenfassung": "Drive logger – summary",
    "Ordner öffnen": "Open folder",
    "Motor: zuerst Fast-Init (KWP2000)": "Engine: fast init first (KWP2000)",
    "Nur für Motorsteuergeräte mit KWP2000, die auf die normale 5-Baud-Reizung nicht "
    "antworten (z. B. manche späteren Dieselsteuergeräte). Kommt keine Antwort, folgt die "
    "normale Reizung. Bei älteren Motoren nicht nötig. Experimentell.":
        "Only for engine control modules with KWP2000 that do not answer the normal 5-baud "
        "init (e.g. some later diesel control modules). If there is no answer, the normal init "
        "follows. Not needed for older engines. Experimental.",
    "VAG-Diagnose {version} – KW1281/KWP2000 über KKL-Kabel":
        "VAG diagnostics {version} – KW1281/KWP2000 via KKL cable",
    "Das ABS wird nur im Stand besucht (z. B. an der Ampel) – viele ABS-Steuergeräte nehmen "
    "während der Fahrt keine Verbindung an.":
        "The ABS is only visited at standstill (e.g. at traffic lights) – many ABS modules do "
        "not accept a connection while driving.",
    "ABS alle … s, nur im Stand (0 = nie):": "ABS every … s, only at standstill (0 = never):",
    "Zum Beispiel wenn eine Warnlampe angeht: setzt eine Markierung und liest sofort den "
    "Fehlerspeicher des Motors, den des ABS beim nächsten Halt.":
        "For example when a warning light comes on: sets a mark and immediately reads the "
        "engine fault codes, those of the ABS at the next stop.",
    "Fahrt wird beendet – Zündung an lassen, bis „Fahrtenschreiber beendet“ erscheint":
        "Finishing the drive – keep the ignition on until “Drive logger finished” appears",
    "Ereignis markiert – lese den Fehlerspeicher des Motors, den des ABS beim nächsten Halt …":
        "Event marked – reading the engine fault codes, those of the ABS at the next stop …",
    "E&xperte": "E&xpert",
    "Expertenmodus …": "Expert mode …",
    "Scan (alle Steuergeräte)": "Scan (all control modules)",
    "Scan": "Scan",
    "Experte": "Expert",
    "Scan starten": "Start scan",
    "Fehlerspeicher mitlesen": "Read fault codes too",
    "Airbag (15) einschließen": "Include airbag (15)",
    "Noch kein Scan.": "No scan yet.",
    "Bauteil": "Component",
    "Teilenummer": "Part number",
    "Fehler": "Faults",
    "Status": "Status",
    "Zeile anklicken: Kennung und Fehler des Steuergeräts.":
        "Click a row: identification and fault codes of the control module.",
    "Drosselklappe anlernen (Motor 01, Grundeinstellung)":
        "Throttle body alignment (engine 01, basic setting)",
    "Zündung an, Motor aus, Gaspedal nicht berühren. vagdiag prüft vorher: Drehzahl 0, "
    "Bordspannung mindestens 11,5 V, Kühlmittel 5–95 °C, kein Fehler im Motor-Fehlerspeicher. "
    "Die Grundeinstellung läuft etwa 30 Sekunden, danach liest vagdiag den Fehlerspeicher.":
        "Ignition on, engine off, do not touch the accelerator. vagdiag checks first: engine "
        "speed 0, supply voltage at least 11.5 V, coolant 5–95 °C, no fault code in the engine. "
        "The basic setting runs for about 30 seconds, then vagdiag reads the fault codes.",
    "Gruppe:": "Group:",
    "Prüfen und anlernen …": "Check and align …",
    "Abbrechen": "Cancel",
    "Service-Intervall zurücksetzen (Kombi 17, Kanal 02)":
        "Reset service interval (cluster 17, channel 02)",
    "Für Kombis mit Service-Anzeige ab etwa 1998: Anpassungskanal 02 auf 0. vagdiag liest den "
    "Kanal vorher, sichert den alten Wert und liest danach zurück. Ohne Kanal 02 geht es nur am "
    "Kombi selbst.":
        "For clusters with a service reminder from about 1998: adaptation channel 02 to 0. "
        "vagdiag reads the channel first, saves the old value and reads it back afterwards. "
        "Without channel 02 the reset only works on the cluster itself.",
    "Lesen und zurücksetzen …": "Read and reset …",
    "Simulator: Motor aus (Zündung an)": "Simulator: engine off (ignition on)",
    "EXPERTENMODUS": "EXPERT MODE",
    "Grundeinstellung läuft: {sekunden:.0f} von {dauer:.0f} s":
        "Basic setting running: {sekunden:.0f} of {dauer:.0f} s",
    "Den Airbag beim Scan mit abfragen?": "Include the airbag in the scan?",
    "Wird abgebrochen …": "Cancelling …",
    "Scan läuft …": "Scan running …",
    "Frage {steuergeraet} ab … ({nummer} von {anzahl})":
        "Querying {steuergeraet} … ({nummer} of {anzahl})",
    "frage ab …": "querying …",
    "Scan mit Fehler beendet.": "Scan stopped with an error.",
    "nicht abgefragt": "not queried",
    "Scan fertig: {gefunden} von {anzahl} Adressen antworten":
        "Scan finished: {gefunden} of {anzahl} addresses answer",
    "Textdateien (*.txt)": "Text files (*.txt)",
    "Expertenmodus": "Expert mode",
    "Expertenmodus an – Änderungen am Steuergerät möglich.":
        "Expert mode on – changes to control modules are possible.",
    "Expertenmodus aus.": "Expert mode off.",
    "EXPERTENMODUS AN – Änderungen werden im Steuergerät gespeichert. Alte Werte sichert "
    "vagdiag vorher, jeder Schreibblock steht im Protokoll.":
        "EXPERT MODE ON – changes are stored in the control module. vagdiag saves old values "
        "beforehand, every write block is in the log.",
    "Expertenmodus aus. Die Funktionen auf dieser Seite ändern Werte im Steuergerät – "
    "einschalten über das Menü Experte → Expertenmodus.":
        "Expert mode off. The functions on this page change values in the control module – "
        "turn it on via the menu Expert → Expert mode.",
    "Simulator": "Simulator",
    "ADP ERROR": "ADP ERROR",
    "ADP i.O.": "ADP OK",
    "ADP läuft": "ADP running",
    "Status unbekannt": "status unknown",
    "Prüfe die Bedingungen …": "Checking the conditions …",
    "Nicht gestartet.": "Not started.",
    "Prüfung Gruppe {gruppe:03d}:": "Check for group {gruppe:03d}:",
    "Nicht gestartet – Bedingung nicht erfüllt.": "Not started – condition not met.",
    "Nicht erfüllt – vagdiag startet die Grundeinstellung nicht:":
        "Not met – vagdiag will not start the basic setting:",
    "Grundeinstellung Gruppe {gruppe:03d} jetzt starten?":
        "Start basic setting group {gruppe:03d} now?",
    "Während der nächsten 30 Sekunden: Gaspedal nicht berühren, Motor nicht starten.":
        "For the next 30 seconds: do not touch the accelerator, do not start the engine.",
    "Nicht prüfbar – bitte selbst sicherstellen: {liste}":
        "Cannot be checked – please make sure yourself: {liste}",
    "Drosselklappe anlernen": "Throttle body alignment",
    "Grundeinstellung startet …": "Basic setting starting …",
    "Grundeinstellung Gruppe {gruppe:03d} gestartet": "Basic setting group {gruppe:03d} started",
    "Wird abgebrochen – zurück zu den Messwerten …": "Cancelling – back to measuring blocks …",
    "Mit Fehler beendet.": "Stopped with an error.",
    "Grundeinstellung mit Fehler beendet: {fehler}": "Basic setting stopped with an error: {fehler}",
    "Laut Steuergerät erfolgreich ({text}).": "Successful according to the control module ({text}).",
    "Das Steuergerät meldet einen Fehler ({text}). Bedingungen prüfen und noch einmal versuchen.":
        "The control module reports an error ({text}). Check the conditions and try again.",
    "Die Anpassung lief am Ende noch ({text}).": "The adaptation was still running at the end ({text}).",
    "Ergebnis unklar – vagdiag kennt den Statustext in Feld 4 noch nicht ({text}). Bitte das "
    "Protokoll schicken.":
        "Result unclear – vagdiag does not know the status text in field 4 yet ({text}). Please "
        "send the log.",
    "Abgebrochen nach {sekunden:.0f} s.": "Cancelled after {sekunden:.0f} s.",
    "Fehlerspeicher danach nicht lesbar.": "Fault codes not readable afterwards.",
    "Grundeinstellung beendet.": "Basic setting finished.",
    "Service-Intervall zurücksetzen": "Reset service interval",
    "{kanal}\n\nAuf 0 zurücksetzen? Der alte Wert wird vorher gesichert.":
        "{kanal}\n\nReset to 0? The old value is saved first.",
    "Service-Intervall nicht zurückgesetzt: {fehler}": "Service interval not reset: {fehler}",
    "Kanal 02: vorher {alt}, jetzt {neu}. Sicherung: {pfad}":
        "Channel 02: was {alt}, now {neu}. Backup: {pfad}",
    "Service-Intervall zurückgesetzt.": "Service interval reset.",
    "Nur lesen: Hier schreibt vagdiag keine Anpassungswerte (Service-Reset: Reiter Experte). "
    "Kanal 00 wird nie angesprochen – er steht bei vielen Steuergeräten für „alle "
    "Anpassungswerte löschen“.":
        "Read only: vagdiag writes no adaptation values here (service reset: Expert tab). "
        "Channel 00 is never accessed – on many control modules it means “erase all adaptation "
        "values”.",
    "Fehler erst beheben oder löschen, danach die Zündung aus- und wieder einschalten.":
        "Fix or clear the faults first, then switch the ignition off and on again.",
    "Simulator mit KWP2000 bei Motor und Kombi (ohne Auto)":
        "Simulator with KWP2000 engine and cluster (no car)",
    "Fragt die Steuergeräte nacheinander ab – nur lesen: Kennung und Fehlerspeicher. „Übliche "
    "Adressen“ nimmt die 15 häufigsten, „Alle Adressen“ jede von 01 bis 7F (außer 33 = OBD-II "
    "und 7C = Werksmodus des Radios) und zeigt nur die, die antworten. Jede nicht verbaute "
    "Adresse kostet einige Sekunden. Doppelklick auf eine gefundene Zeile öffnet das "
    "Steuergerät.":
        "Queries the control modules one after the other – read only: identification and fault "
        "codes. “Usual addresses” takes the 15 most common ones, “All addresses” every one from "
        "01 to 7F (except 33 = OBD-II and 7C = radio factory mode) and shows only those that "
        "answer. Every address that is not fitted takes a few seconds. Double-click a found "
        "row to open the control module.",
    "Übliche Adressen ({anzahl}, etwa 1 Minute)": "Usual addresses ({anzahl}, about 1 minute)",
    "Alle Adressen 01–7F (etwa 8 Minuten)": "All addresses 01–7F (about 8 minutes)",
    "Stellglieddiagnose (geöffnetes Steuergerät)": "Output tests (open control module)",
    "Starten …": "Start …",
    "Weiter": "Next",
    "Nur im Simulator: hält den Motor an, damit sich Grundeinstellung und Stellglieddiagnose "
    "des Motors ausprobieren lassen.":
        "Simulator only: stops the engine so that the basic setting and the engine output "
        "tests can be tried.",
    "KWP2000: vagdiag liest die Kanäle über die VAG-Anpassungsroutine – an echten "
    "Steuergeräten bisher wenig geprüft. Manche verlangen dafür eine Anmeldung; vagdiag "
    "meldet sich nicht an.":
        "KWP2000: vagdiag reads the channels through the VAG adaptation routine – hardly "
        "tested on real control modules yet. Some require a login for it; vagdiag does not "
        "log in.",
    "Keine Adresse hat geantwortet.": "No address answered.",
    "Prüfe …": "Checking …",
    "Prüfung Stellglieddiagnose {steuergeraet}:": "Check for output tests {steuergeraet}:",
    "Nicht erfüllt – vagdiag startet die Stellglieddiagnose nicht:":
        "Not met – vagdiag does not start the output tests:",
    "Stellglieddiagnose an {steuergeraet} starten?": "Start output tests on {steuergeraet}?",
    "Zündung an, Motor aus, Auto steht. Das Steuergerät steuert seine Stellglieder "
    "nacheinander an: Zeiger bewegen sich, Relais und Ventile schalten, Lüfter können "
    "anlaufen. Nicht in Lüfter oder Gestänge greifen.":
        "Ignition on, engine off, car standing still. The control module drives its outputs "
        "one after the other: gauges move, relays and valves switch, fans may start. Keep "
        "hands away from fans and linkages.",
    "KWP2000: experimentell – der Ablauf stammt aus einem Mitschnitt an einem "
    "Diesel-Steuergerät (EDC16). Dort steuert der erste Schritt das angezeigte Stellglied an, "
    "der zweite schaltet weiter.":
        "KWP2000: experimental – the sequence comes from a capture on a diesel control module "
        "(EDC16). There the first step drives the shown output, the second moves on.",
    "Stellglieddiagnose": "Output tests",
    "Stellglieddiagnose startet …": "Output tests starting …",
    "Stellglieddiagnose an {steuergeraet} gestartet": "Output tests on {steuergeraet} started",
    "Schritt {nummer}: wird angesteuert – „Weiter“ schaltet zum nächsten Stellglied.":
        "Step {nummer}: being driven – “Next” moves to the next output.",
    "Schritt {nummer}: angesteuert – „Weiter“ schaltet zum nächsten Stellglied.":
        "Step {nummer}: driven – “Next” moves to the next output.",
    "Schritt {nummer}: angezeigt – beim EDC16 steuert „Weiter“ es jetzt an.":
        "Step {nummer}: shown – on the EDC16 “Next” now drives it.",
    "Stellglied {nummer}: {text}": "Output {nummer}: {text}",
    "Schalte weiter …": "Moving on …",
    "Wird beendet – danach verbindet vagdiag neu …": "Ending – vagdiag then reconnects …",
    "Stellglieddiagnose mit Fehler beendet: {fehler}": "Output tests stopped with an error: {fehler}",
    "Das Steuergerät meldet das Ende der Liste.": "The control module reports the end of the list.",
    "Alle Stellglieder einmal durch – wieder beim ersten.":
        "Went through all outputs once – back at the first one.",
    "Das Steuergerät meldet kein weiteres Stellglied.": "The control module reports no further output.",
    "Nach {anzahl} Schritten beendet.": "Ended after {anzahl} steps.",
    "Von dir beendet.": "Ended by you.",
    "Stellglieddiagnose beendet: {anzahl} Stellglieder in {sekunden:.0f} s.":
        "Output tests finished: {anzahl} outputs in {sekunden:.0f} s.",
    "Die Verbindung wurde beendet und neu aufgebaut.":
        "The connection was ended and established again.",
    "Die Verbindung wurde beendet – bitte das Steuergerät neu öffnen.":
        "The connection was ended – please open the control module again.",
    "Stellglieddiagnose beendet.": "Output tests finished.",
    "Kommt {sekunden:.0f} Sekunden lang kein „Weiter“, beendet vagdiag die "
    "Stellglieddiagnose von selbst.":
        "If there is no “Next” for {sekunden:.0f} seconds, vagdiag ends the output test by "
        "itself.",
    "Nach {sekunden:.0f} Sekunden ohne „Weiter“ von selbst beendet.":
        "Ended automatically after {sekunden:.0f} seconds without “Next”.",
    "Ziel: Simulator – kein Auto": "Target: simulator – no car",
    "Ziel: ECHTES FAHRZEUG über das Kabel": "Target: REAL VEHICLE via the cable",
    "Steuergerät: {kennung}": "Control module: {kennung}",
    "Im Expertenmodus kann vagdiag Werte in Steuergeräten ändern und Stellglieder "
    "ansteuern:\n"
    "• Grundeinstellung starten (Drosselklappe anlernen)\n"
    "• Anpassungswerte speichern (Service-Intervall zurücksetzen)\n"
    "• Stellglieddiagnose (Zeiger, Lampen, Relais und Ventile nacheinander ansteuern)\n\n"
    "Nur am stehenden Auto mit eingeschalteter Zündung benutzen. Eine falsche Einstellung "
    "kann zu Fehlfunktionen führen. vagdiag prüft vorher die Bedingungen, sichert alte Werte "
    "und schreibt jeden Schritt ins Protokoll – die Benutzung bleibt trotzdem auf eigene "
    "Gefahr.\n\n"
    "Auch im Expertenmodus gesperrt: Kanal 00 (alle Anpassungen löschen), der "
    "Kilometerstand, Codierung, Login sowie Grundeinstellung und Anpassung bei Airbag, "
    "Bremsen, Wegfahrsperre, Lenkung und Niveauregulierung. Deren Stellglieddiagnose startet "
    "erst nach einer Warnung, die die möglichen Schäden nennt.\n\n"
    "Der Expertenmodus gilt nur bis zum Beenden des Programms.\n\n"
    "Expertenmodus einschalten?":
        "In expert mode vagdiag can change values in control modules and drive actuators:\n"
        "• start basic settings (throttle body adaptation)\n"
        "• save adaptation values (service interval reset)\n"
        "• output tests (gauges, lamps, relays and valves one after another)\n\n"
        "Only use it with the car stationary and the ignition on. A wrong setting can cause "
        "malfunctions. vagdiag checks the conditions first, backs up old values and logs every "
        "step – use is still at your own risk.\n\n"
        "Locked even in expert mode: channel 00 (erase all adaptations), the odometer, coding, "
        "login, and basic settings and adaptation on airbag, brakes, immobilizer, steering and "
        "level control. Their output tests only start after a warning that lists the possible "
        "damage.\n\n"
        "Expert mode lasts until the program is closed.\n\n"
        "Switch on expert mode?",
    "Die angezeigte Identifikation als Textdatei speichern.":
        "Save the identification shown as a text file.",
    "Alle gelesenen Fehler dieses Steuergeräts als Textdatei speichern.":
        "Save all fault codes read from this control module as a text file.",
    "Speichern …": "Save …",
    "Alle Kanäle in der Liste als Textdatei speichern.":
        "Save all channels in the list as a text file.",
    "Den Scan als Textdatei speichern: alle gefundenen Steuergeräte mit Kennung und Fehlern.":
        "Save the scan as a text file: all control modules found, with identification and "
        "fault codes.",
    "Dafür erst links {steuergeraet} öffnen.": "For this, first open {steuergeraet} on the left.",
    "Steuert die Stellglieder des geöffneten Steuergeräts nacheinander an – im Kombi "
    "z. B. Zeiger, Lampen und Gong, im Motor Relais und Ventile. Zündung an, Motor aus, "
    "Auto steht. „Weiter“ schaltet zum nächsten Stellglied, „Stopp“ hört auf; danach "
    "verbindet vagdiag neu. Bei Bremsen (03, 23, 53), Airbag (15), Wegfahrsperre (25), "
    "Niveauregulierung (34) und Lenkung (44) nennt vagdiag vorher die möglichen Schäden "
    "und fragt nach. Bei KWP2000 experimentell.":
        "Drives the actuators of the open control module one after another – in the "
        "instrument cluster e.g. gauges, lamps and chime, in the engine relays and valves. "
        "Ignition on, engine off, car stationary. “Next” moves to the next actuator, “Stop” "
        "ends; vagdiag then reconnects. For brakes (03, 23, 53), airbag (15), immobilizer (25), "
        "level control (34) and steering (44) vagdiag first lists the possible damage and asks "
        "for confirmation. Experimental with KWP2000.",
    "Gilt für das Steuergerät, das links geöffnet ist – erst dort öffnen, dann hier starten.":
        "Applies to the control module open on the left – open it there first, then start "
        "here.",
    "Nur Übersicht: Die Reihenfolge gibt das Steuergerät vor, weiter geht es mit „Weiter“.":
        "Overview only: the control module sets the order; “Next” moves on.",
    "Scan speichern": "Save scan",
    "Gespeichert: {pfad}": "Saved: {pfad}",
    "Identifikation speichern": "Save identification",
    "Fehlerspeicher speichern": "Save fault codes",
    "Anpassungskanäle speichern": "Save adaptation channels",
    "Nicht gestartet – Warnung nicht bestätigt.": "Not started – warning not confirmed.",
    "Warnung ({art}) nicht bestätigt – nicht gestartet.":
        "Warning ({art}) not confirmed – not started.",
    "Bei diesem Steuergerät: {hinweis}": "On this control module: {hinweis}",
    "Denk an die Vorbereitung aus der Warnung ({art}).":
        "Remember the preparation from the warning ({art}).",
    "Achtung: {steuergeraet} gehört zu „{art}“. Eine Stellglieddiagnose kann hier Schaden "
    "anrichten.":
        "Caution: {steuergeraet} belongs to “{art}”. Output tests can cause damage here.",
    "Mögliche Schäden:": "Possible damage:",
    "vagdiag kennt die Stellglieder dieses Steuergeräts nicht im Einzelnen. Nur weitermachen, "
    "wenn du weißt, was dabei angesteuert wird, und die Vorbereitung erledigt ist.":
        "vagdiag does not know the individual actuators of this control module. Only continue "
        "if you know what will be driven and the preparation is done.",
    "Warnung gelesen – weiter zur Rückfrage?": "Warning read – continue to the confirmation?",
    "Warnung: {art}": "Warning: {art}",
    "Warnung ({art}) bestätigt.": "Warning ({art}) confirmed.",
    "Liste der Stellglieder: erst links ein Steuergerät öffnen.":
        "List of actuators: open a control module on the left first.",
    "Für {steuergeraet} hat vagdiag noch keine Liste der Stellglieder. Sie entsteht beim "
    "ersten Durchlauf – vorher lesen lässt sie sich nicht: Das Steuergerät nennt das nächste "
    "Stellglied erst, wenn es es ansteuert.":
        "vagdiag has no list of actuators for {steuergeraet} yet. It is created during the "
        "first run – it cannot be read beforehand: the control module only names the next "
        "actuator when it drives it.",
    "bis zum Ende": "to the end",
    "vorzeitig beendet – danach können weitere kommen":
        "ended early – more may follow",
    "Stellglieder von {steuergeraet} laut Durchlauf vom {stand} ({anzahl}, {umfang}). Nur "
    "Übersicht – die Reihenfolge gibt das Steuergerät vor:":
        "Actuators of {steuergeraet} from the run on {stand} ({anzahl}, {umfang}). Overview "
        "only – the control module sets the order:",
    "Zeichnet eine ganze Fahrt in einer Datei auf: das Motorsteuergerät durchgehend, das Kombi "
    "in Abständen, das ABS in Abständen nur im Stand, am Anfang und am Ende die Fehlerspeicher "
    "aller Steuergeräte und den Tankinhalt im Stand. Vor dem Losfahren starten (Zündung an, "
    "Motor aus) und den Motor erst anlassen, wenn „jetzt Motor starten“ erscheint – dann ist das "
    "Anlassen mit aufgezeichnet. Am Ziel bei eingeschalteter Zündung beenden und warten, bis die "
    "Abschlussprüfung fertig ist. Während der Fahrt muss niemand den Laptop bedienen – und bitte "
    "den Laptop nicht vor einem Airbag halten.":
        "Records a whole drive in one file: the engine ECU continuously, the cluster at "
        "intervals, the ABS at intervals but only at standstill, and at the start and the end "
        "the fault codes of all control modules and the fuel level at standstill. Start before "
        "driving off (ignition on, engine off) and crank the engine only when “start the engine "
        "now” appears – then cranking is recorded too. At your destination, finish while the "
        "ignition is still on and wait until the final check is done. Nobody needs to operate "
        "the laptop while driving – and please do not hold the laptop in front of an airbag.",
    "EXPERTE: Stellglieddiagnose %02X nicht gestartet – Bedingung nicht erfüllt: %s":
        "EXPERT: output test %02X not started – condition not met: %s",
    "EXPERTE: Stellglieddiagnose %02X – Rückfrage mit Nein beantwortet, nicht gestartet":
        "EXPERT: output test %02X – confirmation answered with No, not started",
    "EXPERTE: Warnung (%s) für %s nicht bestätigt – nicht gestartet":
        "EXPERT: warning (%s) for %s not confirmed – not started",
    "EXPERTE: Warnung (%s) für %s bestätigt": "EXPERT: warning (%s) for %s confirmed",

    # ------------------------------------------------------------ ident.py
    "Adresse:": "Address:",
    "Protokoll:": "Protocol:",
    "{protokoll} (Keyword {keyword})": "{protokoll} (keyword {keyword})",
    "Kabel-Echo:": "Cable echo:",
    "Teilenummer:": "Part number:",
    "Bauteil:": "Component:",
    "Codierung:": "Coding:",
    "Werkstattcode:": "Workshop code:",
    "Zusatzkennung:": "Extra ID:",
    "Zusatzdaten:": "Extra data:",

    # ------------------------------------------------------------ kilometerstand.py
    "Das Kombi liefert den Kilometerstand weder in Messwertgruppe 002 noch in Anpassungskanal "
    "{kanal:02d}.":
        "The cluster provides the odometer neither in measuring block 002 nor in adaptation "
        "channel {kanal:02d}.",
    "Kilometerstand: {km}": "Odometer: {km}",
    "Quelle: {quelle}": "Source: {quelle}",
    "Rohwert {rohwert}": "raw value {rohwert}",
    "Unbestätigt: Bei vielen VAG-Kombis steht in Kanal {kanal:02d} der Kilometerstand in "
    "{schritt}-km-Schritten. Bitte mit der Anzeige im Kombi vergleichen.":
        "Unconfirmed: on many VAG clusters, channel {kanal:02d} holds the odometer in "
        "{schritt} km steps. Please compare with the cluster display.",
    "Geprüft:": "Checked:",
    "Messwertgruppe 002: nicht vorhanden": "Measuring block 002: not present",
    "Messwertgruppe 002: kein Feld mit Kilometern": "Measuring block 002: no field in kilometres",
    "Messwertgruppe 002, Feld {feld}: kein Wert (FF FF)":
        "Measuring block 002, field {feld}: no value (FF FF)",
    "Messwertgruppe 002, Feld {feld}": "Measuring block 002, field {feld}",
    "das Kombi beschreibt den Kanal als „{text}“": "the cluster describes the channel as “{text}”",
    "Anpassungskanal {kanal:02d}: kein Wert (FF FF)": "Adaptation channel {kanal:02d}: no value (FF FF)",
    "Anpassungskanal {kanal:02d}": "Adaptation channel {kanal:02d}",

    # ------------------------------------------------------------ kline.py
    "5-Baud-Reizung Adresse %02X": "5-baud init address %02X",
    "Keine Daten innerhalb {ms:.0f} ms": "No data within {ms:.0f} ms",
    "Kabel liefert Echo (normal bei KKL-Kabeln)": "Cable echoes (normal for KKL cables)",
    "Kabel liefert kein Echo": "Cable does not echo",
    "Echo auf {byte:02X} fehlt – Kabel getrennt?": "Echo of {byte:02X} missing – cable unplugged?",
    "Echo {echo:02X} statt {byte:02X} – Störung auf der K-Leitung?":
        "Echo {echo:02X} instead of {byte:02X} – disturbance on the K-line?",
    "Fast-Init: 25 ms Low, 25 ms High": "Fast init: 25 ms low, 25 ms high",

    # ------------------------------------------------------------ kw1281.py
    "Zusatzkennung anfordern": "Request extra ID",
    "Fehler löschen": "Clear faults",
    "Fehler lesen": "Read faults",
    "Messwertgruppe lesen": "Read measuring block",
    "Anpassung lesen": "Read adaptation",
    "Anpassungswert": "Adaptation value",
    "Kennung": "Identification",
    "Fehlerliste": "Fault list",
    "Messwerte": "Measured values",
    "Kanal {kanal:02d}: {wert} (hex {hex})": "Channel {kanal:02d}: {wert} (hex {hex})",
    "Steuergerät {adresse:02X} antwortet, aber bei keiner der Baudraten {bauds} lesbar. Letzter "
    "Befund: {befund}":
        "Control module {adresse:02X} answers, but is not readable at any of the baud rates "
        "{bauds}. Last finding: {befund}",
    "Reize Adresse %02X (Empfang mit %d Baud) …": "Init address %02X (receiving at %d baud) …",
    "Sync bei {baud} Baud, aber keine Keybytes": "Sync at {baud} baud, but no key bytes",
    "Sync 55, Keybytes %02X %02X → Keyword %d": "Sync 55, key bytes %02X %02X → keyword %d",
    "Unbekannte Keybytes {kb1:02X} {kb2:02X} bei {baud} Baud":
        "Unknown key bytes {kb1:02X} {kb2:02X} at {baud} baud",
    "KWP2000-Bestätigung (invertierte Adresse): %02X":
        "KWP2000 acknowledgement (inverted address): %02X",
    "Zusatzkennung angekündigt, aber abgelehnt": "Extra ID announced, but refused",
    "Verbindungsaufbau abgebrochen: {fehler}": "Connection setup aborted: {fehler}",
    "Verbunden mit %02X: %s %s%s": "Connected to %02X: %s %s%s",
    " – Codierung {codierung:05d}, WSC {wsc:05d}": " – coding {codierung:05d}, WSC {wsc:05d}",
    "Zusatzkennung: %s": "Extra ID: %s",
    "Sync-Zeit abgelaufen": "Sync time expired",
    "Keine Antwort von Adresse {adresse:02X}. Zündung an? Steuergerät vorhanden? Kabel an "
    "OBD-Pin 7?":
        "No response from address {adresse:02X}. Ignition on? Control module present? Cable on "
        "OBD pin 7?",
    "Byte {byte:02X} statt Sync 55 bei {baud} Baud": "Byte {byte:02X} instead of sync 55 at {baud} baud",
    "Verworfen nach Störung: %02X": "Discarded after a disturbance: %02X",
    "Störung: %s – versuche weiterzumachen": "Disturbance: %s – trying to continue",
    "Kein Komplement auf Byte {nummer}/{anzahl} ({byte:02X})":
        "No complement for byte {nummer}/{anzahl} ({byte:02X})",
    "Steuergerät antwortet nicht mehr": "Control module no longer responds",
    "Ungültige Blocklänge {laenge:02X}": "Invalid block length {laenge:02X}",
    "Block bricht nach {anzahl} Bytes ab": "Block breaks off after {anzahl} bytes",
    "Blockende fehlt": "Block end missing",
    "Blockende {ende:02X} statt 03": "Block end {ende:02X} instead of 03",
    "Blockzähler %02X statt %02X – übernehme": "Block counter %02X instead of %02X – accepting",
    "Steuergerät lehnt ab ({block})": "Control module refuses ({block})",
    "Keine Verbindung zum Steuergerät": "No connection to the control module",
    "Fehlerspeicher wird gelöscht": "Clearing fault codes",
    "Messwertgruppe muss zwischen 0 und 255 liegen": "Measuring block must be between 0 and 255",
    "Antwort auf Gruppe {gruppe:03d} mit falschem Blockzähler verworfen":
        "Answer to group {gruppe:03d} with a wrong block counter discarded",
    "Messwertgruppe {gruppe:03d} ist nicht belegt": "Measuring block {gruppe:03d} is not in use",
    "Messwertgruppe {gruppe:03d} abgelehnt": "Measuring block {gruppe:03d} refused",
    "Messwertgruppe {gruppe:03d}: unerwartete Antwort {titel:02X} (gestört oder noch nicht "
    "auswertbar)":
        "Measuring block {gruppe:03d}: unexpected answer {titel:02X} (disturbed or not "
        "decodable yet)",
    "Gruppe %03d: Format geändert, übernehme": "Group %03d: format changed, accepting",
    "Antwort auf Gruppe {gruppe:03d} hat ein anderes Format als bisher – verworfen":
        "Answer to group {gruppe:03d} has a different format than before – discarded",
    "Anpassungskanal muss zwischen 1 und 255 liegen (Kanal 00 wird bewusst nicht angesprochen)":
        "Adaptation channel must be between 1 and 255 (channel 00 is deliberately never "
        "accessed)",
    "Antwort auf Kanal {kanal:02d} mit falschem Blockzähler verworfen":
        "Answer to channel {kanal:02d} with a wrong block counter discarded",
    "Antwort für Kanal %02d statt %02d": "Answer for channel %02d instead of %02d",
    "Anpassungskanal {kanal:02d} abgelehnt – nicht vorhanden oder nur nach Anmeldung (Login) "
    "lesbar":
        "Adaptation channel {kanal:02d} refused – not present or readable only after a login",
    "Anpassungskanal {kanal:02d} ist nicht belegt": "Adaptation channel {kanal:02d} is not in use",
    "Anpassungskanal {kanal:02d}: Antworttyp {titel:02X} wird nicht ausgewertet ({block})":
        "Adaptation channel {kanal:02d}: answer type {titel:02X} is not decoded ({block})",
    "Unerwartete Antwort auf Keep-Alive: %s": "Unexpected answer to keep-alive: %s",
    "Verbindung beendet": "Connection closed",
    "Unerwarteter Block in der Fehlerliste: %s": "Unexpected block in the fault list: %s",
    "Fast-Init: %s – weiter mit der 5-Baud-Reizung": "Fast init: %s – continuing with the 5-baud init",
    "Fast-Init gibt es nur beim Motor (Adresse 01) – nehme die 5-Baud-Reizung":
        "Fast init is only available for the engine (address 01) – using the 5-baud init",
    "Fast-Init an Kopfadresse %02X (Versuch %d von 3) …":
        "Fast init to header address %02X (attempt %d of 3) …",
    "keine Antwort auf den Fast-Init": "no answer to the fast init",
    "KWP2000: Bestätigung %02X statt %02X – versuche es trotzdem":
        "KWP2000: acknowledgement %02X instead of %02X – trying anyway",
    "KWP2000: keine Bestätigung (invertierte Adresse) – versuche es trotzdem":
        "KWP2000: no acknowledgement (inverted address) – trying anyway",
    "Bei KWP2000 gibt es keine KW1281-Blöcke": "KWP2000 has no KW1281 blocks",
    "Anpassung speichern": "Save adaptation",
    "Anpassung testen": "Test adaptation",
    "Grundeinstellung": "Basic setting",
    "Schreiben geht nur im Expertenmodus": "Writing is only possible in expert mode",
    "Block {titel:02X} ({name}) ist in vagdiag gesperrt": "Block {titel:02X} ({name}) is blocked in vagdiag",
    "Anpassungskanal 00 (alle Anpassungen löschen) ist gesperrt":
        "Adaptation channel 00 (erase all adaptations) is blocked",
    "Kanal 09 des Kombis (Kilometerstand) ist gesperrt": "Cluster channel 09 (odometer) is blocked",
    "{name} geht nur im Expertenmodus über eine Expertenfunktion":
        "{name} is only possible in expert mode through an expert function",
    "{name} mit {daten} ist nicht freigegeben": "{name} with {daten} is not permitted",
    "SCHREIBEN: %s": "WRITE: %s",
    "gelesen": "read",
    "Anpassung %s: %s": "Adaptation %s: %s",
    "Messwertgruppe muss zwischen 1 und 255 liegen": "Measuring block group must be between 1 and 255",
    "Antwort auf Grundeinstellung {gruppe:03d} mit falschem Blockzähler verworfen":
        "Reply to basic setting {gruppe:03d} with wrong block counter discarded",
    "Grundeinstellung {gruppe:03d} abgelehnt": "Basic setting {gruppe:03d} refused",
    "Grundeinstellung {gruppe:03d}: unerwartete Antwort {titel:02X}":
        "Basic setting {gruppe:03d}: unexpected reply {titel:02X}",
    "Anpassungswert muss zwischen 0 und 65535 liegen": "Adaptation value must be between 0 and 65535",
    "Steuergerät lehnt Wert {wert} für Kanal {kanal:02d} ab":
        "Control module refuses value {wert} for channel {kanal:02d}",
    "getestet": "tested",
    "Werkstattcode muss zwischen 0 und 99999 liegen": "Workshop code must be between 0 and 99999",
    "Steuergerät speichert Wert {wert} für Kanal {kanal:02d} nicht":
        "Control module does not save value {wert} for channel {kanal:02d}",
    "gespeichert": "saved",
    "Stellglied": "Output",
    "STELLGLIED: %s": "OUTPUT TEST: %s",
    "Antwort der Stellglieddiagnose mit falschem Blockzähler":
        "Output test answer with the wrong block counter",
    "Stellglied: %s": "Output: %s",
    "Stellglieddiagnose: Ende": "Output tests: end",
    "Stellglieddiagnose abgelehnt – nicht unterstützt oder Bedingungen nicht erfüllt (z. B. "
    "Motor läuft)":
        "Output tests refused – not supported or conditions not met (e.g. engine running)",
    "Stellglieddiagnose: unerwartete Antwort {titel:02X}":
        "Output tests: unexpected answer {titel:02X}",
    "Schreiben geht nur bei einem geöffneten Steuergerät":
        "Writing is only possible with an open control module",
    "Die Freigabe gilt für ein anderes Steuergerät – {name} gesperrt":
        "The permission applies to a different control module – {name} blocked",
    "Falsches Komplement {antwort:02X} auf {byte:02X} (erwartet {soll:02X}) – Block "
    "abgebrochen, nicht zu Ende gesendet":
        "Wrong complement {antwort:02X} for {byte:02X} (expected {soll:02X}) – block aborted, "
        "not sent to the end",
    "Steuergerät meldet nach dem Speichern Kanal {gemeldet:02d} mit Wert {jetzt} statt Kanal "
    "{kanal:02d} mit {wert} – Verbindung beendet. Bitte den Kanal neu lesen und prüfen.":
        "After saving, the control module reports channel {gemeldet:02d} with value {jetzt} "
        "instead of channel {kanal:02d} with {wert} – connection ended. Please read the "
        "channel again and check it.",
    "Steuergerät meldet nach dem Testen Kanal {gemeldet:02d} mit Wert {jetzt} statt Kanal "
    "{kanal:02d} mit {wert} – nichts gespeichert, Verbindung beendet. Ein nur getesteter "
    "Wert gilt bis Zündung aus.":
        "After testing, the control module reports channel {gemeldet:02d} with value {jetzt} "
        "instead of channel {kanal:02d} with {wert} – nothing saved, connection ended. A "
        "value that was only tested stays until the ignition is switched off.",
    "Byte {nummer}/{anzahl} wäre {ms:.0f} ms zu spät gekommen (Rechner hing) – Block "
    "abgebrochen, nicht zu Ende gesendet":
        "Byte {nummer}/{anzahl} would have been {ms:.0f} ms too late (computer stalled) – "
        "block aborted, not sent to the end",
    "Byte {nummer}/{anzahl} ging womöglich {ms:.0f} ms zu spät hinaus (Rechner hing "
    "beim Senden) – Block abgebrochen, nichts mehr hinterhergeschickt":
        "Byte {nummer}/{anzahl} may have gone out {ms:.0f} ms too late (computer stalled "
        "while sending) – block aborted, nothing more sent",
    "Stellglieddiagnose bei {adresse:02X} ({art}) nur nach bestätigter Warnung vor möglichen "
    "Schäden":
        "Output tests on {adresse:02X} ({art}) only after a confirmed warning about possible "
        "damage",
    "Grundeinstellung und Anpassung sind bei {adresse:02X} ({art}) in vagdiag gesperrt":
        "Basic settings and adaptation on {adresse:02X} ({art}) are locked in vagdiag",

    # ------------------------------------------------------------ kwp2000.py
    "allgemein abgelehnt": "general reject",
    "Dienst nicht unterstützt": "service not supported",
    "Unterfunktion nicht unterstützt": "sub-function not supported",
    "falsche Länge oder falsches Format": "wrong length or format",
    "beschäftigt – später wiederholen": "busy – repeat the request later",
    "Bedingungen nicht erfüllt": "conditions not correct",
    "außerhalb des gültigen Bereichs": "out of range",
    "Zugriff verweigert (Anmeldung nötig)": "access denied (login required)",
    "Antwort folgt": "response pending",
    "in dieser Diagnosesitzung nicht unterstützt": "not supported in this diagnostic session",
    "Code {code:02X}": "code {code:02X}",
    "Steuergerät lehnt {dienst:02X} ab: {grund}": "Control module refuses {dienst:02X}: {grund}",
    "Importeur {importeur}, Gerätenummer {geraet}":
        "Importer {importeur}, equipment number {geraet}",
    "ohne Adressen": "without addresses",
    "KWP2000: Kopfadresse {kopf}, Diagnosesitzung {sitzung}":
        "KWP2000: header address {kopf}, diagnostic session {sitzung}",
    "Fast-Init": "fast init",
    "Verworfen nach Störung: %s": "Discarded after a disturbance: %s",
    "KWP2000: keine Antwort vom Steuergerät": "KWP2000: no answer from the control module",
    "KWP2000: Nachricht unvollständig ({roh})": "KWP2000: incomplete message ({roh})",
    "KWP2000: Prüfsumme falsch – Antwort verworfen": "KWP2000: wrong checksum – answer discarded",
    "KWP2000: Anfrage gestört ({fehler})": "KWP2000: request disturbed ({fehler})",
    "KWP2000: Steuergerät beschäftigt – frage erneut": "KWP2000: control module busy – asking again",
    "KWP2000: Nachricht an {ziel:02X} statt an den Tester – verworfen":
        "KWP2000: message to {ziel:02X} instead of the tester – discarded",
    "KWP2000: Antwort kommt von %02X statt von %02X – angenommen":
        "KWP2000: answer comes from %02X instead of %02X – accepted",
    "KWP2000: unerwartete Antwort {antwort:02X} auf {dienst:02X}":
        "KWP2000: unexpected answer {antwort:02X} to {dienst:02X}",
    "Fast-Init: StartCommunication abgelehnt (%s)": "Fast init: StartCommunication refused (%s)",
    "Fast-Init: keine gültige Antwort (%s)": "Fast init: no valid answer (%s)",
    "Fast-Init: Antwort mit falscher Prüfsumme – Keybytes übernommen":
        "Fast init: answer with a wrong checksum – key bytes taken over",
    "Fast-Init: Keybytes %02X %02X → Keyword %d": "Fast init: key bytes %02X %02X → keyword %d",
    "KWP2000: versuche Kopfadresse %s": "KWP2000: trying header address %s",
    "KWP2000: Identifikation abgelehnt: %s": "KWP2000: identification refused: %s",
    "Steuergerät {adresse:02X} spricht KWP2000 (Keyword {keyword}), antwortet aber auf keine "
    "Anfrage. Für eine Fehlermeldung bitte das Protokoll mitschicken.":
        "Control module {adresse:02X} speaks KWP2000 (keyword {keyword}) but answers no "
        "request. For a bug report please send the log along.",
    "KWP2000: Steuergerät antwortet unter Kopfadresse %s":
        "KWP2000: control module answers at header address %s",
    "KWP2000: Identifikation nicht lesbar: %s": "KWP2000: identification not readable: %s",
    "Verbunden mit %02X (KWP2000): %s %s": "Connected to %02X (KWP2000): %s %s",
    "KWP2000: keine Antwort auf Diagnosesitzung %02X":
        "KWP2000: no answer to diagnostic session %02X",
    "KWP2000: Diagnosesitzung %02X: %s": "KWP2000: diagnostic session %02X: %s",
    "KWP2000: Diagnosesitzung %02X eröffnet": "KWP2000: diagnostic session %02X opened",
    "KWP2000: keine Diagnosesitzung eröffnet – versuche es ohne":
        "KWP2000: no diagnostic session opened – trying without",
    "KWP2000: Fehlerliste mit unerwarteter Länge %d: %s":
        "KWP2000: fault list with unexpected length %d: %s",
    "Antwort auf Gruppe {gruppe:03d} gehört zu Gruppe {andere:03d} – verworfen":
        "Answer to group {gruppe:03d} belongs to group {andere:03d} – discarded",
    "Gruppe %03d hat %d Felder (angezeigt werden die ersten vier): %s":
        "Group %03d has %d fields (the first four are shown): %s",
    "KWP2000: Tester present nicht unterstützt – halte die Verbindung über die "
    "Diagnosesitzung":
        "KWP2000: tester present not supported – keeping the connection alive via the "
        "diagnostic session",
    "KWP2000: Fehler %05d, Status %02X": "KWP2000: fault %05d, status %02X",
    "KWP2000: Anfrage {daten} ist in vagdiag gesperrt": "KWP2000: request {daten} is blocked in vagdiag",
    "KWP2000: Anpassungswert ohne gewählten Kanal – gesperrt":
        "KWP2000: adaptation value without a selected channel – blocked",
    "SCHREIBEN: KWP %s": "WRITE: KWP %s",
    "STELLGLIED: KWP %s": "OUTPUT TEST: KWP %s",
    "Dieses Steuergerät bietet keine Anpassung über KWP2000 an ({grund})":
        "This control module offers no adaptation over KWP2000 ({grund})",
    "Anpassung nur nach Anmeldung (Zugriffsschutz) – vagdiag meldet sich nicht an":
        "Adaptation only after a login (access protection) – vagdiag does not log in",
    "KWP2000: Anpassung beenden: %s": "KWP2000: ending adaptation: %s",
    "Anpassungskanal {kanal:02d}: {fehler}": "Adaptation channel {kanal:02d}: {fehler}",
    "KWP2000: Anpassung Kanal %02d, Antwort %s": "KWP2000: adaptation channel %02d, answer %s",
    "Anpassungskanal {kanal:02d}: Antwort {roh} wird nicht ausgewertet":
        "Adaptation channel {kanal:02d}: answer {roh} is not evaluated",
    "Werkstattcode des Steuergeräts nicht lesbar – nichts geschrieben":
        "Workshop code of the control module not readable – nothing written",
    "Steuergerät übernimmt Wert {wert} für Kanal {kanal:02d} nicht (zeigt {jetzt}) – nichts "
    "gespeichert":
        "Control module does not take value {wert} for channel {kanal:02d} (shows {jetzt}) – "
        "nothing saved",
    "Dieses Steuergerät bietet keine Stellglieddiagnose über KWP2000 an ({grund})":
        "This control module offers no output tests over KWP2000 ({grund})",
    "Stellglieddiagnose abgelehnt: Bedingungen nicht erfüllt (z. B. Motor läuft)":
        "Output tests refused: conditions not met (e.g. engine running)",
    "Stellglieddiagnose nur nach Anmeldung (Zugriffsschutz) – vagdiag meldet sich nicht an":
        "Output tests only after a login (access protection) – vagdiag does not log in",
    "Stellglied: %s (KWP %s)": "Output: %s (KWP %s)",
    "KWP2000: Stellglied-Status ohne Nummer: %s": "KWP2000: output status without a number: %s",
    "KWP2000: Stellglieddiagnose beenden: %s": "KWP2000: ending output tests: %s",
    "KWP2000: Steuergerät beschäftigt – %s wird nicht wiederholt":
        "KWP2000: control module busy – %s is not repeated",
    "KWP2000: Antwort {antwort} passt nicht zur Routine {routine:02X} – verworfen":
        "KWP2000: response {antwort} does not match routine {routine:02X} – discarded",
    "KWP2000: Anpassung lässt sich nach dem Schreiben nicht beenden (%s) – beende die "
    "Verbindung":
        "KWP2000: adaptation cannot be ended after writing (%s) – ending the connection",
    "Anpassung ließ sich nicht beenden ({fehler}) – Verbindung beendet, damit das "
    "Steuergerät keinen Testwert behält":
        "Adaptation could not be ended ({fehler}) – connection ended so that the control "
        "module does not keep a test value",
    "KWP2000: Byte {nummer}/{anzahl} ging womöglich {ms:.0f} ms zu spät hinaus "
    "(Rechner hing) – Anfrage abgebrochen, nichts mehr hinterhergeschickt":
        "KWP2000: byte {nummer}/{anzahl} may have gone out {ms:.0f} ms too late "
        "(computer stalled) – request aborted, nothing more sent",
    "KWP2000: Byte {nummer}/{anzahl} wäre {ms:.0f} ms zu spät gekommen (Rechner hing) – "
    "Anfrage abgebrochen, nicht zu Ende gesendet":
        "KWP2000: byte {nummer}/{anzahl} would have been {ms:.0f} ms too late (computer "
        "stalled) – request aborted, not sent to the end",

    # ------------------------------------------------------------ messwerte.py
    "warm": "warm",
    "kalt": "cold",
    "Kennfeld 1": "Map 1",
    "Kennfeld 2": "Map 2",
    "kein Wert": "no value",
    "Typ {typ}: {a}/{b}": "type {typ}: {a}/{b}",
    "kein Wert (FF FF)": "no value (FF FF)",
    "Typ {typ}, a={a}, b={b}": "type {typ}, a={a}, b={b}",
    "(Text Nr. {nummer})": "(text no. {nummer})",
    "min {klein} · max {gross} {einheit}": "min {klein} · max {gross} {einheit}",

    # ------------------------------------------------------------ port.py
    "Ist der FTDI-Treiber installiert (README)?": "Is the FTDI driver installed (README)?",
    "Ist die udev-Regel eingerichtet (README)?": "Is the udev rule set up (README)?",
    "Unbekannte Kabel-Adresse „{url}“ – erwartet z. B. ftdi:///1 (Linux) oder d2xx:0 (Windows).":
        "Unknown cable address “{url}” – expected e.g. ftdi:///1 (Linux) or d2xx:0 (Windows).",
    "Das Paket ftd2xx ist nicht installiert (siehe README).":
        "The ftd2xx package is not installed (see README).",
    "Der FTDI-Treiber (ftd2xx.dll) fehlt: {fehler}. Treiber installieren (README).":
        "The FTDI driver (ftd2xx.dll) is missing: {fehler}. Install the driver (README).",
    "KKL-Kabel konnte nicht geöffnet werden ({url}): {fehler}. Steckt das Kabel? Ist es in einem "
    "anderen Programm geöffnet? Ist der FTDI-Treiber installiert?":
        "KKL cable could not be opened ({url}): {fehler}. Is the cable plugged in? Is it open in "
        "another program? Is the FTDI driver installed?",
    "pyftdi ist nicht installiert (siehe README)": "pyftdi is not installed (see README)",
    "USB-Geräte konnten nicht gelesen werden: {fehler}": "USB devices could not be read: {fehler}",
    "reizung muss 'break' oder 'bitbang' sein": "reizung must be 'break' or 'bitbang'",
    "KKL-Kabel konnte nicht geöffnet werden ({url}): {fehler}. Steckt das Kabel? udev-Regel "
    "eingerichtet (README)?":
        "KKL cable could not be opened ({url}): {fehler}. Is the cable plugged in? Is the udev "
        "rule set up (README)?",
    "KKL-Kabel ließ sich nicht einstellen: {fehler}": "KKL cable could not be configured: {fehler}",
    "(Reizung per Bitbang)": "(init via bitbang)",
    "Interface geöffnet: %s, Reizung per %s": "Interface opened: %s, init via %s",
    "Baudrate {baud} nicht einstellbar: {fehler}": "Baud rate {baud} cannot be set: {fehler}",
    "5-Baud-Reizung (Bitbang) fehlgeschlagen: {fehler}": "5-baud init (bitbang) failed: {fehler}",
    "5-Baud-Reizung fehlgeschlagen: {fehler}": "5-baud init failed: {fehler}",
    "Schreiben auf das Kabel fehlgeschlagen: {fehler}": "Writing to the cable failed: {fehler}",
    "Lesen vom Kabel fehlgeschlagen: {fehler}": "Reading from the cable failed: {fehler}",
    "Empfangspuffer ließ sich nicht leeren: {fehler}": "Receive buffer could not be cleared: {fehler}",
    "Dieses Interface kann keinen Fast-Init.": "This interface cannot do a fast init.",
    "Fast-Init fehlgeschlagen: {fehler}": "Fast init failed: {fehler}",

    # ------------------------------------------------------------ protokolldatei.py
    "vagdiag {version} – Protokoll gestartet {zeit}": "vagdiag {version} – log started {zeit}",
    "Protokolldatei: %s": "Log file: %s",
    "Protokolldatei geschlossen: %s": "Log file closed: %s",
    "Protokoll wird fortgesetzt in %s": "Log continues in %s",
    "Fortsetzung des Protokolls aus %s": "Continuation of the log from %s",
    "(ältere Zeilen nicht mehr im Speicher)": "(older lines no longer in memory)",
    "Protokoll gespeichert: %s": "Log saved: %s",

    # ------------------------------------------------------------ scan.py
    "gefunden": "found",
    "übersprungen (Airbag nicht freigegeben)": "skipped (airbag not enabled)",
    "sofort getrennt (Airbag)": "disconnected immediately (airbag)",
    "Fehler beim Abfragen": "error while querying",
    "vagdiag {version} – Scan vom {datum}": "vagdiag {version} – scan of {datum}",
    "{gefunden} von {anzahl} Adressen antworten": "{gefunden} of {anzahl} addresses answer",
    "übersprungen": "skipped",
    "alle Adressen 01–7F": "all addresses 01–7F",

    # ------------------------------------------------------------ session.py
    "Fehler beim Verarbeiten des Ereignisses %s": "Error while handling the event %s",
    "%s – frage erneut": "%s – asking again",
    "{fehler} (dreimal hintereinander)": "{fehler} (three times in a row)",
    "Warte %.1f s, bis das Steuergerät wieder bereit ist":
        "Waiting %.1f s until the control module is ready again",
    "Keine Verbindung zu %02X: %s": "No connection to %02X: %s",
    "Neuverbindung, Versuch %d": "Reconnecting, attempt %d",
    "Neuverbindung fehlgeschlagen: %s": "Reconnect failed: %s",
    "Gruppensuche abgebrochen bei %03d": "Group search cancelled at %03d",
    "Gruppe %03d: %s": "Group %03d: %s",
    "Kanalsuche abgebrochen bei %02d": "Channel search cancelled at %02d",
    "Verbindung zum Steuergerät besteht, Kabel funktioniert.":
        "Connected to the control module, the cable works.",
    "Echo empfangen – Kabel hat Strom und hört die K-Leitung.":
        "Echo received – the cable has power and hears the K-line.",
    "Kein Echo. Ohne 12 V an OBD-Pin 16 ist das normal (Kabel nicht im Auto). Im Auto mit "
    "Zündung an deutet es auf ein Kabelproblem hin – oder auf ein Kabel ohne Echo.":
        "No echo. Without 12 V on OBD pin 16 that is normal (cable not in the car). In the car "
        "with the ignition on it points to a cable problem – or to a cable without echo.",
    "Verbindung verloren: %s": "Connection lost: %s",
    "Fast-Init ohne Antwort, die normale Reizung klappt – in dieser Sitzung nur noch die "
    "normale Reizung":
        "No answer to the fast init, the normal init works – using only the normal init for "
        "the rest of this session",
    "Expertenmodus %s": "Expert mode %s",
    "an": "on",
    "aus": "off",
    "Scan abgebrochen vor %02X": "Scan cancelled before %02X",
    "Inzwischen ist ein anderes Steuergerät verbunden ({jetzt} statt {vorher}) – nichts "
    "gelöscht.":
        "A different control module is connected by now ({jetzt} instead of {vorher}) – "
        "nothing cleared.",

    # ------------------------------------------------------------ sim.py
    "Simulator (keine echten Fahrzeugdaten)": "Simulator (no real vehicle data)",
    "Interface: Simulator – keine echten Fahrzeugdaten": "Interface: simulator – no real vehicle data",
    "Motor": "Engine",
    "KWP2000: {geraete}": "KWP2000: {geraete}",

    # ------------------------------------------------------------ stellglied.py
    "Bremsen": "Brakes",
    "Lenkung": "Steering",
    "Die Stellglieddiagnose schaltet die Rückförderpumpe und die Ventile der "
    "Hydraulikeinheit. Mögliche Folgen: Ist Luft in der Hydraulikeinheit (etwa nach "
    "Arbeiten an der Bremse), gelangt sie in die Bremsleitungen – das Pedal wird weich, "
    "die Bremse muss nach Werksvorschrift entlüftet werden. Während des Tests kann ein "
    "Rad ungebremst sein, die Pumpe kann bei langem Lauf überhitzen, Warnlampen und "
    "Fehlereinträge sind möglich. Vorher: Motor aus, Fahrzeug gegen Wegrollen sichern "
    "(Gang und Keile, nicht nur die Fußbremse), niemand fahrbereit am Steuer. Danach die "
    "Bremse prüfen, bevor du losfährst.":
        "The output tests switch the return pump and the valves of the hydraulic unit. "
        "Possible consequences: if there is air in the hydraulic unit (e.g. after work on the "
        "brakes), it gets into the brake lines – the pedal goes soft and the brakes must be "
        "bled to the factory procedure. During the test a wheel may be unbraked, the pump can "
        "overheat if run for long, warning lamps and fault entries are possible. Before: "
        "engine off, secure the car against rolling away (gear and chocks, not just the foot "
        "brake), nobody ready to drive at the wheel. Afterwards check the brakes before you "
        "drive off.",
    "Ein elektronisch geregelter Bremskraftverstärker kann dabei selbst Bremsdruck "
    "aufbauen und wieder ablassen; das Bremspedal kann sich von allein bewegen. Mögliche "
    "Folgen: eingeklemmte Füße oder Gegenstände am Pedal, Fehlereinträge, danach ein "
    "nötiger Abgleich des Pedalweggebers. Vorher: Fuß weg vom Pedal, nichts im "
    "Fußraum, Fahrzeug gegen Wegrollen sichern.":
        "An electronically controlled brake booster can build up and release brake pressure "
        "by itself; the brake pedal can move on its own. Possible consequences: feet or "
        "objects trapped at the pedal, fault entries, afterwards a required calibration of the "
        "pedal travel sensor. Before: foot off the pedal, nothing in the footwell, secure the "
        "car against rolling away.",
    "Die Stellmotoren der elektrischen Feststellbremse können schließen und lösen. "
    "Mögliche Folgen: Das Fahrzeug rollt weg, wenn die Bremse löst; wird gerade an den "
    "Hinterradbremsen gearbeitet (Wartungsmodus, Kolben zurückgefahren), können Beläge, "
    "Stellmotoren oder Finger eingeklemmt werden; Fehlereinträge. Vorher: Gang bzw. P "
    "einlegen, Keile unterlegen, nicht an den Hinterradbremsen arbeiten.":
        "The motors of the electric parking brake can apply and release. Possible "
        "consequences: the car rolls away when the brake releases; if the rear brakes are "
        "being worked on (service mode, pistons retracted), pads, motors or fingers can be "
        "trapped; fault entries. Before: engage a gear or P, place chocks, do not work on the "
        "rear brakes.",
    "Airbag-Steuergeräte haben meist keine Stellglieddiagnose und lehnen ab. Wo es "
    "sie gibt, betrifft sie nach den bekannten Unterlagen nur die Warnlampe. Mögliche "
    "Folgen: Fehlereinträge und eine leuchtende Airbaglampe, die erst nach dem Löschen "
    "ausgeht; Störungen in der Kommunikation können bei manchen Geräten nicht löschbare "
    "Fehler hinterlassen (6Q0 909 605 A – das trennt vagdiag sofort). Vorher: niemand im "
    "Fahrzeug, nichts vor den Airbags, nicht an Airbags, Gurtstraffern oder deren "
    "Steckern arbeiten.":
        "Airbag control modules usually have no output tests and refuse. Where they exist, "
        "according to the known documentation they only concern the warning lamp. Possible "
        "consequences: fault entries and a lit airbag lamp that only goes out after clearing; "
        "communication errors can leave faults that cannot be cleared on some modules "
        "(6Q0 909 605 A – vagdiag disconnects from it immediately). Before: nobody in the car, "
        "nothing in front of the airbags, no work on airbags, belt tensioners or their "
        "connectors.",
    "Wegfahrsperren haben meist keine Stellglieddiagnose – höchstens die "
    "Kontrollleuchte. Schlüssel und Anlernung bleiben unberührt: Das ginge nur mit "
    "Anmeldung und PIN, die vagdiag nie sendet. Mögliche Folgen: Fehlereinträge, die "
    "Kontrollleuchte blinkt; ist die Diagnose beim Starten noch aktiv, kann die "
    "Freigabe des Motors scheitern – dann Zündung aus und wieder an. Vorher: Motor aus "
    "und erst nach dem Ende der Diagnose starten.":
        "Immobilizers usually have no output tests – at most the warning lamp. Keys and key "
        "learning stay untouched: that would need login and PIN, which vagdiag never sends. "
        "Possible consequences: fault entries, the warning lamp flashes; if the diagnosis is "
        "still active while starting, the engine may not be released – then switch the "
        "ignition off and on again. Before: engine off, and only start it after the diagnosis "
        "has ended.",
    "Bei elektrohydraulischer Lenkung kann die Pumpe anlaufen, bei elektromechanischer "
    "der Motor ein Lenkmoment erzeugen – das Lenkrad kann sich drehen. Mögliche Folgen: "
    "Verletzungen an Händen und Armen am Lenkrad, Fehlereinträge, bei "
    "elektromechanischer Lenkung danach ein nötiger Abgleich des Lenkwinkelsensors. "
    "Vorher: Hände weg vom Lenkrad, Räder geradeaus, Fahrzeug steht.":
        "With electro-hydraulic steering the pump can start, with electromechanical steering "
        "the motor can create steering torque – the steering wheel can turn. Possible "
        "consequences: injuries to hands and arms at the steering wheel, fault entries, with "
        "electromechanical steering a required calibration of the steering angle sensor "
        "afterwards. Before: hands off the steering wheel, wheels straight, car stationary.",
    "Das Fahrzeug kann sich heben oder senken, Kompressor und Ventile schalten. "
    "Mögliche Folgen: Quetschgefahr unter dem Fahrzeug und zwischen Rad und Kotflügel, "
    "Schäden an Wagenheber oder Hebebühne, wenn das Auto darauf steht, ein überhitzter "
    "Kompressor bei langem Lauf, Fehlereinträge. Vorher: niemand unter oder am "
    "Fahrzeug, das Auto steht auf seinen Rädern (nicht aufgebockt).":
        "The car can rise or lower, compressor and valves switch. Possible consequences: risk "
        "of crushing under the car and between wheel and wing, damage to a jack or lift if "
        "the car is on it, an overheated compressor if run for long, fault entries. Before: "
        "nobody under or at the car, the car stands on its wheels (not jacked up).",
    "Kraftstoffpumpe, Ventile und Relais schalten, der Kühlerlüfter kann anlaufen – "
    "nicht in den Lüfter greifen.":
        "Fuel pump, valves and relays switch, the radiator fan can start – keep your hands "
        "away from the fan.",
    "Zeiger bewegen sich, Lampen leuchten, der Gong ertönt.":
        "Gauges move, lamps light up, the chime sounds.",
    "Gebläse und Klappenmotoren laufen, der Klimakompressor kann einschalten.":
        "Blower and flap motors run, the A/C compressor can switch on.",
    "Scheibenwischer, Blinker und Beleuchtung können schalten – Hände weg von den "
    "Wischern.":
        "Wipers, indicators and lights can switch – keep your hands away from the wipers.",
    "Türen können ver- und entriegeln, Fenster und Schiebedach sich bewegen – "
    "Schlüssel nicht im Auto lassen, Hände aus Fenster- und Dachöffnungen.":
        "Doors can lock and unlock, windows and sunroof can move – do not leave the key in "
        "the car, keep hands out of window and roof openings.",
    "Der Sitz kann sich bewegen – niemand auf dem Sitz, nichts im Verstellbereich.":
        "The seat can move – nobody on the seat, nothing in its range of travel.",
    "Die Scheinwerfer verstellen sich.": "The headlights adjust.",
    "Die Lautsprecher können laut werden.": "The speakers can get loud.",
    "Das Steuergerät meldet sich als „{kennung}“ – das sieht nach Airbag, Bremsen, "
    "Wegfahrsperre oder Lenkung aus. Grundeinstellung und Anpassung sind dort gesperrt, "
    "egal unter welcher Adresse.":
        "The control module identifies itself as “{kennung}” – this looks like an airbag, "
        "brake, immobilizer or steering module. Basic settings and adaptation are locked "
        "there, whatever the address.",
    "Unter Adresse {adresse:02X} meldet sich „{kennung}“ – das sieht nach {art} aus und "
    "passt nicht zu dieser Adresse. Vermutlich hat eine Störung die Reizung verfälscht; die "
    "Stellglieddiagnose ist hier gesperrt.":
        "At address {adresse:02X} “{kennung}” answers – this looks like {art} and does not "
        "match this address. A disturbance probably corrupted the wake-up; output tests are "
        "locked here.",
    "Stellglied-Liste nicht gespeichert: %s": "Actuator list not saved: %s",

    # ------------------------------------------------------------ texte.py
    "%d eigene Klartexte geladen": "%d own texts loaded",
    "Eigene Klartexte nicht lesbar (%s): %s": "Own texts not readable (%s): %s",
    "Text Nr. {nummer}": "Text no. {nummer}",
}

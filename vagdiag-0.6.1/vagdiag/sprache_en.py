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
    "übliche Steuergeräte abfragen": "query the usual control modules",
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
    "Simulator, dessen Motor KWP2000 spricht": "simulator whose engine speaks KWP2000",
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

    # ------------------------------------------------------------ einstellungen.py
    "kein JSON-Objekt": "not a JSON object",
    "Einstellungen nicht lesbar (%s) – nehme Standardwerte":
        "Settings not readable (%s) – using defaults",
    "Einstellungen konnten nicht gespeichert werden: %s": "Settings could not be saved: %s",

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
    "Motor nicht erreichbar: %s": "Engine not reachable: %s",
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
    "Startprüfung fertig – Motor starten und losfahren":
        "Start check done – start the engine and drive off",
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
    "Nur lesen: vagdiag schreibt keine Anpassungswerte. Kanal 00 wird nie angesprochen – er "
    "steht bei vielen Steuergeräten für „alle Anpassungswerte löschen“.":
        "Read only: vagdiag never writes adaptation values. Channel 00 is never accessed – on "
        "many control modules it means “erase all adaptation values”.",
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
    "Simulator mit KWP2000-Motor (ohne Auto)": "Simulator with KWP2000 engine (no car)",
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
    "Zeichnet eine ganze Fahrt in einer Datei auf: das Motorsteuergerät durchgehend, das Kombi "
    "in Abständen, das ABS in Abständen nur im Stand, am Anfang und am Ende die Fehlerspeicher "
    "aller Steuergeräte und den Tankinhalt im Stand. Vor dem Losfahren starten (Zündung an), am "
    "Ziel bei eingeschalteter Zündung beenden und warten, bis die Abschlussprüfung fertig ist. "
    "Während der Fahrt muss niemand den Laptop bedienen – und bitte den Laptop nicht vor einem "
    "Airbag halten.":
        "Records a whole drive in one file: the engine ECU continuously, the cluster at "
        "intervals, the ABS at intervals but only at standstill, and at the start and the end "
        "the fault codes of all control modules and the fuel level at standstill. Start before "
        "driving off (ignition on); at your destination, finish while the ignition is still on "
        "and wait until the final check is done. Nobody needs to operate the laptop while "
        "driving – and please do not hold the laptop in front of an airbag.",

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
    "Störung: Komplement %02X auf %02X (erwartet %02X) – versuche weiterzumachen":
        "Disturbance: complement %02X for %02X (expected %02X) – trying to continue",
    "Falsches Komplement {antwort:02X} auf {byte:02X} (erwartet {soll:02X})":
        "Wrong complement {antwort:02X} for {byte:02X} (expected {soll:02X})",
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
    "Anpassung gelesen: %s": "Adaptation read: %s",
    "Anpassungskanal {kanal:02d} abgelehnt – nicht vorhanden oder nur nach Anmeldung (Login) "
    "lesbar":
        "Adaptation channel {kanal:02d} refused – not present or readable only after a login",
    "Anpassungskanal {kanal:02d} ist nicht belegt": "Adaptation channel {kanal:02d} is not in use",
    "Anpassungskanal {kanal:02d}: Antworttyp {titel:02X} wird nicht ausgewertet ({block})":
        "Adaptation channel {kanal:02d}: answer type {titel:02X} is not decoded ({block})",
    "Unerwartete Antwort auf Keep-Alive: %s": "Unexpected answer to keep-alive: %s",
    "Verbindung beendet": "Connection closed",
    "Unerwarteter Block in der Fehlerliste: %s": "Unexpected block in the fault list: %s",
    "Anpassungskanäle lesen gibt es in vagdiag bisher nur bei KW1281 – dieses Steuergerät "
    "spricht KWP2000.":
        "So far vagdiag reads adaptation channels only with KW1281 – this control module "
        "speaks KWP2000.",
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

    # ------------------------------------------------------------ sim.py
    "Simulator (keine echten Fahrzeugdaten)": "Simulator (no real vehicle data)",
    "Interface: Simulator – keine echten Fahrzeugdaten": "Interface: simulator – no real vehicle data",
    "Motor mit KWP2000": "engine with KWP2000",

    # ------------------------------------------------------------ texte.py
    "%d eigene Klartexte geladen": "%d own texts loaded",
    "Eigene Klartexte nicht lesbar (%s): %s": "Own texts not readable (%s): %s",
    "Text Nr. {nummer}": "Text no. {nummer}",
}

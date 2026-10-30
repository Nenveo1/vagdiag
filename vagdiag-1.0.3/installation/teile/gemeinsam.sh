# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
# Gemeinsamer Teil der Linux-Installer – wird von teile/pacman.sh, apt.sh und apk.sh
# eingelesen, nicht selbst starten. Reines sh: läuft auch mit dash (Debian, Ubuntu) und der
# BusyBox-Shell (Alpine). Vorher muss HIER auf den Ordner installation zeigen.

TEILE="$HIER/teile"
HAUPT=$(cd "$HIER/.." && pwd)
VENV="$HAUPT/.venv"
PYFTDI="pyftdi>=0.55"
PYSIDE="PySide6-Essentials>=6.5"
OBERFLAECHE=nein
UDEV=ja
NEUE_GRUPPE=nein
AUTOSTART=nein

schritt() { printf '\n== %s\n' "$*"; }
hinweis() { printf '   %s\n' "$*"; }
abbruch() {
    printf '\nAbbruch: %s\n' "$*" >&2
    exit 1
}

# Kopf: Ordner prüfen. $1 = System, für das dieses Skript gedacht ist
anfang() {
    printf 'vagdiag einrichten – %s\n' "$1"
    printf 'Ordner: %s\n' "$HAUPT"
    if [ ! -f "$HAUPT/vagdiag/__init__.py" ]; then
        abbruch "Im Ordner $HAUPT fehlt das Programm (Unterordner vagdiag). Die ZIP-Datei vollständig entpacken und das Skript aus dem Ordner installation darin starten."
    fi
    if [ "$(id -u)" -eq 0 ]; then
        hinweis "Läuft als root – dann gehört die Python-Umgebung root, und vagdiag läuft auch als root."
    fi
}

# Befehl mit Root-Rechten: sudo, sonst doas (Alpine), als root direkt
als_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    elif command -v doas >/dev/null 2>&1; then
        doas "$@"
    else
        abbruch "Weder sudo noch doas gefunden – das Skript bitte als root starten."
    fi
}

python_ok() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

# Erstes Python ab 3.11 im Suchpfad, Ergebnis in PY. Rückgabe 1, wenn keins da ist
python_waehlen() {
    PY=""
    for kandidat in python3 python3.14 python3.13 python3.12 python3.11; do
        if command -v "$kandidat" >/dev/null 2>&1 && python_ok "$kandidat"; then
            PY=$(command -v "$kandidat")
            return 0
        fi
    done
    return 1
}

python_version() {
    "$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])'
}

# Kann dieses Python PySide6 ab 6.5 laden (etwa aus dem Paket der Distribution)?
pyside_im_system() {
    "$PY" -c 'import sys, PySide6, PySide6.QtWidgets
v = tuple(int(x) for x in PySide6.__version__.split(".")[:2])
sys.exit(0 if v >= (6, 5) else 1)' >/dev/null 2>&1
}

# .venv neu anlegen. $1 = mit_system (PySide6 aus der Distribution sichtbar) oder ohne_system
venv_anlegen() {
    schritt "Python-Umgebung anlegen (.venv, Python $(python_version))"
    if [ "$1" = mit_system ]; then
        if "$PY" -m venv --clear --system-site-packages "$VENV"; then
            return 0
        fi
        # ohne ensurepip (etwa Alpine): pip aus dem System benutzen
        if "$PY" -m venv --clear --system-site-packages --without-pip "$VENV" &&
                "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
            hinweis "pip kommt aus dem System."
            return 0
        fi
    elif "$PY" -m venv --clear "$VENV"; then
        return 0
    fi
    abbruch "Die Python-Umgebung ließ sich nicht anlegen."
}

pip_installieren() {
    "$VENV/bin/python" -m pip install --disable-pip-version-check "$@"
}

pyftdi_installieren() {
    schritt "pyftdi installieren (spricht das Kabel an)"
    pip_installieren "$PYFTDI" || abbruch "pyftdi ließ sich nicht installieren – Internetverbindung prüfen und das Skript noch einmal starten."
}

# Lässt sich die Oberfläche laden? Ergebnis in OBERFLAECHE
oberflaeche_pruefen() {
    if "$VENV/bin/python" -c 'import PySide6.QtWidgets' >/dev/null 2>&1; then
        OBERFLAECHE=ja
    else
        OBERFLAECHE=nein
    fi
}

# udev-Regel: das Kabel ohne root-Rechte benutzen
udev_regel() {
    schritt "Zugriff aufs Kabel einrichten (udev-Regel)"
    if ! command -v udevadm >/dev/null 2>&1; then
        UDEV=nein
        hinweis "Kein udev gefunden (Alpine mit mdev?) – ohne udev darf nur root aufs Kabel."
        hinweis "Abhilfe: „setup-devd udev“ ausführen und dieses Skript noch einmal starten."
        return 0
    fi
    als_root mkdir -p /etc/udev/rules.d &&
        als_root install -m 644 "$TEILE/70-kkl-ftdi.rules" /etc/udev/rules.d/70-kkl-ftdi.rules ||
        abbruch "Die udev-Regel ließ sich nicht einrichten."
    als_root udevadm control --reload-rules || true
    als_root udevadm trigger || true
}

# Gruppe uucp: damit vagdiag das Kabel auch ohne Anmeldung am Bildschirm öffnen darf (SSH,
# automatisch gestarteter Fahrtenschreiber). Am Bildschirm reicht die udev-Regel allein.
gruppe_uucp() {
    if [ "$(id -u)" -eq 0 ]; then
        return 0
    fi
    if ! grep -q '^uucp:' /etc/group 2>/dev/null; then
        return 0
    fi
    benutzer=$(id -un)
    for gruppe in $(id -Gn "$benutzer"); do
        if [ "$gruppe" = uucp ]; then
            return 0
        fi
    done
    schritt "Benutzer $benutzer in die Gruppe uucp aufnehmen (Kabel auch über SSH oder als Dienst)"
    if command -v usermod >/dev/null 2>&1; then
        als_root usermod -aG uucp "$benutzer" && NEUE_GRUPPE=ja
    else
        als_root addgroup "$benutzer" uucp && NEUE_GRUPPE=ja
    fi
    if [ "$NEUE_GRUPPE" = nein ]; then
        hinweis "Ging nicht – am Bildschirm funktioniert das Kabel trotzdem."
    fi
}

# Startdateien aus installation/teile/start in den Ordner vagdiag legen
startdateien_legen() {
    schritt "Startdateien in den Ordner vagdiag legen"
    for datei in vagdiag.sh vagdiag-cli.sh; do
        cp "$TEILE/start/$datei" "$HAUPT/$datei" && chmod 755 "$HAUPT/$datei" ||
            abbruch "$HAUPT/$datei ließ sich nicht anlegen."
        hinweis "$HAUPT/$datei"
    done
}

# Reste einer früheren Installation im Hauptordner (die Installer lagen dort) – nach dem
# Entpacken über den alten Ordner würden sie nur verwirren
alte_dateien_entfernen() {
    alt=""
    for datei in installieren.sh installieren.bat requirements.txt 70-kkl-ftdi.rules; do
        if [ -f "$HAUPT/$datei" ]; then
            rm -f "$HAUPT/$datei" && alt="$alt $datei"
        fi
    done
    if [ -n "$alt" ]; then
        hinweis "Alte Installationsdateien aus dem Hauptordner entfernt:$alt"
    fi
}

# Autostart beim Anmelden: nur mit Oberfläche und nur am Terminal gefragt, Vorauswahl Nein.
# Eingerichtet wird er von vagdiag selbst (python -m vagdiag.autostart, siehe autostart.py)
autostart_fragen() {
    if [ "$OBERFLAECHE" != ja ] || [ ! -t 0 ]; then
        return 0
    fi
    schritt "Autostart"
    if [ "$(id -u)" -eq 0 ]; then
        hinweis "Als root übersprungen – einschalten in vagdiag: Datei → Beim Anmelden starten."
        return 0
    fi
    printf '   vagdiag beim Anmelden automatisch starten? [j/N] '
    antwort=""
    read -r antwort || antwort=""
    case "$antwort" in
        [jJyY]*)
            if (cd "$HAUPT" && "$VENV/bin/python" -m vagdiag.autostart an); then
                AUTOSTART=ja
            else
                hinweis "Ging nicht – einschalten in vagdiag: Datei → Beim Anmelden starten."
            fi
            ;;
        *)
            hinweis "Nein. Einschalten geht jederzeit in vagdiag: Datei → Beim Anmelden starten."
            ;;
    esac
}

ende() {
    printf '\nFertig. Start im Ordner %s:\n' "$HAUPT"
    if [ "$OBERFLAECHE" = ja ]; then
        printf '  ./vagdiag.sh           Oberfläche\n'
    else
        printf '  (Oberfläche nicht verfügbar – PySide6 fehlt für dieses System; nur Kommandozeile)\n'
    fi
    printf '  ./vagdiag-cli.sh -h    Kommandozeile\n'
    if [ "$UDEV" = ja ]; then
        printf 'Das Kabel einmal ab- und wieder anstecken, damit die udev-Regel greift.\n'
    fi
    if [ "$NEUE_GRUPPE" = ja ]; then
        printf 'Die Gruppe uucp gilt ab der nächsten Anmeldung.\n'
    fi
    if [ "$AUTOSTART" = ja ]; then
        printf 'vagdiag startet ab der nächsten Anmeldung von selbst.\n'
    fi
}

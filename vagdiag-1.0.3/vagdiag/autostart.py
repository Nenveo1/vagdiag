# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Autostart: die Oberfläche nach dem Anmelden von selbst starten. Lief beim letzten
Schließen ein passiver Fahrtenschreiber, läuft er dann weiter (siehe gui.py).

Linux und andere Systeme mit XDG-Arbeitsumgebung: Datei vagdiag.desktop im Ordner
~/.config/autostart – die lesen GNOME, KDE, Xfce, Cinnamon, MATE, LXQt und andere.
Windows: Eintrag „vagdiag“ unter HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\
CurrentVersion\\Run. Gestartet wird das Python dieser Installation mit
vagdiag/__main__.py – das findet den Ordner vagdiag selbst, egal wo es startet.

Für die Installer:  python -m vagdiag.autostart an|aus|status
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from .sprache import t

NAME = "vagdiag"
WINDOWS = sys.platform == "win32"
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
# Was im Task-Manager unter „Autostart“ abgeschaltet ist, vermerkt Windows hier
FREIGABE = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
# Zeichen, die im Exec-Eintrag einer .desktop-Datei Anführungszeichen verlangen
_RESERVIERT = set(" \t\"'\\><~|&;$*?#()`")


class AutostartFehler(Exception):
    """Autostart ließ sich nicht einrichten oder entfernen."""


def verfuegbar() -> bool:
    """Richtet vagdiag den Autostart hier selbst ein? (Windows, Linux/BSD mit XDG)"""
    return WINDOWS or (os.name == "posix" and sys.platform != "darwin")


def befehl() -> list[str]:
    """Programm und Argumente des Autostarts. Unter Windows pythonw.exe – ohne
    Konsolenfenster."""
    if not sys.executable:
        raise AutostartFehler(t("Das laufende Python ist unbekannt."))
    python = Path(sys.executable)        # nicht auflösen: sonst fehlt die .venv
    if WINDOWS and python.name.lower() == "python.exe":
        ohne_konsole = python.with_name("pythonw.exe")
        if ohne_konsole.exists():
            python = ohne_konsole
    return [str(python), str(Path(__file__).resolve().with_name("__main__.py"))]


def desktop_datei() -> Path:
    basis = os.environ.get("XDG_CONFIG_HOME", "")
    ordner = Path(basis) if basis and Path(basis).is_absolute() else Path.home() / ".config"
    return ordner / "autostart" / f"{NAME}.desktop"


def _exec_argument(text: str) -> str:
    """Ein Argument für Exec= nach der Desktop Entry Specification: mit Sonderzeichen in
    doppelten Anführungszeichen, darin ", `, $ und \\ mit \\ davor; % als %%. Danach gilt
    die Regel für Zeichenketten: jeder \\ doppelt."""
    if "\n" in text or "\r" in text:
        raise AutostartFehler(t("Ordnernamen mit Zeilenumbruch gehen hier nicht."))
    text = text.replace("%", "%%")
    if any(zeichen in _RESERVIERT for zeichen in text):
        text = '"' + "".join("\\" + z if z in '"`$\\' else z for z in text) + '"'
    return text.replace("\\", "\\\\")


def desktop_inhalt() -> str:
    return ("[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={NAME}\n"
            f"Comment={t('VAG-Diagnose über KKL-Kabel (KW1281/KWP2000)')}\n"
            f"Exec={' '.join(_exec_argument(a) for a in befehl())}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n")


def ist_an() -> bool:
    """Ist der Autostart eingerichtet und nicht in der Arbeitsumgebung abgeschaltet?"""
    try:
        if WINDOWS:
            return _windows_an()
        if not verfuegbar():
            return False
        datei = desktop_datei()
        if not datei.is_file():
            return False
        zeilen = {z.replace(" ", "").lower()
                  for z in datei.read_text(encoding="utf-8", errors="replace").splitlines()}
        return "hidden=true" not in zeilen and "x-gnome-autostart-enabled=false" not in zeilen
    except Exception:
        return False


def einschalten() -> str:
    """Autostart einrichten – auch neu, etwa nach dem Verschieben des Ordners. Ergebnis:
    wo er eingetragen ist."""
    if WINDOWS:
        return _windows_einschalten()
    if not verfuegbar():
        raise AutostartFehler(t("Auf diesem System richtet vagdiag den Autostart nicht selbst "
                                "ein."))
    datei = desktop_datei()
    try:
        inhalt = desktop_inhalt()
        datei.parent.mkdir(parents=True, exist_ok=True)
        neu = datei.with_name(datei.name + ".neu")
        neu.write_text(inhalt, encoding="utf-8")
        os.replace(neu, datei)
    except OSError as exc:
        raise AutostartFehler(t("Autostart nicht eingerichtet: {fehler}", fehler=exc)) from exc
    return str(datei)


def ausschalten() -> None:
    if WINDOWS:
        _windows_ausschalten()
        return
    try:
        desktop_datei().unlink(missing_ok=True)
    except OSError as exc:
        raise AutostartFehler(t("Autostart nicht entfernt: {fehler}", fehler=exc)) from exc


def anleitung() -> str:
    """Wie man den Autostart von Hand einrichtet."""
    try:
        teile = befehl()
    except AutostartFehler as exc:
        return str(exc)
    if WINDOWS:
        return t("Von Hand: Win+R, shell:startup eingeben und dort eine Verknüpfung mit diesem "
                 "Befehl anlegen:\n{befehl}", befehl=subprocess.list2cmdline(teile))
    return t("Von Hand: diesen Befehl in den Autostart der Arbeitsumgebung eintragen:\n"
             "{befehl}", befehl=shlex.join(teile))


# ---------------------------------------------------------------- Windows
def _windows_befehl() -> str:
    return subprocess.list2cmdline(befehl())


def _freigabe_loeschen() -> None:
    """Den Vermerk „im Task-Manager abgeschaltet“ löschen – sonst bliebe der Autostart
    trotz Eintrag aus."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, FREIGABE, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
    except OSError:
        pass


def _windows_an() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN) as k:
            winreg.QueryValueEx(k, NAME)
    except OSError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, FREIGABE) as k:
            wert, _art = winreg.QueryValueEx(k, NAME)
    except OSError:
        return True
    # erstes Byte gerade (02, 06): an; ungerade (03, 07): im Task-Manager abgeschaltet
    return not (isinstance(wert, (bytes, bytearray)) and wert and wert[0] & 1)


def _windows_einschalten() -> str:
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, _windows_befehl())
    except OSError as exc:
        raise AutostartFehler(t("Autostart nicht eingerichtet: {fehler}", fehler=exc)) from exc
    _freigabe_loeschen()
    return "HKEY_CURRENT_USER\\" + RUN


def _windows_ausschalten() -> None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise AutostartFehler(t("Autostart nicht entfernt: {fehler}", fehler=exc)) from exc
    _freigabe_loeschen()


# ---------------------------------------------------------------- Aufruf
def main(argumente: list[str] | None = None) -> int:
    """python -m vagdiag.autostart an|aus|status (für die Installer)."""
    from . import einstellungen, sprache
    sprache.setzen(einstellungen.laden()["sprache"])
    argumente = list(sys.argv[1:] if argumente is None else argumente)
    wunsch = argumente[0].lower() if argumente else "status"
    try:
        if wunsch in ("an", "on"):
            print(t("Autostart an: {ort}", ort=einschalten()))
        elif wunsch in ("aus", "off"):
            ausschalten()
            print(t("Autostart aus."))
        elif wunsch == "status":
            print(t("Autostart an.") if ist_an() else t("Autostart aus."))
        else:
            print("python -m vagdiag.autostart an|aus|status", file=sys.stderr)
            return 2
    except AutostartFehler as exc:
        print(f"{exc}\n{anleitung()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

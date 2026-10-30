# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nenveo
"""Verlaufskurve der Messwertblöcke.

Jedes Zahlenfeld der aktiven Anzeigen wird zu einer Reihe (Zeit, Wert). Gezeigt wird eine
wählbare Zeitspanne bis jetzt (ZEITACHSEN); gespeichert bleibt höchstens die längste. Jede
Reihe bekommt einen eigenen Streifen mit eigener Skala – wie im Kurvenmodus von VCDS –,
denn Drehzahl und Spannung passen nicht auf eine Achse. Alle Streifen teilen die Zeitachse;
der Mauszeiger zeigt die Werte aller Streifen zu einem Zeitpunkt.

Hier steht alles außer Qt – Ausschnitt, Wertebereich, Umrechnung in Bildpunkte, Marken der
Zeitachse und das Zeichnen über einen schlichten „Maler“ (Fläche, Linie, Kurve, Punkt,
Text) –, damit es sich ohne Oberfläche prüfen lässt. gui.Verlaufsbild reicht die Aufrufe an
QPainter weiter.
"""

from __future__ import annotations

import bisect
import itertools
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

from .messwerte import ROHWERT, Messwert
from .sprache import N_, einheit, t, zahl

# (Sekunden, Beschriftung) – Auswahl der Zeitachse
ZEITACHSEN: list[tuple[int, str]] = [
    (30, N_("30 Sekunden")), (60, N_("1 Minute")), (120, N_("2 Minuten")),
    (300, N_("5 Minuten")), (600, N_("10 Minuten")), (1800, N_("30 Minuten")),
    (3600, N_("60 Minuten")),
]
STANDARD_SPANNE = 60
MAX_SEKUNDEN = max(s for s, _ in ZEITACHSEN)
MAX_PUNKTE = 40000           # je Reihe – reicht für 60 Minuten mit gut 10 Werten pro Sekunde
LUECKE = 5.0                 # Sekunden ohne Wert: Die Linie wird unterbrochen
# Für lange Zeitachsen zusätzlich gebündelt: je Bündel (1 s bzw. 5 s) erster, kleinster,
# größter und letzter Wert. Gezeichnet wird aus der gröbsten Stufe, die noch feiner als ein
# Bildpunkt ist – so bleibt eine Stunde mit zehn Feldern schnell, ohne dass eine Spitze fehlt.
STUFEN = (1.0, 5.0)

# Aufteilung in Bildpunkten
STREIFEN_MIN = 64            # Mindesthöhe eines Streifens
KOPF = 18                    # Titelzeile eines Streifens (Name, Wert)
ACHSE = 22                   # Zeitachse unten
RAND = 8
SKALA = 64                   # rechts: größter und kleinster Wert im Ausschnitt

# Farben je Reihe – feste Reihenfolge, für hellen und dunklen Hintergrund abgestimmt
# (je Modus geprüft: Abstand auch bei Farbfehlsichtigkeit, Kontrast zur Fläche). Die Farbe
# ist nur Zugabe: Jeder Streifen trägt seinen Namen.
FARBEN = {
    False: ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6",
            "#e34948"),
    True: ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9",
           "#e66767"),
}
GRUND = {
    False: {"flaeche": "#fcfcfb", "text": "#0b0b0b", "text2": "#52514e", "leise": "#898781",
            "gitter": "#e1e0d9", "achse": "#c3c2b7"},
    True: {"flaeche": "#1a1a19", "text": "#f0efec", "text2": "#c3c2b7", "leise": "#898781",
           "gitter": "#2c2c2a", "achse": "#383835"},
}

# Zündwinkel: Die Richtung steckt in der Einheit (v.OT/n.OT) – in der Kurve zählt vor OT
# positiv, damit ein Streifen nicht bei jedem Wechsel der Richtung neu beginnt
VOR_OT, NACH_OT = "° v.OT", "° n.OT"


@dataclass
class Reihe:
    schluessel: object          # z. B. (Anzeige, Feld)
    art: object                 # was die Reihe misst (z. B. die Gruppe) – ändert sie sich, beginnt die Reihe neu
    name: str                   # angezeigter Name („004/2 Bordspannung“)
    einheit: str                # Einheit (intern, deutsch)
    stellen: int = 1
    punkte: deque = field(default_factory=lambda: deque(maxlen=MAX_PUNKTE))
    # Stufe (Sekunden) → Bündel [Nummer, erste Zeit, erster Wert, kleinster, größter,
    # letzte Zeit, letzter Wert]
    buendel: dict = field(default_factory=lambda: {
        stufe: deque(maxlen=int(MAX_SEKUNDEN / stufe) + 2) for stufe in STUFEN})

    @property
    def letzter(self) -> tuple[float, float] | None:
        return self.punkte[-1] if self.punkte else None

    def anhaengen(self, zeit: float, wert: float, grenze: float) -> None:
        self.punkte.append((zeit, wert))
        while self.punkte and self.punkte[0][0] < grenze:
            self.punkte.popleft()
        for stufe, liste in self.buendel.items():
            nummer = math.floor(zeit / stufe)
            if liste and liste[-1][0] == nummer:
                b = liste[-1]
                b[3], b[4], b[5], b[6] = min(b[3], wert), max(b[4], wert), zeit, wert
            else:
                liste.append([nummer, zeit, wert, wert, wert, zeit, wert])
            while liste and liste[0][5] < grenze:
                liste.popleft()


class Verlauf:
    def __init__(self, max_sekunden: float = MAX_SEKUNDEN):
        self.max_sekunden = float(max_sekunden)
        self.reihen: dict[object, Reihe] = {}
        self._farben: dict[object, int] = {}        # Schlüssel → feste Farbe

    def hinzufuegen(self, schluessel, art, name: str | None, einheit_: str, zeit: float,
                    wert: float, stellen: int = 1) -> None:
        """Einen Wert anhängen. Ändern sich Art oder Einheit (andere Gruppe in derselben
        Anzeige), beginnt die Reihe neu – sonst stünden zwei Größen in einer Kurve. name=None
        lässt den bisherigen Namen stehen (z. B. beim Neuverbinden)."""
        if wert is None:
            return
        wert = float(wert)
        if math.isnan(wert) or math.isinf(wert):
            return
        reihe = self.reihen.get(schluessel)
        if reihe is None or reihe.art != art or reihe.einheit != einheit_:
            reihe = Reihe(schluessel, art, name or "", einheit_, stellen)
            self.reihen[schluessel] = reihe
            self._farben.setdefault(schluessel, len(self._farben))
        elif name is not None:
            reihe.name = name
        reihe.stellen = stellen
        if reihe.punkte and zeit < reihe.punkte[-1][0]:
            return                                   # nie rückwärts (Uhr springt nicht)
        reihe.anhaengen(float(zeit), wert, zeit - self.max_sekunden)

    def entfernen(self, pruefen) -> None:
        """Reihen entfernen, deren Schlüssel pruefen(schluessel) erfüllt."""
        for schluessel in [s for s in self.reihen if pruefen(s)]:
            del self.reihen[schluessel]

    def leeren(self) -> None:
        self.reihen.clear()

    def farbe(self, schluessel, dunkel: bool = False) -> str:
        farben = FARBEN[dunkel]
        return farben[self._farben.get(schluessel, 0) % len(farben)]

    def sichtbar(self, jetzt: float, spanne: float) -> list[Reihe]:
        """Reihen mit mindestens einem Wert in der Zeitspanne – nach Schlüssel geordnet
        (Anzeige 1 oben, darin Feld 1 zuerst)."""
        reihen = [r for r in self.reihen.values() if _hat_werte(r, jetzt - spanne, jetzt)]
        try:
            return sorted(reihen, key=lambda r: r.schluessel)
        except TypeError:
            return reihen


def kurvenwert(m: Messwert, umgerechnet: tuple[float, str, int] | None = None
               ) -> tuple[float, str, int] | None:
    """Was von einem Messwert in die Kurve kommt: (Wert, Einheit, Nachkommastellen) – None
    für Texte und ungültige Werte. Zündwinkel mit Vorzeichen (vor OT positiv). Für einen
    Rohwert der Gruppe 000 gilt `umgerechnet` (beschriftung.rohwert_umgerechnet), sonst der
    Rohwert selbst."""
    if not m.gueltig or m.zahl is None or math.isnan(m.zahl) or math.isinf(m.zahl):
        return None
    if m.typ == ROHWERT:
        return umgerechnet if umgerechnet is not None else (m.zahl, "", 0)
    if m.zuendwinkel:
        return (abs(m.zahl) if m.einheit == VOR_OT else -abs(m.zahl)), VOR_OT, m.stellen
    return m.zahl, m.einheit, m.stellen


def _zeit(punkt: tuple[float, float]) -> float:
    return punkt[0]


def _hat_werte(reihe: Reihe, beginn: float, jetzt: float) -> bool:
    i = bisect.bisect_left(reihe.punkte, beginn, key=_zeit)
    return i < len(reihe.punkte) and reihe.punkte[i][0] <= jetzt


def stufe_fuer(spanne: float, breite: float) -> float | None:
    """Die Stufe, aus der gezeichnet wird: einzelne Werte, solange ein Bildpunkt weniger als
    eine Viertelsekunde zeigt, sonst Bündel zu 1 s bzw. (ab 1,5 s je Bildpunkt) zu 5 s."""
    sekunden = spanne / max(1.0, breite)
    if sekunden < 0.25:
        return None
    return STUFEN[0] if sekunden < 1.5 else STUFEN[1]


def ausschnitt(reihe: Reihe, jetzt: float, spanne: float,
               stufe: float | None = None) -> list[tuple[float, float]]:
    """Die Punkte der letzten `spanne` Sekunden bis `jetzt` (dazu der letzte davor, damit die
    Linie am linken Rand beginnt; spätere als jetzt nicht). Mit stufe aus den Bündeln: je
    Bündel erster, kleinster und größter (in der Mitte des Bündels) und letzter Wert."""
    if stufe is not None:
        return _ausschnitt_gebuendelt(reihe.buendel[stufe], jetzt, spanne)
    punkte = reihe.punkte
    ende = bisect.bisect_right(punkte, jetzt, key=_zeit)
    anfang = bisect.bisect_left(punkte, jetzt - spanne, 0, ende, key=_zeit)
    if anfang == ende:
        return []
    return list(itertools.islice(punkte, max(0, anfang - 1), ende))


def _ausschnitt_gebuendelt(liste: deque, jetzt: float, spanne: float) -> list[tuple[float, float]]:
    ende = bisect.bisect_right(liste, jetzt, key=lambda b: b[1])
    anfang = bisect.bisect_left(liste, jetzt - spanne, 0, ende, key=lambda b: b[5])
    if anfang == ende:
        return []
    punkte: list[tuple[float, float]] = []
    for _, erste, wert, klein, gross, letzte, zuletzt in itertools.islice(
            liste, max(0, anfang - 1), ende):
        punkte.append((erste, wert))
        if letzte > erste:
            if klein != gross:
                mitte = (erste + letzte) / 2
                punkte += [(mitte, klein), (mitte, gross)]
            punkte.append((letzte, zuletzt))
    return [p for p in punkte if p[0] <= jetzt]


def bereich(punkte: list[tuple[float, float]]) -> tuple[float, float]:
    """Wertebereich mit etwas Luft; eine flache Linie liegt in der Mitte."""
    if not punkte:
        return 0.0, 1.0
    werte = [w for _, w in punkte]
    klein, gross = min(werte), max(werte)
    if gross - klein < 1e-9:
        luft = max(abs(gross) * 0.05, 1.0)
        return klein - luft, gross + luft
    luft = (gross - klein) * 0.08
    return klein - luft, gross + luft


def linien(punkte: list[tuple[float, float]], jetzt: float, spanne: float,
           links: float, oben: float, breite: float, hoehe: float,
           wertebereich: tuple[float, float] | None = None,
           luecke: float = LUECKE) -> list[list[tuple[float, float]]]:
    """Punkte in Bildkoordinaten: rechts ist jetzt, links jetzt − spanne; oben der größte
    Wert. Punkte links vom Rand liegen auf dem Rand. Nach einer Lücke (länger als `luecke`
    ohne Wert) beginnt eine neue Linie. Je Bildpunktspalte bleiben höchstens vier Punkte
    (erster, kleinster, größter, letzter) – so bleibt eine Stunde mit tausenden Werten
    schnell gezeichnet, ohne dass eine Spitze verschwindet."""
    if not punkte or spanne <= 0 or breite <= 0 or hoehe <= 0:
        return []
    klein, gross = wertebereich or bereich(punkte)
    beginn = jetzt - spanne
    fx = breite / spanne
    fy = hoehe / (gross - klein)
    ergebnis: list[list[tuple[float, float]]] = []
    aktuell: list[tuple[float, float]] = []
    spalte: list[tuple[float, float]] = []
    spalte_nr = None
    vorige = None

    def spalte_abschliessen() -> None:
        if len(spalte) <= 4:
            aktuell.extend(spalte)
        else:
            ys = [y for _, y in spalte]
            behalten = sorted({0, ys.index(min(ys)), ys.index(max(ys)), len(spalte) - 1})
            aktuell.extend(spalte[i] for i in behalten)
        spalte.clear()

    for zeit, wert in punkte:
        if vorige is not None and zeit - vorige > luecke:
            spalte_abschliessen()
            if aktuell:
                ergebnis.append(aktuell)
            aktuell = []
            spalte_nr = None
        vorige = zeit
        x = min(links + breite, links + (max(zeit, beginn) - beginn) * fx)
        y = oben + (gross - wert) * fy
        nr = int(x)
        if nr != spalte_nr:
            spalte_abschliessen()
            spalte_nr = nr
        spalte.append((x, y))
    spalte_abschliessen()
    if aktuell:
        ergebnis.append(aktuell)
    return ergebnis


def zeitmarken(spanne: float, ende_text: str | None = None) -> list[tuple[float, str]]:
    """Marken der Zeitachse: (Sekunden vor dem rechten Rand, Beschriftung) – höchstens
    sieben, an runden Werten. Rechts steht „jetzt“ (bzw. ende_text, wenn die Anzeige
    steht)."""
    for schritt in (5, 10, 15, 30, 60, 120, 300, 600, 900, 1800):
        if spanne / schritt <= 6:
            break
    marken = []
    s = 0.0
    while s <= spanne + 1e-9:
        if s == 0:
            text = ende_text or t("jetzt")
        elif schritt >= 60:
            text = t("−{minuten} min", minuten=zahl(s / 60, 0))
        else:
            text = t("−{sekunden} s", sekunden=zahl(s, 0))
        marken.append((s, text))
        s += schritt
    return marken


def abstand_text(sekunden: float) -> str:
    """„−12,3 s“ bzw. „−4,5 min“ – Zeitpunkt unter dem Mauszeiger."""
    if sekunden < 120:
        return t("−{sekunden} s", sekunden=zahl(sekunden, 1))
    return t("−{minuten} min", minuten=zahl(sekunden / 60, 1))


def _wert(reihe: Reihe, wert: float) -> str:
    if reihe.einheit == VOR_OT:              # zurück in die Richtung der Anzeige
        richtung = VOR_OT if wert >= 0 else NACH_OT
        return f"{zahl(abs(wert), reihe.stellen)} {einheit(richtung)}"
    return f"{zahl(wert, reihe.stellen)} {einheit(reihe.einheit)}".strip()


def wert_text(reihe: Reihe) -> str:
    """Letzter Wert mit Einheit, z. B. „13,86 V“."""
    letzter = reihe.letzter
    return "–" if letzter is None else _wert(reihe, letzter[1])


def wert_bei(reihe: Reihe, zeit: float, luecke: float = LUECKE) -> float | None:
    """Der Wert, der zur Zeit `zeit` galt (der letzte davor) – None in einer Lücke oder
    vor dem ersten Wert."""
    punkte = reihe.punkte
    if punkte and zeit < punkte[0][0]:
        # älter als die einzeln gespeicherten Werte: aus den Bündeln (letzter Wert je Sekunde)
        liste = reihe.buendel[STUFEN[0]]
        i = bisect.bisect_right(liste, zeit, key=lambda b: b[1]) - 1
        if i < 0 or zeit - liste[i][5] > luecke:
            return None
        return liste[i][6]
    i = bisect.bisect_right(punkte, zeit, key=_zeit) - 1
    if i < 0 or zeit - punkte[i][0] > luecke:
        return None
    return punkte[i][1]


def wert_text_bei(reihe: Reihe, zeit: float) -> str:
    wert = wert_bei(reihe, zeit)
    return "–" if wert is None else _wert(reihe, wert)


def mindesthoehe(anzahl: int) -> int:
    """Höhe, ab der jeder Streifen seine Mindesthöhe hat."""
    return RAND + max(1, anzahl) * STREIFEN_MIN + ACHSE


class Maler(Protocol):
    def flaeche(self, x: float, y: float, b: float, h: float, farbe: str) -> None: ...
    def linie(self, x1: float, y1: float, x2: float, y2: float, farbe: str,
              breite: float = 1.0) -> None: ...
    def kurve(self, punkte: list[tuple[float, float]], farbe: str,
              breite: float = 2.0) -> None: ...
    def punkt(self, x: float, y: float, farbe: str, radius: float = 2.5) -> None: ...
    def text(self, x: float, y: float, b: float, h: float, text: str, farbe: str,
             ausrichtung: str = "links", umbrechen: bool = False) -> None: ...


def zeichnen(maler: Maler, verlauf: Verlauf, jetzt: float, spanne: float, breite: float,
             hoehe: float, dunkel: bool = False, zeiger: float | None = None,
             ende_text: str | None = None) -> None:
    """Das ganze Bild: je Reihe ein Streifen (Farbmarke, Name, Wert; Kurve mit eigener
    Skala, rechts größter und kleinster Wert), unten die gemeinsame Zeitachse. zeiger: x des
    Mauszeigers – dann zeigen alle Streifen den Wert zu diesem Zeitpunkt."""
    farben = GRUND[dunkel]
    maler.flaeche(0, 0, breite, hoehe, farben["flaeche"])
    links, rechts = RAND, breite - RAND - SKALA
    plotbreite = rechts - links
    if plotbreite <= 20 or hoehe <= ACHSE + KOPF:
        return
    marken = zeitmarken(spanne, ende_text)
    reihen = verlauf.sichtbar(jetzt, spanne)
    stufe = stufe_fuer(spanne, plotbreite)
    zeit_zeiger = None
    if zeiger is not None and links <= zeiger <= rechts:
        zeit_zeiger = jetzt - spanne + (zeiger - links) / plotbreite * spanne
    unten = hoehe - ACHSE
    if not reihen:
        maler.text(links, 0, plotbreite, unten, t(
            "Noch keine Werte – nach dem Start erscheint hier je Zahlenfeld ein Streifen."),
            farben["leise"], "mitte", umbrechen=True)
    streifen = (unten - RAND / 2) / max(1, len(reihen))
    for i, reihe in enumerate(reihen):
        oben = RAND / 2 + i * streifen
        farbe = verlauf.farbe(reihe.schluessel, dunkel)
        punkte = ausschnitt(reihe, jetzt, spanne, stufe) or ausschnitt(reihe, jetzt, spanne)
        kurve_oben = oben + KOPF
        kurve_hoehe = max(4.0, streifen - KOPF - 8)
        # Kopf: Farbmarke, Name; rechts der Wert (am Mauszeiger der Wert zu dieser Zeit)
        maler.linie(links, oben + KOPF / 2, links + 12, oben + KOPF / 2, farbe, 3.0)
        maler.text(links + 18, oben, plotbreite * 0.62 - 18, KOPF, reihe.name,
                   farben["text"], "links")
        wert = wert_text(reihe) if zeit_zeiger is None else wert_text_bei(reihe, zeit_zeiger)
        maler.text(links + plotbreite * 0.62, oben, plotbreite * 0.38, KOPF, wert,
                   farben["text2"], "rechts")
        # Gitter der Zeitachse, Grundlinie
        for s, _ in marken:
            x = rechts - s / spanne * plotbreite
            maler.linie(x, kurve_oben, x, kurve_oben + kurve_hoehe, farben["gitter"], 1.0)
        maler.linie(links, kurve_oben + kurve_hoehe, rechts, kurve_oben + kurve_hoehe,
                    farben["achse"], 1.0)
        # Skala: größter und kleinster Wert im Ausschnitt
        werte = [w for _, w in punkte]
        maler.text(rechts + 6, kurve_oben - 4, SKALA - 6, 14, zahl(max(werte), reihe.stellen),
                   farben["leise"], "links")
        maler.text(rechts + 6, kurve_oben + kurve_hoehe - 10, SKALA - 6, 14,
                   zahl(min(werte), reihe.stellen), farben["leise"], "links")
        klein, gross = bereich(punkte)
        for linie in linien(punkte, jetzt, spanne, links, kurve_oben, plotbreite, kurve_hoehe,
                            (klein, gross)):
            if len(linie) == 1:
                maler.punkt(linie[0][0], linie[0][1], farbe)
            else:
                maler.kurve(linie, farbe, 2.0)
        if zeit_zeiger is not None:
            wert_zeiger = wert_bei(reihe, zeit_zeiger)
            if wert_zeiger is not None:
                y = kurve_oben + (gross - wert_zeiger) / (gross - klein) * kurve_hoehe
                maler.punkt(zeiger, min(max(y, kurve_oben), kurve_oben + kurve_hoehe), farbe,
                            4.0)
    # Zeitachse: Beschriftung mittig unter der Marke, am Rand bündig
    for s, text in marken:
        x = rechts - s / spanne * plotbreite
        if x - 45 < 0:
            maler.text(max(0.0, x - 2), unten, 90, ACHSE, text, farben["leise"], "links")
        elif x + 45 > breite:
            maler.text(breite - 90, unten, 90, ACHSE, text, farben["leise"], "rechts")
        else:
            maler.text(x - 45, unten, 90, ACHSE, text, farben["leise"], "mitte")
    if zeit_zeiger is not None:
        maler.linie(zeiger, RAND / 2, zeiger, unten, farben["text2"], 1.0)
        kasten = min(max(zeiger - 45, 0), breite - 90)
        maler.flaeche(kasten, unten + 2, 90, ACHSE - 4, farben["flaeche"])
        maler.text(kasten, unten, 90, ACHSE, abstand_text(jetzt - zeit_zeiger),
                   farben["text"], "mitte")

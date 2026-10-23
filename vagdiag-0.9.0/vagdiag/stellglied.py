"""Stellglieddiagnose: Nummern und Namen der Stellglieder.

Bei der Stellglieddiagnose meldet ein Steuergerät jedes Stellglied mit einer Nummer aus
derselben Liste wie die fünfstelligen VAG-Fehlercodes (z. B. 00662 = Drehzahlmesser).
01195 (hex 04AB) und 00000 bedeuten „Ende“.

Die eingebauten Namen stammen aus Beobachtungen, die das freie Programm kw1281test
(MIT-Lizenz, Greg Menounos und Mitwirkende) veröffentlicht hat: Kombiinstrument
(KW1281) und Diesel-Motorsteuergeräte EDC15/EDC16 (KWP2000). Unbekannte Nummern zeigt
vagdiag ohne Namen; eigene Namen lassen sich wie Fehlertexte in fehlertexte.json im
Einstellungsordner eintragen, z. B. {"01247": "Magnetventil Aktivkohlebehälter"}.

Bremsen, Airbag, Wegfahrsperre, Lenkung und Niveauregulierung (GEFAHR) steuert vagdiag
erst nach einer Warnung an, die die möglichen Schäden für genau dieses Steuergerät nennt
(bis 0.7.2 waren sie ganz gesperrt). Die Bestätigung reicht bis in die Schreibsperren in
kw1281.py und kwp2000.py: Ohne sie geht kein Stellglied-Block hinaus. Meldet sich unter einer
Adresse ein Gerät, das nach seiner Kennung zu einer anderen Art gehört (etwa ein ABS unter
17, wenn eine Störung die Reizung verfälscht hat), bleibt die Stellglieddiagnose gesperrt.

Nach jedem Durchlauf merkt sich vagdiag die Reihenfolge der Stellglieder je Steuergerät
(Teilenummer und Bauteil) in ~/vagdiag-daten/stellglieder.json – der Simulator nur im
Speicher. Lesen lässt sich die Liste vorher nicht: Das Steuergerät nennt das nächste
Stellglied erst, wenn es es ansteuert.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass

from .fehler import eigene_beschreibung, vag_text
from .pfade import DATEN_ORDNER
from .sprache import N_, englisch, t

log = logging.getLogger("vagdiag.proto")

ENDE = (0x04AB, 0x0000)

# ---------------------------------------------------------------- gefährliche Steuergeräte
ARTEN = {
    "bremsen": N_("Bremsen"),
    "airbag": N_("Airbag"),
    "wegfahrsperre": N_("Wegfahrsperre"),
    "lenkung": N_("Lenkung"),
    "fahrwerk": N_("Niveauregulierung"),
}

GEFAHR = {0x03: "bremsen", 0x23: "bremsen", 0x53: "bremsen", 0x15: "airbag",
          0x25: "wegfahrsperre", 0x44: "lenkung", 0x34: "fahrwerk"}

# Mögliche Schäden je Steuergerät – Text der Warnung vor dem Start
SCHAEDEN = {
    0x03: N_("Die Stellglieddiagnose schaltet die Rückförderpumpe und die Ventile der "
             "Hydraulikeinheit. Mögliche Folgen: Ist Luft in der Hydraulikeinheit (etwa nach "
             "Arbeiten an der Bremse), gelangt sie in die Bremsleitungen – das Pedal wird weich, "
             "die Bremse muss nach Werksvorschrift entlüftet werden. Während des Tests kann ein "
             "Rad ungebremst sein, die Pumpe kann bei langem Lauf überhitzen, Warnlampen und "
             "Fehlereinträge sind möglich. Vorher: Motor aus, Fahrzeug gegen Wegrollen sichern "
             "(Gang und Keile, nicht nur die Fußbremse), niemand fahrbereit am Steuer. Danach die "
             "Bremse prüfen, bevor du losfährst."),
    0x23: N_("Ein elektronisch geregelter Bremskraftverstärker kann dabei selbst Bremsdruck "
             "aufbauen und wieder ablassen; das Bremspedal kann sich von allein bewegen. Mögliche "
             "Folgen: eingeklemmte Füße oder Gegenstände am Pedal, Fehlereinträge, danach ein "
             "nötiger Abgleich des Pedalweggebers. Vorher: Fuß weg vom Pedal, nichts im "
             "Fußraum, Fahrzeug gegen Wegrollen sichern."),
    0x53: N_("Die Stellmotoren der elektrischen Feststellbremse können schließen und lösen. "
             "Mögliche Folgen: Das Fahrzeug rollt weg, wenn die Bremse löst; wird gerade an den "
             "Hinterradbremsen gearbeitet (Wartungsmodus, Kolben zurückgefahren), können Beläge, "
             "Stellmotoren oder Finger eingeklemmt werden; Fehlereinträge. Vorher: Gang bzw. P "
             "einlegen, Keile unterlegen, nicht an den Hinterradbremsen arbeiten."),
    0x15: N_("Airbag-Steuergeräte haben meist keine Stellglieddiagnose und lehnen ab. Wo es "
             "sie gibt, betrifft sie nach den bekannten Unterlagen nur die Warnlampe. Mögliche "
             "Folgen: Fehlereinträge und eine leuchtende Airbaglampe, die erst nach dem Löschen "
             "ausgeht; Störungen in der Kommunikation können bei manchen Geräten nicht löschbare "
             "Fehler hinterlassen (6Q0 909 605 A – das trennt vagdiag sofort). Vorher: niemand im "
             "Fahrzeug, nichts vor den Airbags, nicht an Airbags, Gurtstraffern oder deren "
             "Steckern arbeiten."),
    0x25: N_("Wegfahrsperren haben meist keine Stellglieddiagnose – höchstens die "
             "Kontrollleuchte. Schlüssel und Anlernung bleiben unberührt: Das ginge nur mit "
             "Anmeldung und PIN, die vagdiag nie sendet. Mögliche Folgen: Fehlereinträge, die "
             "Kontrollleuchte blinkt; ist die Diagnose beim Starten noch aktiv, kann die "
             "Freigabe des Motors scheitern – dann Zündung aus und wieder an. Vorher: Motor aus "
             "und erst nach dem Ende der Diagnose starten."),
    0x44: N_("Bei elektrohydraulischer Lenkung kann die Pumpe anlaufen, bei elektromechanischer "
             "der Motor ein Lenkmoment erzeugen – das Lenkrad kann sich drehen. Mögliche Folgen: "
             "Verletzungen an Händen und Armen am Lenkrad, Fehlereinträge, bei "
             "elektromechanischer Lenkung danach ein nötiger Abgleich des Lenkwinkelsensors. "
             "Vorher: Hände weg vom Lenkrad, Räder geradeaus, Fahrzeug steht."),
    0x34: N_("Das Fahrzeug kann sich heben oder senken, Kompressor und Ventile schalten. "
             "Mögliche Folgen: Quetschgefahr unter dem Fahrzeug und zwischen Rad und Kotflügel, "
             "Schäden an Wagenheber oder Hebebühne, wenn das Auto darauf steht, ein überhitzter "
             "Kompressor bei langem Lauf, Fehlereinträge. Vorher: niemand unter oder am "
             "Fahrzeug, das Auto steht auf seinen Rädern (nicht aufgebockt)."),
}

# Was sich bei den übrigen Steuergeräten bewegen kann – steht in der Rückfrage vor dem Start
HINWEISE = {
    0x01: N_("Kraftstoffpumpe, Ventile und Relais schalten, der Kühlerlüfter kann anlaufen – "
             "nicht in den Lüfter greifen."),
    0x17: N_("Zeiger bewegen sich, Lampen leuchten, der Gong ertönt."),
    0x08: N_("Gebläse und Klappenmotoren laufen, der Klimakompressor kann einschalten."),
    0x09: N_("Scheibenwischer, Blinker und Beleuchtung können schalten – Hände weg von den "
             "Wischern."),
    0x35: N_("Türen können ver- und entriegeln, Fenster und Schiebedach sich bewegen – "
             "Schlüssel nicht im Auto lassen, Hände aus Fenster- und Dachöffnungen."),
    0x46: N_("Türen können ver- und entriegeln, Fenster und Schiebedach sich bewegen – "
             "Schlüssel nicht im Auto lassen, Hände aus Fenster- und Dachöffnungen."),
    0x06: N_("Der Sitz kann sich bewegen – niemand auf dem Sitz, nichts im Verstellbereich."),
    0x36: N_("Der Sitz kann sich bewegen – niemand auf dem Sitz, nichts im Verstellbereich."),
    0x55: N_("Die Scheinwerfer verstellen sich."),
    0x56: N_("Die Lautsprecher können laut werden."),
}

# Woran man Airbag, Bremsen, Wegfahrsperre und Lenkung an der Kennung erkennt – falls sich so
# ein Gerät unter einer anderen Adresse meldet (etwa wenn eine Störung die Reizung verfälscht
# hat): Mitte der VAG-Teilenummer (909 5xx/6xx und 959 655 Airbag, 907 379 und 614 xxx ABS/ESP,
# 907 801 Parkbremse, 953 2xx Wegfahrsperre, 423 xxx und 909 144 Lenkung) und Wörter im Namen.
# Ein Kombi mit eingebauter Wegfahrsperre zählt nicht dazu.
_KENNUNG = (
    ("airbag", re.compile(r"^[0-9A-Z]{3}(?:909[56]\d\d|959655)"),
     re.compile(r"(?<![A-Z])AIRBAG(?![A-Z])")),
    ("bremsen", re.compile(r"^[0-9A-Z]{3}(?:907379|907801|614\d{3})"),
     re.compile(r"(?<![A-Z])(?:ABS|ESP|EDS|ASR)(?![A-Z])")),
    ("wegfahrsperre", re.compile(r"^[0-9A-Z]{3}9532[3-5]\d"), None),
    ("lenkung", re.compile(r"^[0-9A-Z]{3}(?:909144|423\d{3})"),
     re.compile(r"(?<![A-Z])(?:EPS|LENKHILFE|LENKUNG)(?![A-Z])")),
)


def art_nach_kennung(teilenummer: str, bauteil: str) -> str | None:
    """Airbag, Bremsen, Wegfahrsperre oder Lenkung – nach Teilenummer und Name (oder None)."""
    teil = re.sub(r"[\s.-]", "", (teilenummer or "").upper())
    text = f"{teilenummer} {bauteil}".upper()
    for art, teile, woerter in _KENNUNG:
        if teile.match(teil) or (woerter is not None and woerter.search(text)):
            return art
    return None


def gesperrt_nach_kennung(teilenummer: str, bauteil: str) -> str | None:
    """Grund, warum dieses Gerät nach seiner Kennung keine Grundeinstellung und keine
    Anpassung bekommt (für die Stellglieddiagnose siehe gefahr())."""
    if art_nach_kennung(teilenummer, bauteil):
        return t("Das Steuergerät meldet sich als „{kennung}“ – das sieht nach Airbag, Bremsen, "
                 "Wegfahrsperre oder Lenkung aus. Grundeinstellung und Anpassung sind dort "
                 "gesperrt, egal unter welcher Adresse.",
                 kennung=f"{teilenummer} {bauteil}".strip())
    return None


@dataclass(frozen=True)
class Gefahr:
    """Die Stellglieddiagnose an diesem Steuergerät kann Schaden anrichten."""
    art: str                # Schlüssel aus ARTEN
    adresse: int

    @property
    def name(self) -> str:
        return t(ARTEN[self.art])

    @property
    def schaeden(self) -> str:
        return t(SCHAEDEN[self.adresse])


def gefahr(adresse: int | None, teilenummer: str = "",
           bauteil: str = "") -> tuple[Gefahr | None, str | None]:
    """(Gefahr, Widerspruch): Gefahr – vor dem Start warnen und bestätigen lassen;
    Widerspruch – Grund, warum die Stellglieddiagnose hier gesperrt ist, weil die Kennung
    nicht zur Adresse passt (dann ist vermutlich ein anderes Gerät dran)."""
    nach_adresse = GEFAHR.get(adresse) if adresse is not None else None
    nach_kennung = art_nach_kennung(teilenummer, bauteil)
    if nach_kennung is not None and nach_kennung != nach_adresse:
        return None, t("Unter Adresse {adresse:02X} meldet sich „{kennung}“ – das sieht nach "
                       "{art} aus und passt nicht zu dieser Adresse. Vermutlich hat eine Störung "
                       "die Reizung verfälscht; die Stellglieddiagnose ist hier gesperrt.",
                       adresse=adresse or 0, kennung=f"{teilenummer} {bauteil}".strip(),
                       art=t(ARTEN[nach_kennung]))
    if nach_adresse is not None:
        return Gefahr(nach_adresse, adresse), None
    return None, None


def hinweis(adresse: int | None) -> str | None:
    """Was sich bei diesem (ungefährlichen) Steuergerät bewegen kann – oder None."""
    return t(HINWEISE[adresse]) if adresse in HINWEISE else None


# Nummer → (deutsch, englisch)
TEXTE: dict[int, tuple[str, str]] = {
    # Kombiinstrument (KW1281)
    0x01F5: ("Warnleuchte Ölstand", "Oil level warning light"),
    0x01F6: ("Kontrollleuchte Wegfahrsperre", "Immobilizer warning light"),
    0x0272: ("Glühzeit-Kontrollleuchte", "Glow plug warning light"),
    0x0295: ("Kühlmitteltemperaturanzeige", "Coolant temperature gauge"),
    0x0296: ("Drehzahlmesser", "Rev counter"),
    0x0297: ("Geschwindigkeitsmesser", "Speedometer"),
    0x0298: ("Kraftstoffvorratsanzeige", "Fuel gauge"),
    0x0299: ("Gurtwarnleuchte", "Seat belt warning light"),
    0x029A: ("Gong", "Gong"),
    0x02F2: ("Warnleuchte Kühlmitteltemperatur", "Coolant temperature warning light"),
    0x02F3: ("Warnleuchte Öldruck", "Oil pressure warning light"),
    0x031E: ("Segmenttest der Anzeigen", "Display segment test"),
    0x03FF: ("Summer", "Chime"),
    0x0416: ("Warnleuchte Bremsbeläge", "Brake pad warning light"),
    0x0417: ("Warnleuchte Bremse", "Brake warning light"),
    0x043A: ("Warnleuchte Kraftstoffreserve", "Low fuel warning light"),
    0x043B: ("Warnleuchte Waschwasserstand", "Low washer fluid warning light"),
    # Diesel-Motorsteuergeräte EDC15/EDC16 (KWP2000)
    0x0243: ("Magnetventil Ladedruckbegrenzung (N75)", "Boost pressure control valve (N75)"),
    0x04EE: ("Magnetventil Ladedruckbegrenzung (N75)", "Boost pressure control valve (N75)"),
    0x0270: ("Abschaltung Klimakompressor", "A/C compressor cut-off"),
    0x02EE: ("Abgaswarnleuchte (K83)", "Malfunction indicator lamp (K83)"),
    0x1690: ("Abgaswarnleuchte", "Malfunction indicator lamp"),
    0x46B4: ("Abgaswarnleuchte", "Malfunction indicator lamp"),
    0x0403: ("Ventil Abgasrückführung", "EGR valve"),
    0x04F1: ("Ventil Abgasrückführung", "EGR valve"),
    0x0480: ("Kühlerlüfter 1", "Radiator fan 1"),
    0x09E6: ("Kühlerlüfter 1", "Radiator fan 1"),
    0x04A9: ("Relais Zusatzheizung Kühlmittel (kleine Leistung)",
             "Coolant heater relay (low output)"),
    0x3003: ("Relais Zusatzheizung Kühlmittel (kleine Leistung)",
             "Coolant heater relay (low output)"),
    0x04AA: ("Relais Zusatzheizung Kühlmittel (große Leistung)",
             "Coolant heater relay (high output)"),
    0x3005: ("Relais Zusatzheizung Kühlmittel (große Leistung)",
             "Coolant heater relay (high output)"),
    0x04D5: ("Kraftstoffabschaltventil (N109)", "Fuel shut-off valve (N109)"),
    0x04F2: ("Relais Glühkerzen (J52)", "Glow plug relay (J52)"),
    0x04F5: ("Ventil Spritzbeginn (N108)", "Injection timing valve (N108)"),
    0x0684: ("Steuergerät Glühzeit", "Glow plug control module"),
    0x42AC: ("Steuergerät Glühzeit", "Glow plug control module"),
    0x09E8: ("Umschaltventil Kühler Abgasrückführung", "EGR cooler bypass valve"),
    0x1495: ("Umschaltventil Kühler Abgasrückführung", "EGR cooler bypass valve"),
    0x1616: ("Glühzeit-Kontrollleuchte", "Glow plug warning light"),
    0x162D: ("Kontrollleuchte Partikelfilter", "Particulate filter warning light"),
    0x3100: ("Saugrohrklappe", "Intake manifold flap"),
    0x4C64: ("Saugrohrklappe", "Intake manifold flap"),
    0x3372: ("Drallklappen-Steller", "Swirl flap actuator"),
    0x4808: ("Drallklappen-Steller", "Swirl flap actuator"),
    # Ende der Stellglieddiagnose
    0x04AB: ("Ende", "End"),
    0x0000: ("Ende", "End"),
}

# Namen, die nur der Simulator meldet (Nummern ab F000) – eingetragen von sim.py
SIMULATOR: dict[int, tuple[str, str]] = {}


def name(code: int) -> str:
    """Name eines Stellglieds in der eingestellten Sprache: eigene Texte, dann die Namen für
    Stellglieder (TEXTE – sie kennen den Zusammenhang, z. B. 0243 = N75 beim EDC15, obwohl
    00579 als Fehlercode etwas anderes bedeutet), dann die Fehlertexte."""
    eigener = eigene_beschreibung(code)
    if eigener:
        return eigener
    for tabelle in (TEXTE, SIMULATOR):
        if code in tabelle:
            return tabelle[code][1 if englisch() else 0]
    return vag_text(code) or t("(kein Klartext hinterlegt)")


@dataclass
class Stellglied:
    code: int
    roh: bytes = b""            # Antwortdaten des Steuergeräts (fürs Protokoll)

    @property
    def code_text(self) -> str:
        return f"{self.code:05d}"

    @property
    def name(self) -> str:
        return name(self.code)

    @property
    def ende(self) -> bool:
        return self.code in ENDE

    @property
    def text(self) -> str:
        return f"{self.code_text} – {self.name}"


# ---------------------------------------------------------------- gemerkte Listen
LISTEN_DATEI = DATEN_ORDNER / "stellglieder.json"
_SIM_LISTEN: dict[str, dict] = {}         # Simulator: nur im Speicher
_LISTEN_SPERRE = threading.Lock()


@dataclass
class GemerkteListe:
    """Die Stellglieder eines Steuergeräts in der Reihenfolge eines früheren Durchlaufs."""
    adresse: int
    codes: list[int]
    vollstaendig: bool          # bis zum „Ende“ des Steuergeräts durchlaufen
    stand: str                  # wann (JJJJ-MM-TT hh:mm)

    @property
    def stellglieder(self) -> list[Stellglied]:
        return [Stellglied(code) for code in self.codes]


def _schluessel(teilenummer: str, bauteil: str) -> str:
    return " ".join(f"{teilenummer} {bauteil}".split())


def _alle(sim: bool) -> dict:
    if sim:
        return _SIM_LISTEN
    try:
        daten = json.loads(LISTEN_DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return daten if isinstance(daten, dict) else {}


def liste_laden(teilenummer: str, bauteil: str, sim: bool = False) -> GemerkteListe | None:
    """Die gemerkte Liste dieses Steuergeräts (nur lesen, keine Verbindung) – oder None."""
    eintrag = _alle(sim).get(_schluessel(teilenummer, bauteil))
    if not isinstance(eintrag, dict):
        return None
    try:
        return GemerkteListe(int(eintrag["adresse"]), [int(c) for c in eintrag["codes"]],
                             bool(eintrag["vollstaendig"]), str(eintrag.get("stand", "")))
    except (KeyError, TypeError, ValueError):
        return None


def liste_merken(adresse: int, teilenummer: str, bauteil: str, codes: list[int],
                 vollstaendig: bool, sim: bool = False) -> GemerkteListe | None:
    """Nach einem Durchlauf: Reihenfolge merken. Ein abgebrochener Durchlauf ersetzt keine
    längere Liste, die genauso beginnt. Gleiche Nummern direkt hintereinander (KWP2000:
    erst anzeigen, dann ansteuern) zählen einmal."""
    folge: list[int] = []
    for code in codes:
        if not folge or folge[-1] != code:
            folge.append(code)
    if not folge:
        return liste_laden(teilenummer, bauteil, sim)
    with _LISTEN_SPERRE:
        alt = liste_laden(teilenummer, bauteil, sim)
        if (alt is not None and not vollstaendig and len(alt.codes) >= len(folge)
                and alt.codes[:len(folge)] == folge):
            return alt
        neu = GemerkteListe(adresse, folge, vollstaendig, time.strftime("%Y-%m-%d %H:%M"))
        alle = _alle(sim)
        alle[_schluessel(teilenummer, bauteil)] = {
            "adresse": adresse, "codes": folge, "vollstaendig": vollstaendig,
            "stand": neu.stand, "kennung": _schluessel(teilenummer, bauteil)}
        if not sim:
            try:
                LISTEN_DATEI.parent.mkdir(parents=True, exist_ok=True)
                zwischen = LISTEN_DATEI.with_suffix(".tmp")
                zwischen.write_text(json.dumps(alle, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
                zwischen.replace(LISTEN_DATEI)
            except OSError as exc:
                log.warning(t("Stellglied-Liste nicht gespeichert: %s"), exc)
        return neu

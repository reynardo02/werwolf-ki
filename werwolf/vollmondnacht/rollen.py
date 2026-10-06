"""Rollen, Parteien, Nachtreihenfolge, Szenarien und Siegbedingung von Vollmondnacht."""

import random
from enum import Enum


class Partei(Enum):
    DORF = "Dorfgemeinschaft"
    WERWOELFE = "Werwolfsrudel"
    GERBER = "Gerber"


class Rolle(Enum):
    DOPPELGAENGERIN = "Doppelgängerin"
    WERWOLF = "Werwolf"
    GUENSTLING = "Günstling"
    FREIMAURER = "Freimaurer"
    SEHERIN = "Seherin"
    RAEUBER = "Räuber"
    UNRUHESTIFTERIN = "Unruhestifterin"
    BETRUNKENER = "Betrunkener"
    SCHLAFLOSE = "Schlaflose"
    JAEGER = "Jäger"
    GERBER = "Gerber"
    DORFBEWOHNER = "Dorfbewohner"

    @property
    def partei(self) -> Partei:
        # Die Doppelgängerin gehört zur Partei der Rolle, die sie nachahmt.
        # Das löst die Engine auf, bevor sie diese Eigenschaft benutzt.
        if self in (Rolle.WERWOLF, Rolle.GUENSTLING):
            return Partei.WERWOELFE
        if self is Rolle.GERBER:
            return Partei.GERBER
        return Partei.DORF


# In dieser Reihenfolge wachen die Rollen nachts auf (Spielleiterbogen).
# Jäger, Gerber und Dorfbewohner sind durchschlafend.
NACHT_REIHENFOLGE = [
    Rolle.DOPPELGAENGERIN,
    Rolle.WERWOLF,
    Rolle.GUENSTLING,
    Rolle.FREIMAURER,
    Rolle.SEHERIN,
    Rolle.RAEUBER,
    Rolle.UNRUHESTIFTERIN,
    Rolle.BETRUNKENER,
    Rolle.SCHLAFLOSE,
]

# Was jede Rolle kann – so, wie es alle Spieler aus der Anleitung kennen.
# Wer eine Rolle behauptet, muss dazu passende Erlebnisse erzählen.
FAEHIGKEITEN = {
    Rolle.DOPPELGAENGERIN: (
        "wacht als Erste auf, sieht die Karte eines Mitspielers an und wird zu dieser Rolle "
        "(als Seherin, Räuber, Unruhestifterin, Betrunkener oder Günstling handelt sie sofort)"
    ),
    Rolle.WERWOLF: (
        "die Werwölfe sehen sich gegenseitig; ist nur einer unter den Spielern, "
        "darf er sich eine Karte aus der Mitte ansehen"
    ),
    Rolle.GUENSTLING: "sieht, wer die Werwölfe sind; die Werwölfe kennen ihn nicht",
    Rolle.FREIMAURER: "die Freimaurer sehen sich gegenseitig",
    Rolle.SEHERIN: "sieht entweder die Karte eines Mitspielers oder zwei Karten aus der Mitte",
    Rolle.RAEUBER: "darf seine Karte mit der eines Mitspielers tauschen und sieht dann seine neue Karte",
    Rolle.UNRUHESTIFTERIN: "darf die Karten von zwei anderen Spielern vertauschen, ohne sie anzusehen",
    Rolle.BETRUNKENER: "muss seine Karte mit einer aus der Mitte tauschen, ohne sie anzusehen",
    Rolle.SCHLAFLOSE: "sieht am Ende der Nacht ihre eigene Karte an",
    Rolle.JAEGER: "keine Nachtaktion; stirbt er, stirbt auch der Spieler, auf den er zeigt",
    Rolle.GERBER: "keine Nachtaktion; gewinnt nur, wenn er selbst stirbt",
    Rolle.DORFBEWOHNER: "keine Nachtaktion",
}


def faehigkeiten_text(rollen: set[Rolle]) -> str:
    """Die Rollen einer Partie mit ihren Fähigkeiten, in der Reihenfolge der Nacht."""
    reihenfolge = NACHT_REIHENFOLGE + [r for r in Rolle if r not in NACHT_REIHENFOLGE]
    return "\n".join(f"- {r.value}: {FAEHIGKEITEN[r]}" for r in reihenfolge if r in rollen)


# Alle 16 Karten der Schachtel.
SCHACHTEL = (
    [Rolle.DORFBEWOHNER] * 3 + [Rolle.WERWOLF] * 2 + [Rolle.FREIMAURER] * 2
    + [Rolle.SEHERIN, Rolle.RAEUBER, Rolle.UNRUHESTIFTERIN, Rolle.GERBER, Rolle.BETRUNKENER,
       Rolle.JAEGER, Rolle.SCHLAFLOSE, Rolle.GUENSTLING, Rolle.DOPPELGAENGERIN]
)

W, S, R, U, D = Rolle.WERWOLF, Rolle.SEHERIN, Rolle.RAEUBER, Rolle.UNRUHESTIFTERIN, Rolle.DORFBEWOHNER
B, SL, J, G = Rolle.BETRUNKENER, Rolle.SCHLAFLOSE, Rolle.JAEGER, Rolle.GUENSTLING
F, GE, DG = Rolle.FREIMAURER, Rolle.GERBER, Rolle.DOPPELGAENGERIN

# Szenarien aus der Anleitung (S. 17–19): Grundbesetzung für die kleinste
# Spielerzahl, dazu je Spielerzahl die zusätzlichen Karten.
SZENARIEN: dict[str, tuple[list[Rolle], dict[int, list[Rolle]]]] = {
    "Die erste Nacht": ([W, W, S, R, U, D], {3: [], 4: [D], 5: [D, D]}),
    "Mondsucht": ([W, W, SL, R, U, D], {3: [], 4: [D], 5: [D, S], 6: [D, D, S]}),
    "Einsame Nacht": ([W, S, R, U, D, D], {3: [], 4: [D]}),
    "Konfusion": ([W, W, B, R, U, SL], {
        3: [], 4: [D], 5: [D, S], 6: [D, D, S], 7: [D, D, D, S],
        8: [D, D, D, S, G], 9: [D, D, S, G, F, F],
    }),
    "Payback": ([W, W, J, S, R, B, SL], {4: [], 5: [U], 6: [U, D], 7: [U, D, D]}),
    "Geheime Gefährten": ([W, W, G, J, S, R, U, F, F], {6: [], 7: [D]}),
    "Stunden der Verzweiflung": ([W, W, GE, S, R, B, SL], {
        4: [], 5: [U], 6: [U, D], 7: [U, F, F], 8: [U, F, F, J],
        9: [U, F, F, J, G], 10: [U, F, F, J, G, D],
    }),
    "Allianz im Zwielicht": ([W, W, F, F, G, R, U, SL], {
        5: [], 6: [B], 7: [B, S], 8: [B, S, D], 9: [B, S, D, D], 10: [B, S, D, D, GE],
    }),
    "Wiedergänger": ([W, W, DG, G, J, S, R, U, D, F, F], {8: [], 9: [SL], 10: [SL, B]}),
}
ANARCHIE = "Anarchie"


def szenario_karten(name: str, anzahl_spieler: int, rng: random.Random) -> list[Rolle]:
    """Die Karten eines Szenarios: immer genau 3 mehr als Spieler."""
    if name == ANARCHIE:
        # 2 Werwölfe und 1 Dorfbewohner fest, der Rest zufällig aus der Schachtel.
        if not 3 <= anzahl_spieler <= 10:
            raise ValueError("Anarchie gibt es für 3–10 Spieler.")
        rest = list(SCHACHTEL)
        for karte in (W, W, D):
            rest.remove(karte)
        return [W, W, D] + rng.sample(rest, anzahl_spieler)
    if name not in SZENARIEN:
        raise ValueError(f"Unbekanntes Szenario '{name}'. Möglich: {', '.join(szenario_namen())}")
    basis, zusaetze = SZENARIEN[name]
    if anzahl_spieler not in zusaetze:
        raise ValueError(f"'{name}' gibt es für {min(zusaetze)}–{max(zusaetze)} Spieler.")
    return basis + zusaetze[anzahl_spieler]


def szenario_namen(anzahl_spieler: int | None = None) -> list[str]:
    """Alle Szenarien, optional nur die für eine Spielerzahl passenden."""
    namen = [n for n, (_, z) in SZENARIEN.items() if anzahl_spieler is None or anzahl_spieler in z]
    if anzahl_spieler is None or 3 <= anzahl_spieler <= 10:
        namen.append(ANARCHIE)
    return namen


def gewinner_bestimmen(endrollen: dict[str, Rolle], tote: set[str]) -> set[Partei]:
    """Der „Wer-hat-gewonnen-Check“ vom Spielleiterbogen.

    `endrollen` sind die Rollen der Karten, die am Ende vor den Spielern liegen
    (die Doppelgängerin schon aufgelöst). Der Jäger ist in `tote` bereits
    berücksichtigt. Leere Menge: niemand gewinnt.
    """
    woelfe = {n for n, r in endrollen.items() if r is Rolle.WERWOLF}
    guenstlinge = {n for n, r in endrollen.items() if r is Rolle.GUENSTLING}
    gerber = {n for n, r in endrollen.items() if r is Rolle.GERBER}

    if not tote:
        return {Partei.WERWOELFE} if woelfe else {Partei.DORF}
    if gerber & tote:
        return {Partei.GERBER, Partei.DORF} if woelfe & tote else {Partei.GERBER}
    if woelfe & tote:
        return {Partei.DORF}
    if guenstlinge & tote:
        # Stirbt nur der Günstling: Mit Werwölfen gewinnt trotzdem das Rudel,
        # ohne Werwölfe hat das Dorf richtig gelegen.
        return {Partei.WERWOELFE} if woelfe else {Partei.DORF}
    if woelfe or guenstlinge:
        return {Partei.WERWOELFE}
    return set()  # Kein Werwolf im Spiel, aber ein Unschuldiger ist gestorben.

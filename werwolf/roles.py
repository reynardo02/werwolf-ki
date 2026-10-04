"""Rollen, Teams und die Rollenverteilung zu Spielbeginn."""

import random
from enum import Enum


class Team(Enum):
    DORF = "Dorf"
    WERWOELFE = "Werwölfe"


class Rolle(Enum):
    WERWOLF = "Werwolf"
    SEHERIN = "Seherin"
    DORFBEWOHNER = "Dorfbewohner"

    @property
    def team(self) -> Team:
        # Nur Werwölfe spielen für die Werwölfe, alle anderen fürs Dorf.
        return Team.WERWOELFE if self is Rolle.WERWOLF else Team.DORF


MIN_SPIELER = 5


def anzahl_werwoelfe(anzahl_spieler: int) -> int:
    """Ein Drittel der Spieler (abgerundet) sind Werwölfe: 5 -> 1, 6/7 -> 2."""
    return max(1, anzahl_spieler // 3)


def rollen_verteilen(namen: list[str], rng: random.Random) -> dict[str, Rolle]:
    """Verteilt die Rollen zufällig: Werwölfe, eine Seherin, Rest Dorfbewohner."""
    if len(namen) < MIN_SPIELER:
        raise ValueError(f"Mindestens {MIN_SPIELER} Spieler nötig, nicht {len(namen)}.")
    if len(set(namen)) != len(namen):
        raise ValueError("Spielernamen müssen eindeutig sein.")

    werwoelfe = anzahl_werwoelfe(len(namen))
    rollen = (
        [Rolle.WERWOLF] * werwoelfe
        + [Rolle.SEHERIN]
        + [Rolle.DORFBEWOHNER] * (len(namen) - werwoelfe - 1)
    )
    rng.shuffle(rollen)
    return dict(zip(namen, rollen))

"""Kurzzeitgedächtnis: welche Erinnerungen ein Agent in seinen Kontext bekommt.

Ältere Runden werden weggelassen, weil der Agent sie in seinen Notizen
zusammengefasst hat. Das hält den Prompt klein. Was dauerhaft wichtig ist
(z. B. ein Todesfall), entscheidet das Spiel – dieses Modul kennt keine Regeln.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Erinnerung:
    runde: int
    text: str
    wichtig: bool = False  # bleibt auch nach Ablauf des Fensters im Kontext


def kontext_auswaehlen(
    erinnerungen: list[Erinnerung], aktuelle_runde: int, volle_runden: int = 1
) -> list[Erinnerung]:
    """Die letzten `volle_runden` Runden komplett, davor nur wichtige Erinnerungen."""
    grenze = aktuelle_runde - volle_runden + 1
    return [e for e in erinnerungen if e.wichtig or e.runde >= grenze]

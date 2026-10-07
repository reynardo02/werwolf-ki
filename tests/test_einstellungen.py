"""Einstellungen einer neuen Partie (web/einstellungen.py), gemeinsam für Server und Browser."""

import pytest

from web.einstellungen import Fehler, einstellungen_pruefen


def test_mehrere_menschen() -> None:
    e = einstellungen_pruefen({"regeln": "vollmondnacht", "spieler": 7, "llm": "alle", "menschen": ["Clara", "Anna"]})
    assert e.menschen == ("Anna", "Clara")  # Sitzreihenfolge
    assert e.anzahl_llm == 5


def test_altes_format_mit_ich() -> None:
    # Im Browser gespeicherte Partien von früher kennen nur „ich“.
    e = einstellungen_pruefen({"regeln": "vollmondnacht", "spieler": 5, "llm": "alle", "ich": "Ben"})
    assert e.menschen == ("Ben",) and e.anzahl_llm == 4


@pytest.mark.parametrize("falsch", [
    {"menschen": ["Anna", "Anna"]},  # doppelt
    {"menschen": ["Greta"], "spieler": 5},  # Platz gibt es nicht
    {"menschen": ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda"], "spieler": 8},  # mehr als 5
    {"menschen": ["Anna", "Ben", "Clara"], "spieler": 5, "llm": "3"},  # nur 2 Plätze frei
    {"menschen": "Anna"},  # keine Liste
])
def test_falsche_menschen(falsch: dict) -> None:
    with pytest.raises(Fehler):
        einstellungen_pruefen({"regeln": "vollmondnacht", "spieler": 7, "llm": "0"} | falsch)


def test_alle_plaetze_menschlich() -> None:
    e = einstellungen_pruefen({"regeln": "vollmondnacht", "spieler": 4, "llm": "alle",
                               "menschen": ["Anna", "Ben", "Clara", "Dario"]})
    assert e.anzahl_llm == 0

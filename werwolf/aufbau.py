"""Aufbau einer Partie: Namen, Spielerzahlen, Agenten und Engine.

Liegt hier statt in main.py, damit auch die Browser-Version (Pyodide) es nutzen kann:
main.py lädt die .env und das openai-SDK, beides gibt es im Browser nicht.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.llm_client import LLMClient
from werwolf.engine import Engine, Ergebnis
from werwolf.llm_spieler import LLMSpieler, persoenlichkeiten_laden
from werwolf.mensch_spieler import MenschSpieler
from werwolf.mock_agent import MockAgent
from werwolf.schnittstelle import Agent, Ereignis
from werwolf.vollmondnacht.engine import VollmondEngine, VollmondErgebnis
from werwolf.vollmondnacht.llm_spieler import VollmondLLMSpieler
from werwolf.vollmondnacht.rollen import szenario_karten

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta", "Hugo", "Ida", "Jonas"]
KLASSISCH = "klassisch"
VOLLMONDNACHT = "vollmondnacht"
SPIELERZAHL = {KLASSISCH: (5, 7), VOLLMONDNACHT: (3, 10)}


def engine_bauen(
    regeln: str, agenten: dict[str, Agent], rng: random.Random, szenario: str,
    beobachter: Callable[[Ereignis], None],
) -> tuple[Engine | VollmondEngine, dict[str, str]]:
    """Baut die Engine der gewählten Variante und gibt die (Start-)Rolle jedes Spielers zurück."""
    if regeln == VOLLMONDNACHT:
        karten = szenario_karten(szenario, len(agenten), rng)
        engine = VollmondEngine(agenten, karten, rng=rng, beobachter=beobachter)
        return engine, {s.name: s.startrolle.value for s in engine.spieler.values()}
    klassisch = Engine(agenten, rng=rng, beobachter=beobachter)
    return klassisch, {s.name: s.rolle.value for s in klassisch.spieler.values()}


def ergebnis_zusammenfassen(ergebnis: Ergebnis | VollmondErgebnis) -> tuple[str, list[str], dict[str, Any]]:
    """Kurzfassung, Zeilen fürs Protokoll und Daten fürs Log."""
    if isinstance(ergebnis, VollmondErgebnis):
        gewinner = " und ".join(sorted(p.value for p in ergebnis.gewinner)) or "Niemand"
        tote = f"tot: {', '.join(ergebnis.tote)}" if ergebnis.tote else "niemand stirbt"
        kurz = f"{gewinner} gewinnt ({tote})"
        zeilen = [f"{kurz}.", f"Sieger: {', '.join(ergebnis.sieger) or 'niemand'}"]
        daten = {
            "gewinner": sorted(p.value for p in ergebnis.gewinner),
            "sieger": ergebnis.sieger,
            "tote": ergebnis.tote,
            "endrollen": {n: r.value for n, r in ergebnis.endrollen.items()},
        }
        return kurz, zeilen, daten
    kurz = f"{ergebnis.gewinner.value} gewinnen nach {ergebnis.runden} Runden"
    zeilen = [f"{kurz}.", f"Überlebende: {', '.join(ergebnis.ueberlebende)}"]
    daten = {"gewinner": ergebnis.gewinner.value, "runden": ergebnis.runden, "ueberlebende": ergebnis.ueberlebende}
    return kurz, zeilen, daten



@dataclass
class Besetzung:
    """Wer an welchem Platz sitzt."""

    agenten: dict[str, Agent] = field(default_factory=dict)
    persoenlichkeit_von: dict[str, str | None] = field(default_factory=dict)
    typ_von: dict[str, str] = field(default_factory=dict)  # "mensch", "llm" oder "mock"


def agenten_bauen(
    seed: int, rng: random.Random, namen: list[str], anzahl_llm: int, client: LLMClient | None,
    regeln: str, mensch: str | None = None, mensch_spieler: Agent | None = None,
) -> Besetzung:
    """Verteilt die Plätze: du (falls `mensch`), dann LLM-Spieler, der Rest MockAgenten."""
    # Jeder LLM-Spieler bekommt eine andere, zufällige Persönlichkeit.
    # Die Rollen werden zufällig verteilt, daher ist egal, welche Namen das LLM bekommt.
    persoenlichkeiten = rng.sample(persoenlichkeiten_laden(), anzahl_llm)
    llm_klasse = VollmondLLMSpieler if regeln == VOLLMONDNACHT else LLMSpieler
    b = Besetzung()
    llm_vergeben = 0
    for name in namen:
        if name == mensch:
            b.agenten[name] = mensch_spieler or MenschSpieler()
            b.persoenlichkeit_von[name] = None
            b.typ_von[name] = "mensch"
        elif client and llm_vergeben < anzahl_llm:
            # Eigener Zufall pro Spieler aus Seed und Name: verbraucht nichts vom
            # Zufall der Partie, gleiche Seeds verteilen also gleiche Karten.
            persoenlichkeit = persoenlichkeiten[llm_vergeben]
            b.agenten[name] = llm_klasse(client, persoenlichkeit, rng=random.Random(f"{seed}-{name}"))
            b.persoenlichkeit_von[name] = persoenlichkeit
            b.typ_von[name] = "llm"
            llm_vergeben += 1
        else:
            b.agenten[name] = MockAgent(random.Random(rng.random()))
            b.persoenlichkeit_von[name] = None
            b.typ_von[name] = "mock"
    return b

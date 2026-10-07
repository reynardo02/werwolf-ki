"""Aufbau einer Partie: Namen, Spielerzahlen, Agenten und Engine.

Liegt hier statt in main.py, damit auch die Browser-Version (Pyodide) es nutzen kann:
main.py lädt die .env und das openai-SDK, beides gibt es im Browser nicht.
"""

import random
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import datetime
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
    beobachter: Callable[[Ereignis], None], menschen: Collection[str] = (),
) -> tuple[Engine | VollmondEngine, dict[str, str]]:
    """Baut die Engine der gewählten Variante und gibt die (Start-)Rolle jedes Spielers zurück.

    Teilen sich mehrere Menschen ein Gerät, kommen sie nachts alle reihum dran (`nacht_reihum`),
    damit niemand an Reihenfolge oder Überspringen eine Rolle erkennt. Allein braucht es das nicht.
    """
    reihum = menschen if len(menschen) > 1 else ()
    if regeln == VOLLMONDNACHT:
        karten = szenario_karten(szenario, len(agenten), rng)
        engine = VollmondEngine(agenten, karten, rng=rng, beobachter=beobachter, nacht_reihum=reihum)
        return engine, {s.name: s.startrolle.value for s in engine.spieler.values()}
    klassisch = Engine(agenten, rng=rng, beobachter=beobachter, nacht_reihum=reihum)
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
    regeln: str, menschen: Collection[str] = (), mensch_spieler: Agent | None = None,
) -> Besetzung:
    """Verteilt die Plätze: Menschen (`menschen`), dann LLM-Spieler, der Rest MockAgenten.

    Alle menschlichen Plätze teilen sich ein Agent-Objekt (`mensch_spieler`): Es sieht an
    `zug.ich`, wer gerade gefragt ist – so können mehrere Menschen an einem Gerät spielen.
    """
    # Jeder LLM-Spieler bekommt eine andere, zufällige Persönlichkeit.
    # Die Rollen werden zufällig verteilt, daher ist egal, welche Namen das LLM bekommt.
    persoenlichkeiten = rng.sample(persoenlichkeiten_laden(), anzahl_llm)
    llm_klasse = VollmondLLMSpieler if regeln == VOLLMONDNACHT else LLMSpieler
    b = Besetzung()
    llm_vergeben = 0
    for name in namen:
        if name in menschen:
            if mensch_spieler is None:
                mensch_spieler = MenschSpieler()
            b.agenten[name] = mensch_spieler
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


def kopf_bauen(
    regeln: str, modell: str | None, seed: int, namen: list[str], rolle_von: dict[str, str],
    besetzung: Besetzung, engine: Engine | VollmondEngine, szenario: str | None,
) -> dict[str, Any]:
    """Erste Zeile des JSONL-Logs: Wer hat mit welcher Karte gespielt?"""
    kopf: dict[str, Any] = {
        "zeit": datetime.now().isoformat(timespec="seconds"),
        "regeln": regeln,
        "modell": modell,
        "seed": seed,
        "spieler": [
            {
                "name": name,
                "rolle": rolle_von[name],
                "typ": besetzung.typ_von[name],
                "persoenlichkeit": besetzung.persoenlichkeit_von[name],
            }
            for name in namen
        ],
    }
    if isinstance(engine, VollmondEngine):
        kopf["szenario"] = szenario
        kopf["mitte"] = [r.value for r in engine.mitte]
    return kopf


def protokoll_kopf(kopf: dict[str, Any]) -> tuple[str, list[str]]:
    """Titel und Besetzung für das lesbare Protokoll, aus dem Log-Kopf."""
    zeit = datetime.fromisoformat(kopf["zeit"])
    titel = f"Werwolf ({kopf['regeln']}) – {zeit:%d.%m.%Y %H:%M} – Seed {kopf['seed']}"
    if kopf.get("szenario"):
        titel += f" – Szenario: {kopf['szenario']}"
    if kopf.get("modell"):
        titel += f" – Modell: {kopf['modell']}"
    art_von = {"mensch": "Mensch", "mock": "MockAgent"}
    zeilen = []
    for s in kopf["spieler"]:
        art = f"LLM, {s['persoenlichkeit']}" if s["typ"] == "llm" else art_von[s["typ"]]
        zeilen.append(f"{s['name']}: {s['rolle']} ({art})")
    if "mitte" in kopf:
        zeilen.append(f"Mitte: {', '.join(kopf['mitte'])}")
    return titel, zeilen

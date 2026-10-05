"""Startet eine Partie Werwolf mit MockAgenten und/oder LLM-Spielern."""

import argparse
import random
from datetime import datetime
from pathlib import Path

from core.konfig import konfig_laden
from core.llm_client import BudgetErschoepft
from werwolf.engine import Engine
from werwolf.llm_spieler import LLMSpieler, persoenlichkeiten_laden
from werwolf.mock_agent import MockAgent
from werwolf.protokoll import Protokoll
from werwolf.schnittstelle import Agent

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta"]
LOGS = Path(__file__).parent / "logs"


def main() -> None:
    parser = argparse.ArgumentParser(description="Werwolf mit Agenten")
    parser.add_argument("--spieler", type=int, default=7, help="Anzahl Spieler (5–7)")
    parser.add_argument("--seed", type=int, default=None, help="Zufallsstartwert")
    parser.add_argument(
        "--llm", default="0", help="Wie viele Spieler das LLM steuert, Zahl oder 'alle' (Rest: MockAgent)"
    )
    args = parser.parse_args()

    if not 5 <= args.spieler <= len(NAMEN):
        parser.error(f"--spieler muss zwischen 5 und {len(NAMEN)} liegen")
    anzahl_llm = args.spieler if args.llm == "alle" else int(args.llm) if args.llm.isdigit() else -1
    if not 0 <= anzahl_llm <= args.spieler:
        parser.error("--llm muss 'alle' oder eine Zahl zwischen 0 und --spieler sein")

    rng = random.Random(args.seed)
    namen = NAMEN[: args.spieler]
    try:
        client = konfig_laden().client() if anzahl_llm else None
    except ValueError as fehler:
        parser.error(f"{fehler} (Vorlage: .env.example)")

    # Jeder LLM-Spieler bekommt eine andere, zufällige Persönlichkeit.
    # Die Rollen werden zufällig verteilt, daher ist egal, welche Namen das LLM bekommt.
    persoenlichkeiten = rng.sample(persoenlichkeiten_laden(), anzahl_llm)
    agenten: dict[str, Agent] = {}
    beschreibung: dict[str, str] = {}
    for i, name in enumerate(namen):
        if client and i < anzahl_llm:
            agenten[name] = LLMSpieler(client, persoenlichkeiten[i])
            beschreibung[name] = f"LLM, {persoenlichkeiten[i]}"
        else:
            agenten[name] = MockAgent(random.Random(rng.random()))
            beschreibung[name] = "MockAgent"

    protokoll = Protokoll()
    engine = Engine(agenten, rng=rng, beobachter=protokoll)

    titel = f"Werwolf – {datetime.now():%d.%m.%Y %H:%M}"
    if client:
        titel += f" – Modell: {client.modell}"
    protokoll.kopf(
        titel,
        [f"{s.name}: {s.rolle.value} ({beschreibung[s.name]})" for s in engine.spieler.values()],
    )

    try:
        ergebnis = engine.spielen()
        protokoll.schreiben()
        protokoll.schreiben(f"{ergebnis.gewinner.value} gewinnen nach {ergebnis.runden} Runden.")
        protokoll.schreiben(f"Überlebende: {', '.join(ergebnis.ueberlebende)}")
    except BudgetErschoepft as fehler:
        protokoll.schreiben()
        protokoll.schreiben(f"Partie abgebrochen: {fehler} (LLM_MAX_AUFRUFE in der .env)")

    if client:
        st = client.statistik
        protokoll.schreiben(
            f"API: {st.aufrufe} Aufrufe, {st.input_tokens} Input- / {st.output_tokens} Output-Tokens"
        )
        if st.fehler or st.ohne_tool_call:
            protokoll.schreiben(
                f"Achtung: {st.fehler} API-Fehler, {st.ohne_tool_call} Antworten ohne Tool-Call."
            )
        if st.letzter_fehler:
            protokoll.schreiben(f"Letzter Fehler: {st.letzter_fehler}")

    pfad = LOGS / f"partie_{datetime.now():%Y%m%d_%H%M%S}.txt"
    protokoll.speichern(pfad)
    print(f"\nProtokoll gespeichert: {pfad}")


if __name__ == "__main__":
    main()

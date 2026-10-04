"""Startet eine Partie Werwolf mit MockAgenten und optional LLM-Spielern."""

import argparse
import random

from core.konfig import konfig_laden
from werwolf.engine import Engine
from werwolf.llm_spieler import LLMSpieler
from werwolf.mock_agent import MockAgent
from werwolf.schnittstelle import Agent, Ereignis

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta"]


def ausgeben(ereignis: Ereignis) -> None:
    # Private Ereignisse (Nachtaktionen, Begründungen) werden markiert.
    praefix = "" if ereignis.oeffentlich else "  [geheim] "
    print(f"[R{ereignis.runde} {ereignis.phase.value:<10}] {praefix}{ereignis.text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Werwolf mit Agenten")
    parser.add_argument("--spieler", type=int, default=7, help="Anzahl Spieler (5–7)")
    parser.add_argument("--seed", type=int, default=None, help="Zufallsstartwert")
    parser.add_argument(
        "--llm", type=int, default=0, help="Wie viele Spieler das LLM steuert (Rest: MockAgent)"
    )
    args = parser.parse_args()

    if not 5 <= args.spieler <= len(NAMEN):
        parser.error(f"--spieler muss zwischen 5 und {len(NAMEN)} liegen")
    if not 0 <= args.llm <= args.spieler:
        parser.error("--llm muss zwischen 0 und --spieler liegen")

    rng = random.Random(args.seed)
    namen = NAMEN[: args.spieler]
    # Die Rollen werden zufällig verteilt, daher ist egal, welche Namen das LLM bekommt.
    try:
        client = konfig_laden().client() if args.llm else None
    except ValueError as fehler:
        parser.error(f"{fehler} (Vorlage: .env.example)")
    agenten: dict[str, Agent] = {}
    for i, name in enumerate(namen):
        if client and i < args.llm:
            agenten[name] = LLMSpieler(client)
        else:
            agenten[name] = MockAgent(random.Random(rng.random()))
    engine = Engine(agenten, rng=rng, beobachter=ausgeben)

    if client:
        print(f"LLM-Spieler: {', '.join(namen[: args.llm])} (Modell: {client.modell})")

    print("Rollen:", ", ".join(f"{s.name}={s.rolle.value}" for s in engine.spieler.values()))
    ergebnis = engine.spielen()
    print(f"\n{ergebnis.gewinner.value} gewinnen nach {ergebnis.runden} Runden.")
    print("Überlebende:", ", ".join(ergebnis.ueberlebende))
    if client:
        st = client.statistik
        print(f"API: {st.aufrufe} Aufrufe, {st.input_tokens} Input- / {st.output_tokens} Output-Tokens")


if __name__ == "__main__":
    main()

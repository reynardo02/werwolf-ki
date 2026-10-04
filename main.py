"""Startet eine Partie Werwolf. In Meilenstein 1 nur mit MockAgenten."""

import argparse
import random

from werwolf.engine import Engine
from werwolf.mock_agent import MockAgent
from werwolf.schnittstelle import Ereignis

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta"]


def ausgeben(ereignis: Ereignis) -> None:
    # Private Ereignisse (Nachtaktionen, Begründungen) werden markiert.
    praefix = "" if ereignis.oeffentlich else "  [geheim] "
    print(f"[R{ereignis.runde} {ereignis.phase.value:<10}] {praefix}{ereignis.text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Werwolf mit Agenten")
    parser.add_argument("--spieler", type=int, default=7, help="Anzahl Spieler (5–7)")
    parser.add_argument("--seed", type=int, default=None, help="Zufallsstartwert")
    args = parser.parse_args()

    if not 5 <= args.spieler <= len(NAMEN):
        parser.error(f"--spieler muss zwischen 5 und {len(NAMEN)} liegen")

    rng = random.Random(args.seed)
    agenten = {name: MockAgent(random.Random(rng.random())) for name in NAMEN[: args.spieler]}
    engine = Engine(agenten, rng=rng, beobachter=ausgeben)

    print("Rollen:", ", ".join(f"{s.name}={s.rolle.value}" for s in engine.spieler.values()))
    ergebnis = engine.spielen()
    print(f"\n{ergebnis.gewinner.value} gewinnen nach {ergebnis.runden} Runden.")
    print("Überlebende:", ", ".join(ergebnis.ueberlebende))


if __name__ == "__main__":
    main()

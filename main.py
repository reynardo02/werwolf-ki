"""Startet eine oder mehrere Partien Werwolf mit MockAgenten und/oder LLM-Spielern."""

import argparse
import random
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from core.konfig import konfig_laden
from core.llm_client import BudgetErschoepft, OpenAIKompatiblerClient, Statistik
from werwolf.engine import Engine
from werwolf.jsonl_log import JsonlLog
from werwolf.llm_spieler import LLMSpieler, persoenlichkeiten_laden
from werwolf.mock_agent import MockAgent
from werwolf.protokoll import Protokoll
from werwolf.schnittstelle import Agent, Ereignis

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta"]
LOGS = Path(__file__).parent / "logs"


def partie_spielen(
    seed: int,
    anzahl_spieler: int,
    anzahl_llm: int,
    client: OpenAIKompatiblerClient | None,
    dateiname: str,
    ausfuehrlich: bool,
    ordner: Path = LOGS,
) -> str:
    """Spielt eine Partie, schreibt Protokoll (.txt) und Log (.jsonl), gibt eine Kurzfassung zurück."""
    rng = random.Random(seed)
    namen = NAMEN[:anzahl_spieler]
    if client:
        # Statistik und Budget gelten pro Partie.
        client.statistik = Statistik()

    # Jeder LLM-Spieler bekommt eine andere, zufällige Persönlichkeit.
    # Die Rollen werden zufällig verteilt, daher ist egal, welche Namen das LLM bekommt.
    persoenlichkeiten = rng.sample(persoenlichkeiten_laden(), anzahl_llm)
    agenten: dict[str, Agent] = {}
    persoenlichkeit_von: dict[str, str | None] = {}
    for i, name in enumerate(namen):
        if client and i < anzahl_llm:
            agenten[name] = LLMSpieler(client, persoenlichkeiten[i])
            persoenlichkeit_von[name] = persoenlichkeiten[i]
        else:
            agenten[name] = MockAgent(random.Random(rng.random()))
            persoenlichkeit_von[name] = None

    protokoll = Protokoll(ausgabe=print if ausfuehrlich else None)
    # Die Engine hat einen Beobachter, wir verteilen an Protokoll und Log.
    beobachter: list[Callable[[Ereignis], None]] = [protokoll]

    def beobachten(ereignis: Ereignis) -> None:
        for b in beobachter:
            b(ereignis)

    engine = Engine(agenten, rng=rng, beobachter=beobachten)
    modell = client.modell if client else None

    log = JsonlLog(
        ordner / f"{dateiname}.jsonl",
        {
            "zeit": datetime.now().isoformat(timespec="seconds"),
            "modell": modell,
            "seed": seed,
            "spieler": [
                {
                    "name": s.name,
                    "rolle": s.rolle.value,
                    "typ": "llm" if persoenlichkeit_von[s.name] else "mock",
                    "persoenlichkeit": persoenlichkeit_von[s.name],
                }
                for s in engine.spieler.values()
            ],
        },
    )
    beobachter.append(log)

    titel = f"Werwolf – {datetime.now():%d.%m.%Y %H:%M} – Seed {seed}"
    if modell:
        titel += f" – Modell: {modell}"
    protokoll.kopf(
        titel,
        [
            f"{s.name}: {s.rolle.value} ({f'LLM, {persoenlichkeit_von[s.name]}' if persoenlichkeit_von[s.name] else 'MockAgent'})"
            for s in engine.spieler.values()
        ],
    )

    try:
        ergebnis = engine.spielen()
        kurz = f"{ergebnis.gewinner.value} gewinnen nach {ergebnis.runden} Runden"
        protokoll.schreiben()
        protokoll.schreiben(f"{kurz}.")
        protokoll.schreiben(f"Überlebende: {', '.join(ergebnis.ueberlebende)}")
        log.eintrag(
            "ergebnis",
            gewinner=ergebnis.gewinner.value,
            runden=ergebnis.runden,
            ueberlebende=ergebnis.ueberlebende,
            api=asdict(client.statistik) if client else None,
        )
    except BudgetErschoepft as fehler:
        kurz = f"abgebrochen: {fehler}"
        protokoll.schreiben()
        protokoll.schreiben(f"Partie abgebrochen: {fehler} (LLM_MAX_AUFRUFE in der .env)")
        log.eintrag("abbruch", grund=str(fehler), api=asdict(client.statistik) if client else None)
    finally:
        log.schliessen()

    if client:
        st = client.statistik
        protokoll.schreiben(
            f"API: {st.aufrufe} Aufrufe, {st.input_tokens} Input- / {st.output_tokens} Output-Tokens"
        )
        if st.fehler or st.ohne_tool_call:
            protokoll.schreiben(
                f"Achtung: {st.fehler} API-Fehler, {st.ohne_tool_call} Antworten ohne Tool-Call."
            )
            kurz += f" ({st.fehler} API-Fehler)"
        if st.gewartet:
            protokoll.schreiben(f"Wegen Tempolimit gewartet: {st.gewartet / 60:.1f} Minuten")
        if st.letzter_fehler:
            protokoll.schreiben(f"Letzter Fehler: {st.letzter_fehler}")

    protokoll.speichern(ordner / f"{dateiname}.txt")
    return kurz


def main() -> None:
    parser = argparse.ArgumentParser(description="Werwolf mit Agenten")
    parser.add_argument("--spieler", type=int, default=7, help="Anzahl Spieler (5–7)")
    parser.add_argument("--seed", type=int, default=None, help="Zufallsstartwert der ersten Partie")
    parser.add_argument(
        "--llm", default="0", help="Wie viele Spieler das LLM steuert, Zahl oder 'alle' (Rest: MockAgent)"
    )
    parser.add_argument("--partien", type=int, default=1, help="Wie viele Partien nacheinander")
    args = parser.parse_args()

    if not 5 <= args.spieler <= len(NAMEN):
        parser.error(f"--spieler muss zwischen 5 und {len(NAMEN)} liegen")
    anzahl_llm = args.spieler if args.llm == "alle" else int(args.llm) if args.llm.isdigit() else -1
    if not 0 <= anzahl_llm <= args.spieler:
        parser.error("--llm muss 'alle' oder eine Zahl zwischen 0 und --spieler sein")
    if args.partien < 1:
        parser.error("--partien muss mindestens 1 sein")

    try:
        client = konfig_laden().client() if anzahl_llm else None
    except ValueError as fehler:
        parser.error(f"{fehler} (Vorlage: .env.example)")

    # Den Seed immer festhalten, damit jede Partie wiederholbar ist.
    start_seed = args.seed if args.seed is not None else random.randrange(1_000_000)
    zeitstempel = f"{datetime.now():%Y%m%d_%H%M%S}"
    ausfuehrlich = args.partien == 1

    for i in range(args.partien):
        seed = start_seed + i
        dateiname = f"partie_{zeitstempel}" + (f"_{i + 1:03d}" if args.partien > 1 else "")
        kurz = partie_spielen(seed, args.spieler, anzahl_llm, client, dateiname, ausfuehrlich)
        if not ausfuehrlich:
            print(f"Partie {i + 1}/{args.partien} (Seed {seed}): {kurz}")

    print(f"\nLogs gespeichert in {LOGS}/partie_{zeitstempel}*")
    if args.partien > 1:
        print(f"Auswerten: python auswerten.py logs/partie_{zeitstempel}_*.jsonl")


if __name__ == "__main__":
    main()

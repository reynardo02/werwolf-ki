"""Startet eine oder mehrere Partien Werwolf mit MockAgenten und/oder LLM-Spielern.

Zwei Spielvarianten:
  klassisch      – viele Runden Nacht/Tag (Meilensteine 1–4)
  vollmondnacht  – „Werwölfe Vollmondnacht“: eine Nacht, ein Tag, eine Abstimmung
"""

import argparse
import random
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from core.konfig import konfig_laden
from core.llm_client import (
    BudgetErschoepft,
    KontingentErschoepft,
    OpenAIKompatiblerClient,
    Statistik,
)
from werwolf.aufbau import (  # noqa: F401 – NAMEN & Co. nutzen auch web/ und die Tests
    KLASSISCH,
    NAMEN,
    SPIELERZAHL,
    VOLLMONDNACHT,
    agenten_bauen,
    engine_bauen,
    ergebnis_zusammenfassen,
    kopf_bauen,
    protokoll_kopf,
)
from werwolf.jsonl_log import JsonlLog
from werwolf.protokoll import Protokoll
from werwolf.schnittstelle import Agent, Ereignis
from werwolf.vollmondnacht.rollen import szenario_namen

LOGS = Path(__file__).parent / "logs"


def partie_spielen(
    seed: int,
    anzahl_spieler: int,
    anzahl_llm: int,
    client: OpenAIKompatiblerClient | None,
    dateiname: str,
    ausfuehrlich: bool,
    ordner: Path = LOGS,
    regeln: str = KLASSISCH,
    szenario: str | None = None,
    mensch: str | None = None,
    mensch_spieler: Agent | None = None,
    beobachter_extra: Callable[[Ereignis], None] | None = None,
    konsole: bool = True,
) -> str:
    """Spielt eine Partie, schreibt Protokoll (.txt) und Log (.jsonl), gibt eine Kurzfassung zurück.

    `mensch`: Name des Platzes, an dem du selbst per Tastatur spielst. Dann zeigt die
    Konsole nur, was öffentlich am Tisch passiert – Rollen und Geheimnisse stehen erst
    hinterher im Protokoll.
    `beobachter_extra` bekommt zusätzlich jedes Ereignis (z. B. für die Web-Oberfläche),
    `konsole=False` schaltet die Ausgabe auf der Konsole ab.
    """
    rng = random.Random(seed)
    namen = NAMEN[:anzahl_spieler]
    if client:
        # Statistik und Budget gelten pro Partie.
        client.statistik = Statistik()
    if regeln == VOLLMONDNACHT and szenario is None:
        szenario = szenario_namen(anzahl_spieler)[0]

    besetzung = agenten_bauen(seed, rng, namen, anzahl_llm, client, regeln, mensch, mensch_spieler)
    agenten, typ_von = besetzung.agenten, besetzung.typ_von

    # Spielst du selbst mit, darf die Konsole nichts Geheimes zeigen.
    protokoll = Protokoll(ausgabe=print if ausfuehrlich and not mensch and konsole else None)
    # Die Engine hat einen Beobachter, wir verteilen an Protokoll und Log.
    beobachter: list[Callable[[Ereignis], None]] = [protokoll]
    if beobachter_extra:
        beobachter.append(beobachter_extra)
    if mensch and konsole:
        tisch = Protokoll(ausgabe=print)
        beobachter.append(lambda e: tisch(e) if e.oeffentlich else None)

    def beobachten(ereignis: Ereignis) -> None:
        for b in beobachter:
            b(ereignis)

    engine, rolle_von = engine_bauen(regeln, agenten, rng, szenario or "", beobachten)
    modell = client.modell if client else None
    kopf = kopf_bauen(regeln, modell, seed, namen, rolle_von, besetzung, engine, szenario)
    log = JsonlLog(ordner / f"{dateiname}.jsonl", kopf)
    beobachter.append(log)

    titel, zeilen = protokoll_kopf(kopf)
    protokoll.kopf(titel, zeilen)
    if mensch and konsole:
        andere = ", ".join(f"{n} ({'LLM' if typ_von[n] == 'llm' else 'MockAgent'})" for n in namen if n != mensch)
        print(f"{titel}\nDu spielst als {mensch}. Am Tisch: {andere}.")

    try:
        kurz, zeilen, daten = ergebnis_zusammenfassen(engine.spielen())
        protokoll.schreiben()
        for zeile in zeilen:
            protokoll.schreiben(zeile)
        log.eintrag("ergebnis", **daten, api=asdict(client.statistik) if client else None)
    except BudgetErschoepft as fehler:
        kurz = f"abgebrochen: {fehler}"
        protokoll.schreiben()
        protokoll.schreiben(f"Partie abgebrochen: {fehler} (LLM_MAX_AUFRUFE in der .env)")
        log.eintrag("abbruch", grund=str(fehler), api=asdict(client.statistik) if client else None)
    except (KontingentErschoepft, KeyboardInterrupt) as fehler:
        # Die ganze Serie muss stoppen. Vorher die Partie als abgebrochen festhalten,
        # damit Protokoll und Log vollständig lesbar bleiben.
        grund = "Mit Strg+C abgebrochen" if isinstance(fehler, KeyboardInterrupt) else (
            "Kontingent des Anbieters erschöpft (z. B. Tageslimit)"
        )
        protokoll.schreiben()
        protokoll.schreiben(f"Partie abgebrochen: {grund}")
        log.eintrag("abbruch", grund=grund, api=asdict(client.statistik) if client else None)
        protokoll.speichern(ordner / f"{dateiname}.txt")
        raise
    finally:
        log.schliessen()

    if client:
        st = client.statistik
        protokoll.schreiben(
            f"API: {st.aufrufe} Aufrufe, {st.input_tokens} Input- / {st.output_tokens} Output-Tokens"
            + (f", davon {st.gecachte_tokens} Input-Tokens aus dem Cache" if st.gecachte_tokens else "")
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
    parser.add_argument("--regeln", choices=[KLASSISCH, VOLLMONDNACHT], default=KLASSISCH)
    parser.add_argument(
        "--szenario", default=None,
        help="Nur Vollmondnacht: Szenario aus der Anleitung (Standard: das erste passende)",
    )
    parser.add_argument(
        "--spieler", type=int, default=7, help="Anzahl Spieler (klassisch 5–7, Vollmondnacht 3–10)"
    )
    parser.add_argument("--seed", type=int, default=None, help="Zufallsstartwert der ersten Partie")
    parser.add_argument(
        "--llm", default="0", help="Wie viele Spieler das LLM steuert, Zahl oder 'alle' (Rest: MockAgent)"
    )
    parser.add_argument("--partien", type=int, default=1, help="Wie viele Partien nacheinander")
    parser.add_argument(
        "--mensch", nargs="?", const=NAMEN[0], default=None, metavar="NAME",
        help=f"Selbst mitspielen per Tastatur, optional mit Platz-Name (Standard: {NAMEN[0]})",
    )
    args = parser.parse_args()

    minimum, maximum = SPIELERZAHL[args.regeln]
    if not minimum <= args.spieler <= maximum:
        parser.error(f"--spieler muss bei '{args.regeln}' zwischen {minimum} und {maximum} liegen")
    if args.szenario is not None:
        if args.regeln != VOLLMONDNACHT:
            parser.error("--szenario gibt es nur mit --regeln vollmondnacht")
        if args.szenario not in szenario_namen(args.spieler):
            parser.error(
                f"Szenario '{args.szenario}' gibt es nicht für {args.spieler} Spieler. "
                f"Möglich: {', '.join(szenario_namen(args.spieler))}"
            )
    if args.mensch is not None and args.mensch not in NAMEN[:args.spieler]:
        parser.error(f"--mensch: Name muss einer von {', '.join(NAMEN[:args.spieler])} sein")
    # Mit dir am Tisch bleibt ein Platz weniger für das LLM.
    plaetze = args.spieler - (args.mensch is not None)
    anzahl_llm = plaetze if args.llm == "alle" else int(args.llm) if args.llm.isdigit() else -1
    if not 0 <= anzahl_llm <= plaetze:
        parser.error(f"--llm muss 'alle' oder eine Zahl zwischen 0 und {plaetze} sein")
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
        try:
            kurz = partie_spielen(
                seed, args.spieler, anzahl_llm, client, dateiname, ausfuehrlich,
                regeln=args.regeln, szenario=args.szenario, mensch=args.mensch,
            )
        except (KontingentErschoepft, KeyboardInterrupt) as fehler:
            if isinstance(fehler, KontingentErschoepft):
                print(f"\nPartie {i + 1} abgebrochen: Der Anbieter sperrt für lange Zeit.")
                print(f"Meldung: {str(fehler)[:300]}")
            else:
                print(f"\nPartie {i + 1} mit Strg+C abgebrochen.")
            print("Später weitermachen (gleiche Seeds, abgebrochene Partie wird wiederholt):")
            szenario = f' --szenario "{args.szenario}"' if args.szenario else ""
            print(
                f"  python main.py --regeln {args.regeln}{szenario} --llm {args.llm} "
                f"--spieler {args.spieler} --partien {args.partien - i} --seed {seed}"
            )
            break
        if args.mensch:
            print(f"\nErgebnis: {kurz}. Alle Geheimnisse stehen im Protokoll: logs/{dateiname}.txt")
        elif not ausfuehrlich:
            print(f"Partie {i + 1}/{args.partien} (Seed {seed}): {kurz}")

    print(f"\nLogs gespeichert in {LOGS}/partie_{zeitstempel}*")
    if args.partien > 1:
        print(f"Auswerten: python auswerten.py logs/partie_{zeitstempel}_*.jsonl")


if __name__ == "__main__":
    main()

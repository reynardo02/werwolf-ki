"""Wertet die JSONL-Logs vieler Partien aus.

Beispiele:
  python auswerten.py                         # alle Logs in logs/
  python auswerten.py "logs/partie_20261005_*.jsonl"
"""

import argparse
import glob
from pathlib import Path

from werwolf.auswertung import auswerten, bericht, partie_aus_log
from werwolf.jsonl_log import log_lesen


def main() -> None:
    parser = argparse.ArgumentParser(description="Statistik über Werwolf-Partien")
    parser.add_argument(
        "muster", nargs="*", default=["logs/*.jsonl"], help="Log-Dateien oder Muster (Standard: logs/*.jsonl)"
    )
    args = parser.parse_args()

    # Die Muster selbst auflösen: Die Windows-PowerShell macht das nicht.
    dateien = sorted({Path(p) for m in args.muster for p in glob.glob(m)})
    if not dateien:
        parser.error(f"Keine Logs gefunden für: {' '.join(args.muster)}")

    partien = []
    for datei in dateien:
        try:
            partien.append(partie_aus_log(log_lesen(datei)))
        except (ValueError, KeyError) as fehler:
            print(f"Übersprungen: {datei} ({fehler})")

    gesamt = auswerten(partien)
    print(bericht(gesamt, f"Gesamt über {len(partien)} Partien"))
    # Nur aufschlüsseln, wenn es mehrere Gruppen gibt (z. B. Mock vs. LLM).
    if len(gesamt.gruppen) > 1:
        for name, gruppe in sorted(gesamt.gruppen.items()):
            print()
            print(bericht(gruppe, name))


if __name__ == "__main__":
    main()

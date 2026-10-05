"""Wertet die JSONL-Logs vieler Partien aus – getrennt nach Spielvariante.

Beispiele:
  python auswerten.py                         # alle Logs in logs/
  python auswerten.py "logs/partie_20261005_*.jsonl"
  python auswerten.py --mensch                # nur deine eigenen Partien (--mensch beim Spielen)
"""

import argparse
import glob
from pathlib import Path

from werwolf import auswertung as klassisch
from werwolf.jsonl_log import log_lesen
from werwolf.vollmondnacht import auswertung as vollmond


def main() -> None:
    parser = argparse.ArgumentParser(description="Statistik über Werwolf-Partien")
    parser.add_argument(
        "muster", nargs="*", default=["logs/*.jsonl"], help="Log-Dateien oder Muster (Standard: logs/*.jsonl)"
    )
    parser.add_argument(
        "--mensch", action="store_true", help="Nur Vollmondnacht-Partien, in denen du selbst mitgespielt hast"
    )
    args = parser.parse_args()

    # Die Muster selbst auflösen: Die Windows-PowerShell macht das nicht.
    dateien = sorted({Path(p) for m in args.muster for p in glob.glob(m)})
    if not dateien:
        parser.error(f"Keine Logs gefunden für: {' '.join(args.muster)}")

    klassische, vollmondnaechte = [], []
    for datei in dateien:
        zeilen = log_lesen(datei)
        try:
            # Alte Logs haben noch kein Feld "regeln": Die sind klassisch.
            if zeilen and zeilen[0].get("regeln") == "vollmondnacht":
                vollmondnaechte.append(vollmond.partie_aus_log(zeilen))
            else:
                klassische.append(klassisch.partie_aus_log(zeilen))
        except (ValueError, KeyError, IndexError) as fehler:
            print(f"Übersprungen: {datei} ({fehler})")

    if args.mensch:
        print(vollmond.mensch_bericht(vollmondnaechte))
        return

    if klassische:
        gesamt = klassisch.auswerten(klassische)
        print(klassisch.bericht(gesamt, f"Klassisch: {len(klassische)} Partien"))
        if len(gesamt.gruppen) > 1:
            for name, gruppe in sorted(gesamt.gruppen.items()):
                print()
                print(klassisch.bericht(gruppe, name))
    if vollmondnaechte:
        if klassische:
            print("\n")
        gesamt_v = vollmond.auswerten(vollmondnaechte)
        print(vollmond.bericht(gesamt_v, f"Vollmondnacht: {len(vollmondnaechte)} Partien"))
        if len(gesamt_v.gruppen) > 1:
            for name, gruppe in sorted(gesamt_v.gruppen.items()):
                print()
                print(vollmond.bericht(gruppe, name))
        if any(p.mensch for p in vollmondnaechte):
            print("\n" + vollmond.mensch_bericht(vollmondnaechte))


if __name__ == "__main__":
    main()

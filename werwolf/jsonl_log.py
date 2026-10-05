"""Maschinenlesbares Spiel-Log im Format JSON Lines: eine JSON-Zeile pro Eintrag.

Aufbau einer Datei:
  1. Zeile  {"art": "partie", ...}    Spieler, Rollen, Modell, Seed
  dann      {"art": "stimme", ...}    ein Eintrag pro Ereignis
  letzte    {"art": "ergebnis", ...}  Gewinner, Runden, API-Statistik

Jede Zeile wird sofort geschrieben, damit bei einem Abbruch nichts verloren geht.
"""

import json
from pathlib import Path
from typing import Any

from werwolf.schnittstelle import Ereignis


def ereignis_als_dict(ereignis: Ereignis) -> dict[str, Any]:
    return {
        "art": ereignis.art,
        "runde": ereignis.runde,
        "phase": ereignis.phase.value,
        "oeffentlich": ereignis.oeffentlich,
        "text": ereignis.text,
        "daten": ereignis.daten,
    }


class JsonlLog:
    """Als `beobachter` an die Engine übergeben, schreibt jedes Ereignis mit."""

    def __init__(self, pfad: Path, kopf: dict[str, Any]) -> None:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad = pfad
        self._datei = pfad.open("w", encoding="utf-8")
        self.eintrag("partie", **kopf)

    def __call__(self, ereignis: Ereignis) -> None:
        self._schreiben(ereignis_als_dict(ereignis))

    def eintrag(self, art: str, **werte: Any) -> None:
        self._schreiben({"art": art, **werte})

    def schliessen(self) -> None:
        self._datei.close()

    def _schreiben(self, zeile: dict[str, Any]) -> None:
        # ensure_ascii=False: Umlaute bleiben lesbar statt ü.
        self._datei.write(json.dumps(zeile, ensure_ascii=False) + "\n")
        self._datei.flush()


def log_lesen(pfad: Path) -> list[dict[str, Any]]:
    """Liest eine JSONL-Datei. Kaputte Zeilen (z. B. nach Absturz) werden übersprungen."""
    zeilen = []
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        try:
            zeilen.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue
    return zeilen

import random

from werwolf.engine import Engine
from werwolf.jsonl_log import JsonlLog, log_lesen
from werwolf.mock_agent import MockAgent

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil"]


def test_log_enthaelt_kopf_ereignisse_und_ergebnis(tmp_path) -> None:
    pfad = tmp_path / "partie.jsonl"
    log = JsonlLog(pfad, {"seed": 3, "modell": None})
    engine = Engine({n: MockAgent(random.Random(i)) for i, n in enumerate(NAMEN)},
                    rng=random.Random(3), beobachter=log)
    ergebnis = engine.spielen()
    log.eintrag("ergebnis", gewinner=ergebnis.gewinner.value)
    log.schliessen()

    zeilen = log_lesen(pfad)
    assert zeilen[0] == {"art": "partie", "seed": 3, "modell": None}
    assert zeilen[-1] == {"art": "ergebnis", "gewinner": ergebnis.gewinner.value}
    # Jedes Ereignis der Engine steht genau einmal im Log.
    assert len(zeilen) == len(engine.protokoll) + 2
    stimme = next(z for z in zeilen if z["art"] == "stimme")
    assert set(stimme) == {"art", "runde", "phase", "oeffentlich", "text", "daten"}
    assert set(stimme["daten"]) == {"von", "ziel"}


def test_kaputte_zeile_wird_uebersprungen(tmp_path) -> None:
    pfad = tmp_path / "kaputt.jsonl"
    pfad.write_text('{"art": "partie"}\n{"art": "sti', encoding="utf-8")
    assert log_lesen(pfad) == [{"art": "partie"}]


def test_umlaute_bleiben_lesbar(tmp_path) -> None:
    pfad = tmp_path / "u.jsonl"
    log = JsonlLog(pfad, {"gewinner": "Werwölfe"})
    log.schliessen()
    assert "Werwölfe" in pfad.read_text(encoding="utf-8")

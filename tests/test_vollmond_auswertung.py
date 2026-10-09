from pathlib import Path

import pytest

from main import VOLLMONDNACHT, partie_spielen
from werwolf.jsonl_log import log_lesen
from werwolf.vollmondnacht.auswertung import VollmondPartie, auswerten, bericht, partie_aus_log


def test_zwanzig_vollmondnaechte_auswerten(tmp_path: Path) -> None:
    for i in range(20):
        partie_spielen(i, 8, 0, None, f"v_{i:03d}", ausfuehrlich=False, ordner=tmp_path,
                       regeln=VOLLMONDNACHT, szenario="Wiedergänger")
    partien = [partie_aus_log(log_lesen(p)) for p in sorted(tmp_path.glob("*.jsonl"))]
    a = auswerten(partien)

    assert a.partien == 20 and a.abgebrochen == 0
    # Jede Partie hat mindestens eine Gewinnerpartei oder „niemand gewinnt“.
    assert sum(a.siege.values()) + a.niemand_gewinnt >= 20
    assert a.dorf_stimmen > 0
    assert set(a.gruppen) == {"Wiedergänger, nur MockAgenten"}
    assert "Sieg Werwolfsrudel" in bericht(a, "Test")


def test_klassisches_log_wird_abgelehnt(tmp_path: Path) -> None:
    partie_spielen(1, 5, 0, None, "k", ausfuehrlich=False, ordner=tmp_path)
    with pytest.raises(ValueError):
        partie_aus_log(log_lesen(tmp_path / "k.jsonl"))


def test_stimmen_gegen_start_und_end_werwoelfe() -> None:
    # Ben startet als Werwolf, Clara raubt ihn und ist am Ende Werwolf.
    p = VollmondPartie(
        gruppe="Test",
        startrollen={"Anna": "Dorfbewohner", "Ben": "Werwolf", "Clara": "Räuber"},
        endrollen={"Anna": "Dorfbewohner", "Ben": "Räuber", "Clara": "Werwolf"},
        gewinner=["Werwolfsrudel"], tote=["Ben"],
        stimmen={"Anna": "Ben", "Ben": "Clara", "Clara": "Ben"},
        zufallsaktionen=0, api=None,
    )
    a = auswerten([p])
    # Nur Anna und Ben sind am Ende im Dorf; Clara (Werwolf) zählt nicht mit.
    assert a.dorf_stimmen == 2
    assert a.dorf_stimmen_startwerwolf == 1  # Anna -> Ben
    assert a.dorf_stimmen_werwolf == 1  # Ben -> Clara
    assert "Stimmen gegen Start-Werwölfe:" in bericht(a, "Test")


def test_cache_anteil_im_bericht() -> None:
    def partie(api: dict | None) -> VollmondPartie:
        return VollmondPartie("Test", {"Anna": "Werwolf"}, {"Anna": "Werwolf"}, [], [], {}, 0, api)

    # Ältere Logs ohne gecachte_tokens zählen als 0.
    a = auswerten([partie({"aufrufe": 10, "input_tokens": 1000}), partie(None),
                   partie({"aufrufe": 10, "input_tokens": 3000, "gecachte_tokens": 1000})])
    assert "Input-Tokens aus dem Cache:" in bericht(a, "Test") and "25%" in bericht(a, "Test")
    assert "aus dem Cache" not in bericht(auswerten([partie(None)]), "Test")


def test_denk_anteil_im_bericht() -> None:
    def partie(api: dict) -> VollmondPartie:
        return VollmondPartie("Test", {"Anna": "Werwolf"}, {"Anna": "Werwolf"}, [], [], {}, 0, api)

    # Ältere Logs ohne denk_tokens zählen als 0.
    a = auswerten([partie({"aufrufe": 10, "input_tokens": 2000, "output_tokens": 400}),
                   partie({"aufrufe": 10, "input_tokens": 4000, "output_tokens": 1600, "denk_tokens": 1000})])
    text = bericht(a, "Test")
    assert "Input-Tokens pro Partie:" in text and "3.000" in text
    assert "Output-Tokens pro Partie:" in text and "1.000" in text
    assert "Output-Tokens zum Nachdenken:" in text and "50%" in text


def test_mensch_bericht() -> None:
    from werwolf.vollmondnacht.auswertung import mensch_bericht

    def partie(start: str, ende: str, stimme: str, sieger: list[str]) -> VollmondPartie:
        return VollmondPartie(
            gruppe="Test", startrollen={"Anna": start, "Ben": "Werwolf", "Clara": "Dorfbewohner"},
            endrollen={"Anna": ende, "Ben": "Werwolf", "Clara": "Dorfbewohner"},
            gewinner=["x"], tote=["Ben"], stimmen={"Anna": stimme, "Ben": "Anna", "Clara": "Ben"},
            zufallsaktionen=0, api=None, sieger=sieger, mensch="Anna", seed=1,
        )

    partien = [
        partie("Dorfbewohner", "Dorfbewohner", "Ben", ["Anna", "Clara"]),
        partie("Räuber", "Werwolf", "Clara", []),  # Karte getauscht: zählt als Werwolfsrudel
        VollmondPartie("Test", {}, {}, ["x"], [], {}, 0, None),  # ohne Mensch: wird ignoriert
        # Kein Werwolf am Tisch: zählt als Partie, aber nicht bei „Stimme traf Werwolf“.
        VollmondPartie("Test", {"Anna": "Dorfbewohner", "Ben": "Seherin"}, {"Anna": "Dorfbewohner", "Ben": "Seherin"},
                       [], ["Anna"], {"Anna": "Ben", "Ben": "Anna"}, 0, None, sieger=[], mensch="Anna"),
    ]
    text = mensch_bericht(partien)
    assert "Partien:" in text and "33.3%" in text
    assert "als Dorfgemeinschaft:" in text and "1 von 2 gewonnen" in text
    assert "als Werwolfsrudel:" in text and "0 von 1 gewonnen" in text
    assert "1 von 1 (im Dorf" in text  # nur die Stimme als Dorf mit Werwolf am Tisch zählt
    assert "Räuber → Werwolf" in text

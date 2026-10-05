from pathlib import Path

import pytest

from main import VOLLMONDNACHT, partie_spielen
from werwolf.jsonl_log import log_lesen
from werwolf.vollmondnacht.auswertung import auswerten, bericht, partie_aus_log


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

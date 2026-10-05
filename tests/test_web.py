import time
from pathlib import Path

import pytest

from web.sitzung import Sitzung


def antwort(frage: dict) -> tuple[str, dict[str, str]]:
    """Wählt wie ein ungeduldiger Mensch: erstes Tool, erste freie Werte, kurzer Text."""
    tool = frage["tools"][0]
    parameter: dict[str, str] = {}
    for name, werte in tool["parameter"].items():
        parameter[name] = next(w for w in werte if w not in parameter.values())
    if tool["text"]:
        parameter["text"] = "Ich bin harmlos."
    return tool["name"], parameter


def durchspielen(sitzung: Sitzung, frist: float = 10.0) -> dict:
    sitzung.starten()
    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        zustand = sitzung.zustand()
        if zustand["ende"] or zustand["fehler"]:
            return zustand
        if zustand["frage"]:
            assert sitzung.antworten(*antwort(zustand["frage"]))
        time.sleep(0.01)
    pytest.fail("Partie wurde nicht fertig")


@pytest.mark.parametrize("regeln", ["vollmondnacht", "klassisch"])
def test_partie_im_browser_durchspielen(regeln: str, tmp_path: Path) -> None:
    sitzung = Sitzung(regeln=regeln, spieler=5, llm="0", ich="Ben", ordner=tmp_path, seed=3)
    zustand = durchspielen(sitzung)
    assert zustand["fehler"] is None and zustand["ende"]
    texte = [e["text"] for e in zustand["ereignisse"]]
    assert any("Spielende" in t for t in texte)
    assert (tmp_path / f"{sitzung.dateiname}.jsonl").exists()


def test_browser_sieht_keine_geheimnisse(tmp_path: Path) -> None:
    sitzung = Sitzung(regeln="vollmondnacht", spieler=5, llm="0", ich="Anna", ordner=tmp_path, seed=8)
    zustand = durchspielen(sitzung)
    arten = {e["art"] for e in zustand["ereignisse"]}
    assert "nacht_aktion" not in arten and "begruendung" not in arten
    # Im vollständigen Protokoll stehen sie aber.
    assert "[geheim]" in (tmp_path / f"{sitzung.dateiname}.txt").read_text(encoding="utf-8")


def test_doppelklick_wird_ignoriert(tmp_path: Path) -> None:
    sitzung = Sitzung(regeln="vollmondnacht", spieler=5, llm="0", ich="Anna", ordner=tmp_path, seed=1)
    sitzung.starten()
    while not sitzung.zustand()["frage"]:
        time.sleep(0.01)
    tool, parameter = antwort(sitzung.zustand()["frage"])
    assert sitzung.antworten(tool, parameter)
    assert not sitzung.antworten(tool, parameter)  # zweite Antwort auf dieselbe Frage
    sitzung.beenden()


def test_abbrechen_beendet_wartende_partie(tmp_path: Path) -> None:
    sitzung = Sitzung(regeln="vollmondnacht", spieler=5, llm="0", ich="Anna", ordner=tmp_path, seed=1)
    sitzung.starten()
    while not sitzung.zustand()["frage"]:
        time.sleep(0.01)
    sitzung.beenden()
    for _ in range(200):
        if sitzung.zustand()["ende"]:
            break
        time.sleep(0.01)
    assert sitzung.zustand()["ende"] == "abgebrochen"

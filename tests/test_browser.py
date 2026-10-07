"""Die Browser-Version (web/browser.py) – hier in normalem Python mit simuliertem LLM."""

import json
import subprocess
import sys

import pytest

from web.browser import antwort_aus_json, schritt, schritt_json
from werwolf.vollmondnacht.auswertung import partie_aus_log


def llm_antwort(anfrage: dict) -> dict:
    """Simuliert /chat/completions: erstes Tool, erste erlaubte Werte, kurzer Text."""
    funktion = anfrage["tools"][0]["function"]
    argumente = {}
    for name, schema in funktion["parameters"]["properties"].items():
        if "enum" in schema:
            argumente[name] = next(w for w in schema["enum"] if w not in argumente.values())
        else:
            argumente[name] = "Ich bin harmlos."
    return {"choices": [{"message": {"content": None, "tool_calls": [
        {"type": "function", "function": {"name": funktion["name"], "arguments": json.dumps(argumente)}},
    ]}}]}


def mensch_antwort(frage: dict) -> dict:
    tool = frage["tools"][0]
    parameter: dict[str, str] = {}
    for name, werte in tool["parameter"].items():
        parameter[name] = next(w for w in werte if w not in parameter.values())
    if tool["text"]:
        parameter["text"] = "Ich war es nicht."
    return {"tool": tool["name"], "parameter": parameter}


def durchspielen(einstellungen: dict, seed: int = 5) -> tuple[dict, list, list, int]:
    mensch, llm, aufrufe = [], [], 0
    for _ in range(500):
        aufrufe += 1
        z = schritt(einstellungen, seed, mensch, llm, modell="test-modell")
        if z["ende"]:
            return z, mensch, llm, aufrufe
        if z["llm_anfrage"]:
            llm.append(llm_antwort(z["llm_anfrage"]))
        else:
            mensch.append(mensch_antwort(z["frage"]))
    pytest.fail("Partie wurde nicht fertig")


@pytest.mark.parametrize("regeln, spieler", [("vollmondnacht", 7), ("klassisch", 5)])
def test_partie_mit_llm_durch_wiederholen(regeln: str, spieler: int) -> None:
    einstellungen = {"regeln": regeln, "spieler": spieler, "llm": "alle", "ich": "Clara"}
    z, mensch, llm, aufrufe = durchspielen(einstellungen)
    assert mensch and llm and aufrufe == len(mensch) + len(llm) + 1
    assert z["gewonnen"] in (True, False)
    assert "[geheim]" in z["protokoll"]
    assert all(e["art"] not in ("nacht_aktion", "begruendung", "notiz") for e in z["ereignisse"])
    # Wiederholen ist deterministisch: gleiche Antworten, gleicher Verlauf.
    assert schritt(einstellungen, 5, mensch, llm, modell="test-modell") == z


def test_log_zum_herunterladen_ist_auswertbar() -> None:
    einstellungen = {"regeln": "vollmondnacht", "spieler": 5, "llm": "2", "ich": "Ben"}
    z, *_ = durchspielen(einstellungen)
    zeilen = [json.loads(zeile) for zeile in z["log"].splitlines()]
    kopf = zeilen[0]
    assert kopf["modell"] == "test-modell"
    # LLM-Plätze werden der Reihe nach vergeben, dein Platz wird übersprungen.
    assert [s["typ"] for s in kopf["spieler"]] == ["llm", "mensch", "llm", "mock", "mock"]
    partie = partie_aus_log(zeilen)
    assert partie.mensch == "Ben" and partie.gewinner is not None


def test_frage_traegt_laufende_nummer() -> None:
    einstellungen = {"regeln": "vollmondnacht", "spieler": 5, "llm": "0", "ich": "Anna"}
    erste = schritt(einstellungen, 1, [], [])
    assert erste["frage"]["nummer"] == 1 and erste["llm_anfrage"] is None
    zweite = schritt(einstellungen, 1, [mensch_antwort(erste["frage"])], [])
    assert zweite["frage"]["nummer"] == 2


def test_falsche_einstellungen_als_json_fehler() -> None:
    antwort = json.loads(schritt_json(json.dumps({"einstellungen": {"regeln": "schach"}, "seed": 1})))
    assert "Unbekannte Regeln" in antwort["fehler"]


@pytest.mark.parametrize("roh", [
    {}, {"choices": []}, {"choices": [{"message": {"content": "nur Text"}}]},
    {"choices": [{"message": {"tool_calls": [{"function": {"name": "x", "arguments": "kaputt"}}]}}]},
])
def test_kaputte_llm_antworten_sind_kein_tool_call(roh: dict) -> None:
    assert antwort_aus_json(roh).tool_call is None


def test_laeuft_ohne_openai_sdk() -> None:
    """Im Browser gibt es kein openai-Paket – der Platzhalter muss reichen."""
    code = (
        "import sys; sys.modules['openai'] = None\n"  # None: jeder Import schlägt fehl
        "import json, web.browser as b\n"
        "z = json.loads(b.schritt_json(json.dumps({'einstellungen': {'regeln': 'vollmondnacht', "
        "'spieler': 5, 'llm': 'alle', 'ich': 'Anna'}, 'seed': 1})))\n"
        "assert z['llm_anfrage'] or z['frage'], z\n"
        "print('ok')\n"
    )
    ergebnis = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert ergebnis.stdout.strip() == "ok", ergebnis.stderr


def test_seite_bauen(tmp_path) -> None:
    import zipfile

    from web.seite_bauen import PYODIDE_DATEIEN, bauen

    pyodide = tmp_path / "pyodide-paket"
    pyodide.mkdir()
    for datei in PYODIDE_DATEIEN:
        (pyodide / datei).write_text("platzhalter")
    ziel = tmp_path / "site"
    bauen(ziel, pyodide)

    seite = (ziel / "index.html").read_text(encoding="utf-8")
    assert '<meta name="werwolf-modus" content="browser">' in seite
    assert (ziel / "pyodide-backend.js").exists() and (ziel / ".nojekyll").exists()
    assert (ziel / "karten" / "rueckseite.jpg").exists() and (ziel / "karten" / "werwolf.jpg").exists()
    assert all((ziel / "pyodide" / d).exists() for d in PYODIDE_DATEIEN)
    namen = zipfile.ZipFile(ziel / "werwolf-ki.zip").namelist()
    assert "web/browser.py" in namen and "werwolf/prompts/persoenlichkeiten.txt" in namen
    assert "werwolf/vollmondnacht/prompts/system.txt" in namen
    assert not any("__pycache__" in n or n.startswith("tests/") or "static/" in n for n in namen)


@pytest.mark.parametrize("regeln, titel", [("vollmondnacht", "Deine Karte zu Beginn"), ("klassisch", "Deine Rolle")])
def test_deine_karte_steht_von_anfang_an_fest(regeln: str, titel: str) -> None:
    # Auch wenn zuerst andere dran sind (LLM-Anfrage offen), kennt der Browser schon deine Karte.
    einstellungen = {"regeln": regeln, "spieler": 5, "llm": "alle", "ich": "Emil"}
    z = schritt(einstellungen, 4, [], [], modell="test-modell")
    assert z["llm_anfrage"] is not None and z["frage"] is None
    assert z["karte"] and z["karte_titel"] == titel

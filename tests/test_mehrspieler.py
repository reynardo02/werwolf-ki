"""Mitspieler per Link (web/static/mehrspieler.js): Was ein Gast bekommt und was der Gastgeber annimmt.

Die Logik ist JavaScript; geprüft wird sie mit Node, falls installiert (auf GitHub Actions ist es das).
Das Zusammenspiel zweier Browser prüft ein Playwright-Lauf von Hand (siehe CLAUDE.md).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MEHRSPIELER = Path(__file__).parent.parent / "web" / "static" / "mehrspieler.js"
node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="Node.js nicht installiert")


def js(ausdruck: str) -> object:
    """Wertet einen Ausdruck mit den Funktionen aus mehrspieler.js aus und gibt das Ergebnis zurück."""
    skript = (
        f"const m = await import({json.dumps(MEHRSPIELER.as_uri())});\n"
        f"console.log(JSON.stringify({ausdruck}));"
    )
    ergebnis = subprocess.run(
        [node, "--input-type=module", "-e", skript], capture_output=True, text=True, timeout=30, check=True
    )
    return json.loads(ergebnis.stdout)


STAND = {
    "seed": 7, "menschen": ["Anna", "Ben"], "ereignisse": [], "anzahl": 0,
    "frage": {"wer": "Anna", "nummer": 3, "rolle": "Seherin", "geheimwissen": ["Anna-Geheimnis"]},
    "karten": {"Anna": "Seherin", "Ben": "Werwolf"}, "karte_titel": "Deine Karte zu Beginn",
    "geheimwissen": {"Anna": ["Anna-Geheimnis"], "Ben": ["Die Werwölfe sind: Ben, Emil."]},
    "jetzt_karten": {"Ben": "Werwolf"}, "ende": None, "gewonnen": {}, "fehler": None, "status": "",
}


def test_gast_bekommt_nur_seine_geheimnisse() -> None:
    ereignisse = [{"phase": "Nacht", "art": "runde", "text": "Es wird Nacht."}]
    gast = js(f"m.fuerGast({json.dumps(STAND)}, {json.dumps(ereignisse)}, 'Ben')")
    assert gast["menschen"] == ["Ben"]
    assert gast["karten"] == {"Ben": "Werwolf"} and gast["geheimwissen"] == {"Ben": ["Die Werwölfe sind: Ben, Emil."]}
    assert gast["frage"] is None  # Anna ist dran, nicht Ben
    assert gast["status"] == "Anna ist dran …"
    assert "Anna-Geheimnis" not in json.dumps(gast) and "Seherin" not in json.dumps(gast)
    assert gast["ereignisse"] == ereignisse  # Öffentliches bekommt jeder


def test_gast_bekommt_seine_frage() -> None:
    gast = js(f"m.fuerGast({json.dumps(STAND)}, [], 'Anna')")
    assert gast["frage"]["nummer"] == 3 and gast["karten"] == {"Anna": "Seherin"}
    assert "Werwolf" not in json.dumps(gast)


def test_gastgeber_nimmt_nur_einfache_parameter_an() -> None:
    assert js("m.sauber({ziel: 'Ben', text: 'Hallo'})") == {"ziel": "Ben", "text": "Hallo"}
    # Kaputtes würde die gespeicherte Partie unspielbar machen: wird verworfen.
    assert js("m.sauber(['Ben'])") == {} and js("m.sauber('Ben')") == {} and js("m.sauber(null)") == {}
    assert js("m.sauber({ziel: {x: 1}, 'a b': 'x', ok: 'ja'})") == {"ok": "ja"}
    assert len(js("m.sauber({text: 'x'.repeat(5000)})")["text"]) == 2000

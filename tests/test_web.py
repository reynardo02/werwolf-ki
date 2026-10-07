import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from web.server import WerwolfServer
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
    assert zustand["gewonnen"] in (True, False)
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


# --- Server über echtes HTTP ---------------------------------------------------


@pytest.fixture
def server(tmp_path: Path):
    s = WerwolfServer(("127.0.0.1", 0), ordner=tmp_path)  # Port 0: das System wählt einen freien
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()
    if s.sitzung:
        s.sitzung.beenden()
    s.server_close()


def anfrage(url: str, daten: dict | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, data=json.dumps(daten).encode() if daten is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=5) as antwort:
            inhalt = antwort.read().decode()
            status = antwort.status
    except urllib.error.HTTPError as fehler:
        inhalt, status = fehler.read().decode(), fehler.code
    try:
        return status, json.loads(inhalt)
    except json.JSONDecodeError:
        return status, inhalt


def test_server_startseite_und_optionen(server: str) -> None:
    status, seite = anfrage(server + "/")
    assert status == 200 and "<title>Werwolf-KI</title>" in seite
    status, optionen = anfrage(server + "/api/optionen?spieler=5")
    assert optionen["namen"] == ["Anna", "Ben", "Clara", "Dario", "Emil"] and optionen["szenarien"]
    assert anfrage(server + "/api/zustand")[1] == {"laeuft": False}
    assert anfrage(server + "/gibtsnicht")[0] == 404


def test_server_liefert_kartenbilder(server: str) -> None:
    with urllib.request.urlopen(server + "/karten/rueckseite.jpg", timeout=5) as antwort:
        assert antwort.status == 200 and antwort.headers["Content-Type"] == "image/jpeg"
        assert antwort.read(3) == b"\xff\xd8\xff"  # JPEG-Anfang
    # Fehlende Bilder und Pfade außerhalb von karten/ gibt es nicht.
    assert anfrage(server + "/karten/gibtsnicht.jpg")[0] == 404
    assert anfrage(server + "/karten/..%2Fserver.py")[0] == 404


@pytest.mark.parametrize("falsch", [
    {"regeln": "schach"},
    {"regeln": "klassisch", "spieler": 9},
    {"regeln": "vollmondnacht", "spieler": 5, "llm": "5"},
    {"regeln": "vollmondnacht", "spieler": 5, "ich": "Greta"},
    {"regeln": "klassisch", "spieler": 5, "szenario": "Payback"},
])
def test_server_lehnt_falsche_einstellungen_ab(server: str, falsch: dict) -> None:
    status, antwort = anfrage(server + "/api/neu", falsch)
    assert status == 400 and antwort["fehler"]


def test_server_partie_durchspielen(server: str) -> None:
    assert anfrage(server + "/api/aktion", {"tool": "sprechen"})[0] == 400  # keine Partie
    status, _ = anfrage(server + "/api/neu", {"regeln": "vollmondnacht", "spieler": 5, "llm": "0", "ich": "Clara"})
    assert status == 200
    ende = time.monotonic() + 10
    while time.monotonic() < ende:
        _, z = anfrage(server + "/api/zustand?seit=0")
        if z["ende"]:
            break
        if z["frage"]:
            tool, parameter = antwort(z["frage"])
            anfrage(server + "/api/aktion", {"tool": tool, "parameter": parameter})
        time.sleep(0.02)
    assert z["ende"] and z["ich"] == "Clara" and not z["fehler"]
    assert anfrage(server + "/api/aktion", {"tool": "sprechen"})[0] == 409  # niemand gefragt


def test_jede_frage_hat_eine_neue_nummer(tmp_path: Path) -> None:
    # Klassisch mit 5 Spielern: Du sprichst mehrmals hintereinander – gleiche Frage, neue Nummer.
    sitzung = Sitzung(regeln="klassisch", spieler=5, llm="0", ich="Anna", ordner=tmp_path, seed=2)
    sitzung.starten()
    nummern = []
    ende = time.monotonic() + 10
    while time.monotonic() < ende and not sitzung.zustand()["ende"]:
        frage = sitzung.zustand()["frage"]
        if frage:
            nummern.append(frage["nummer"])
            sitzung.antworten(*antwort(frage))
        time.sleep(0.01)
    assert len(nummern) >= 2 and nummern == sorted(set(nummern))


def test_jede_rolle_hat_ein_kartenbild() -> None:
    # Gleiche Regel wie kartenDatei() in index.html: klein, Umlaute ausgeschrieben, nur a–z.
    from werwolf.roles import Rolle as KlassischeRolle
    from werwolf.vollmondnacht.rollen import Rolle as VollmondRolle

    karten = Path(__file__).parent.parent / "web" / "static" / "karten"
    umlaute = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
    for rolle in [*VollmondRolle, *KlassischeRolle]:
        name = "".join(z for z in rolle.value.lower().translate(umlaute) if "a" <= z <= "z")
        assert (karten / f"{name}.jpg").is_file(), rolle.value
    assert (karten / "rueckseite.jpg").is_file()


def test_karte_steht_vor_dem_ersten_zug_fest(tmp_path: Path) -> None:
    sitzung = Sitzung(regeln="vollmondnacht", spieler=5, llm="0", ich="Clara", ordner=tmp_path, seed=6)
    sitzung.starten()
    while not sitzung.zustand()["frage"]:
        time.sleep(0.01)
    zustand = sitzung.zustand()
    assert zustand["karte"] == zustand["frage"]["rolle"]
    assert zustand["karte_titel"] == "Deine Karte zu Beginn"
    sitzung.beenden()

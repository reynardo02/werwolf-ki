import random

from werwolf.engine import Engine
from werwolf.mensch_spieler import MenschSpieler
from werwolf.mock_agent import MockAgent
from werwolf.schnittstelle import ABSTIMMEN, SPRECHEN, Phase, Zug
from werwolf.vollmondnacht.engine import NICHTS_TUN, VERTAUSCHEN, VollmondEngine
from werwolf.vollmondnacht.rollen import Rolle

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil"]


class Tastatur:
    """Simuliert Eingaben: Auswahlfragen bekommen der Reihe nach `wahlen`, Texte einen Satz."""

    def __init__(self, wahlen: list[str] | None = None) -> None:
        self.wahlen = list(wahlen or [])
        self.fragen: list[str] = []

    def __call__(self, frage: str) -> str:
        self.fragen.append(frage)
        if frage.startswith("Deine Wahl"):
            return self.wahlen.pop(0) if self.wahlen else "1"
        return "Ich bin harmlos."


def zug(**felder) -> Zug:
    standard = dict(
        ich="Anna", rolle=Rolle.UNRUHESTIFTERIN, runde=1, phase=Phase.NACHT, erlaubte_tools=[ABSTIMMEN],
        lebende=["Anna", "Ben", "Clara"], geheimwissen=[], notizen=[], ereignisse=[],
    )
    return Zug(**(standard | felder))


def test_auswahl_per_nummer_und_name_und_falsche_eingabe() -> None:
    ausgaben: list[str] = []
    mensch = MenschSpieler(Tastatur(["7", "abc", "clara"]), ausgaben.append)
    aktion = mensch.handeln(zug(ziele=["Ben", "Clara"]))
    assert aktion.tool == ABSTIMMEN and aktion.parameter == {"ziel": "Clara"}
    assert sum("Bitte eine Zahl" in a for a in ausgaben) == 2


def test_mehrere_tools_und_parameter() -> None:
    optionen = {VERTAUSCHEN: {"ziel1": ["Ben", "Clara"], "ziel2": ["Ben", "Clara"]}, NICHTS_TUN: {}}
    mensch = MenschSpieler(Tastatur(["1", "2", "1"]), lambda _: None)  # ziel2: nur noch Ben übrig
    aktion = mensch.handeln(zug(erlaubte_tools=[VERTAUSCHEN, NICHTS_TUN], optionen=optionen))
    assert aktion.tool == VERTAUSCHEN and aktion.parameter == {"ziel1": "Clara", "ziel2": "Ben"}

    nichts = MenschSpieler(Tastatur(["2"]), lambda _: None).handeln(
        zug(erlaubte_tools=[VERTAUSCHEN, NICHTS_TUN], optionen=optionen))
    assert nichts.tool == NICHTS_TUN and nichts.parameter == {}


def test_geheimwissen_nur_einmal_zeigen() -> None:
    ausgaben: list[str] = []
    mensch = MenschSpieler(Tastatur(), ausgaben.append)
    wissen = ["Deine Karte zu Spielbeginn: Unruhestifterin."]
    mensch.handeln(zug(erlaubte_tools=[SPRECHEN], geheimwissen=wissen))
    mensch.handeln(zug(erlaubte_tools=[SPRECHEN], geheimwissen=wissen + ["Du hast nichts vertauscht."]))
    assert sum("Spielbeginn" in a for a in ausgaben) == 1
    assert any("Du hast nichts vertauscht." in a for a in ausgaben)


def test_leerer_text_wird_nochmal_abgefragt() -> None:
    antworten = iter(["", "  ", "Hallo zusammen."])
    aktion = MenschSpieler(lambda _: next(antworten), lambda _: None).handeln(zug(erlaubte_tools=[SPRECHEN]))
    assert aktion.parameter == {"text": "Hallo zusammen."}


def test_vollmondnacht_mit_mensch_ohne_zufallsaktion() -> None:
    for seed in range(10):
        rng = random.Random(seed)
        agenten = {n: MockAgent(random.Random(seed + i)) for i, n in enumerate(NAMEN)}
        agenten["Anna"] = MenschSpieler(Tastatur(), lambda _: None)
        karten = [Rolle.WERWOLF, Rolle.WERWOLF, Rolle.SEHERIN, Rolle.RAEUBER, Rolle.UNRUHESTIFTERIN,
                  Rolle.DORFBEWOHNER, Rolle.DORFBEWOHNER, Rolle.SCHLAFLOSE]
        ereignisse = []
        VollmondEngine(agenten, karten, rng=rng, beobachter=ereignisse.append).spielen()
        # Der Mensch gibt immer gültige Aktionen ab.
        assert not [e for e in ereignisse if e.daten.get("spieler") == "Anna" and e.art == "ungueltig"]


def test_klassische_partie_mit_mensch() -> None:
    tastatur = Tastatur()
    agenten = {n: MockAgent(random.Random(i)) for i, n in enumerate(NAMEN)}
    agenten["Anna"] = MenschSpieler(tastatur, lambda _: None)
    ereignisse = []
    Engine(agenten, rng=random.Random(3), beobachter=ereignisse.append).spielen()
    assert tastatur.fragen  # Anna wurde gefragt
    assert not [e for e in ereignisse if e.daten.get("spieler") == "Anna" and e.art == "ungueltig"]


def test_partie_mit_mensch_verraet_keine_geheimnisse(tmp_path, capsys) -> None:
    from main import VOLLMONDNACHT, partie_spielen
    from werwolf.jsonl_log import log_lesen

    mensch = MenschSpieler(Tastatur(), print)
    partie_spielen(5, 5, 0, None, "m", ausfuehrlich=True, ordner=tmp_path,
                   regeln=VOLLMONDNACHT, mensch="Ben", mensch_spieler=mensch)
    ausgabe = capsys.readouterr().out
    assert "Du spielst als Ben" in ausgabe
    assert "[geheim]" not in ausgabe and "Mitte:" not in ausgabe  # keine Besetzung, keine Nachtaktionen
    assert "Startkarte" in ausgabe  # Aufdecken am Ende ist öffentlich
    kopf = log_lesen(tmp_path / "m.jsonl")[0]
    assert {s["name"]: s["typ"] for s in kopf["spieler"]}["Ben"] == "mensch"
    from werwolf.vollmondnacht.auswertung import partie_aus_log
    assert partie_aus_log(log_lesen(tmp_path / "m.jsonl")).gruppe.endswith("mit Mensch")
    assert "[geheim]" in (tmp_path / "m.txt").read_text(encoding="utf-8")  # Protokoll bleibt vollständig

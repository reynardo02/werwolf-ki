"""Tests für den LLMSpieler mit einem Fake-Client – kostenlos und ohne Internet."""

import random
from collections.abc import Callable

import pytest

from core.llm_client import Antwort, BudgetErschoepft, LLMFehler
from core.tools import ToolCall, ToolSchema
from werwolf.engine import Engine
from werwolf.llm_spieler import LLMSpieler, persoenlichkeiten_laden
from werwolf.mock_agent import MockAgent
from werwolf.roles import Rolle
from werwolf.schnittstelle import Agent, Ereignis, Phase, Zug

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta"]
ROLLEN = {
    "Anna": Rolle.WERWOLF,
    "Ben": Rolle.WERWOLF,
    "Clara": Rolle.SEHERIN,
    "Dario": Rolle.DORFBEWOHNER,
    "Emil": Rolle.DORFBEWOHNER,
    "Frieda": Rolle.DORFBEWOHNER,
    "Greta": Rolle.DORFBEWOHNER,
}


class FakeClient:
    """Spielt das LLM. `entscheiden` bekommt die Tools und liefert eine Antwort."""

    def __init__(self, entscheiden: Callable[[list[ToolSchema]], Antwort] | None = None) -> None:
        self.entscheiden = entscheiden or vernuenftig
        self.anfragen_liste: list[tuple[str, str, list[ToolSchema]]] = []

    def anfragen(self, system: str, nachricht: str, tools: list[ToolSchema]) -> Antwort:
        self.anfragen_liste.append((system, nachricht, tools))
        return self.entscheiden(tools)


def vernuenftig(tools: list[ToolSchema]) -> Antwort:
    """Nimmt das erste Tool und das erste erlaubte Ziel bzw. einen festen Text."""
    tool = tools[0]
    if "ziel" in tool.parameter:
        return Antwort(ToolCall(tool.name, {"ziel": tool.parameter["ziel"]["enum"][0]}))
    return Antwort(ToolCall(tool.name, {"text": "Ich habe ein komisches Gefühl."}))


def engine_mit(llm_name: str, client: FakeClient, seed: int = 1) -> Engine:
    rng = random.Random(seed)
    agenten: dict[str, Agent] = {
        name: LLMSpieler(client) if name == llm_name else MockAgent(random.Random(rng.random()))
        for name in NAMEN
    }
    return Engine(agenten, rng=rng, rollen=ROLLEN)


@pytest.mark.parametrize("llm_name", ["Anna", "Clara", "Dario"])
def test_partie_mit_einem_llm_spieler(llm_name: str) -> None:
    """Meilenstein-2-Kriterium: Ein LLM-Spieler spielt eine Partie regelkonform zu Ende."""
    client = FakeClient()
    engine = engine_mit(llm_name, client)
    engine.spielen()

    assert client.anfragen_liste, "Der LLM-Spieler wurde nie gefragt."
    # Ein Seher- oder Dorf-Spieler wählt mit diesem Fake nie ein ungültiges Ziel.
    if llm_name != "Anna":
        assert not any(f"Ungültige Aktion von {llm_name}" in e.text for e in engine.protokoll)


def test_prompt_enthaelt_rolle_geheimwissen_und_passende_tools() -> None:
    client = FakeClient()
    engine_mit("Anna", client).spielen()

    system, nachricht, tools = client.anfragen_liste[0]  # erste Nacht
    assert "Du bist Anna" in system
    assert "Werwolf" in system and "lügen" in system
    assert "Ben ist Werwolf (Mitspieler)" in nachricht
    assert [t.name for t in tools] == ["opfer_waehlen"]
    assert "Anna" not in tools[0].parameter["ziel"]["enum"]


def test_llm_sieht_keine_geheimen_ereignisse() -> None:
    client = FakeClient()
    engine_mit("Dario", client).spielen()
    for _, nachricht, _ in client.anfragen_liste:
        assert "(Werwolf) wählt" not in nachricht
        assert "(Seherin) prüft" not in nachricht


def test_ohne_tool_call_zweiter_versuch_mit_hinweis() -> None:
    client = FakeClient(lambda tools: Antwort(None, "Ich weiß nicht."))
    engine = engine_mit("Clara", client)
    engine.spielen()

    # Erste Nacht: Clara wird zweimal gefragt, beim zweiten Mal mit Hinweis.
    erste, zweite = client.anfragen_liste[0][1], client.anfragen_liste[1][1]
    assert "ungültig" not in erste
    assert "Dein letzter Versuch war ungültig" in zweite
    assert any("Clara bekommt eine Zufallsaktion" in e.text for e in engine.protokoll)


def test_api_fehler_bricht_partie_nicht_ab() -> None:
    def fehler(tools: list[ToolSchema]) -> Antwort:
        raise LLMFehler("Server nicht erreichbar")

    engine = engine_mit("Clara", FakeClient(fehler))
    ergebnis = engine.spielen()
    assert ergebnis.gewinner is not None


def test_budget_stoppt_die_partie() -> None:
    def leer(tools: list[ToolSchema]) -> Antwort:
        raise BudgetErschoepft("Limit erreicht")

    with pytest.raises(BudgetErschoepft):
        engine_mit("Clara", FakeClient(leer)).spielen()


def test_hinweis_landet_im_prompt() -> None:
    spieler = LLMSpieler(FakeClient())
    zug = Zug(
        ich="Emil", rolle=Rolle.DORFBEWOHNER, runde=2, phase=Phase.ABSTIMMUNG,
        erlaubte_tools=["abstimmen"], lebende=["Anna", "Emil"], geheimwissen=[],
        notizen=["Runde 1: Anna wirkt nervös."], ereignisse=[], hinweis="'Zoe' ist kein gültiges Ziel.",
    )
    text = spieler.zug_prompt(zug)
    assert "Runde 1: Anna wirkt nervös." in text
    assert "'Zoe' ist kein gültiges Ziel." in text
    assert "Nutze das Tool abstimmen" in text


def test_werwolf_bekommt_mitwolf_nicht_als_ziel() -> None:
    client = FakeClient()
    engine_mit("Anna", client).spielen()
    _, _, tools = client.anfragen_liste[0]  # erste Nacht, Anna ist Werwolf
    assert "Ben" not in tools[0].parameter["ziel"]["enum"]


def test_persoenlichkeiten_und_im_system_prompt() -> None:
    persoenlichkeiten = persoenlichkeiten_laden()
    assert len(persoenlichkeiten) >= 7  # genug für eine volle Runde
    assert not any(p.startswith("#") for p in persoenlichkeiten)

    client = FakeClient()
    spieler = LLMSpieler(client, persoenlichkeiten[0])
    agenten: dict[str, Agent] = {n: MockAgent(random.Random(i)) for i, n in enumerate(NAMEN)}
    agenten["Dario"] = spieler
    Engine(agenten, rng=random.Random(0), rollen=ROLLEN).spielen()
    assert f"Persönlichkeit: {persoenlichkeiten[0]}" in client.anfragen_liste[0][0]


def test_alte_diskussionen_fallen_weg_tode_bleiben() -> None:
    spieler = LLMSpieler(FakeClient())
    zug = Zug(
        ich="Emil", rolle=Rolle.DORFBEWOHNER, runde=2, phase=Phase.DISKUSSION,
        erlaubte_tools=["sprechen"], lebende=["Anna", "Ben", "Emil"], geheimwissen=[],
        notizen=[], ereignisse=[
            Ereignis(1, Phase.MORGEN, "Dario wurde getötet. Dario war Dorfbewohner."),
            Ereignis(1, Phase.DISKUSSION, 'Anna: "Alte Rede"'),
            Ereignis(1, Phase.ABSTIMMUNG, "Ben stimmt für Anna."),
            Ereignis(2, Phase.DISKUSSION, 'Ben: "Neue Rede"'),
        ],
    )
    text = spieler.zug_prompt(zug)
    assert "Dario wurde getötet" in text
    assert "Ben stimmt für Anna." in text
    assert "Neue Rede" in text
    assert "Alte Rede" not in text

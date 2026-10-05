"""Vollmondnacht mit LLM-Spielern – mit Fake-Client, kostenlos und ohne Internet."""

import random

from core.llm_client import Antwort
from core.tools import ToolCall, ToolSchema
from werwolf.vollmondnacht.engine import NACHAHMEN, NICHTS_TUN, VERTAUSCHEN, VollmondEngine
from werwolf.vollmondnacht.llm_spieler import ROLLEN_HINWEISE, VollmondLLMSpieler
from werwolf.vollmondnacht.rollen import Rolle, szenario_karten

NAMEN = ["Anna", "Ben", "Clara", "Dario", "Emil", "Frieda", "Greta", "Hugo"]


class FakeClient:
    """Wählt immer das erste Tool und für jeden Parameter den ersten erlaubten Wert."""

    def __init__(self) -> None:
        self.anfragen_liste: list[tuple[str, str, list[ToolSchema]]] = []

    def anfragen(self, system: str, nachricht: str, tools: list[ToolSchema]) -> Antwort:
        self.anfragen_liste.append((system, nachricht, tools))
        tool = tools[0]
        argumente = {}
        for name, schema in tool.parameter.items():
            if "enum" in schema:
                # Bei zwei Zielen verschiedene Werte nehmen.
                argumente[name] = schema["enum"][len(argumente) % len(schema["enum"])]
            elif name in tool.pflicht:
                argumente[name] = "Ich bin ein harmloser Dorfbewohner."
        return Antwort(ToolCall(tool.name, argumente))


def test_jede_rolle_hat_einen_hinweis() -> None:
    assert set(ROLLEN_HINWEISE) == set(Rolle)


def test_ganze_partie_nur_mit_llm_spielern_ohne_zufallsaktionen() -> None:
    # „Wiedergänger“ enthält fast alle Rollen, auch die Doppelgängerin.
    client = FakeClient()
    karten = szenario_karten("Wiedergänger", 8, random.Random(1))
    agenten = {n: VollmondLLMSpieler(client, "ruhig") for n in NAMEN}
    e = VollmondEngine(agenten, karten, rng=random.Random(1))
    e.spielen()

    assert not any(x.art in ("zufallsaktion", "ungueltig") for x in e.protokoll)
    tools = {t.name for _, _, ts in client.anfragen_liste for t in ts}
    assert {"sprechen", "abstimmen"} <= tools


def test_prompts_und_tools() -> None:
    client = FakeClient()
    verteilung = {"Anna": Rolle.UNRUHESTIFTERIN, "Ben": Rolle.WERWOLF, "Clara": Rolle.DORFBEWOHNER}
    agenten = {n: VollmondLLMSpieler(client, "frech") for n in verteilung}
    mitte = [Rolle.SEHERIN, Rolle.RAEUBER, Rolle.DOPPELGAENGERIN]
    e = VollmondEngine(agenten, list(verteilung.values()) + mitte, rng=random.Random(0),
                       verteilung=verteilung, mitte=mitte)
    e.spielen()

    system, nachricht, tools = client.anfragen_liste[0]  # Nacht der Unruhestifterin
    assert "Du bist Anna" in system and "Unruhestifterin" in system and "frech" in system
    assert "Im Spiel sind diese 6 Karten" in nachricht
    assert [t.name for t in tools] == [VERTAUSCHEN, NICHTS_TUN]
    assert tools[0].parameter["ziel1"]["enum"] == ["Ben", "Clara"]
    assert tools[1].parameter == {}
    # Die Doppelgängerin liegt in der Mitte, also fragt die Engine nie nach „nachahmen“.
    assert not any(NACHAHMEN in [t.name for t in ts] for _, _, ts in client.anfragen_liste)
